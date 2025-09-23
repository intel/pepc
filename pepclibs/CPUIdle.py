# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide API for Linux "cpuidle" subsystem sysfs knobs.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
from typing import cast
import contextlib
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs import CPUInfo, _PerCPUCache

if typing.TYPE_CHECKING:
    from typing import Literal, TypedDict, Union, Generator, Iterable, Final
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType

    class ReqCStateInfoTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the requestable C-state information.

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
    ReqCStateInfoKeysType = Literal["index", "name", "desc", "disable", "latency", "residency",
                                    "time", "usage"]

    # Type for the return value of 'enable_cstates()' and 'disable_cstates()' methods.
    ReqCStateToggleResultType = dict[int, dict[Literal["csnames"], list[str]]]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# The C-state sysfs file names which are read by 'get_cstates_info()'.
_CST_SYSFS_FNAMES: Final[set[str]] = {"name", "desc", "disable", "latency", "residency", "time",
                                      "usage"}

class CPUIdle(ClassHelpers.SimpleCloseContext):
    """
    Provide an API for interacting with the Linux "cpuidle" subsystem via sysfs. Refer to Linux
    kernel documentation for details about C-state attributes.

    Methods Overview:
        enable_cstates(csnames="all", cpus="all")
            Enable specified C-states on specified CPUs.

        disable_cstates(csnames="all", cpus="all")
            Disable specified C-states on specified CPUs.

        get_cstates_info(csnames="all", cpus="all")
            Yield information about specified C-states for specified CPUs.

        get_cpu_cstates_info(cpu, csnames="all")
            Get information about specified C-states for a single CPU.

        get_cpu_cstate_info(cpu, csname)
            Get information about a single C-state for a single CPU.

        get_idle_driver()
            Return the name of the current idle driver.

        get_current_governor()
            Return the name of the current idle driver governor.

        get_available_governors()
            Return a list of available idle driver governors.

        set_current_governor(governor)
            Set the current idle driver governor.

        close()
            Uninitialize the class object and release resources.
    """

    def __init__(self, pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 enable_cache=True):
        """
        Initialize a class instance.

        Args:
            pman: A process manager object for the target host. If not provided, a local process
                  manager will be used.
            cpuinfo: A 'CPUinfo.CPUInfo' object for the target. If not provided, a new instance is
                     created.
            enable_cache: Enable or disable caching of cpuidle subsystem information.
        """

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        # Write-through "cpuidle" subsystem information cache.
        self._cache = _PerCPUCache.PerCPUCache(self._cpuinfo, enable_cache=self._enable_cache)

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_cache", "_cpuinfo", "_pman"))

    def _get_kernel_cmdline(self) -> str:
        """
        Retrieve the kernel boot parameters from '/proc/cmdline'.

        Returns:
            The kernel boot parameters as a string.
        """

        try:
            with self._pman.open("/proc/cmdline", "r") as fobj:
                return fobj.read().strip()
        except Error as err:
            raise Error(f"Failed to read kernel boot parameters{self._pman.hostmsg}\n"
                        f"{err.indent(2)}") from err

    def _read_fpaths_and_values(self, cpus: AbsNumsType) -> tuple[list[str], list[str]]:
        """
        Extract sysfs file paths and their values for all C-states and the specified CPUs.

        Args:
            cpus: CPU numbers to collect C-state information for.

        Returns:
            A tuple containing:
                - fpaths: Sorted list of sysfs file paths for each required C-state attribute.
                - values: List of values read from each file in 'fpaths', in the same order.

        Raises:
            ErrorNotFound: If no C-state files are found for the specified CPUs.
        """

        # Use shell commands to read C-states information from sysfs files, because it is a lot
        # faster on systems with large amounts of CPUs in case of a remote host.
        #
        # Start with forming the file paths to read by running the 'find' program.
        indexes_regex = "[[:digit:]]+"
        cpus_regex = "|".join([str(cpu) for cpu in cpus])
        cmd = fr"find '{self._sysfs_base}' -type f -regextype posix-extended " \
              fr"-regex '.*cpu({cpus_regex})/cpuidle/state({indexes_regex})/[^/]+'"
        files, _ = self._pman.run_verify_nojoin(cmd)
        if not files:
            msg = f"Failed to find C-state files in '{self._sysfs_base}'{self._pman.hostmsg}."
            for opt in self._get_kernel_cmdline().split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    msg += f"\nThe '/proc/cmdline' file{self._pman.hostmsg} indicates that the " \
                           f"'{opt}' kernel boot parameter is set.\nThis may be the reason why " \
                           f"there are no C-states{self._pman.hostmsg}"
                    break
            raise ErrorNotFound(msg)

        # At this point 'files' contains the list of files to read. Something like this:
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

        # Drop unnecessary files.
        fpaths: list[str] = []
        for fpath in files:
            if fpath.split("/")[-1].strip() in _CST_SYSFS_FNAMES:
                fpaths.append(fpath)

        # Write the names to a temporary file and then read them all in an efficient way.
        tmpdir = self._pman.mkdtemp(prefix="_linuxcstates_")
        tmpfile = tmpdir / "fpaths.txt"
        values: list[str]

        try:
            with self._pman.open(tmpfile, "w") as fobj:
                fobj.write("".join(fpaths))

            # The 'xargs' tool will make sure 'cat' is invoked once on all the files. It may be
            # invoked few times, but only if the list of files is too long.
            cmd = f"xargs -a '{tmpfile}' cat"
            values, _ = self._pman.run_verify_nojoin(cmd)
        finally:
            self._pman.rmtree(tmpdir)

        if len(fpaths) != len(values):
            raise Error("BUG: Mismatch between sysfs C-state paths and values")

        _LOG.debug("Read the following C-state values from sysfs files:\n%s",
                   "".join(f"{fpath.strip()} = {value.strip()}\n"
                           for fpath, value in zip(fpaths, values)))
        return fpaths, values

    def _read_cstates_info(self, cpus: AbsNumsType) -> \
                               Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about all requestable C-states for the specified CPUs.

        Args:
            cpus: CPU numbers to yield C-state information for.

        Yields:
            Tuples of (CPU number, C-state information dictionary).
        """

        def _add_cstate(csinfo: dict[str, ReqCStateInfoTypedDict], cstate: ReqCStateInfoTypedDict):
            """
            Add a C-state dictionary to the CPU C-states dictionary.

            Args:
                csinfo: The C-states information dictionary to insert into.
                cstate: The C-state information dictionary to insert to 'csinfo'.
            """

            if "name" not in cstate:
                cstate_info = ""
                for key, val in cstate.items():
                    cstate_info += f"\n{key} - {val}"
                raise Error(f"Unexpected Linux sysfs C-states file structure: the 'name' file "
                            f"is missing.\nHere is all the collected information about the\n"
                            f"C-state:{cstate_info}")

            _LOG.debug("Adding C-state: name: '%s', index: %s, desc: '%s', disable: %s, "
                       "latency: %s, residency: %s, time: %s, usage: %s",
                       cstate["name"], cstate["index"], cstate.get("desc", "<unknown>"),
                       cstate.get("disable", "<unknown>"), cstate.get("latency", "<unknown>"),
                       cstate.get("residency", "<unknown>"), cstate.get("time", "<unknown>"),
                       cstate.get("usage", "<unknown>"))

            csname = self._normalize_csname(cstate["name"])

            # Ensure the desired keys order.
            csinfo[csname] = {}
            csinfo[csname]["index"] = cstate["index"]
            for _key in _CST_SYSFS_FNAMES:
                if typing.TYPE_CHECKING:
                    key = cast(ReqCStateInfoKeysType, _key)
                else:
                    key = _key
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
        csinfo: dict[str, ReqCStateInfoTypedDict] = {}
        # This is a temporary dictionary where we'll collect all data for a single C-state.
        cstate: ReqCStateInfoTypedDict = {}

        prev_index = prev_cpu = -1
        fpath_regex = re.compile(r".+/cpu([0-9]+)/cpuidle/state([0-9]+)/(.+)")

        # Build the C-states information dictionary out of sysfs file names and and values.
        for fpath, val in zip(fpaths, values):
            fpath = fpath.strip()
            val = val.strip()

            matchobj = re.match(fpath_regex, fpath)
            if not matchobj:
                raise Error(f"Failed to parse the following file name from '{self._sysfs_base}'"
                            f"{self._pman.hostmsg}:\n  {fpath}")

            _cpu = matchobj.group(1)
            if not Trivial.is_int(_cpu):
                raise Error(f"Failed to parse CPU number from the following file name "
                            f"{self._pman.hostmsg}:\n  {fpath}")
            cpu = int(_cpu)
            if cpu < 0:
                raise Error(f"Invalid CPU number parsed from the following file name "
                            f"{self._pman.hostmsg}:\n  {fpath}")

            _index = matchobj.group(2)
            if not Trivial.is_int(_index):
                raise Error(f"Failed to parse C-state index from the following file name "
                            f"{self._pman.hostmsg}:\n  {fpath}")
            index = int(_index)
            if index < 0:
                raise Error(f"Invalid C-state index parsed from the following file name "
                            f"{self._pman.hostmsg}:\n  {fpath}")

            if typing.TYPE_CHECKING:
                fname = cast(ReqCStateInfoKeysType, matchobj.group(3))
            else:
                fname = matchobj.group(3)

            if prev_cpu == -1:
                prev_cpu = cpu
            if prev_index == -1:
                prev_index = index

            if cpu != prev_cpu or index != prev_index:
                # The CPU or the C-state index changed, 'cstate' contains all information about the
                # previous C-state, add it to 'csinfo'.
                _add_cstate(csinfo, cstate)
                cstate = {}

            if cpu != prev_cpu:
                # The CPU changed, yield the collected C-states information for the previous CPU.
                yield prev_cpu, csinfo
                csinfo = {}

            prev_cpu = cpu
            prev_index = index

            cstate["index"] = index

            if Trivial.is_int(val):
                if fname == "disable":
                    cstate[fname] = bool(int(val))
                else:
                    cstate[fname] = int(val)
            else:
                cstate[fname] = val

        _add_cstate(csinfo, cstate)
        yield cpu, csinfo

    def _get_cstates_info(self,
                          csnames: Iterable[str] | Literal["all"],
                          cpus: AbsNumsType) -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about requestable C-states for given CPUs.

        Args:
            csnames: Requestable C-state names to get information about.
            cpus: CPU numbers to get requestable C-states information for.

        Yields:
            Tuples of (CPU number, C-state information dictionary).
        """

        csinfo: dict[str, ReqCStateInfoTypedDict]
        read_csinfos: dict[int, dict[str, ReqCStateInfoTypedDict]] = {}

        # Form list of CPUs that do not have their C-states information cached. The
        # '_read_cstates_info()' method is more efficient reading information for multiple CPUs in
        # one go.
        read_cpus = [cpu for cpu in cpus if not self._cache.is_cached("csinfo", cpu)]
        if read_cpus:
            # Load their information into the cache.
            for cpu, csinfo in self._read_cstates_info(read_cpus):
                self._cache.add("csinfo", cpu, csinfo)
                read_csinfos[cpu] = csinfo

        # Yield the requested C-states information.
        for cpu in cpus:
            if self._enable_cache:
                csinfo = self._cache.get("csinfo", cpu)
            else:
                csinfo = read_csinfos[cpu]

            if csnames == "all":
                csnames = csinfo.keys()

            result_csinfo = {}
            for csname in csnames:
                try:
                    result_csinfo[csname] = csinfo[csname].copy()
                except KeyError:
                    csnames = ", ".join(csname for csname in csinfo)
                    raise Error(f"Bad C-state name '{csname}' for CPU {cpu}, valid names are: "
                                f"{csnames}") from None

            yield cpu, result_csinfo

    @staticmethod
    def _normalize_csname(csname: str) -> str:
        """
        Normalize a C-state name.

        Args:
            csname: The C-state name to normalize.

        Returns:
            The normalized C-state name in uppercase.
        """

        return csname.upper()

    def _normalize_csnames(self, csnames: Iterable[str] | Literal["all"]) -> \
                                                                Iterable[str] | Literal["all"]:
        """
        Normalize a collection of C-state names.

        Convert all C-state names in 'csnames' to uppercase, remove duplicates, and return the
        normalized list. If 'csnames' is "all", return it unchanged. Do not validate the names.

        Args:
            csnames: C-state names to normalize, or the string "all".

        Returns:
            List of normalized, deduplicated C-state names, or "all".
        """

        if csnames == "all":
            return csnames

        if not Trivial.is_iterable(csnames):
            raise Error("Bad collection of C-state names: must be an iterable")

        csnames = Trivial.list_dedup(csnames)
        return [self._normalize_csname(csname) for csname in csnames]

    def get_cstates_info(self,
                         csnames: Iterable[str] | Literal["all"] = "all",
                         cpus: AbsNumsType | Literal["all"] = "all") -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about requestable C-states for given CPUs.

        Requestable C-state information is read from Linux sysfs. Refer to the Linux kernel
        documentation for details on C-state attributes.

        Args:
            csnames: Requestable C-state names to get information about, or 'all' for all available
                     C-states.
            cpus: CPU numbers to get requestable C-states information for, or 'all' for all CPUs.

        Yields:
            Tuples of (CPU number, C-states information dictionary).

        Raises:
            ErrorNotSupported: If there are no requestable C-states available.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        if not self.get_idle_driver():
            raise ErrorNotSupported(f"There is no idle driver in use{self._pman.hostmsg}")

        csnames = self._normalize_csnames(csnames)
        yield from self._get_cstates_info(csnames, cpus)

    def get_cpu_cstates_info(self,
                             cpu: int,
                             csnames: Iterable[str] | Literal["all"] = "all") -> \
                                                            dict[str, ReqCStateInfoTypedDict]:
        """
        Retrieve information about specified C-states for a given CPU.

        Args:
            cpu: CPU number to retrieve C-states information for.
            csnames: Requestable C-state names to retrieve information for, or "all" to include all
                     available C-states.

        Returns:
            C-states information dictionary.

        Raises:
            ErrorNotSupported: If there are no requestable C-states available.
        """

        csinfo: dict[str, ReqCStateInfoTypedDict] = {}
        for _, csinfo in self.get_cstates_info(csnames=csnames, cpus=(cpu,)):
            break
        return csinfo

    def get_idle_driver(self) -> str:
        """
        Retrieve the name of the currently used Linux CPU idle driver.

        Returns:
            The name of the current Linux CPU idle driver.

        Raises:
            ErrorNotSupported: If no idle driver is found.
        """

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("current_driver", 0)

        path = self._sysfs_base / "cpuidle" / "current_driver"
        try:
            idle_driver = self._pman.read_file(path).strip()
        except ErrorNotFound as err:
            msg = f"Failed to detect current Linux idle driver name:\n{err.indent(2)}"
            for opt in self._get_kernel_cmdline().split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    msg += f"\nThe '/proc/cmdline' file{self._pman.hostmsg} indicates that the " \
                           f"'{opt}' kernel boot parameter is set, this may be the reason"
            raise ErrorNotSupported(msg) from err

        self._cache.add("current_driver", 0, idle_driver)
        return idle_driver

    def get_current_governor(self) -> str:
        """
        Retrieve the name of the current Linux CPU idle governor.

        Returns:
            The name of the current CPU idle governor.

        Raises:
            ErrorNotSupported: If no idle driver is present.
        """

        # Verify there is an idle driver.
        try:
            self.get_idle_driver()
        except ErrorNotSupported as err:
            raise ErrorNotSupported(f"Failed to detect idle governor because there is no idle "
                                    f"driver:\n{err.indent(2)}") from err

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("current_governor", 0)

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            governor = self._pman.read_file(path).strip()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"Failed to detect idle governor:\n{err.indent(2)}") from err

        return self._cache.add("current_governor", 0, governor)

    def get_available_governors(self) -> list[str]:
        """
        Retrieve the list of available CPU idle governors.

        Returns:
            List of available idle governors.

        Raises:
            ErrorNotSupported: If no idle driver is detected.
        """

        # Verify there is an idle driver.
        try:
            self.get_idle_driver()
        except ErrorNotSupported as err:
            raise ErrorNotSupported(f"Failed to detect idle governors because there is no idle "
                                    f"driver:\n{err.indent(2)}") from err

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get("available_governors", 0)

        path = self._sysfs_base / "cpuidle" / "available_governors"
        try:
            avail_governors = self._pman.read_file(path).strip().split()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"Failed to detect idle governors:\n{err.indent(2)}") from err

        return self._cache.add("available_governors", 0, avail_governors)

    def _toggle_cstate(self, cpu: int, index: int, enable: bool):
        """
        Enable or disable a C-state for a given CPU.

        Args:
            cpu: The CPU number to enable or disable the C-state for.
            index: The index of the C-state to enable or disable.
            enable: If True, enable the C-state, otherwise disable it.
        """

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
                _LOG.debug("Writing '%s' to '%s'", val, path)
                fobj.write(val + "\n")
        except Error as err:
            raise Error(f"Failed to {msg}:\n{err.indent(2)}") from err

        try:
            with self._pman.open(path, "r") as fobj:
                read_val = fobj.read().strip()
        except Error as err:
            raise Error(f"Failed to {msg}:\n{err.indent(2)}") from err

        if val != read_val:
            raise Error(f"Failed to {msg}:\n   File '{path}' contains '{read_val}', but should "
                        f"contain '{val}'")

    def _toggle_cstates(self,
                        csnames: Iterable[str] | Literal["all"] = "all",
                        cpus: AbsNumsType | Literal["all"] = "all",
                        enable: bool = True) -> ReqCStateToggleResultType:
        """
        Enable or disable specified CPU C-states on selected CPUs.

        Args:
            csnames: Requestable C-state names to enable or disable, or 'all' to select all
                     available C-states.
            cpus: CPU numbers to apply the changes to, or 'all' for all CPUs.
            enable: If True, enable the specified C-states, otherwise disable them.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of toggled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        if not self.get_idle_driver():
            raise ErrorNotSupported(f"there is no idle driver in use{self._pman.hostmsg}")

        cpus = self._cpuinfo.normalize_cpus(cpus)
        csnames = self._normalize_csnames(csnames)

        toggled: ReqCStateToggleResultType = {}

        for cpu, csinfo in self._get_cstates_info(csnames, cpus):
            for csname, cstate in csinfo.items():
                self._toggle_cstate(cpu, cstate["index"], enable)

                if cpu not in toggled:
                    toggled[cpu] = {"csnames" : []}
                toggled[cpu]["csnames"].append(csname)

                # Update the cached data.
                if self._enable_cache:
                    csinfo = self._cache.get("csinfo", cpu)
                    csinfo[csname]["disable"] = not enable
                    self._cache.add("csinfo", cpu, csinfo)

        return toggled

    def enable_cstates(self,
                       csnames: Iterable[str] | Literal["all"] = "all",
                       cpus: AbsNumsType | Literal["all"] = "all") -> ReqCStateToggleResultType:
        """
        Enable specified CPU C-states on selected CPUs.

        Args:
            csnames: Requestable C-state names to enable, or 'all' to select all available C-states.
            cpus: CPU numbers to apply the changes to, or 'all' for all CPUs.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of enabled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        return self._toggle_cstates(csnames, cpus, True)

    def disable_cstates(self,
                       csnames: Iterable[str] | Literal["all"] = "all",
                       cpus: AbsNumsType | Literal["all"] = "all") -> ReqCStateToggleResultType:
        """
        Enable specified CPU C-states on selected CPUs.

        Args:
            csnames: Requestable C-state names to disable, or 'all' to select all available
                     C-states.
            cpus: CPU numbers to apply the changes to, or 'all' for all CPUs.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of disabled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        return self._toggle_cstates(csnames, cpus, False)

    def set_current_governor(self, governor: str):
        """
        Set the current CPU idle governor.

        Args:
            governor: Name of the governor to set.

        Raises:
            ErrorNotSupported: If idle governors are not supported on the system.
        """

        self._cache.remove("current_governor", 0)

        governors = self.get_available_governors()
        if not governors:
            raise ErrorNotSupported(f"Idle governors are not supported{self._pman.hostmsg}")
        if governor not in governors:
            governors_str = ", ".join(governors)
            raise Error(f"Bad governor name '{governor}', use one of: {governors_str}")

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            with self._pman.open(path, "r+") as fobj:
                fobj.write(governor)
        except Error as err:
            raise type(err)(f"Failed to set 'governor'{self._pman.hostmsg}:\n{err.indent(2)}") \
                            from err

        self._cache.add("current_governor", 0, governor)
