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
from pepclibs.helperlibs import Procs, Trivial, Human, FSHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo
from pepclibs.msr import MSR, PowerCtl, PCStateConfigCtl

_LOG = logging.getLogger()

# This dictionary describes the C-state properties this module supports. Many of the properties are
# just features controlled by an MSR, such as "c1e_autopromote" from 'PowerCtl.FEATURES'.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'CStates' objects. Use the full dictionary via
# 'CStates.props'.
PROPS = {
    "pkg_cstate_limit" : {
        "name" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["name"],
        "help" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["help"],
        "type" : PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["type"],
        "scope": PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["scope"],
        "writable" : True,
        "subprops" : {
            "pkg_cstate_limit_locked" : {
                "name" : "Package C-state limit lock",
                "help" : """Whether the package C-state limit in MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                            (MSR_PKG_CST_CONFIG_CONTROL) is locked and cannot be modified.""",
                "type" : "bool",
                "writable" : False,
            },
            "pkg_cstate_limits" : {
                "name" : "Available package C-state limits",
                "help" : """List of package C-state names which can be used for limiting the deepest
                            package C-state the platform is allowed to enter.""",
                "type" : "list[str]",
                "writable" : False,
            },
            "pkg_cstate_limit_aliases" : {
                "name" : "Package C-state limit aliases",
                "help" : """Some package C-states have multiple names, and this is a dictionary
                            mapping aliases to the name.""",
                "type" : "dict[str,str]",
                "writable" : False,
            },
        },
    },
    "c1_demotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_demotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_demotion"]["help"],
        "type" : PCStateConfigCtl.FEATURES["c1_demotion"]["type"],
        "scope": PCStateConfigCtl.FEATURES["c1_demotion"]["scope"],
        "writable" : True,
    },
    "c1_undemotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_undemotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_undemotion"]["help"],
        "type" : PCStateConfigCtl.FEATURES["c1_undemotion"]["type"],
        "scope": PCStateConfigCtl.FEATURES["c1_undemotion"]["scope"],
        "writable" : True,
    },
    "c1e_autopromote" : {
        "name" : PowerCtl.FEATURES["c1e_autopromote"]["name"],
        "help" : PowerCtl.FEATURES["c1e_autopromote"]["help"],
        "type" : PowerCtl.FEATURES["c1e_autopromote"]["type"],
        "scope": PowerCtl.FEATURES["c1e_autopromote"]["scope"],
        "writable" : True,
    },
    "cstate_prewake" : {
        "name" : PowerCtl.FEATURES["cstate_prewake"]["name"],
        "help" : PowerCtl.FEATURES["cstate_prewake"]["help"],
        "type" : PowerCtl.FEATURES["cstate_prewake"]["type"],
        "scope": PowerCtl.FEATURES["cstate_prewake"]["scope"],
        "writable" : True,
    },
}

# The C-state sysfs file names which are read by 'get_cstates_info()'. The C-state
# information dictionary returned by 'get_cstates_info()' uses these file names as keys as well.
CST_SYSFS_FNAMES = ["name", "desc", "disable", "latency", "residency", "time", "usage"]

class ReqCStates:
    """
    This class provides API for managing requestable C-states via Linux sysfs API.

    Public methods overview.

    1. Enable/disable multiple C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    2. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For a single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For a single CPU and a single C-state:  'get_cpu_cstate_info()'.
    """

    def _add_to_cache(self, csinfo, cpu):
        """Add C-state information to the cache."""

        if cpu not in self._cache:
            self._cache[cpu] = {}
        self._cache[cpu] = csinfo

    def _read_fpaths_and_values(self, cpus):
        """
        This is a helper for '_read_cstates_info()' which extracts all the required sysfs data from
        the target system for CPUs in 'cpus'. Returns a the following tuple: ('fpaths', 'values').
          * fpaths - sorted list of sysfs file paths for every necessary attribute of all C-states
                      of CPUs in 'cpus'. The paths are not stripped.
          * values - values for every file in 'fpaths' (not stripped either).
        """

        # We will use shell commands to read C-states information from sysfs files, because it is a
        # lot faster on systems with large amounts of CPUs in case of a remote host.
        #
        # Start with forming the file paths to read by running the 'find' program.
        indexes_regex = "[[:digit:]]+"
        cpus_regex = "|".join([str(cpu) for cpu in cpus])
        cmd = fr"find '{self._sysfs_base}' -type f -regextype posix-extended " \
              fr"-regex '.*cpu({cpus_regex})/cpuidle/state({indexes_regex})/[^/]+'"
        files, _ = self._proc.run_verify(cmd, join=False)
        if not files:
            raise Error(f"failed to find C-state files in '{self._sysfs_base}'{self._proc.hostmsg}")

        # At this point 'files' contains the list of files we'll have to read. Something like this:
        # [
        #   '/sys/devices/system/cpu/cpu0/cpuidle/state0/disable\n',
        #   '/sys/devices/system/cpu/cpu0/cpuidle/state0/name\n',
        #   '/sys/devices/system/cpu/cpu0/cpuidle/state0/residency\n',
        #      ... and so on for CPU 0 state 0 ...
        #   '/sys/devices/system/cpu/cpu0/cpuidle/state1/disable\n',
        #   '/sys/devices/system/cpu/cpu0/cpuidle/state1/name\n',
        #      ... and so on for CPU 0 state 1 ...
        #   '/sys/devices/system/cpu/cpu1/cpuidle/state1/disable\n',
        #   '/sys/devices/system/cpu/cpu1/cpuidle/state1/name\n',
        #      ... and so on for CPU 1 and other CPUs ...
        # ]
        #
        # Sorting will make sure everything is ordered by CPU number and C-state index number.
        files = sorted(files)

        # We are only interested in some of the files.
        keep_fnames = set(CST_SYSFS_FNAMES)
        fpaths = []
        for fpath in files:
            if fpath.split("/")[-1].strip() in keep_fnames:
                fpaths.append(fpath)

        # Write the names to a temporary file and then read them all in an efficient way.
        tmpdir = FSHelpers.mktemp(prefix="_linuxcstates_", proc=self._proc)
        tmpfile = tmpdir / "fpaths.txt"

        try:
            with self._proc.open(tmpfile, "w") as fobj:
                fobj.write("".join(fpaths))

            # The 'xargs' tool will make sure 'cat' is invoked once on all the files. It may be
            # invoked few times, but only if the list of files is too long.
            cmd = f"xargs -a '{tmpfile}' cat"
            values, _ = self._proc.run_verify(cmd, join=False)
        finally:
            FSHelpers.rm_minus_rf(tmpdir, proc=self._proc)

        # At this point 'values' will contain the value for every file in 'fpaths'.

        if len(fpaths) != len(values):
            raise Error("BUG: mismatch between sysfs C-state paths and values")

        return fpaths, values

    def _read_cstates_info(self, cpus):
        """
        Yield information about all C-states of CPUs in 'cpus' and yield a C-state information
        dictionary for every CPU in 'cpus'.
        """

        def _add_cstate(csinfo, cstate):
            """Add C-state dictionary 'cstate' to the CPU C-states dictionary 'cstates'."""

            if "name" not in cstate:
                cstate_info = ""
                for key, val in cstate.items():
                    cstate_info += f"\n{key} - {val}"
                raise Error(f"unexpected Linux sysfs C-states file structure: the 'name' file "
                            f"is missing.\nHere is all the collected information about the\n"
                            f"C-state:{cstate_info}")

            name = cstate["name"]
            # Ensure the desired keys order.
            csinfo[name] = {}
            csinfo[name]["index"] = cstate["index"]
            for key in CST_SYSFS_FNAMES:
                csinfo[name][key] = cstate[key]

        fpaths, values = self._read_fpaths_and_values(cpus)

        # This is the dictionary that we'll yield out. It'll contain information for every C-state
        # of a CPU.
        csinfo = {}
        # This is a temporary dictionary where we'll collect all data for a single C-state.
        cstate = {}

        index = prev_index = cpu = prev_cpu = None
        fpath_regex = re.compile(r".+/cpu([0-9]+)/cpuidle/state([0-9]+)/(.+)")

        # Build the C-states information dictionary out of sysfs file names and and values.
        for fpath, val in zip(fpaths, values):
            fpath = fpath.strip()
            val = val.strip()

            matchobj = re.match(fpath_regex, fpath)
            if not matchobj:
                raise Error(f"failed to parse the following file name from '{self._sysfs_base}'"
                            f"{self._proc.hostmsg}:\n{fpath}")

            cpu = int(matchobj.group(1))
            index = int(matchobj.group(2))
            key = matchobj.group(3)

            if Trivial.is_int(val):
                val = int(val)

            if prev_index is not None and index != prev_index:
                # A C-state has been processed. Add it to 'csinfo'.
                _add_cstate(csinfo, cstate)
                cstate = {}

            if prev_cpu is not None and cpu != prev_cpu:
                yield prev_cpu, csinfo
                csinfo = {}

            prev_cpu = cpu
            prev_index = index

            cstate["index"] = index
            cstate[key] = val

        _add_cstate(csinfo, cstate)
        yield cpu, csinfo

    @staticmethod
    def _normalize_csnames(csnames):
        """
        Normalize the the C-states list in 'csnames'. The arguments are as follows.
          * csnames - same as in 'get_cstates_info()'.

        Returns a list of normalized C-state names or "all". The names will be upper-cased,
        duplicate names will be removed. The names are not validated.
        """

        if csnames == "all":
            return csnames

        if isinstance(csnames, str):
            csnames = Trivial.split_csv_line(csnames)

        if not Trivial.is_iterable(csnames):
            raise Error("bad C-states list. Should either be a string or an iterable collection")

        csnames = Trivial.list_dedup(csnames)

        return [csname.upper() for csname in csnames]

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

    def _get_cstates_info(self, csnames, cpus):
        """Implements 'get_cstates_info()'. Yields ('cpu', 'csinfo') tuples."""

        # Form list of CPUs that do not have their C-states information cached.
        read_cpus = [cpu for cpu in cpus if cpu not in self._cache]
        if read_cpus:
            # Load their information into the cache.
            for cpu, csinfo in self._read_cstates_info(read_cpus):
                self._add_to_cache(csinfo, cpu)

        # Yield the requested C-states information.
        for cpu in cpus:
            if csnames == "all":
                names = self._cache[cpu].keys()
            else:
                names = csnames

            csinfo = {}
            for name in names:
                if name in self._cache[cpu]:
                    csinfo[name] = self._cache[cpu][name]
                else:
                    csnames = ", ".join(name for name in self._cache[cpu])
                    raise Error(f"bad C-state name '{name}' for CPU {cpu}\n"
                                f"Valid names are: {csnames}")

            yield cpu, csinfo

    def _toggle_cstates(self, csnames="all", cpus="all", enable=True):
        """
        Enable or disable C-states 'csnames' on CPUs 'cpus'. The arguments are as follows.
          * csnames - same as in 'get_cstates_info()'.
          * cpus - same as in 'get_cstates_info()'.
          * enabled - if 'True', the specified C-states should be enabled on the specified CPUS,
                      otherwise disabled.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        csnames = self._normalize_csnames(csnames)

        toggled = {}
        for cpu, csinfo in self._get_cstates_info(csnames, cpus):
            for csname, cstate in csinfo.items():
                self._toggle_cstate(cpu, cstate["index"], enable)

                if cpu not in toggled:
                    toggled[cpu] = {"csnames" : []}
                toggled[cpu]["csnames"].append(csname)

                # Update the cached data.
                self._cache[cpu][csname]["disable"] = not enable

        return toggled

    def enable_cstates(self, csnames="all", cpus="all"):
        """
        Enable C-states 'csnames' on CPUs 'cpus'. The arguments are as follows.
          * cpus - same as in 'get_cstates_info()'.
          * csnames - same as in 'get_cstates_info()'.

        Returns a dictionary of the following structure:
          { cpunum: { "csnames" : [ cstate1, cstate2, ...]}}
            * cpunum - integer CPU number.
            * [cstate1, cstate2, ...] - list of C-states names enabled for CPU 'cpunum'.
        """

        return self._toggle_cstates(csnames, cpus, True)

    def disable_cstates(self, csnames="all", cpus="all"):
        """Similar to 'enable_cstates()', but disables instead of enabling."""

        return self._toggle_cstates(csnames, cpus, False)

    def get_cstates_info(self, cpus="all", csnames="all"):
        """
        Yield information about C-states specified in 'csnames' for CPUs specified in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).
          * csnames - list of C-states names to get information about. It can be both a list of
                      names or a string containing a comma-separated list of names. Value 'all' mean
                      "all C-states" (default).

        This method yields a dictionary for every CPU in 'cpus'. The yielded dictionaries describe
        all C-states in 'csnames' for the CPU. Here is the format of the yielded dictionaries.

        { csname1: { "index":     C-State index,
                     "name":      C-state name,
                     "desc":      C-state description,
                     "disable":   'True' if the C-state is disabled,
                     "latency":   C-state latency in microseconds,
                     "residency": C-state target residency in microseconds,
                     "time":      time spent in the C-state in microseconds,
                     "usage":     how many times the C-state was requested },
          csname2: { ... etc ... },
           ... and so on for all C-states ... }

        The C-state keys come from Linux sysfs. Please, refer to Linux kernel documentation for more
        details.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        csnames = self._normalize_csnames(csnames)
        yield from self._get_cstates_info(csnames, cpus)

    def get_cpu_cstates_info(self, cpu, csnames="all"):
        """Same as 'get_cstates_info()', but for a single CPU."""

        csinfo = None
        for _, csinfo in self.get_cstates_info(cpus=(cpu,), csnames=csnames):
            pass
        return csinfo

    def get_cpu_cstate_info(self, cpu, csname):
        """Same as 'get_cstates_info()', but for a single CPU and a single C-state."""

        csinfo = None
        for _, csinfo in self.get_cstates_info(cpus=(cpu,), csnames=(csname,)):
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
        # Write-through, per-CPU C-states information cache.
        self._cache = {}

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

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()


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

    def _get_rcsobj(self):
        """Returns a 'ReqCStates()' object."""

        if not self._rcsobj:
            self._rcsobj = ReqCStates(self._proc, cpuinfo=self._cpuinfo)
        return self._rcsobj

    def get_cstates_info(self, cpus="all", csnames="all"):
        """Same as 'ReqCStates.get_cstates_info()'."""

        yield from self._get_rcsobj().get_cstates_info(cpus=cpus, csnames=csnames)

    def get_cpu_cstates_info(self, cpu, csnames="all"):
        """Same as 'ReqCStates.get_cpu_cstates_info()'."""

        return self._get_rcsobj().get_cpu_cstates_info(cpu, csnames=csnames)

    def get_cpu_cstate_info(self, cpu, csname):
        """Same as 'ReqCStates.get_cpu_cstate_info()'."""

        return self._get_rcsobj().get_cpu_cstate_info(cpu, csname)

    def enable_cstates(self, csnames="all", cpus="all"):
        """Same as 'ReqCStates.enable_cstates()'."""

        return self._get_rcsobj().enable_cstates(csnames=csnames, cpus=cpus)

    def disable_cstates(self, csnames="all", cpus="all"):
        """Same as 'ReqCStates.disable_cstates()'."""

        return self._get_rcsobj().disable_cstates(csnames=csnames, cpus=cpus)

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

    def _read_prop_from_msr(self, pname, cpu):
        """Read property 'pname' from the corresponding MSR register on CPU 'cpu'."""

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
            pinfo[pname] = {pname : None}

            if pname == "pkg_cstate_limit":
                # Add the "locked" bit as a sub-property.
                val = self._read_prop_from_msr("locked", cpu)
                pinfo[pname]["pkg_cstate_limit_locked"] = val

            try:
                val = self._read_prop_from_msr(pname, cpu)
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
        yield a ('cpu', 'pinfo') tuple, where 'pinfo' is dictionary containing the read values of
        all the properties. The arguments are as follows.
          * pnames - list or an iterable collection of properties to read and yield the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).

        The yielded 'pinfo' dictionaries have the following format.

        { property1_name: { property1_name : property1_value,
                            subprop1_key : subprop1_value,
                            subprop2_key : subprop2_value,
                            ... etc for every key ...},
          property2_name: { property2_name : property2_value,
                            subprop1_key : subprop2_value,
                            ... etc ...},
          ... etc ... }

        So each property has the (main) value, and possibly sub-properties, which provide additional
        read-only information related to the property. For example, the 'pkg_cstate_limit' property
        comes with 'pkg_cstate_limit_locked' and other sub-properties. Most properties have no
        sub-properties.

        If a property is not supported, its value will be 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        for pname in pnames:
            self._check_prop(pname)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, self._get_pinfo(pnames, cpu)

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for _, pinfo in self.get_props(pnames, cpus=(cpu,)):
            pass
        return pinfo

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_props()', but for a single CPU and a single property."""

        pinfo = None
        for _, pinfo in self.get_props((pname,), cpus=(cpu,)):
            pass
        return pinfo

    def _validate_prop_scope(self, pname, cpus):
        """
        Make sure that CPUs in 'cpus' match the scope of the 'pname' feature. For example, if the
        feature has "package" scope, 'cpus' should include all CPUs in one or more packages.
        """

        scope = self._props[pname]["scope"]
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

        name =  self._props[pname]["name"]
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

        Properties of "bool" type accept the following values:
           * True, "on", "enable" for enabling the feature.
           * False, "off", "disable" for disabling the feature.
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

            if not self._props[pname]["writable"]:
                name = self._props[pname][pname]
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
            # Every features should include the 'subprops' sub-dictionary.
            if "subprops" not in prop:
                prop["subprops"] = {}
            else:
                # Propagate the "scope" key to sub-properties.
                for subprop in prop["subprops"].values():
                    if "scope" not in subprop:
                        subprop["scope"] = prop["scope"]

        self._props = copy.deepcopy(self.props)

    def __init__(self, proc=None, cpuinfo=None, rcsobj=None, msr=None):
        """
        The class constructor. The arguments are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * rcsobj - a 'CStates.ReqCStates()' object which should be used for reading and setting
                     requestable C-state properties.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._rcsobj = None
        self._msr = msr

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_rcsobj = rcsobj is None
        self._close_msr = msr is None

        self._rcsobj = None
        self._powerctl = None
        self._pcstatectl = None

        self.props = None
        # Internal version of 'self.props'. Contains some data which we don't want to expose to the
        # user.
        self._props = None

        if not self._proc:
            self._proc = Procs.Proc()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_pcstatectl", "_powerctl"):
            obj = getattr(self, attr, None)
            if obj:
                obj.close()
                setattr(self, attr, None)

        for attr in ("_msr", "_rcsobj", "_cpuinfo", "_proc"):
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
