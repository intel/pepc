# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This class provides API for Linux "cpuidle" subsystem sysfs knobs.
"""

# TODO: finish annotating and modernizing this module.
from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import contextlib
from pathlib import Path
from typing import Literal, TypedDict, Union
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs import CPUInfo, _PerCPUCache

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class ReqCStateInfoTypedDict(TypedDict, total=False):
    """
    Type for the Requestable C-state information dictionary returned by 'get_cstates_info()' and
    similar methods.

    Attributes:
        index: C-state index.
        name: C-state name.
        desc: C-state description.
        disable: True if the C-state is disabled.
        latency: C-state latency in microseconds.
        residency: C-state target residency in microseconds.
        time: Time spent in the C-state in microseconds.
        usage: Number of times the C-state was requested.
    """

    index: int
    name: str
    desc: str
    disable: bool
    latency: int
    residency: int
    time: int
    usage: int

# The type of the values in the Requestable C-state information dictionary.
ReqCStateInfoValuesType = Union[int, str, bool]

# The type of the keys in the Requestable C-state information dictionary.
ReqCStateInfoKeysType = Literal["index", "name", "desc", "disable",
                                "latency", "residency", "time", "usage"]

# The C-state sysfs file names which are read by 'get_cstates_info()'. The C-state
# information dictionary returned by 'get_cstates_info()' uses these file names as keys as well.
CST_SYSFS_FNAMES = ["name", "desc", "disable", "latency", "residency", "time", "usage"]

class CPUIdle(ClassHelpers.SimpleCloseContext):
    """
    This class provides API for Linux "cpuidle" subsystem sysfs knobs.

    Public methods overview.

    1. Enable/disable multiple C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    2. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For a single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For a single CPU and a single C-state:  'get_cpu_cstate_info()'.
    """

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
            for opt in self._get_cmdline().split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    msg += f"\nThe '/proc/cmdline' file{self._pman.hostmsg} indicates that the " \
                           f"'{opt}' kernel boot parameter is set.\nThis may be the reason why " \
                           f"there are no C-states{self._pman.hostmsg}"
                    break
            raise ErrorNotFound(msg)

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

            csname = self._normalize_csname(cstate["name"])
            # Ensure the desired keys order.
            csinfo[csname] = {}
            csinfo[csname]["index"] = cstate["index"]
            for key in CST_SYSFS_FNAMES:
                csinfo[csname][key] = cstate[key]

        try:
            fpaths, values = self._read_fpaths_and_values(cpus)
        except ErrorNotFound as err:
            _LOG.debug(err)
            for cpu in cpus:
                yield cpu, {}
            return

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

            if key == "disable":
                val = bool(val)

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
    def _normalize_csname(csname):
        """Normalize C-state name 'csname'."""
        return csname.upper()

    def _normalize_csnames(self, csnames):
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
        return [self._normalize_csname(csname) for csname in csnames]

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

        # Form list of CPUs that do not have their C-states information cached. The
        # '_read_cstates_info()' method is more efficient reading information for multiple CPUs in
        # one go.
        read_cpus = [cpu for cpu in cpus if not self._cache.is_cached("csinfo", cpu)]
        if read_cpus:
            # Load their information into the cache.
            for cpu, csinfo in self._read_cstates_info(read_cpus):
                self._cache.add("csinfo", cpu, csinfo)

        # Yield the requested C-states information.
        for cpu in cpus:
            csinfo = self._cache.get("csinfo", cpu)
            if csnames == "all":
                csnames = csinfo.keys()

            result_csinfo = {}
            for csname in csnames:
                try:
                    result_csinfo[csname] = csinfo[csname].copy()
                except KeyError:
                    csnames = ", ".join(csname for csname in csinfo)
                    raise Error(f"bad C-state name '{csname}' for CPU {cpu}\n"
                                f"Valid names are: {csnames}") from None

            yield cpu, result_csinfo

    def get_cstates_info(self, cpus="all", csnames="all"):
        """
        Yield information about C-states specified in 'csnames' for CPUs specified in 'cpus'.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * csnames - list of C-states names to get information about. It can be both a list of
                      names or a string containing a comma-separated list of names. Value 'all' mean
                      "all C-states" (default).

        This method yields a dictionary for every CPU in 'cpus'. The yielded dictionaries describe
        all C-states in 'csnames' for the CPU. Here is the format of the yielded dictionaries.

        { csname1: { "index":     C-state index,
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
        if not self.get_idle_driver():
            raise ErrorNotSupported(f"There is no idle driver in use{self._pman.hostmsg}")

        csnames = self._normalize_csnames(csnames)
        yield from self._get_cstates_info(csnames, cpus)

    def get_cpu_cstates_info(self, cpu, csnames="all"):
        """
        Get information about C-states specified in 'csnames' for CPU 'cpu'.
          * cpu - integer CPU number to get C-states information about.
          * csnames - same as in 'get_cstates_info()'.

        Return a dictionary similar to the dictionaries yielded by 'get_cstates_info()'.
        """

        csinfo = None
        for _, csinfo in self.get_cstates_info(cpus=(cpu,), csnames=csnames):
            pass
        return csinfo

    def get_cpu_cstate_info(self, cpu, csname):
        """
        Get information about C-states 'csname' for CPU 'cpu'.
          * cpu - integer CPU number to get C-state information about.
          * csname - name of the C-state to get information about.

        Return a dictionary similar to the dictionaries yielded by 'get_cstates_info()'.
        """

        csinfo = None
        for _, csinfo in self.get_cstates_info(cpus=(cpu,), csnames=(csname,)):
            pass
        return csinfo

    def get_idle_driver(self):
        """
        Return name of Linux idle driver currently used by the kernel. Raise 'ErrorNotSupported' if
        there is no idle driver.
        """

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("current_driver", 0)

        path = self._sysfs_base / "cpuidle" / "current_driver"
        try:
            idle_driver = self._pman.read_file(path).strip()
        except ErrorNotFound as err:
            msg = f"failed to detect current Linux idle driver name:\n{err.indent(2)}"
            for opt in self._get_cmdline().split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    msg += f"\nThe '/proc/cmdline' file{self._pman.hostmsg} indicates that the " \
                           f"'{opt}' kernel boot parameter is set, may be the reason"
            raise ErrorNotSupported(msg) from err

        self._cache.add("current_driver", 0, idle_driver)
        return idle_driver

    def get_current_governor(self):
        """
        Return name of the current Linux idle driver governor. Raise 'ErrorNotSUpported' if there is
        no idle driver, and therefore, not idle governor.
        """

        # Verify there is an idle driver.
        try:
            self.get_idle_driver()
        except ErrorNotSupported as err:
            raise ErrorNotSupported(f"failed to detect idle governor because there is no idle "
                                    f"driver:\n{err.indent(2)}") from err

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("current_governor", 0)

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            governor = self._pman.read_file(path).strip()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"failed to detect idle governor:\n{err.indent(2)}") from err

        return self._cache.add("current_governor", 0, governor)

    def get_available_governors(self):
        """Get list of available idle driver governors."""

        # Verify there is an idle driver.
        try:
            self.get_idle_driver()
        except ErrorNotSupported as err:
            raise ErrorNotSupported(f"failed to detect idle governors because there is no idle "
                                    f"driver:\n{err.indent(2)}") from err

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("available_governors", 0)

        path = self._sysfs_base / "cpuidle" / "available_governors"
        try:
            avail_governors = self._pman.read_file(path).strip().split()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"failed to detect idle governors:\n{err.indent(2)}") from err

        return self._cache.add("available_governors", 0, avail_governors)

    def _toggle_cstates(self, csnames="all", cpus="all", enable=True):
        """
        Enable or disable C-states 'csnames' on CPUs 'cpus'. The arguments are as follows.
          * csnames - same as in 'get_cstates_info()'.
          * cpus - same as in 'get_cstates_info()'.
          * enabled - if 'True', the specified C-states should be enabled on the specified CPUs,
                      otherwise disabled.
        """

        if not self.get_idle_driver():
            raise ErrorNotSupported(f"there is no idle driver in use{self._pman.hostmsg}")

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
                csinfo = self._cache.get("csinfo", cpu)
                csinfo[csname]["disable"] = not enable
                self._cache.add("csinfo", cpu, csinfo)

        return toggled

    def enable_cstates(self, csnames="all", cpus="all"):
        """
        Enable C-states 'csnames' on CPUs 'cpus'. The arguments are as follows.
          * cpus - collection of integer CPU numbers to enable. Special value 'all' means "all
                   CPUs".
          * csnames - list of C-states names to enable. It can be both a list of names or a string
                      containing a comma-separated list of names. Value 'all' mean "all C-states".

        Returns a dictionary of the following structure:
          { cpu: { "csnames" : [ cstate1, cstate2, ...]}}
            * cpu - integer CPU number.
            * [cstate1, cstate2, ...] - list of C-states names enabled for CPU 'cpu'.
        """

        return self._toggle_cstates(csnames, cpus, True)

    def disable_cstates(self, csnames="all", cpus="all"):
        """
        Disable C-states 'csnames' on CPUs 'cpus'. The arguments are as follows.
          * cpus - collection of integer CPU numbers to disable. Special value 'all' means "all
                   CPUs".
          * csnames - list of C-states names to enable. It can be both a list of names or a string
                      containing a comma-separated list of names. Value 'all' mean "all C-states".

        Return a dictionary similar to the dictionary returned by 'enable_cstates()'.
        """

        return self._toggle_cstates(csnames, cpus, False)

    def set_current_governor(self, governor):
        """
        Set current idle driver governor. The arguments are as follows.
          * governor - name of the governor to set.
        """

        self._cache.remove("current_governor", 0)

        governors = self.get_available_governors()
        if not governors:
            raise ErrorNotSupported(f"idle governors are not supported{self._pman.hostmsg}")
        if governor not in governors:
            governors = ", ".join(governors)
            raise Error(f"bad governor name '{governor}', use one of: {governors}")

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            with self._pman.open(path, "r+") as fobj:
                fobj.write(governor)
        except Error as err:
            raise type(err)(f"failed to set 'governor'{self._pman.hostmsg}:\n{err.indent(2)}") \
                            from err

        self._cache.add("current_governor", 0, governor)

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # Write-through "cpuidle" subsystem information cache.
        self._cache = _PerCPUCache.PerCPUCache(self._cpuinfo, enable_cache=self._enable_cache)

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_cache", "_cpuinfo", "_pman"))
