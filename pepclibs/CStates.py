# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides C-state management API.
"""

import re
import copy
import logging
from pathlib import Path
from pepclibs.helperlibs import FSHelpers, Procs, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo
from pepclibs.msr import MSR, PowerCtl, PCStateConfigCtl

_LOG = logging.getLogger()

# This dictionary describes various CPU properties this module supports. Many of the properties are
# just features controlled by an MSR, such as "c1e_autopromote" from 'PowerCtl.FEATURES'.
#
# Define the global 'PROPS' dictionary, and then refine update it later. Full dictionary is
# available via 'CStates.props'.
PROPS = {
    "pkg_cstate_limit" : {
        "name" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["name"],
        "help" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["help"],
        "type" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["type"],
        "scope": PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["scope"],
        "subprops" : {
            "pkg_cstate_limit_locked" : {
                "name" : "Package C-state limit locked",
                "help" : """Whether the package C-state limit in MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                            (MSR_PKG_CST_CONFIG_CONTROL) is locked and cannot be modified.""",
                "type" : "bool",
            },
            "pkg_cstate_limits" : {
                "name" : "Available package C-state limits",
                "help" : """List of package C-state names which can be used for limiting the deepest
                            package C-state the platform is allowed to enter.""",
                "type" : "list[str]",
            },
            "pkg_cstate_limit_aliases" : {
                "name" : "Package C-state limit aliases",
                "help" : """Some package C-states have multiple names, and this is a dictionary
                            mapping aliases to the name.""",
                "type" : "dict[str,str]",
            },
        },
    },
    "c1_demotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_demotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_demotion"]["help"],
        "type" : PCStateConfigCtl.FEATURES["c1_demotion"]["type"],
        "scope": PCStateConfigCtl.FEATURES["c1_demotion"]["scope"]
    },
    "c1_undemotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_undemotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_undemotion"]["help"],
        "type" : PCStateConfigCtl.FEATURES["c1_undemotion"]["type"],
        "scope": PCStateConfigCtl.FEATURES["c1_undemotion"]["scope"]
    },
    "c1e_autopromote" : {
        "name" : PowerCtl.FEATURES["c1e_autopromote"]["name"],
        "help" : PowerCtl.FEATURES["c1e_autopromote"]["help"],
        "type" : PowerCtl.FEATURES["c1e_autopromote"]["type"],
        "scope": PowerCtl.FEATURES["c1e_autopromote"]["scope"]
    },
    "cstate_prewake" : {
        "name" : PowerCtl.FEATURES["cstate_prewake"]["name"],
        "help" : PowerCtl.FEATURES["cstate_prewake"]["help"],
        "type" : PowerCtl.FEATURES["cstate_prewake"]["type"],
        "scope": PowerCtl.FEATURES["cstate_prewake"]["scope"]
    },
}

class _LinuxCStates:
    """
    This class provides API for managing Linux C-states via sysfs.
    """

    def _get_cstate_indexes(self, cpu):
        """Yield tuples of of C-state indexes and sysfs paths for cpu number 'cpu'."""

        basedir = self._sysfs_base / f"cpu{cpu}" / "cpuidle"
        name = None
        for name, path, typ in FSHelpers.lsdir(basedir, proc=self._proc):
            errmsg = f"unexpected entry '{name}' in '{basedir}'{self._proc.hostmsg}"
            if typ != "/" or not name.startswith("state"):
                raise Error(errmsg)
            index = name[len("state"):]
            if not Trivial.is_int(index):
                raise Error(errmsg)
            yield int(index), Path(path)

        if name is None:
            raise Error(f"C-states are not supported{self._proc.hostmsg}")

    def _name2idx(self, name, cpu=0):
        """Return C-state index for C-state name 'name'."""

        if cpu in self._name2idx_cache:
            if name in self._name2idx_cache[cpu]:
                return self._name2idx_cache[cpu][name]
        else:
            self._name2idx_cache[cpu] = {}

        names = []
        for index, path in self._get_cstate_indexes(cpu):
            with self._proc.open(path / "name", "r") as fobj:
                val = fobj.read().strip().upper()
            self._name2idx_cache[cpu][val] = index
            if val == name:
                return index
            names.append(val)

        names = ", ".join(names)
        raise Error(f"unkown C-state '{name}', here are the C-states supported"
                    f"{self._proc.hostmsg}:\n{names}")

    def _idx2name(self, index, cpu=0):
        """Return C-state name for C-state index 'index'."""

        if cpu in self._idx2name_cache:
            if index in self._idx2name_cache[cpu]:
                return self._idx2name_cache[cpu][index]

        if cpu not in self._cscache:
            self._cscache[cpu] = self.get_cpu_cstates_info(cpu)

        self._idx2name_cache[cpu] = {}
        for csinfo in self._cscache[cpu].values():
            self._idx2name_cache[cpu][csinfo['index']] = csinfo['name']

        if index not in self._idx2name_cache[cpu]:
            indices = ", ".join(f"{idx} ({v['name']})" for idx, v in  self._cscache[cpu].items())
            raise Error(f"unkown C-state index '{index}', here are the C-state indices supported"
                        f"{self._proc.hostmsg}:\n{indices}") from None

        return self._idx2name_cache[cpu][index]

    def _read_cstates_info(self, cpus, indexes, ordered):
        """
        Read information about C-states in 'indexes' of CPUs in 'cpus' and yield C-state information
        dictionary for every CPU in 'cpus'.
        """

        indexes_regex = cpus_regex = "[[:digit:]]+"
        cpus_regex = "|".join([str(cpu) for cpu in cpus])
        if indexes != "all":
            indexes_regex = "|".join([str(index) for index in indexes])

        cmd = fr"find '{self._sysfs_base}' -type f -regextype posix-extended " \
              fr"-regex '.*cpu({cpus_regex})/cpuidle/state({indexes_regex})/[^/]+' " \
              fr"-exec printf '%s' {{}}: \; -exec grep . {{}} \;"

        stdout, _ = self._proc.run_verify(cmd, join=False)
        if not stdout:
            raise Error(f"failed to find C-states information in '{self._sysfs_base}'"
                        f"{self._proc.hostmsg}")

        if ordered:
            stdout = sorted(stdout)

        regex = re.compile(r".+/cpu([0-9]+)/cpuidle/state([0-9]+)/(.+):([^\n]+)")
        csinfo = {}
        index = prev_index = cpu = prev_cpu = None

        for line in stdout:
            matchobj = re.match(regex, line)
            if not matchobj:
                raise Error(f"failed to parse the follwoing line from file in '{self._sysfs_base}'"
                            f"{self._proc.hostmsg}:\n{line.strip()}")

            cpu = int(matchobj.group(1))
            index = int(matchobj.group(2))
            key = matchobj.group(3)
            val = matchobj.group(4)
            if Trivial.is_int(val):
                val = int(val)

            if prev_cpu is None:
                prev_cpu = cpu
            if prev_index is None:
                prev_index = index

            if cpu != prev_cpu or index != prev_index:
                csinfo["CPU"] = prev_cpu
                csinfo["index"] = prev_index
                yield csinfo
                prev_cpu = cpu
                prev_index = index
                csinfo = {}

            csinfo[key] = val

        csinfo["CPU"] = prev_cpu
        csinfo["index"] = prev_index
        yield csinfo

    def _normalize_cstates(self, cstates):
        """
        Some methods accept the C-states to operate on as a string or a list. This method normalizes
        the C-states 'cstates' and returns a list of integer C-state indices. 'cstates' can be:
          * a C-state name
          * a C-state index as a string or an integer
          * a list containing one or more of the above
          * a string containing comma-separated C-state indices or names
        """

        if cstates == "all":
            return cstates

        if isinstance(cstates, int):
            cstates = str(cstates)
        if isinstance(cstates, str):
            cstates = Trivial.split_csv_line(cstates, dedup=True)

        indices = []
        for cstate in cstates:
            if not Trivial.is_int(cstate):
                cstate = self._name2idx(cstate.upper())
            idx = int(cstate)
            if idx not in indices:
                indices.append(idx)

        return indices

    def _toggle_cstate(self, cpu, index, enable):
        """Enable or disable the 'index' C-state for CPU 'cpu'."""

        path = self._sysfs_base / f"cpu{cpu}" / "cpuidle" / f"state{index}" / "disable"
        if enable:
            val = "0"
            action = "enable"
        else:
            val = "1"
            action = "disable"

        msg = f"{action} C-state with index '{index}' for CPU {cpu}"
        _LOG.debug(msg)

        try:
            with self._proc.open(path, "r+") as fobj:
                fobj.write(val + "\n")
        except Error as err:
            raise Error(f"failed to {msg}:\n{err}") from err

        try:
            with self._proc.open(path, "r") as fobj:
                read_val = fobj.read().strip()
        except Error as err:
            raise Error(f"failed to {msg}:\n{err}") from err

        if val != read_val:
            raise Error(f"failed to {msg}:\nfile '{path}' contains '{read_val}', but should "
                        f"contain '{val}'")

    def _do_toggle_cstates(self, cpus, indexes, enable):
        """Implements '_toggle_cstates()'."""

        toggled = {}
        go_cpus = cpus
        go_indexes = indexes

        cpus = set(cpus)
        if indexes != "all":
            indexes = set(indexes)

        for csinfo in self._read_cstates_info(go_cpus, go_indexes, False):
            cpu = csinfo["CPU"]
            index = csinfo["index"]
            if cpu in cpus and (indexes == "all" or index in indexes):
                self._toggle_cstate(cpu, index, enable)
                if cpu not in toggled:
                    toggled[cpu] = {"cstates" : []}
                toggled[cpu]["cstates"].append(self._idx2name(index, cpu=cpu))

        return toggled

    def _toggle_cstates(self, cpus="all", cstates="all", enable=True):
        """
        Enable or disable C-states 'cstates' on CPUs 'cpus'. The arguments are as follows.
          * cstates - same as in 'get_cstates_info()'.
          * cpus - same as in 'get_cstates_info()'.
          * enabled - if 'True', the specified C-states should be enabled on the specified CPUS,
                      otherwise disabled.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)

        if isinstance(cstates, str) and cstates != "all":
            cstates = Trivial.split_csv_line(cstates, dedup=True)
        indexes = self._normalize_cstates(cstates)

        return self._do_toggle_cstates(cpus, indexes, enable)

    def enable_cstates(self, cpus="all", cstates="all"):
        """Same as 'CStates.enable_cstates()'."""

        return self._toggle_cstates(cpus, cstates, True)

    def disable_cstates(self, cpus="all", cstates="all"):
        """Same as 'CStates.disable_cstates()'."""

        return self._toggle_cstates(cpus, cstates, False)

    def get_cstates_info(self, cpus="all", cstates="all", ordered=True):
        """Same as 'CStates.get_cstates_info()'."""

        cpus = self._cpuinfo.normalize_cpus(cpus)
        indexes = self._normalize_cstates(cstates)
        if indexes != "all":
            indexes = set(indexes)

        for cpu in cpus:
            if cpu in self._cscache:
                # We have the C-states info for this CPU cached.
                if indexes == "all":
                    indices = self._cscache[cpu]
                else:
                    indices = indexes
                for idx in indices:
                    yield self._cscache[cpu][idx]
            else:
                # The C-state info for this CPU is not available in the cache.
                # Current implementation limitation: the C-state cache is a per-CPU dictionary. The
                # dictionary includes all C-states available for this CPU. Therefore, even if user
                # requested only partial information (not all C-states), we read information about
                # all the C-states anyway. This limitation makes this function slower than
                # necessary.
                self._cscache[cpu] = {}
                for csinfo in self._read_cstates_info([cpu], "all", ordered):
                    self._cscache[cpu][csinfo["index"]] = csinfo
                    if indexes == "all" or csinfo["index"] in indexes:
                        yield csinfo

    def get_cpu_cstates_info(self, cpu, cstates="all", ordered=True):
        """Same as 'CStates.get_cpu_cstates_info()'."""

        csinfo_dict = {}
        for csinfo in self.get_cstates_info(cpus=(cpu,), cstates=cstates, ordered=ordered):
            csinfo_dict[csinfo["index"]] = csinfo
        return csinfo_dict

    def get_cpu_cstate_info(self, cpu, cstate):
        """Same as 'CStates.get_cpu_cstate_info()'."""

        csinfo = None
        for csinfo in self.get_cstates_info(cpus=(cpu,), cstates=(cstate,)):
            pass
        return csinfo

    def __init__(self, proc=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        # Used for caching the C-state information for each CPU.
        self._cscache = {}
        # Used for mapping C-state indices to C-state names and vice versa.
        self._name2idx_cache = {}
        self._idx2name_cache = {}

        if not self._proc:
            self._proc = Procs.Proc()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)


class CStates:
    """
    This class provides C-state management API.

    Public methods overview.

    1. Enable multiple disable C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    2. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For a single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For a single CPU and a single C-state:  'get_cpu_cstate_info()'.
    3. Get/set C-state properties.
       * For multiple properties and multiple CPUs: 'get_props()', 'set_props()'.
       * For single properties and multiple CPUs: 'set_prop()'.
       * For multiple properties and single CPU: 'get_cpu_props()', 'set_cpu_props()'.
       * For single property and single CPU: 'get_cpu_prop()', 'set_cpu_prop()'.
    """

    def _get_lcsobj(self):
        """Returns a '_LinuxCStates()' object."""

        if not self._lcsobj:
            self._lcsobj = _LinuxCStates(self._proc, cpuinfo=self._cpuinfo)
        return self._lcsobj

    def get_cstates_info(self, cpus="all", cstates="all", ordered=True):
        """
        Yield information about C-states specified in 'cstate' for CPUs specified in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).
          * cstates - the list of C-states to get information about. The list can contain both
                      C-state names and C-state indexes. It can be both a list or a string
                      containing a comma-separated list. Value 'all' mean "all C-states"
                      (default).
          * ordered - if 'True', the yielded C-states will be ordered so that smaller CPU numbers
                      will go first, and for each CPU number shallower C-states will go first.
        """

        return self._get_lcsobj().get_cstates_info(cpus=cpus, cstates=cstates, ordered=ordered)

    def get_cpu_cstates_info(self, cpu, cstates="all", ordered=True):
        """Same as 'get_cstates_info()', but for a single CPU."""

        return self._get_lcsobj().get_cpu_cstates_info(cpu, cstates=cstates, ordered=ordered)

    def get_cpu_cstate_info(self, cpu, cstate):
        """Same as 'get_cstates_info()', but for a single CPU and a single C-state."""

        return self._get_lcsobj().get_cpu_cstate_info(cpu, cstate)

    def enable_cstates(self, cpus="all", cstates="all"):
        """
        Enable C-states 'cstates' on CPUs 'cpus'. The arguments are as follows.
          * cpus - same as in 'get_cstates_info()'.
          * cstates - same as in 'get_cstates_info()'.

        Returns a dictionary of the following structure.

          { cpunum: { "cstates" : [ cstate1, cstate2, ...]}}

          * cpunum - integer CPU number.
          * [cstate1, cstate2, ...] - list of C-ststate names enabled for CPU 'cpunum'.

        """

        return self._get_lcsobj().enable_cstates(cpus=cpus, cstates=cstates)

    def disable_cstates(self, cpus="all", cstates="all"):
        """Similar to 'enable_cstates()', but disables instead of enabling."""

        return self._get_lcsobj().disable_cstates(cpus=cpus, cstates=cstates)

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._proc, cpuinfo=self._cpuinfo)
        return self._msr

    def _get_powerctl(self):
        """Return an instance of 'PowerCtl' class."""

        if self._powerctl is None:
            msr = self._get_msr()
            self._powerctl = PowerCtl.PowerCtl(proc=self._proc, cpuinfo=self._cpuinfo, msr=msr)
        return self._powerctl

    def _get_pcstatectl(self):
        """Return an instance of 'PCStateConfigCtl' class."""

        if self._pcstatectl is None:
            msr = self._get_msr()
            self._pcstatectl = PCStateConfigCtl.PCStateConfigCtl(proc=self._proc,
                                                                 cpuinfo=self._cpuinfo, msr=msr)
        return self._pcstatectl

    def _check_prop(self, pname):
        """Raise an error if a property 'pname' is not supported."""

        if pname not in PROPS:
            pnames_str = ", ".join(set(PROPS))
            raise ErrorNotSupported(f"property '{pname}' is not supported{self._proc.hostmsg}, "
                                    f"use one of the following: {pnames_str}")

    def _find_feature(self, pname, cpu):
        """Find an MSR feature corresponding to property 'pname'."""

        if pname in PowerCtl.FEATURES:
            module = self._get_powerctl()
        else:
            module = self._get_pcstatectl()

        return module.read_cpu_feature(pname, cpu)

    def _get_pinfo(self, pnames, cpu):
        """
        Build and return the properties information dictionary for properties in 'pnames' and CPU
        number 'cpu'.
        """

        pinfo = {}

        for pname in pnames:
            pinfo[pname] = {pname : None, "CPU" : cpu}

            try:
                val = self._find_feature(pname, cpu)
            except ErrorNotSupported:
                continue

            if isinstance(val, dict):
                for fkey, fval in val.items():
                    pinfo[pname][fkey] = fval
            else:
                pinfo[pname][pname] = val

        return pinfo

    def get_props(self, pnames, cpus="all"):
        """
        Read all properties specified in the 'pnames' list for CPUs in 'cpus', and for every CPU
        yield a dictionary containing the read values of all the properties. The arguments are as
        follows.
          * pnames - list or an iterable collection of properties to read and yeild the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).

        The yielded dictionaries have the following format.

        { property1_name: { property1_name : property1_value,
                            "CPU" : <CPU number>,
                            subprop1_key : subprop1_value,
                            subprop2_key : subprop2_value,
                            ... etc for every key ...},
          property2_name: { property2_name : property2_value,
                            "CPU" : <CPU number>,
                            subprop1_key : subprop2_value,
                            ... etc ...},
          ... etc ... }

        So each property has the (main) value, but it also comes with the "CPU" and possibly
        sub-properties, which provide additional read-only information related to the property. For
        example, the 'pkg_cstate_limit' property comes with 'pkg_cstate_limit_locked' and other
        sub-properties. Most properties have no sub-properties.

        If a property is not supported, its value will be 'None'.
        """

        for pname in pnames:
            self._check_prop(pname)

        cpus = self._cpuinfo.normalize_cpus(cpus)

        for cpu in cpus:
            yield self._get_pinfo(pnames, cpu)

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for pinfo in self.get_props(pnames, cpus=(cpu,)):
            pass
        return pinfo

    def _validate_prop_scope(self, pname, cpus):
        """
        Make sure that CPUs in 'cpus' match the scope of the 'pname' feature. For example, if the
        feature has "package" scope, 'cpus' should include all CPUs in one or more packages.
        """

        scope = self.props[pname]["scope"]
        if scope == "CPU":
            return

        if scope not in {"package", "core"}:
            raise Error("BUG: unsupported {scope}")

        _, rem_cpus = getattr(self._cpuinfo, f"cpus_div_{scope}s")(cpus)
        if not rem_cpus:
            return

        mapping = ""
        for pkg in self._cpuinfo.get_packages():
            pkg_cpus = self._cpuinfo.package_to_cpus(pkg)
            pkg_cpus_str = Human.rangify(pkg_cpus)
            mapping += f"\n  * package {pkg}: CPUs: {pkg_cpus_str}"

            if scope == "core":
                # Add cores information in case of "core" scope.
                pkg_cores = self._cpuinfo.package_to_cores(pkg)
                pkg_cores_str = Human.rangify(pkg_cores)
                mapping += f"\n               cores: {pkg_cores_str}"

                # Build the cores to CPUs mapping string.
                clist = []
                for core in pkg_cores:
                    cpus = self._cpuinfo.cores_to_cpus(packages=(pkg,), cores=(core,))
                    cpus_str = Human.rangify(cpus)
                    clist.append(f"{core}:{cpus_str}")

                # The core->CPU numbers mapping may be very long, wrap it to 100 symbols.
                import textwrap # pylint: disable=import-outside-toplevel

                prefix = "               cores to CPUs: "
                indent = " " * len(prefix)
                clist_wrapped = textwrap.wrap(", ".join(clist), width=100,
                                              initial_indent=prefix, subsequent_indent=indent)
                clist_str = "\n".join(clist_wrapped)

                mapping += f"\n{clist_str}"

        name =  self.props[pname]["name"]
        rem_cpus_str = Human.rangify(rem_cpus)

        if scope == "core":
            mapping_name = "relation between CPUs, cores, and packages"
        else:
            mapping_name = "relation between CPUs and packages"

        errmsg = f"{name} has {scope} scope, so the list of CPUs must include all CPUs" \
                 f"in one or multiple {scope}s.\n" \
                 f"However, the following CPUs do not comprise full {scope}(s): {rem_cpus_str}\n" \
                 f"Here is the {mapping_name}{self._proc.hostmsg}:{mapping}"

        raise Error(errmsg)

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_props()', but for a single CPU and a single property."""

        pinfo = None
        for pinfo in self.get_props((pname,), cpus=(cpu,)):
            pass
        return pinfo

    def set_props(self, pinfo, cpus="all"):
        """
        Set multiple properties described by 'pinfo' to values also provided in 'pinfo'.
          * pinfo - an iterable collection of property names and values.
          * cpus - same as in 'get_props()'.

        This method accepts two 'pinfo' formats.

        1. An iterable collection (e.g., list or a tuple) of ('pname', 'val') pairs. For example:
           * [("c1_demotion", "on"), ("c1_undemotion", "off")]
        2. A dictionary with property names as keys. For example:
           * {"c1_demotion" : "on", "c1_undemotion" : "off"}
        """

        inprops = {}
        if hasattr(pinfo, "items"):
            for pname, val in pinfo.items():
                inprops[pname] = val
        else:
            for pname, val in pinfo:
                inprops[pname] = val

        for pname, val in inprops.items():
            self._check_prop(pname)
            self._validate_prop_scope(pname, cpus)

            if not self.props[pname]["writable"]:
                name = self.props[pname][pname]
                raise Error(f"failed to change read-only property '{pname}' ({name})")

            if pname in PowerCtl.FEATURES:
                powerctl = self._get_powerctl()
                powerctl.write_feature(pname, val, cpus)
            elif pname in PCStateConfigCtl.FEATURES:
                pcstatectl = self._get_pcstatectl()
                pcstatectl.write_feature(pname, val, cpus=cpus)
            else:
                raise Error(f"BUG: undefined property '{pname}'")

    def set_prop(self, pname, val, cpus="all"):
        """Same as 'set_props()', but for a single property."""

        self.set_props(((pname, val),), cpus=cpus)

    def set_cpu_props(self, pinfo, cpu):
        """Same as 'set_props()', but for a single CPU."""

        self.set_props(pinfo, cpus=(cpu,))

    def set_cpu_prop(self, pname, val, cpu):
        """Same as 'set_props()', but for a single CPU and a single property."""

        self.set_props(((pname, val),), cpus=(cpu,))

    def _init_props_dict(self):
        """Initialize the 'props' dictionary."""

        self.props = copy.deepcopy(PROPS)

        for prop in self.props.values():
            if "writable" not in prop:
                prop["writable"] = True
            # Every features should include the 'subprops' sub-dictionary.
            if "subprops" not in prop:
                prop["subprops"] = {}

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The arguments are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._lcsobj = None
        self._powerctl = None
        self._pcstatectl = None

        self.props = None

        if not self._proc:
            self._proc = Procs.Proc()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_lcsobj", "_pcstatectl", "_powerctl"):
            obj = getattr(self, attr, None)
            if obj:
                obj.close()
                setattr(self, attr, None)

        for attr in ("_msr", "_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
