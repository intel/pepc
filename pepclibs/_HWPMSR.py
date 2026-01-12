# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability for reading HWP performance levels from 'MSR_HWP_CAPABILITIES'.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers

if typing.TYPE_CHECKING:
    from typing import Generator, Literal
    from pepclibs.msr import MSR, PMEnable, HWPCapabilities
    from pepclibs.CPUInfoTypes import AbsNumsType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    PerfLevelNameType = Literal["lowest", "efficient", "guaranteed", "highest"]

_PERF_LEVEL_NAMES: set[PerfLevelNameType] = {
    "lowest",
    "efficient",
    "guaranteed",
    "highest",
}

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class HWPMSR(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read HWP performance levels from 'MSR_HWP_CAPABILITIES'.

    Public Methods:
        - get_lowest_perf(cpus): Yield (cpu, value) pairs for the lowest performance level.
        - get_efficient_perf(cpus): Yield (cpu, value) pairs for the most efficient performance
                                    level.
        - get_guaranteed_perf(cpus): Yield (cpu, value) pairs for the guaranteed performance level.
        - get_highest_perf(cpus): Yield (cpu, value) pairs for the highest performance level.
        - get_hwp(cpus): Yield (cpu, value) pairs indicating HWP enabled status.

    Notes:
        Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid and
        online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object for MSR access. Will be created if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access, used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo

        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._pmenable: PMEnable.PMEnable | None = None
        self._hwpcap: HWPCapabilities.HWPCapabilities | None = None

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_pmenable", "_hwpcap", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_msr(self) -> MSR.MSR:
        """
        Return an instance of the 'MSR.MSR' class.

        Returns:
            An initialized 'MSR.MSR' object.
        """

        if not self._msr:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_pmenable(self) -> PMEnable.PMEnable:
        """
        Return an instance of the 'PMEnable.PMEnable' class.

        Returns:
            The an initialized 'PMEnable.PMEnable' object.
        """

        if not self._pmenable:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import PMEnable

            msr = self._get_msr()
            self._pmenable = PMEnable.PMEnable(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._pmenable

    def _get_hwpcap(self) -> HWPCapabilities.HWPCapabilities:
        """
        Return an instance of the 'HWPCapabilities.HWPCapabilities' class.

        Returns:
            The an initialized 'HWPCapabilities.HWPCapabilities' object.
        """

        if not self._hwpcap:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPCapabilities

            msr = self._get_msr()
            self._hwpcap = HWPCapabilities.HWPCapabilities(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)

        return self._hwpcap

    def _get_perf_level(self,
                        plname: PerfLevelNameType,
                        cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the performance level value for specified CPUs and performance level
        name.

        Args:
            plname: Name of the performance level to retrieve (e.g., "guaranteed").
            cpus: CPU numbers to get the performance level value for.

        Yields:
            Tuple of (cpu, value), where 'cpu' is the CPU number and 'value' is the performance
            level.

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        fname = f"{plname}_perf"
        hwpcap = self._get_hwpcap()
        yield from hwpcap.read_feature_int(fname, cpus=cpus)

    def get_lowest_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the lowest performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the lowest performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the lowest performance
            level.

        Raises:
            ErrorNotSupported: If the HWP is not supported or disabled.
        """

        yield from self._get_perf_level("lowest", cpus)

    def get_efficient_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the most efficient performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the most efficient performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the most efficient
            performance
            level.

        Raises:
            ErrorNotSupported: If the HWP is not supported or disabled.
        """

        yield from self._get_perf_level("efficient", cpus)

    def get_guaranteed_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the guaranteed performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the guaranteed performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the guaranteed
            performance level.

        Raises:
            ErrorNotSupported: If the HWP is not supported or disabled.
        """

        yield from self._get_perf_level("guaranteed", cpus)

    def get_highest_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the highest performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the highest performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the highest performance
            level.

        Raises:
            ErrorNotSupported: If the HWP is not supported or disabled.
        """

        yield from self._get_perf_level("highest", cpus)

    def get_hwp(self, cpus: AbsNumsType) -> Generator[tuple[int, bool], None, None]:
        """
        Yield the hardware power management (HWP) status for specified CPUs.

        Args:
            cpus: CPU numbers to get the HWP status for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is the HWP status (True if
            HWP is enabled, False otherwise).

        Raises:
            ErrorNotSupported: If the platform does not support HWP.
        """

        pmenable = self._get_pmenable()
        yield from pmenable.is_feature_enabled("hwp", cpus=cpus)
