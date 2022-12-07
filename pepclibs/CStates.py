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
import logging
import contextlib
from pathlib import Path
from pepclibs import _PropsCache
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs import _PCStatesBase, CPUInfo
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
        "type" : "str",
        "sname": PCStateConfigCtl.FEATURES["pkg_cstate_limit"]["sname"],
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
        "sname": PCStateConfigCtl.FEATURES["c1_demotion"]["sname"],
        "writable" : True,
    },
    "c1_undemotion" : {
        "name" : PCStateConfigCtl.FEATURES["c1_undemotion"]["name"],
        "help" : PCStateConfigCtl.FEATURES["c1_undemotion"]["help"],
        "type" : PCStateConfigCtl.FEATURES["c1_undemotion"]["type"],
        "sname": PCStateConfigCtl.FEATURES["c1_undemotion"]["sname"],
        "writable" : True,
    },
    "c1e_autopromote" : {
        "name" : PowerCtl.FEATURES["c1e_autopromote"]["name"],
        "help" : PowerCtl.FEATURES["c1e_autopromote"]["help"],
        "type" : PowerCtl.FEATURES["c1e_autopromote"]["type"],
        "sname": PowerCtl.FEATURES["c1e_autopromote"]["sname"],
        "writable" : True,
    },
    "cstate_prewake" : {
        "name" : PowerCtl.FEATURES["cstate_prewake"]["name"],
        "help" : PowerCtl.FEATURES["cstate_prewake"]["help"],
        "type" : PowerCtl.FEATURES["cstate_prewake"]["type"],
        "sname": PowerCtl.FEATURES["cstate_prewake"]["sname"],
        "writable" : True,
    },
    "idle_driver" : {
        "name" : "Idle driver",
        "help" : """Idle driver is responsible for enumerating and requesting the C-states
                    available on the platform.""",
        "type" : "str",
        "sname": "global",
        "writable" : False,
    },
    "governor" : {
        "name" : "Idle governor",
        "help" : "Idle governor decides which C-state to request on an idle CPU.",
        "type" : "str",
        "sname": "global",
        "writable" : True,
        "subprops" : {
            "governors" : {
                "name" : "Available idle governors",
                "help" : """Idle governors decide which C-state to request on an idle CPU.
                            Different governors implement different selection policy.""",
                "type" : "list[str]",
                "sname": "global",
                "writable" : False,
            },
        },
    },
}

# The C-state sysfs file names which are read by 'get_cstates_info()'. The C-state
# information dictionary returned by 'get_cstates_info()' uses these file names as keys as well.
CST_SYSFS_FNAMES = ["name", "desc", "disable", "latency", "residency", "time", "usage"]

class ReqCStates(ClassHelpers.SimpleCloseContext):
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

        # Normalize C-state names before adding them to the cache.
        csnames = self._normalize_csnames(csinfo)
        for normalized_name, name in zip(csnames, csinfo):
            self._cache[cpu][normalized_name] = csinfo[name]

    def _get_cmdline(self):
        """Get kernel boot parameters."""

        try:
            with self._pman.open("/proc/cmdline", "r") as fobj:
                return fobj.read().strip()
        except Error as err:
            raise Error(f"failed to read kernel boot parameters{self._pman.hostmsg}\n"
                        f"{err.indent(2)}") from err

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
        files, _ = self._pman.run_verify(cmd, join=False)
        if not files:
            msg = f"failed to find C-state files in '{self._sysfs_base}'{self._pman.hostmsg}."

            # Try to give helpful hints for the following cases.
            # * There is no idle driver.
            # * There is a kernel boot parameter like 'idle=poll'.
            with contextlib.suppress(Error):
                with CStates(pman=self._pman, rcsobj=self) as csobj:
                    drvname = csobj.get_cpu_prop("idle_driver", 0)["idle_driver"]["idle_driver"]
                    if drvname == "none":
                        msg += f"\n  There is no idle driver in use{self._pman.hostmsg}, which " \
                               f"may be why Linux C-states support was not found."

                        cmdline = self._get_cmdline()
                        idleoption = [item for item in cmdline.split() if "idle=" in item]
                        if idleoption:
                            msg += f"\n  You have the '{idleoption[0]}' kernel boot parameter" \
                                   f"{self._pman.hostmsg}, which may be why there is no idle " \
                                   f"driver."

            raise Error(msg)

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
        tmpdir = self._pman.mkdtemp(prefix="_linuxcstates_")
        tmpfile = tmpdir / "fpaths.txt"

        try:
            with self._pman.open(tmpfile, "w") as fobj:
                fobj.write("".join(fpaths))

            # The 'xargs' tool will make sure 'cat' is invoked once on all the files. It may be
            # invoked few times, but only if the list of files is too long.
            cmd = f"xargs -a '{tmpfile}' cat"
            values, _ = self._pman.run_verify(cmd, join=False)
        finally:
            self._pman.rmtree(tmpdir)

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
                            f"{self._pman.hostmsg}:\n{fpath}")

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
            with self._pman.open(path, "r+") as fobj:
                fobj.write(val + "\n")
        except Error as err:
            raise Error(f"failed to {msg}:\n{err.indent(2)}") from err

        try:
            with self._pman.open(path, "r") as fobj:
                read_val = fobj.read().strip()
        except Error as err:
            raise Error(f"failed to {msg}:\n{err.indent(2)}") from err

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

    def __init__(self, pman=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")
        # Write-through, per-CPU C-states information cache.
        self._cache = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_cpuinfo", "_pman"))

class CStates(_PCStatesBase.PCStatesBase):
    """
    This class provides C-state management API.

    Public methods overview.

    1. Enable multiple disable C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    2. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For single CPU and a single C-state:  'get_cpu_cstate_info()'.
    3. Get/set C-state properties.
       * For multiple properties and multiple CPUs: 'get_props()', 'set_props()'.
       * For single property and multiple CPUs: 'set_prop()'.
       * For multiple properties and single CPU: 'get_cpu_props()', 'set_cpu_props()'.
       * For single property and single CPU: 'get_cpu_prop()', 'set_cpu_prop()'.
    """

    def _get_rcsobj(self):
        """Returns a 'ReqCStates()' object."""

        if not self._rcsobj:
            self._rcsobj = ReqCStates(self._pman, cpuinfo=self._cpuinfo)
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
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    def _get_powerctl(self):
        """Return an instance of 'PowerCtl' class."""

        if self._powerctl is None:
            msr = self._get_msr()
            self._powerctl = PowerCtl.PowerCtl(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)
        return self._powerctl

    def _get_pcstatectl(self):
        """Return an instance of 'PCStateConfigCtl' class."""

        if self._pcstatectl is None:
            msr = self._get_msr()
            self._pcstatectl = PCStateConfigCtl.PCStateConfigCtl(pman=self._pman,
                                                                 cpuinfo=self._cpuinfo, msr=msr)
        return self._pcstatectl

    def _get_pkg_cstate_limit(self, pname, cpu):
        """Return the 'pname' sub-property for the 'pkg_cstate_limit' property."""

        pcstatectl = self._get_pcstatectl()

        try:
            pkg_cstate_limit_props = pcstatectl.read_cpu_feature("pkg_cstate_limit", cpu)
        except ErrorNotSupported:
            return None

        return pkg_cstate_limit_props[pname]

    def _read_prop_value_from_msr(self, pname, cpu):
        """
        Read property 'pname' from the corresponding MSR register on CPU 'cpu' and return its value.
        """

        if pname in PowerCtl.FEATURES:
            module = self._get_powerctl()
        else:
            module = self._get_pcstatectl()

        try:
            return module.read_cpu_feature(pname, cpu)
        except ErrorNotSupported:
            return None

    def _get_cpu_prop_value_sysfs(self, prop):
        """
        This is a helper for '_get_cpu_prop_value()' which handles the properties backed by a sysfs
        file.
        """

        path = self._sysfs_cpuidle / prop["fname"]

        try:
            return self._read_prop_value_from_sysfs(prop, path)
        except ErrorNotFound:
            _LOG.debug("can't read value of property '%s', path '%s' missing", prop["name"], path)
            return None

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """"Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        if prop is None:
            prop = self._props[pname]

        _LOG.debug("getting '%s' (%s) for CPU %d%s", pname, prop["name"], cpu, self._pman.hostmsg)

        if pname in {"pkg_cstate_limit", "pkg_cstate_limits", "pkg_cstate_limit_aliases"}:
            return self._get_pkg_cstate_limit(pname, cpu)

        if pname == "pkg_cstate_limit_locked":
            return self._read_prop_value_from_msr("locked", cpu)

        if pname in {"c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake"}:
            return self._read_prop_value_from_msr(pname, cpu)

        if self._pcache.is_cached(pname, cpu):
            return self._pcache.get(pname, cpu)

        if "fname" in prop:
            val = self._get_cpu_prop_value_sysfs(prop)
        else:
            raise Error(f"BUG: unsupported property '{pname}'")

        self._pcache.add(pname, cpu, val, sname=prop["sname"])
        return val

    def _set_prop_value(self, pname, val, cpus):
        """Sets user-provided property 'pname' to value 'val' for CPUs 'cpus'."""

        if pname in PowerCtl.FEATURES:
            self._get_powerctl().write_feature(pname, val, cpus=cpus)
            return

        if pname in PCStateConfigCtl.FEATURES:
            self._get_pcstatectl().write_feature(pname, val, cpus=cpus)
            return

        # Removing 'cpus' from the cache will make sure the following '_pcache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_pcache.add()'
        # method.
        for cpu in cpus:
            self._pcache.remove(pname, cpu)

        prop = self._props[pname]

        for cpu in cpus:
            if self._pcache.is_cached(pname, cpu):
                if prop["sname"] == "global":
                    break
                continue

            if "fname" in prop:
                path = self._sysfs_cpuidle / prop["fname"]
                self._write_prop_value_to_sysfs(prop, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the 'sname' siblings. For example, if property
                # scope name is "package", 'val' will be cached for all CPUs in the package that
                # contains CPU number 'cpu'.
                self._pcache.add(pname, cpu, val, sname=prop["sname"])
            else:
                raise Error(f"BUG: undefined property '{pname}'")

    def set_props(self, inprops, cpus="all"):
        """Refer to 'set_props() in '_PCStatesBase' class."""

        inprops = self._normalize_inprops(inprops)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        for pname, val in inprops.items():
            self._validate_cpus_vs_scope(self._props[pname], cpus)

            if pname == "governor":
                self._validate_governor_name(val)

        for pname, val in inprops.items():
            self._set_prop_value(pname, val, cpus)

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # These properties are backed by a sysfs file.
        self._props["idle_driver"]["fname"] = "current_driver"
        self._props["governor"]["fname"] = "current_governor"
        self._props["governor"]["subprops"]["governors"]["fname"] = "available_governors"

    def __init__(self, pman=None, cpuinfo=None, rcsobj=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * rcsobj - a 'CStates.ReqCStates()' object which should be used for reading and setting
                     requestable C-state properties.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

        self._rcsobj = rcsobj
        self._close_rcsobj = rcsobj is None

        self._powerctl = None
        self._pcstatectl = None

        self._init_props_dict()

        self._sysfs_cpuidle = Path("/sys/devices/system/cpu/cpuidle")

        # The write-through per-CPU properties cache. The properties that are backed by an MSR are
        # not cached, because the MSR layer implements its own caching.
        self._enable_cache = enable_cache
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=self._enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcstatectl", "_powerctl", "_rcsobj", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
