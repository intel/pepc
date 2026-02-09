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
import contextlib

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs.helperlibs import Trivial, ClassHelpers
from pepclibs import _EPBase

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs import CPUInfo
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
    Provide a capability of reading and changing EPB (Energy Performance Bias) on Intel CPUs.

    Public Methods:
        - get_vals(): read EPB value(s).
        - set_vals(): set EPB value(s).
        - get_cpu_val(): read EPB value for a specific CPU.
        - set_cpu_val(): set EPB value for a specific CPU.
        - close(): uninitialize the class instance.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 enable_cache: bool = True):
        """
        Initialize class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object which should be used for accessing MSR registers. Will be
                 created on demand if not provided.
            enable_cache: Whether to enable caching.
        """

        super().__init__("EPB", pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._epbmsr_obj: EnergyPerfBias.EnergyPerfBias | None = None

        # EPB scope is "CPU" on most platforms, but it may be something else of some platforms.
        try:
            self.sname = self._get_epbmsr_obj().features["epb"]["sname"]
        except ErrorNotSupported:
            self.sname = "CPU"

        # EPB policy to EPB value dictionary.
        self._epb_policies: dict[str, int] = {name: -1 for name in _EPB_POLICIES}
        self._sysfs_epb_path = "/sys/devices/system/cpu/cpu%d/power/energy_perf_bias"

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, close_attrs=("_epbmsr_obj",))
        super().close()

    def _get_epbmsr_obj(self):
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

    def _read_from_msr(self, cpu: int) -> int:
        """Refer to '_EPBase._read_from_msr()'."""

        return self._get_epbmsr_obj().read_cpu_feature("epb", cpu)

    def _write_to_msr(self, val: str | int, cpu: int):
        """Refer to '_EPBase._write_to_msr()'."""

        if not Trivial.is_int(val):
            raise Error(f"Cannot set EPB to '{val}' using MSR mechanism, because it is not an "
                        f"integer value")

        epbmsr = self._get_epbmsr_obj()

        try:
            epbmsr.write_cpu_feature("epb", val, cpu)
        except Error as err:
            raise type(err)(f"Failed to set EPB{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _read_from_sysfs(self, cpu: int) -> str | int:
        """Refer to '_EPBase._read_from_sysfs()'."""

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get("epb", cpu, "sysfs")

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r") as fobj:
                val_str: str = fobj.read()
                val_str = val_str.strip()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"EPB sysfs entry not found for CPU {cpu}"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        return self._pcache.add("epb", cpu, int(val_str), "sysfs")

    def _write_to_sysfs(self, val: str | int, cpu: int):
        """Refer to '_EPBase._write_to_sysfs()'."""

        self._pcache.remove("epb", cpu, "sysfs")
        val_str = str(val).strip()

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r+") as fobj:
                fobj.write(val_str)
        except Error as err:
            if isinstance(err, ErrorNotFound):
                err = ErrorNotSupported(str(err))
            errmsg = f"Failed to set EPB{self._pman.hostmsg}"
            raise type(err)(f"{errmsg}:\n{err.indent(2)}") from err

        # Setting EPB to policy name will not read back the name, rather the numeric value.
        # E.g. "performance" EPB might be "0".
        if not Trivial.is_int(val_str):
            if self._epb_policies[val_str] == -1:
                self._epb_policies[val_str] = int(self._read_from_sysfs(cpu))
            self._pcache.add("epb", cpu, self._epb_policies[val_str], "sysfs")
        else:
            self._pcache.add("epb", cpu, int(val_str), "sysfs")
