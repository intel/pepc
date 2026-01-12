# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability for reading ACPI CPPC properties via Linux sysfs.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs import CPUInfo, _SysfsIO
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorBadFormat, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, Literal
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType

    PerfLevelNameType = Literal["lowest", "lowest_nonlinear", "guaranteed", "nominal", "highest"]

_PERF_LEVEL_NAMES: set[PerfLevelNameType] = {
    "lowest",
    "lowest_nonlinear",
    "guaranteed",
    "nominal",
    "highest",
}

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPPCSysfs(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read CPU frequency and performance information from ACPI CPPC via Linux
    sysfs.

    Public Methods:
        TODO: update
        - get_min_freq_limit(cpus): Yield minimum frequency limits for CPUs from ACPI CPPC.
        - get_max_freq_limit(cpus): Yield maximum frequency limits for CPUs from ACPI CPPC.
        - get_nominal_freq(cpus): Yield nominal frequency for CPUs from ACPI CPPC.
        - get_min_perf_limit(cpus): Yield minimum performance limits for CPUs from ACPI CPPC.
        - get_max_perf_limit(cpus): Yield maximum performance limits for CPUs from ACPI CPPC.
        - get_nominal_perf(cpus): Yield nominal performance for CPUs from ACPI CPPC.

    Notes:
        Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid and
        online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access, used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo
        self._sysfs_io: _SysfsIO.SysfsIO

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

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

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_sysfs_io", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_sysfs_path(self, cpu: int, fname: str) -> Path:
        """
        Construct and return full sysfs path for a given CPU and file name under the 'acpi_cppc'
        sysfs sub-directory.

        Args:
            cpu: CPU number for which to construct the path.
            fname: Name of the sysfs file under the 'acpi_cppc' sysfs sub-directory.

        Returns:
            The full path to the requested sysfs file.
        """

        return self._sysfs_base / f"cpu{cpu}/acpi_cppc" / fname

    def _read_cppc_sysfs_file(self, cpu: int, fname: str, what: str) -> int:
        """
        Read the specified ACPI CPPC sysfs file for a given CPU and gracefully handle errors. Cache
        the value read from the sysfs file to avoid repeated reads.

        Args:
            cpu: CPU number for which to read the sysfs file.
            fname: Name of the sysfs file under the 'acpi_cppc' sysfs sub-directory to read.
            what: Description of the value being read, used for logging and error messages.

        Returns:
            The value read from the sysfs file, after adding it to the cache.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        path = self._get_sysfs_path(cpu, fname)

        val: int | None = None

        try:
            val = self._sysfs_io.read_int(path, what=what)
        except ErrorBadFormat:
            raise
        except ErrorNotSupported:
            raise
        except Error as err:
            # On some platforms reading CPPC sysfs files always fails. So treat these errors as if
            # the sysfs file was not even available and raise 'ErrorNotSupported'.
            _LOG.debug("ACPI CPPC sysfs file '%s' is not readable%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(str(err)) from err

        if val == 0:
            _LOG.debug("ACPI CPPC sysfs file '%s' contains 0%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(f"Read '0' for {what} from '{path}'")

        self._sysfs_io.cache_add(path, str(val))
        return val

    def _get_perf_level(self, plname: PerfLevelNameType,
                        cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the performance level value for specified CPUs and performance level
        name.

        Args:
            plname: Name of the performance level to retrieve (e.g., "nominal").
            cpus: CPU numbers to get the performance level value for.

        Yields:
            Tuple of (cpu, value), where 'cpu' is the CPU number and 'value' is the performance
            level.
        """

        if plname not in _PERF_LEVEL_NAMES:
            raise Error(f"BUG: Unknown performance level name '{plname}'")

        fname = f"{plname}_perf"

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, fname, f"{plname} CPU {cpu} performance")
            yield cpu, val

    def get_lowest_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the lowest performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the lowest performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the lowest performance
            level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        yield from self._get_perf_level("lowest", cpus)

    def get_lowest_nonlinear_perf(self,
                                  cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the lowest_nonlinear performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the lowest_nonlinear performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the lowest nonlinear
            performance level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        yield from self._get_perf_level("lowest_nonlinear", cpus)

    def get_guaranteed_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the guaranteed performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the guaranteed performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the guaranteed
            performance level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        yield from self._get_perf_level("guaranteed", cpus)

    def get_nominal_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the nominal performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the nominal performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the nominal performance
            level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        yield from self._get_perf_level("nominal", cpus)

    def get_highest_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the highest performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the highest performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the highest performance
            level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        yield from self._get_perf_level("highest", cpus)

    def _get_freq(self,
                  cpus: AbsNumsType,
                  plname: PerfLevelNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the frequency for specified CPUs and performance level name.

        Args:
            cpus: CPU numbers to get the frequency limit for.
            plname: Name of the performance level to retrieve (e.g., "nominal").

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            frequency in Hz.
        """

        if plname not in _PERF_LEVEL_NAMES:
            raise Error(f"BUG: Unknown performance level name '{plname}'")

        fname = f"{plname}_freq"

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, fname, f"{plname} CPU {cpu} frequency")
            yield cpu, val * 1000 * 1000

    def get_nominal_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the nominal frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the nominal frequency for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the nominal
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq(cpus, "nominal")
