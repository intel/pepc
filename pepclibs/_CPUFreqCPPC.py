# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability for reading and CPU frequency settings from ACPI CPPC via Linux sysfs.
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

    FreqType = Literal["min", "max", "base"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqCPPC(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read CPU frequency and performance information from ACPI CPPC via Linux
    sysfs.

    Public Methods:
        - get_min_freq_limit(cpus): Yield minimum frequency limits for CPUs from ACPI CPPC.
        - get_max_freq_limit(cpus): Yield maximum frequency limits for CPUs from ACPI CPPC.
        - get_base_freq(cpus): Yield base frequency for CPUs from ACPI CPPC.
        - get_min_perf_limit(cpus): Yield minimum performance limits for CPUs from ACPI CPPC.
        - get_max_perf_limit(cpus): Yield maximum performance limits for CPUs from ACPI CPPC.
        - get_base_perf(cpus): Yield base performance for CPUs from ACPI CPPC.

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

        # The min. and max frequency limit files are often problematic. This flag helps to avoid
        # repeated read attempts.
        self._min_max_freq_supported = True

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

        val = None

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

    def get_min_perf_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the the minimum performance level limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum performance level limit for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its minimum performance
            level limit.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"min. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "lowest_perf", what)
            yield cpu, val

    def get_max_perf_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the the maximum performance level limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum performance level limit for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its maximum performance
            level limit.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"max. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "highest_perf", what)
            yield cpu, val

    def get_base_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the base performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the base performance
            level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "nominal_perf", f"base CPU {cpu} performance")
            yield cpu, val

    def _get_freq(self,
                  cpus: AbsNumsType,
                  ftype: FreqType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield or specified CPUs.

        Args:
            cpus: CPU numbers to get the frequency limit for.
            ltype: Type of frequency to retrieve (e.g., "min").

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            frequency in Hz.
        """

        if ftype == "min":
            fname = "lowest_freq"
        elif ftype == "max":
            fname = "highest_freq"
        elif ftype == "base":
            fname = "nominal_freq"
        else:
            raise Error(f"BUG: Unknown frequency type '{ftype}'")

        if ftype == "base" or self._min_max_freq_supported:
            yielded = False
            try:
                for cpu in cpus:
                    val = self._read_cppc_sysfs_file(cpu, fname,
                                                     f"{ftype} CPU {cpu} frequency")
                    yield cpu, val * 1000 * 1000
                    yielded = True
            except Error:
                if yielded:
                    # Something was yielded, do not try to recover from the error.
                    raise
                if ftype == "base":
                    # The base frequency file is not available, do not try to recover either,
                    # because the recovery method requires the base frequency.
                    raise
                if self._cpuinfo.info["vendor"] != "GenuineIntel":
                    # I did not see the recovery method giving realistic results on Intel CPUs, but
                    # it seems to give correct results on AMD Server CPUs (checked Rome, Milan,
                    # Genoa).
                    raise

                # Do not try reading frequency files again.
                self._min_max_freq_supported = False

            if self._min_max_freq_supported:
                # All frequencies were read and yielded successfully.
                return

        # Reading min/max frequency files failed. Try to compute the frequency from the performance
        # values and the base frequency.
        if ftype == "min":
            fname = "lowest_perf"
        else:
            fname = "highest_perf"

        for cpu in cpus:
            base_freq = self._read_cppc_sysfs_file(cpu, "nominal_freq",
                                                   f"nominal CPU {cpu} frequency")
            base_perf = self._read_cppc_sysfs_file(cpu, "nominal_perf",
                                                   f"nominal CPU {cpu} performance")
            perf = self._read_cppc_sysfs_file(cpu, fname, f"{ftype} CPU {cpu} performance limit")

            freq = int(base_freq * perf / base_perf)
            # Round down to the nearest 100MHz.
            freq = freq - (freq % 100)
            yield cpu, freq * 1000 * 1000

    def get_min_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum frequency limit for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the minimum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq(cpus, "min")

    def get_max_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum frequency limit for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq(cpus, "max")

    def get_base_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq(cpus, "base")
