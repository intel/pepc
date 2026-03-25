# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#
# Parts of the code was contributed by Len Brown <len.brown@intel.com>.

"""
Provide a capability of reading and changing EPB (Energy Performance Bias) on Intel CPUs.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorPath, ErrorPerCPUPath
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailedPath, ErrorVerifyFailedPerCPUPath
from pepclibs.helperlibs import Trivial, ClassHelpers
from pepclibs import _EPBase

if typing.TYPE_CHECKING:
    from typing import Final, Generator, Sequence
    from pepclibs import CPUInfo, _SysfsIO
    from pepclibs.msr import MSR, EnergyPerfBias
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# EPB policy names, from the following Linux kernel file: arch/x86/kernel/cpu/intel_epb.c
_EPB_POLICIES: Final[tuple[str, ...]] = ("performance", "balance-performance", "normal",
                                         "balance-power", "power")

# The minimum and maximum EPB values.
_EPB_MIN: Final[int] = 0
_EPB_MAX: Final[int] = 15

class EPB(_EPBase.EPBase):
    """
    Provide API for reading and changing EPB (Energy Performance Bias) on Intel CPUs.

    Public methods overview.

    1. Multi-CPU I/O.
        - 'get_vals()' - read EPB values.
        - 'set_vals()' - set EPB values.
    2. Single-CPU I/O.
        - 'get_cpu_val()' - read EPB value for a single CPU.
        - 'set_cpu_val()' - set EPB value for a single CPU.
    3. Miscellaneous.
        - 'close()' - uninitialize the class instance.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object which should be used for accessing MSR registers. Will be
                 created on demand if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Whether to enable caching.
        """

        super().__init__("EPB", pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._epbmsr_obj: EnergyPerfBias.EnergyPerfBias | None = None

        # EPB scope is "CPU" on most platforms, but it may be something else of some platforms.
        try:
            self.sname = self._get_epbmsr_obj().features["epb"]["sname"]
        except ErrorNotSupported:
            self.sname = "CPU"

        self._sysfs_epb_path = "/sys/devices/system/cpu/cpu%d/power/energy_perf_bias"

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, close_attrs=("_epbmsr_obj",))
        super().close()

    def _extract_cpu_from_path(self, path: Path) -> int:
        """
        Extract the CPU number from EPB sysfs path.

        Args:
            path: The EPB sysfs path.

        Returns:
            The CPU number.
        """

        # Path format: /sys/devices/system/cpu/cpu<N>/power/energy_perf_bias
        # Extract "cpu<N>" from the path
        dir_name = path.parent.parent.name
        cpu_str = dir_name.replace("cpu", "")
        return Trivial.str_to_int(cpu_str, what=f"CPU number from path '{path}'")

    def _get_epbmsr_obj(self) -> EnergyPerfBias.EnergyPerfBias:
        """
        Return an 'EnergyPerfBias.EnergyPerfBias' object.

        Returns:
            An instance of 'EnergyPerfBias.EnergyPerfBias'.
        """

        if not self._epbmsr_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import EnergyPerfBias

            msr = self._get_msr()
            self._epbmsr_obj = EnergyPerfBias.EnergyPerfBias(self._cpuinfo, pman=self._pman,
                                                             msr=msr)
        return self._epbmsr_obj

    def _validate_value(self, val: str | int, policy_ok: bool = False):
        """Refer to '_EPBase._validate_value()'."""

        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPB_MIN, _EPB_MAX, what="EPB value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPB value must be an integer within [{_EPB_MIN},{_EPB_MAX}]")
        elif val not in _EPB_POLICIES:
            policies = ", ".join(_EPB_POLICIES)
            raise ErrorNotSupported(f"EPB value must be one of the following EPB policies: "
                                    f"{policies}, or integer within [{_EPB_MIN},{_EPB_MAX}]")

    def _fetch_from_msr(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Fetch EPB for CPUs in 'cpus' from MSR.

        Args:
            cpus: Collection of integer CPU numbers (already normalized).

        Yields:
            Tuple of (cpu, value) for each CPU.

        Raises:
            ErrorNotSupported: If EPB MSR is not supported or disabled.
        """

        epbmsr_obj = self._get_epbmsr_obj()
        yield from epbmsr_obj.read_feature_int("epb", cpus=cpus)

    def _write_to_msr(self, val: str | int, cpus: Sequence[int]):
        """Refer to '_EPBase._write_to_msr()'."""

        epbmsr_obj = self._get_epbmsr_obj()
        epbmsr_obj.write_feature("epb", val, cpus=cpus)

    def __fetch_from_sysfs(self,
                           cpus: Sequence[int]) -> Generator[tuple[int, str | int], None, None]:
        """Implement '_fetch_from_sysfs()'. Arguments are the same."""

        sysfs_io = self._get_sysfs_io()
        paths_iter = (Path(self._sysfs_epb_path % cpu) for cpu in cpus)

        for cpu, (_, val) in zip(cpus, sysfs_io.read_paths(paths_iter, what="EPB")):
            yield cpu, val

    def _fetch_from_sysfs(self,
                          cpus: Sequence[int]) -> Generator[tuple[int, str | int], None, None]:
        """
        Refer to '_EPBase._fetch_from_sysfs()'.

        Raises:
            ErrorPerCPUPath: If reading the sysfs file fails with path-related error.
        """

        try:
            yield from self.__fetch_from_sysfs(cpus)
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err

    def __write_to_sysfs(self, val: str | int, cpus: Sequence[int]):
        """Implement '_write_to_sysfs()'. Arguments are the same."""

        sysfs_io = self._get_sysfs_io()
        paths_iter = (Path(self._sysfs_epb_path % cpu) for cpu in cpus)

        sysfs_io.write_paths(paths_iter, str(val).strip(), what="EPB")

    def _write_to_sysfs(self, val: str | int, cpus: Sequence[int]):
        """
        Refer to '_EPBase._write_to_sysfs()'.

        Raises:
            ErrorPerCPUPath: If writing the sysfs file fails with path-related error.
            ErrorVerifyFailedPerCPUPath: If the written value doesn't match the expected value.
        """

        try:
            self.__write_to_sysfs(val, cpus)
        except ErrorVerifyFailedPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorVerifyFailedPerCPUPath(str(err), cpu=cpu, path=err.path,
                                              expected=err.expected, actual=err.actual) from err
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err
