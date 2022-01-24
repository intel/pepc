# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API for dealing with the Linux "cpuidle" subsystem.
"""

import re
import copy
import logging
from pathlib import Path
from pepclibs.helperlibs import FSHelpers, Procs, Trivial
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
        "type" : "str",
        "scope": "package",
    },
    "c1_demotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_demotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_demotion"]["help"],
        "type" : "bool",
        "scope": "CPU",
    },
    "c1_undemotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_undemotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_undemotion"]["help"],
        "type" : "bool",
        "scope": "CPU",
    },
    "c1e_autopromote" : {
        "name" : PowerCtl.FEATURES["c1e_autopromote"]["name"],
        "help" : PowerCtl.FEATURES["c1e_autopromote"]["help"],
        "type" : "bool",
        "scope": "package",
    },
    "cstate_prewake" : {
        "name" : PowerCtl.FEATURES["cstate_prewake"]["name"],
        "help" : PowerCtl.FEATURES["cstate_prewake"]["help"],
        "type" : "bool",
        "scope": "package",
    },
}

class CStates:
    """
    This class provides API to the "cpuidle" Linux sybsystem.

    Public methods overview.

    1. Enable multiple disable C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    2. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For a single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For a single CPU and a single C-state:  'get_cpu_cstate_info()'.
    3. Get/set a C-state property for multiple CPUs: 'get_props()', 'set_prop()'.
    4. Get a C-state property scope: 'get_scope()'.
    """

    def _get_cpuinfo(self):
        """Return an instance of 'CPUInfo' class."""

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)
        return self._cpuinfo

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

        if cpu not in self._csinfos:
            self._csinfos[cpu] = self.get_cpu_cstates_info(cpu)

        self._idx2name_cache[cpu] = {}
        for csinfo in self._csinfos[cpu].values():
            self._idx2name_cache[cpu][csinfo['index']] = csinfo['name']

        if index not in self._idx2name_cache[cpu]:
            indices = ", ".join(f"{idx} ({v['name']})" for idx, v in  self._csinfos[cpu].items())
            raise Error(f"unkown C-state index '{index}', here are the C-state indices supported"
                        f"{self._proc.hostmsg}:\n{indices}") from None

        return self._idx2name_cache[cpu][index]

    def _normalize_cstates(self, cstates):
        """
        Some methods accept the C-states to operate on as a string or a list. This method normalizes
        the C-states 'cstates' and returns a list of integer C-state indices. 'cstates' can be:
          * a C-state name
          * a C-state index as a string or an integer
          * a list containing one or more of the above
          * a string containing comma-separated C-state indices or names
        """

        if cstates in ("all", None):
            return None

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

    def _normalize_cpus(self, cpus):
        """
        Some methods accept CPUs as list or range of CPUs as described in 'get_cstates_info()'.
        Turn this userinput in 'cpus' as list of integers and return it.
        """

        cpuinfo = self._get_cpuinfo()
        return cpuinfo.normalize_cpus(cpus)

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

        if cpus is not None:
            cpus = set(cpus)
        if indexes is not None:
            indexes = set(indexes)

        for info in self._get_cstates_info(go_cpus, go_indexes, False):
            cpu = info["CPU"]
            index = info["index"]
            if (cpus is None or cpu in cpus) and (indexes is None or index in indexes):
                self._toggle_cstate(cpu, index, enable)
                if cpu not in toggled:
                    toggled[cpu] = {"cstates" : []}
                toggled[cpu]["cstates"].append(self._idx2name(index, cpu=cpu))

        return toggled

    def _toggle_cstates(self, cpus=None, cstates=None, enable=True):
        """
        Enable or disable C-states 'cstates' on CPUs 'cpus'. The arguments are as follows.
          * cstates - same as in 'get_cstates_info()'.
          * cpus - same as in 'get_cstates_info()'.
          * enabled - if 'True', the specified C-states should be enabled on the specified CPUS,
                      otherwise disabled.
        """

        cpus = self._normalize_cpus(cpus)

        if isinstance(cstates, str) and cstates != "all":
            cstates = Trivial.split_csv_line(cstates, dedup=True)
        indexes = self._normalize_cstates(cstates)

        return self._do_toggle_cstates(cpus, indexes, enable)

    def enable_cstates(self, cpus=None, cstates=None):
        """
        Enable C-states 'cstates' on CPUs 'cpus'. The 'cstates' and 'cpus' arguments are the same as
        in 'get_cstates_info()'. Returns a dictionary of the following format:

        CPU number:
            csates:
                list of C-state names enabled for the CPU
        """
        return self._toggle_cstates(cpus, cstates, True)

    def disable_cstates(self, cpus=None, cstates=None):
        """
        Similarr to 'enable_cstates()', but disables instead of enabling.
        """
        return self._toggle_cstates(cpus, cstates, False)

    def _get_cstates_info(self, cpus, indexes, ordered):
        """Implements 'get_cstates_info()'."""

        indexes_regex = cpus_regex = "[[:digit:]]+"
        if cpus is not None:
            cpus_regex = "|".join([str(cpu) for cpu in cpus])
        if indexes is not None:
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
        info = {}
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
                info["CPU"] = prev_cpu
                info["index"] = prev_index
                yield info
                prev_cpu = cpu
                prev_index = index
                info = {}

            info[key] = val

        info["CPU"] = prev_cpu
        info["index"] = prev_index
        yield info

    def get_cstates_info(self, cpus=None, cstates=None, ordered=True):
        """
        Yield information about C-states specified in 'cstate' for CPUs specified in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
          * cstates - the list of C-states to get information about. The list can contain both
                      C-state names and C-state indexes. It can be both a list or a string
                      containing a comma-separated list. 'None' and 'all' mean "all C-states"
                      (default).
          * ordered - if 'True', the yielded C-states will be ordered so that smaller CPU numbers
                      will go first, and for each CPU number shallower C-states will go first.
        """

        cpus = self._normalize_cpus(cpus)
        indexes = self._normalize_cstates(cstates)
        if indexes:
            indexes = set(indexes)

        for cpu in cpus:
            if cpu in self._csinfos:
                # We have the C-states info for this CPU cached.
                if indexes is None:
                    indices = self._csinfos[cpu]
                else:
                    indices = indexes
                for idx in indices:
                    yield self._csinfos[cpu][idx]
            else:
                # The C-state info for this CPU is not available in the cache.
                # Current implementation limitation: the C-state cache is a per-CPU dictionary. The
                # dictionary includes all C-states available for this CPU. Therefore, even if user
                # requested only partial information (not all C-states), we read information about
                # all the C-states anyway. This limitation makes this function slower than
                # necessary.
                self._csinfos[cpu] = {}
                for csinfo in self._get_cstates_info([cpu], None, ordered):
                    self._csinfos[cpu][csinfo["index"]] = csinfo
                    if indexes is None or csinfo["index"] in indexes:
                        yield csinfo

    def get_cpu_cstates_info(self, cpu, cstates=None, ordered=True):
        """
        Returns a dictionary describing all C-states of CPU 'cpu'. C-state index is used as
        dictionary key. The 'cstates' and 'ordered' arguments are the same as in
        'get_cstates_info()'.
        """

        if not Trivial.is_int(cpu):
            raise Error(f"bad CPU number '{cpu}', should be an integer")

        info_dict = {}
        for info in self.get_cstates_info(cpus=cpu, cstates=cstates, ordered=ordered):
            info_dict[info["index"]] = info
        return info_dict

    def get_cpu_cstate_info(self, cpu, cstate):
        """
        Returns information about C-state 'cstate' on CPU number 'cpu'. The C-state can be specified
        both by its index and name.
        """

        return next(self.get_cstates_info(cpu, cstate))

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._proc, cpuinfo=self._cpuinfo)
        return self._msr

    def _get_powerctl(self):
        """Return an instance of 'PowerCtl' class."""

        if self._powerctl is None:
            cpuinfo = self._get_cpuinfo()
            msr = self._get_msr()
            self._powerctl = PowerCtl.PowerCtl(proc=self._proc, cpuinfo=cpuinfo, msr=msr)
        return self._powerctl

    def _get_pcstatectl(self):
        """Return an instance of 'PCStateConfigCtl' class."""

        if self._pcstatectl is None:
            cpuinfo = self._get_cpuinfo()
            msr = self._get_msr()
            self._pcstatectl = PCStateConfigCtl.PCStateConfigCtl(proc=self._proc, cpuinfo=cpuinfo,
                                                                 msr=msr)
        return self._pcstatectl

    @staticmethod
    def _check_prop(pname):
        """Raise an error if a property 'pname' is not supported."""

        if pname not in PROPS:
            pnames_str = ", ".join(set(PROPS))
            raise Error(f"property '{pname}' not supported, use one of the following: "
                        f"{pnames_str}")

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

        pinfos = {}

        for pname in pnames:
            pinfo = pinfos[pname] = {pname : None, "CPU" : cpu}

            try:
                val = self._find_feature(pname, cpu)
            except ErrorNotSupported:
                pinfo[f"{pname}_supported"] = False
                continue

            pinfo[f"{pname}_supported"] = True

            if isinstance(val, dict):
                for fkey, fval in val.items():
                    pinfo[fkey] = fval
            else:
                pinfo[pname] = val

        return pinfos

    def get_props(self, pnames, cpus="all"):
        """
        Read all properties specified in the 'pnames' list for CPUs in 'cpus', and for every CPU
        yield a dictionary containing the read values of all the properties. The arguments are as
        follows.
          * pnames - list or an iterable collection of properties to read and yeild the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - the CPUs to yield the properties for, same as the 'cpus' argument of the
                   'get_cstates_info()' function.

        The yielded dictionaries have the following format.

        { property1_name: { property1_name : property1_value,
                            "CPU" : <CPU number>,
                            property1_key1 : property1_key1_value,
                            property2_key2 : property1_key1_value,
                            ... etc for every key ...},
          property2_name: { property2_name : property2_value,
                            "CPU" : <CPU number>,
                            property2_key1 : property2_key1_value,
                            ... etc ...},
          ... etc ... }

        So each property has the (main) value, but it also comes with a number "kwys", which include
        the CPU number and may also include "sub-properties", which provide additional read-only
        information related to the property. For example, the 'pkg_cstate_limit' property comes with
        'pkg_cstate_limit_locked' and other sub-properties.
        """

        for pname in pnames:
            self._check_prop(pname)

        cpus = self._normalize_cpus(cpus)

        for cpu in cpus:
            yield self._get_pinfo(pnames, cpu)

    def set_prop(self, pname, val, cpus="all"):
        """
        Set value 'val' for property 'pname' for CPUs 'cpus'. The arguments are as follows.
          * pname - name of the property to set (see 'self.props' for the full list).
          * val - the value to set the property to.
          * cpus - same as in 'get_props()'.
        """

        self._check_prop(pname)

        if pname in PowerCtl.FEATURES:
            powerctl = self._get_powerctl()
            powerctl.write_feature(pname, val, cpus)
        elif pname in PCStateConfigCtl.FEATURES:
            pcstatectl = self._get_pcstatectl()
            pcstatectl.write_feature(pname, val, cpus=cpus)
        else:
            raise Error(f"BUG: undefined property '{pname}'")

    @staticmethod
    def get_scope(pname):
        """Get scope of property 'pname'. The 'pname' argument is same as in 'set_prop()'."""

        CStates._check_prop(pname)

        if pname in PowerCtl.FEATURES:
            return PowerCtl.FEATURES[pname]["scope"]
        if pname in PCStateConfigCtl.FEATURES:
            return PCStateConfigCtl.FEATURES[pname]["scope"]

        raise Error(f"BUG: undefined property '{pname}'")

    @staticmethod
    def _create_props_dict():
        """Create an extended version of the 'PROPS' dictionary."""

        props = copy.deepcopy(PROPS)

        # Add property keys.
        for pname, prop in props.items():
            # Each propery has at least one key with the same name.
            prop[pname] = prop["name"]
            prop[f"{pname}_supported"] = f"{prop['name']} supported"

        # The 'pkg_cstate_limits' property has sub-properties.
        prop = props["pkg_cstate_limit"]
        prop["pkg_cstate_limits"]        = "Available package C-state limits"
        prop["pkg_cstate_limit_locked"]  = "Package C-state limit locked"
        prop["pkg_cstate_limit_aliases"] = "Package C-state limit aliases"

        return props

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

        self._powerctl = None
        self._pcstatectl = None

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self.props = self._create_props_dict()

        # Used for caching the C-state information for each CPU.
        self._csinfos = {}
        # Used for mapping C-state indices to C-state names and vice versa.
        self._name2idx_cache = {}
        self._idx2name_cache = {}

        if not self._proc:
            self._proc = Procs.Proc()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_pcstatectl", None):
            self._pcstatectl.close()
            self._pcstatectl = None

        if getattr(self, "_powerctl", None):
            self._powerctl.close()
            self._powerctl = None

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
