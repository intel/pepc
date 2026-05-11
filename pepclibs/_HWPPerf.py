# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of reading and changing HWP min/max performance levels in
'MSR_HWP_REQUEST'.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Generator, Literal, Sequence
    from pepclibs.msr import MSR, HWPRequest, HWPRequestPkg
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    HWPPerfNameType = Literal["min_perf", "max_perf"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class HWPPerf(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and changing HWP min/max performance levels from
    'MSR_HWP_REQUEST'.

    Public Methods:
        - get_min_perf(cpus): Yield (cpu, value) pairs for the minimum performance level.
        - get_max_perf(cpus): Yield (cpu, value) pairs for the maximum performance level.
        - set_min_perf(val, cpus): Set the minimum performance level for specified CPUs.
        - set_max_perf(val, cpus): Set the maximum performance level for specified CPUs.

    Notes:
        - Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid
          and online.
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
            enable_cache: Enable or disable caching for MSR access.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo

        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._hwpreq: HWPRequest.HWPRequest | None = None
        self._hwpreq_pkg: HWPRequestPkg.HWPRequestPkg | None = None

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

        close_attrs = ("_hwpreq", "_hwpreq_pkg", "_cpuinfo", "_pman")
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

    def _get_hwpreq(self) -> HWPRequest.HWPRequest:
        """
        Return an 'HWPRequest.HWPRequest' object.

        Returns:
            An instance of 'HWPRequest.HWPRequest'.
        """

        if not self._hwpreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequest

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(cpuinfo=self._cpuinfo, pman=self._pman, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self) -> HWPRequestPkg.HWPRequestPkg:
        """
        Return an 'HWPRequestPkg.HWPRequestPkg' object.

        Returns:
            An instance of 'HWPRequestPkg.HWPRequestPkg'.
        """

        if not self._hwpreq_pkg:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequestPkg

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(cpuinfo=self._cpuinfo, pman=self._pman,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_perf_remote(self,
                         fname: HWPPerfNameType,
                         cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Implement '_get_perf()' for a remote host, where it is more optimal to read MSRs in bulk.

        Args:
            fname: Name of the performance feature to read ("min_perf" or "max_perf").
            cpus: CPU numbers to read the performance level for.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the performance
            level.
        """

        hwpreq = self._get_hwpreq()

        # Separate CPUs into package-controlled and per-CPU controlled.
        cpus_list: list[int] = []
        pkg_controlled_cpus: list[int] = []
        percpu_controlled_cpus: list[int] = []

        for cpu, pkg_controlled in hwpreq.is_feature_pkg_controlled(fname, cpus=cpus):
            cpus_list.append(cpu)
            if pkg_controlled:
                pkg_controlled_cpus.append(cpu)
            else:
                percpu_controlled_cpus.append(cpu)

        # Read from per-CPU MSR for CPUs not controlled by package MSR.
        perf_vals: dict[int, int] = {}
        if percpu_controlled_cpus:
            for cpu, vals in hwpreq.read_features([fname], cpus=percpu_controlled_cpus):
                perf_vals[cpu] = int(vals[fname])

        # Read from package MSR for CPUs controlled by package MSR.
        if pkg_controlled_cpus:
            hwpreq_pkg = self._get_hwpreq_pkg()
            for cpu, vals in hwpreq_pkg.read_features([fname], cpus=pkg_controlled_cpus):
                perf_vals[cpu] = int(vals[fname])

        # Yield in the order of input CPUs.
        for cpu in cpus_list:
            yield cpu, perf_vals[cpu]

    def _read_cpu_perf(self, fname: HWPPerfNameType, cpu: int) -> int:
        """
        Read the HWP performance level for a specific CPU from MSR.

        Args:
            fname: Name of the performance feature to read ("min_perf" or "max_perf").
            cpu: CPU number to read the performance level for.

        Returns:
            The performance level value.
        """

        hwpreq_union: HWPRequest.HWPRequest | HWPRequestPkg.HWPRequestPkg
        hwpreq_union = hwpreq = self._get_hwpreq()

        if hwpreq.is_cpu_feature_pkg_controlled(fname, cpu):
            hwpreq_union = self._get_hwpreq_pkg()

        return hwpreq_union.read_cpu_feature_int(fname, cpu)

    def _get_perf(self,
                  fname: HWPPerfNameType,
                  cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the HWP performance level for specified CPUs.

        Args:
            fname: Name of the performance feature to read ("min_perf" or "max_perf").
            cpus: CPU numbers to get the performance level for.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the performance
            level.

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        if self._pman.is_remote:
            yield from self._get_perf_remote(fname, cpus)
        else:
            for cpu in cpus:
                yield cpu, self._read_cpu_perf(fname, cpu)

    def get_min_perf(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum HWP performance level for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum performance level for (the caller must validate
                  CPU numbers).

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the minimum
            performance level.

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        yield from self._get_perf("min_perf", cpus)

    def get_max_perf(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum HWP performance level for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum performance level for (the caller must validate
                  CPU numbers).

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the maximum
            performance level.

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        yield from self._get_perf("max_perf", cpus)

    def _set_perf_remote(self, fname: HWPPerfNameType, val: int, cpus: Sequence[int]):
        """
        Implement '_set_perf()' for a remote host, where it is more optimal to write MSRs in bulk.

        Args:
            fname: Name of the performance feature to set ("min_perf" or "max_perf").
            val: The performance level value to set.
            cpus: CPU numbers to set the performance level for.
        """

        hwpreq = self._get_hwpreq()

        # Disable package control for all CPUs.
        hwpreq.disable_feature_pkg_control(fname, cpus=cpus)

        try:
            hwpreq.write_feature(fname, val, cpus=cpus)
        except Error as err:
            raise type(err)(f"Failed to set HWP {fname}{self._pman.hostmsg}:\n"
                            f"{err.indent(2)}") from err

    def _write_cpu_perf(self, fname: HWPPerfNameType, val: int, cpu: int):
        """
        Write the HWP performance level for a specific CPU to MSR.

        Args:
            fname: Name of the performance feature to set ("min_perf" or "max_perf").
            val: The performance level value to set.
            cpu: CPU number to set the performance level for.
        """

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control(fname, cpu)

        try:
            hwpreq.write_cpu_feature(fname, val, cpu)
        except Error as err:
            raise type(err)(f"Failed to set HWP {fname}{self._pman.hostmsg}:\n"
                            f"{err.indent(2)}") from err

    def _set_perf(self, fname: HWPPerfNameType, val: int, cpus: Sequence[int]):
        """
        Set the HWP performance level for specified CPUs.

        Args:
            fname: Name of the performance feature to set ("min_perf" or "max_perf").
            val: The performance level value to set.
            cpus: CPU numbers to set the performance level for.

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        if self._pman.is_remote:
            self._set_perf_remote(fname, val, cpus)
        else:
            for cpu in cpus:
                self._write_cpu_perf(fname, val, cpu)

    def set_min_perf(self, val: int, cpus: Sequence[int]):
        """
        Set the minimum HWP performance level for specified CPUs.

        Args:
            val: The minimum performance level value to set.
            cpus: CPU numbers to set the minimum performance level for (the caller must validate
                  CPU numbers).

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        self._set_perf("min_perf", val, cpus)

    def set_max_perf(self, val: int, cpus: Sequence[int]):
        """
        Set the maximum HWP performance level for specified CPUs.

        Args:
            val: The maximum performance level value to set.
            cpus: CPU numbers to set the maximum performance level for (the caller must validate
                  CPU numbers).

        Raises:
            ErrorNotSupported: If HWP is not supported or disabled.
        """

        self._set_perf("max_perf", val, cpus)
