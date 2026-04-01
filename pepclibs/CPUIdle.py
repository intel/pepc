# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
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
import stat
import typing
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound, ErrorPerCPUPath
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied
from pepclibs import CPUInfo, _PerCPUCache, _SysfsIO

if typing.TYPE_CHECKING:
    from typing import cast, Literal, TypedDict, Union, Generator, Iterable, Final, Sequence
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

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
_CST_SYSFS_FNAMES: Final[frozenset[str]] = frozenset({
    "name",
    "desc",
    "disable",
    "latency",
    "residency",
    "time",
    "usage",
})

class CPUIdle(ClassHelpers.SimpleCloseContext):
    """
    Provide API for interacting with the Linux "cpuidle" subsystem via sysfs.

    Public methods overview.

    1. C-states control.
        - 'enable_cstates()' - enable C-states.
        - 'disable_cstates()' - disable C-states.
    2. C-states information.
        - 'get_cstates_info()' - get C-states info for multiple CPUs.
        - 'get_cpu_cstates_info()' - get C-states info for a single CPU.
        - 'get_cpu_cstate_info()' - get single C-state info for a single CPU.
    3. Idle driver control.
        - 'get_idle_driver()' - get current idle driver name.
        - 'get_current_governor()' - get current idle governor name.
        - 'get_available_governors()' - get available idle governors.
        - 'set_current_governor()' - set idle governor.
    4. Miscellaneous.
        - 'close()' - uninitialize the class object.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache=True):
        """
        Initialize a class instance.

        Args:
            pman: A process manager object for the target host. If not provided, a local process
                  manager will be used.
            cpuinfo: A 'CPUinfo.CPUInfo' object for the target. If not provided, a new instance is
                     created.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not
                      provided.
            enable_cache: Enable or disable caching of cpuidle subsystem information, used only when
                          'sysfs_io' is not provided. If 'sysfs_io' is provided, this argument is
                          ignored.
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

        if not sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)
        else:
            self._sysfs_io = sysfs_io

        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        # Cache for C-state directory names (state0, state1, etc.).
        self._lsdir_cache = _PerCPUCache.PerCPUCache(self._cpuinfo, enable_cache=self._enable_cache)

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, close_attrs=("_lsdir_cache", "_sysfs_io", "_cpuinfo", "_pman"))

    def _format_idle_off_msg(self) -> str:
        """
        Format message about idle states disabled in kernel command line.

        Returns:
            Message fragment if relevant boot parameters found, empty string otherwise.
        """

        fpath = Path("/proc/cmdline")
        try:
            cmdline = self._sysfs_io.read(fpath, what="kernel cmdline")
            for opt in cmdline.split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' " \
                           f"kernel boot parameter is set, this may be the reason"
        except Error as err:
            _LOG.warning("Failed to read '%s'%s: %s", fpath, self._pman.hostmsg, err)
        return ""

    def _get_cstate_dirs(self, cpus: Sequence[int]) -> Generator[Path, None, None]:
        """
        Yield C-state directory paths for the specified CPUs.

        Args:
            cpus: CPU numbers to collect C-state directory paths for.

        Yields:
            Path objects for C-state directories. The yielded paths structure is:
            /sys/devices/system/cpu/cpu{cpu}/cpuidle/state{index}

        Notes:
            - Yielded paths are guaranteed to be in CPU order and C-state index order (using natural
              sort, so state0, state1, ..., state9, state10, etc.).
        """

        # Use optimized remote I/O for remote hosts.
        if self._pman.is_remote:
            yield from self._get_cstate_dirs_remote(cpus)
            return

        for cpu in cpus:
            cpu_path = self._sysfs_base / f"cpu{cpu}"
            cpuidle_path = cpu_path / "cpuidle"

            state_names: list[str]

            # Check if C-state directory names for this CPU are cached.
            if self._enable_cache and self._lsdir_cache.is_cached("state_names", cpu):
                state_names = self._lsdir_cache.get("state_names", cpu)
                for state_name in state_names:
                    yield cpuidle_path / state_name
                continue

            # Collect state directory names to cache them.
            state_names = []

            try:
                # Iterate over all state directories for this CPU, sorted with natural ordering, so
                # that "state1" comes before "state10".
                for entry in self._pman.lsdir(cpuidle_path, sort_by="natural"):
                    # Make sure this is a C-state directory, which has the format "state{index}".
                    if not entry["name"].startswith("state"):
                        continue
                    if not stat.S_ISDIR(entry["mode"]):
                        continue
                    if not Trivial.is_int(entry["name"][5:]):
                        continue

                    state_names.append(entry["name"])
            except ErrorNotFound:
                # No cpuidle directory for this CPU.
                pass

            # Cache the state directory names for this CPU.
            if self._enable_cache:
                self._lsdir_cache.add("state_names", cpu, state_names)

            # Yield the full paths for each state directory.
            for state_name in state_names:
                yield cpuidle_path / state_name

    def _get_cstate_dirs_remote(self, cpus: Sequence[int]) -> Generator[Path, None, None]:
        """
        Yield C-state directory paths for the specified CPUs using optimized remote I/O.

        This method is similar to '_get_cstate_dirs()' but optimized for remote hosts. Instead of
        calling 'lsdir()' separately for each CPU, it creates a Python script that lists all
        C-state directories for multiple CPUs in a single SSH command.

        Args:
            cpus: CPU numbers to collect C-state directory paths for.

        Yields:
            Path objects for C-state directories. The yielded paths structure is:
            /sys/devices/system/cpu/cpu{cpu}/cpuidle/state{index}

        Notes:
            - Yielded paths are guaranteed to be in CPU order and C-state index order (using natural
              sort, so state0, state1, ..., state9, state10, etc.).

        Raises:
            ErrorPerCPUPath: If there is an error listing C-state directories for a specific CPU.
        """

        # Separate CPUs into cached and uncached.
        uncached_cpus = []
        cpu_results: dict[int, list[str]] = {}

        for cpu in cpus:
            if self._enable_cache and self._lsdir_cache.is_cached("state_names", cpu):
                cpu_results[cpu] = self._lsdir_cache.get("state_names", cpu)
            else:
                uncached_cpus.append(cpu)

        # If all CPUs are cached, yield and return.
        if not uncached_cpus:
            for cpu in cpus:
                cpuidle_path = self._sysfs_base / f"cpu{cpu}" / "cpuidle"
                state_names = cpu_results.get(cpu, [])
                for state_name in state_names:
                    yield cpuidle_path / state_name
            return

        # Fetch uncached CPUs via remote script.
        python_path = self._pman.get_python_path()
        sysfs_base_str = str(self._sysfs_base)
        cpus_str = ",".join(str(cpu) for cpu in uncached_cpus)

        cmd = f"""{python_path} -c '
import os, stat

sysfs_base = "{sysfs_base_str}"
cpus = [{cpus_str}]

try:
    for cpu in cpus:
        cpuidle_path = os.path.join(sysfs_base, "cpu%d" % cpu, "cpuidle")

        if not os.path.isdir(cpuidle_path):
            print("%d:" % cpu)
            continue

        try:
            entries = os.listdir(cpuidle_path)
        except PermissionError as err:
            print("ERROR: Permission: Path: %s: Error: %s" % (cpuidle_path, err))
            raise SystemExit(0)
        except Exception as err:
            print("ERROR: Listdir: Path: %s: Error: %s" % (cpuidle_path, err))
            raise SystemExit(0)

        state_names = []

        for name in entries:
            if not name.startswith("state"):
                continue
            entry_path = os.path.join(cpuidle_path, name)
            if not stat.S_ISDIR(os.stat(entry_path).st_mode):
                continue
            suffix = name[5:]
            if not suffix.isdigit():
                continue
            state_names.append(name)

        subdirs = ",".join(state_names)
        print("%d:%s" % (cpu, subdirs))
except Exception as err:
    print("Unexpected error: %s" % err)
    raise SystemExit(1)
'"""

        try:
            stdout, stderr = self._pman.run_verify_nojoin(cmd)
        except Error as err:
            errmsg = err.indent(2)
            raise type(err)(f"Failed to list C-state directories{self._pman.hostmsg}:\n"
                            f"{errmsg}") from err

        if stderr:
            stderr_str = "".join(stderr)
            raise Error(f"Unexpected output on stderr{self._pman.hostmsg}:\n{stderr_str}")

        # Parse the output format: <cpu>:<state0,state1,...>
        for line in stdout:
            line = line.strip()
            if not line:
                continue

            if line.startswith("ERROR:"):
                # Format: ERROR: (Permission|Listdir): Path: <path>: Error: <error>
                generic_errmsg = f"Failed to list C-state directories{self._pman.hostmsg}:\n" \
                                 f"  {line}"

                mobj = re.match(r"ERROR: (Permission|Listdir): Path: ([^:]+): Error: (.+)", line)
                if not mobj:
                    raise Error(generic_errmsg)

                errtype = mobj.group(1)
                path_str = mobj.group(2)
                path = Path(path_str)

                # Extract CPU number from path.
                sysfs_base_escaped = re.escape(str(self._sysfs_base))
                cpu_match = re.match(rf"{sysfs_base_escaped}/cpu(\d+)/cpuidle$", path_str)
                if not cpu_match:
                    raise Error(generic_errmsg)
                cpu = int(cpu_match.group(1))

                if errtype == "Permission":
                    raise ErrorPermissionDenied(f"No permissions to list C-state directories for "
                                                f"CPU {cpu}{self._pman.hostmsg}:\n  {line}")
                raise ErrorPerCPUPath(f"Failed to list C-state directories for CPU {cpu}"
                                      f"{self._pman.hostmsg}:\n  {mobj.group(3)}",
                                      path=path, cpu=cpu)

            # Parse normal format: <cpu>:<state0,state1,...>
            if ":" not in line:
                raise Error(f"Failed to parse output line: {line}")

            cpu_str, subdirs_str = line.split(":", 1)

            cpu = Trivial.str_to_int(cpu_str, what="CPU number in output line")

            if subdirs_str:
                state_names = subdirs_str.split(",")
                # Sort with natural ordering (state0, state1, ..., state10, ...).
                state_names.sort(key=Trivial.natural_sort_key)
            else:
                state_names = []

            cpu_results[cpu] = state_names
            if self._enable_cache:
                self._lsdir_cache.add("state_names", cpu, state_names)

        # Yield results in the order of input CPUs.
        for cpu in cpus:
            cpuidle_path = self._sysfs_base / f"cpu{cpu}" / "cpuidle"
            state_names = cpu_results.get(cpu, [])
            for state_name in state_names:
                yield cpuidle_path / state_name

    def _get_cstates(self,
                     cpus: Sequence[int]) -> Generator[tuple[int, int, str, str], None, None]:
        """
        Yield C-state attribute information for the specified CPUs.

        Args:
            cpus: CPU numbers to collect C-state information for.

        Yields:
            Tuples of (cpu, index, fname, value) where:
                - cpu: CPU number.
                - index: C-state index.
                - fname: Attribute file name (e.g., 'name', 'disable', 'latency').
                - value: Attribute value as a string.

        Raises:
            ErrorNotFound: If no C-state files are found for the specified CPUs.
        """

        yielded_any = False

        # Build generator of all file paths to read from state directory paths.
        # Example paths: /path/to/cpu0/cpuidle/state0/name,
        #                /path/to/cpu0/cpuidle/state0/desc,
        #                ...
        #                /path/to/cpu0/cpuidle/state1/name,
        #                /path/to/cpu0/cpuidle/state1/desc,
        #                ...
        #                /path/to/cpu1/cpuidle/state0/name,
        #                /path/to/cpu1/cpuidle/state0/desc,
        #                ...
        paths_iter = (state_dir_path / fname
                      for state_dir_path in self._get_cstate_dirs(cpus)
                      for fname in _CST_SYSFS_FNAMES)

        # Read all C-state attribute files.
        for path, val in self._sysfs_io.read_paths(paths_iter, what="C-state attribute"):
            yielded_any = True
            # Extract cpu, index, and fname from the path.
            # Path format: /sys/devices/system/cpu/cpu{cpu}/cpuidle/state{index}/{fname}
            fname = path.name
            state_dir_name = path.parent.name
            cpu_dir_name = path.parent.parent.parent.name

            index = int(state_dir_name[5:])
            cpu = int(cpu_dir_name[3:])

            _LOG.debug("Read C-state value: CPU %d, state %d, %s = %s", cpu, index, fname, val)
            yield cpu, index, fname, val

        if not yielded_any:
            msg = f"Failed to find C-state files in '{self._sysfs_base}'{self._pman.hostmsg}."
            msg += self._format_idle_off_msg()
            raise ErrorNotFound(msg)

    def _read_cstates_info(self,
                           cpus: Sequence[int]) -> \
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
            for key in _CST_SYSFS_FNAMES:
                csinfo[csname][key] = cstate[key] # type: ignore

        # This is the dictionary that we'll yield out. It'll contain information for every
        # C-state of a CPU.
        csinfo: dict[str, ReqCStateInfoTypedDict] = {}
        # This is a temporary dictionary where we'll collect all data for a single C-state.
        cstate: ReqCStateInfoTypedDict = {}

        prev_cpu = prev_index = -1

        try:
            # Build the C-states information dictionary from the yielded tuples.
            for cpu, index, fname, val in self._get_cstates(cpus):
                if typing.TYPE_CHECKING:
                    fname = cast(ReqCStateInfoKeysType, fname)

                if prev_cpu == -1:
                    prev_cpu = cpu
                if prev_index == -1:
                    prev_index = index

                if cpu != prev_cpu or index != prev_index:
                    # The CPU or the C-state index changed, 'cstate' contains all information
                    # about the previous C-state, add it to 'csinfo'.
                    _add_cstate(csinfo, cstate)
                    cstate = {}

                if cpu != prev_cpu:
                    # The CPU changed, yield the collected C-states information for the previous
                    # CPU.
                    yield prev_cpu, csinfo
                    csinfo = {}

                prev_cpu = cpu
                prev_index = index

                # Set the index for this C-state.
                cstate["index"] = index

                # Convert the value to the appropriate type.
                if Trivial.is_int(val):
                    if fname == "disable":
                        cstate[fname] = bool(int(val))
                    else:
                        cstate[fname] = int(val) # type: ignore
                else:
                    cstate[fname] = val # type: ignore

            # Add the last C-state and yield the last CPU.
            if prev_cpu != -1:
                _add_cstate(csinfo, cstate)
                yield prev_cpu, csinfo
        except ErrorNotFound as err:
            _LOG.debug(err)
            for cpu in cpus:
                yield cpu, {}

    def _get_cstates_info(self,
                          cpus: Sequence[int],
                          csnames: Iterable[str] | Literal["all"]) -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about requestable C-states for given CPUs.

        Args:
            cpus: CPU numbers to get requestable C-states information for (the caller must validate
                  CPU numbers).
            csnames: Requestable C-state names to get information about.

        Yields:
            Tuples of (CPU number, C-state information dictionary).
        """

        for cpu, csinfo in self._read_cstates_info(cpus):
            if csnames == "all":
                yield cpu, csinfo
                continue

            result_csinfo: dict[str, ReqCStateInfoTypedDict] = {}
            for csname in csnames:
                try:
                    result_csinfo[csname] = csinfo[csname].copy()
                except KeyError:
                    csnames_str = ", ".join(csname for csname in csinfo)
                    raise Error(f"Bad C-state name '{csname}' for CPU {cpu}, valid names are: "
                                f"{csnames_str}") from None

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

    def _normalize_csnames(self,
                           csnames: Iterable[str] | Literal["all"]) -> \
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

    def get_idle_driver(self) -> str:
        """
        Retrieve the name of the currently used Linux CPU idle driver.

        Returns:
            The name of the current Linux CPU idle driver.

        Raises:
            ErrorNotSupported: If no idle driver is found.
        """

        path = self._sysfs_base / "cpuidle" / "current_driver"
        try:
            return self._sysfs_io.read(path, what="idle driver")
        except ErrorNotSupported as err:
            msg = f"Failed to detect current Linux idle driver name:\n{err.indent(2)}"
            msg += self._format_idle_off_msg()
            raise type(err)(msg) from err

    def get_cstates_info(self,
                         cpus: Sequence[int],
                         csnames: Iterable[str] | Literal["all"] = "all") -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about requestable C-states for given CPUs.

        Requestable C-state information is read from Linux sysfs. Refer to the Linux kernel
        documentation for details on C-state attributes.

        Args:
            cpus: CPU numbers to get requestable C-states information for (the caller must validate
                  CPU numbers).
            csnames: Requestable C-state names to get information about, or 'all' for all available
                     C-states.

        Yields:
            Tuples of (CPU number, C-states information dictionary).

        Raises:
            ErrorNotSupported: If there are no requestable C-states available.
        """

        # Verify there is an idle driver.
        self.get_idle_driver()

        csnames = self._normalize_csnames(csnames)
        yield from self._get_cstates_info(cpus, csnames)

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
        for _, csinfo in self.get_cstates_info(cpus=(cpu,), csnames=csnames):
            break
        return csinfo

    def get_current_governor(self) -> str:
        """
        Retrieve the name of the current Linux CPU idle governor.

        Returns:
            The name of the current CPU idle governor.

        Raises:
            ErrorNotSupported: If no idle driver is present.
        """

        # Verify there is an idle driver.
        self.get_idle_driver()

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            return self._sysfs_io.read(path, what="idle governor")
        except Error as err:
            raise type(err)(f"Failed to detect idle governor:\n{err.indent(2)}") from err

    def get_available_governors(self) -> list[str]:
        """
        Retrieve the list of available CPU idle governors.

        Returns:
            List of available idle governors.

        Raises:
            ErrorNotSupported: If no idle driver is detected.
        """

        # Verify there is an idle driver.
        self.get_idle_driver()

        path = self._sysfs_base / "cpuidle" / "available_governors"
        try:
            return self._sysfs_io.read(path, what="available governors").split()
        except Error as err:
            raise type(err)(f"Failed to detect idle governors:\n{err.indent(2)}") from err

    def _toggle_cstates(self,
                        cpus: Sequence[int],
                        csnames: Iterable[str] | Literal["all"] = "all",
                        enable: bool = True) -> ReqCStateToggleResultType:
        """
        Enable or disable specified CPU C-states on selected CPUs.

        Args:
            cpus: CPU numbers to apply the changes to (the caller must validate CPU numbers).
            csnames: Requestable C-state names to enable or disable, or 'all' to select all
                     available C-states.
            enable: If True, enable the specified C-states, otherwise disable them.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of toggled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        # Verify there is an idle driver.
        self.get_idle_driver()

        csnames = self._normalize_csnames(csnames)

        if enable:
            val = "0"
            action = "enable"
        else:
            val = "1"
            action = "disable"

        toggled: ReqCStateToggleResultType = {}
        paths = []

        for cpu, csinfo in self._get_cstates_info(cpus, csnames):
            for csname, cstate in csinfo.items():
                path = self._sysfs_base / f"cpu{cpu}/cpuidle/state{cstate['index']}/disable"
                paths.append(path)

                _LOG.debug("%s C-state: CPU %d, state %d", action.upper(), cpu, cstate["index"])

                if cpu not in toggled:
                    toggled[cpu] = {"csnames": []}
                toggled[cpu]["csnames"].append(csname)

        if paths:
            try:
                self._sysfs_io.write_paths_verify(paths, val, what=f"{action} C-state")
            except Error as err:
                raise type(err)(f"Failed to {action} C-states:\n{err.indent(2)}") from err

        return toggled

    def enable_cstates(self,
                       cpus: Sequence[int],
                       csnames: Iterable[str] | Literal["all"] = "all") -> \
                                                                        ReqCStateToggleResultType:
        """
        Enable specified CPU C-states on selected CPUs.

        Args:
            cpus: CPU numbers to apply the changes to (the caller must validate CPU numbers).
            csnames: Requestable C-state names to enable, or 'all' to select all available C-states.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of enabled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        return self._toggle_cstates(cpus, csnames, True)

    def disable_cstates(self,
                        cpus: Sequence[int],
                        csnames: Iterable[str] | Literal["all"] = "all") -> \
                                                                        ReqCStateToggleResultType:
        """
        Disable specified CPU C-states on selected CPUs.

        Args:
            cpus: CPU numbers to apply the changes to (the caller must validate CPU numbers).
            csnames: Requestable C-state names to disable, or 'all' to select all available
                     C-states.

        Returns:
            A dictionary mapping each affected CPU to a dictionary containing the list of disabled
            C-state names.

        Raises:
            ErrorNotSupported: If no idle driver is in use on the target host.
        """

        return self._toggle_cstates(cpus, csnames, False)

    def set_current_governor(self, governor: str):
        """
        Set the current CPU idle governor.

        Args:
            governor: Name of the governor to set.

        Raises:
            ErrorNotSupported: If idle governors are not supported on the system.
        """

        governors = self.get_available_governors()
        if not governors:
            raise ErrorNotSupported(f"Idle governors are not supported{self._pman.hostmsg}")
        if governor not in governors:
            governors_str = ", ".join(governors)
            raise Error(f"Bad governor name '{governor}', use one of: {governors_str}")

        path = self._sysfs_base / "cpuidle" / "current_governor"
        try:
            self._sysfs_io.write_verify(path, governor, what="idle governor")
        except Error as err:
            raise type(err)(f"Failed to set 'governor'{self._pman.hostmsg}:\n"
                            f"{err.indent(2)}") from err
