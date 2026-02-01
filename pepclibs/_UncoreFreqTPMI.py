# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide functionality for reading and modifying uncore frequency and other properties on Intel CPUs
via TPMI.
"""

# TODO: check TPMI version before using ELC, see the kernel driver.
#       Check AUTONOMOUS_UFS_DISABLED before using ELC
from __future__ import annotations # Remove when switching to Python 3.10+.

import math
import typing
from pepclibs import TPMI, _UncoreFreqBase
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import ClassHelpers

if typing.TYPE_CHECKING:
    from typing import Generator, Final
    from pepclibs import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._UncoreFreqBase import ELCThresholdType as _ELCThresholdType
    from pepclibs._UncoreFreqBase import ELCZoneType as _ELCZoneType
    from pepclibs._UncoreFreqBase import FreqValueType as _FreqValueType
    from pepclibs._UncoreFreqBase import UncoreDieInfoTypedDict
    from pepclibs.PropsTypes import MechanismNameType
    from pepclibs.CPUInfoTypes import RelNumsType

# The uncore frequency ratio -> uncore frequency Hz multiplier.
RATIO_MULTIPLIER: Final[int] = 100_000_000 # 100MHz

# Unfortunately TPMI does not provide the limit values. The way the Linux kernel driver
# works-around this is it assumes that the initial min/max values at the driver
# initialization time (boot time) are the actual limits. But in theory, these may not be the
# actual limits, these may be the limits the BIOS configured or even mis-configured. So just
# pick some reasonable numbers for the limits.
MIN_FREQ_LIMIT: Final[int] = 100_000_000   # 100MHz
MAX_FREQ_LIMIT: Final[int] = 5_000_000_000 # 5GHz

class UncoreFreqTpmi(_UncoreFreqBase.UncoreFreqBase):
    """
    Provide functionality for reading and modifying uncore frequency and other properties on Intel
    CPUs via TPMI.

    Note: Methods of this class do not validate the 'cpus' and 'dies' arguments. The caller is
    responsible for ensuring that the provided package, die, and CPU numbers exist and that CPUs are
    online.
    """

    mname: MechanismNameType = "tpmi"

    def __init__(self, cpuinfo: CPUInfo.CPUInfo, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()').
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
        """

        super().__init__(cpuinfo, pman, enable_cache=False)

        self._tpmi: TPMI.TPMI = cpuinfo.get_dieinfo().get_tpmi()

    def close(self):
        """Uninitialize the class object."""

        unref_attrs = ("_tpmi",)
        ClassHelpers.close(self, unref_attrs=unref_attrs)

    def _get_tpmi_addr(self, package: int, die: int) -> tuple[str, int, int]:
        """
        Return the TPMI address, instance, and cluster for the given package and die.

        Args:
            package: The package number.
            die: The die number.

        Returns:
            Tuple containing:
                - addr: The TPMI PCI device address.
                - instance: The TPMI instance number.
                - cluster: The TPMI cluster number.
        """

        dies_info = self._cpuinfo.get_all_dies_info()
        die_info = dies_info[package][die]

        addr = die_info["addr"]
        instance = die_info["instance"]
        cluster = die_info["cluster"]

        return addr, instance, cluster

    @staticmethod
    def _get_freq_regname(ftype: _FreqValueType) -> tuple[str, str]:
        """
        Return the TPMI register name and bit-field name corresponding to the frequency value type.

        Args:
            ftype: The frequency value type.

        Returns:
            Tuple containing:
                - regname: TPMI register name.
                - bfname: TPMI bitfield name.
        """

        if ftype == "min":
            regname = "UFS_CONTROL"
            bfname = "MIN_RATIO"
        elif ftype == "max":
            regname = "UFS_CONTROL"
            bfname = "MAX_RATIO"
        else:
            regname = "UFS_STATUS"
            bfname = "CURRENT_RATIO"

        return regname, bfname

    def _get_freq_dies(self,
                       ftype: _FreqValueType,
                       dies: RelNumsType,
                       limit: bool = False) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_freq_dies()'."""

        if limit:
            raise ErrorNotSupported("TPMI does not support min/max uncore frequency limit values")

        regname, bfname = self._get_freq_regname(ftype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                ratio = self._tpmi.read_ufs_register(addr, instance, cluster, regname,
                                                     bfname=bfname)
                yield (package, die, ratio * RATIO_MULTIPLIER)

    @staticmethod
    def _get_elc_zone_freq_regname(ztype: _ELCZoneType, ftype: _FreqValueType) -> tuple[str, str]:
        """
        Return the TPMI register name and bit-field name for the ELC zone frequency.

        Args:
            ztype: The ELC zone type.
            ftype: The frequency value type.

        Returns:
            Tuple containing:
                - regname: TPMI register name.
                - bfname: TPMI bitfield name.
        """

        if ftype != "min":
            raise ErrorNotSupported(f"ELC {ztype} zone {ftype} uncore frequency is not available")

        if ztype == "low":
            regname = "UFS_CONTROL"
            bfname = "EFFICIENCY_LATENCY_CTRL_LOW_RATIO"
        elif ztype == "mid":
            regname = "UFS_CONTROL"
            bfname = "EFFICIENCY_LATENCY_CTRL_MID_RATIO"
        else:
            raise Error(f"BUG: Bad ELC zone type '{ztype}'")

        return regname, bfname

    def _get_elc_zone_freq_dies(self,
                                ztype: _ELCZoneType,
                                ftype: _FreqValueType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_elc_zone_freq_dies()'."""

        regname, bfname = self._get_elc_zone_freq_regname(ztype, ftype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                ratio = self._tpmi.read_ufs_register(addr, instance, cluster, regname,
                                                     bfname=bfname)
                yield (package, die, ratio * RATIO_MULTIPLIER)

    def _validate_freq(self,
                       freq: int,
                       package: int,
                       die: int,
                       ftype: _FreqValueType,
                       ztype: _ELCZoneType | None = None):
        """
        Validate that a frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            ztype: The uncore frequency ELC zone type (e.g., "low" for the low zone). The default
                   None value means that this is not an ELC zone frequency.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If max. uncore frequency is less than min. uncore frequency.
        """

        min_freq: int | None = None
        max_freq: int | None = None

        addr, instance, cluster = self._get_tpmi_addr(package, die)

        if ftype == "min":
            regname, bfname = self._get_freq_regname("max")
            ratio = self._tpmi.read_ufs_register(addr, instance, cluster, regname, bfname=bfname)
            max_freq = ratio * RATIO_MULTIPLIER
        else:
            regname, bfname = self._get_freq_regname("min")
            ratio = self._tpmi.read_ufs_register(addr, instance, cluster, regname, bfname=bfname)
            min_freq = ratio * RATIO_MULTIPLIER

        if ztype:
            zname = f"ELC {ztype} zone "
        else:
            zname = ""
        self._validate_frequency(freq, ftype, package, die, MIN_FREQ_LIMIT, MAX_FREQ_LIMIT,
                                 min_freq=min_freq, max_freq=max_freq, zname=zname)

    def _set_freq_dies(self, freq: int, ftype: _FreqValueType, dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_freq_dies()'."""

        ratio = int(freq / RATIO_MULTIPLIER)
        regname, bfname = self._get_freq_regname(ftype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                self._validate_freq(freq, package, die, ftype)
                self._tpmi.write_ufs_register(ratio, addr, instance, cluster, regname,
                                              bfname=bfname)

    def _set_elc_zone_freq_dies(self,
                                freq: int,
                                ztype: _ELCZoneType,
                                ftype: _FreqValueType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_zone_freq_dies()'."""

        ratio = int(freq / RATIO_MULTIPLIER)
        regname, bfname = self._get_elc_zone_freq_regname(ztype, ftype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                self._validate_freq(freq, package, die, ftype, ztype=ztype)
                self._tpmi.write_ufs_register(ratio, addr, instance, cluster, regname,
                                              bfname=bfname)

    @staticmethod
    def _get_elc_threshold_regname(thrtype: _ELCThresholdType,
                                   status: bool = False) -> tuple[str, str]:
        """
        Return the TPMI register name and bit-field name corresponding to the ELC threshold type.

        Args:
            thrtype: The ELC threshold type.
            status: Return the register for the ELC threshold value if False, return the register
                    for the ELC threshold enabled/disable status if True.

        Returns:
            Tuple containing:
                - regname: TPMI register name.
                - bfname: TPMI bitfield name.
        """

        if thrtype == "low":
            if status:
                raise Error("BUG: ELC low threshold enabled/disabled status TPMI register does not "
                            "exist")
            regname = "UFS_CONTROL"
            bfname = "EFFICIENCY_LATENCY_CTRL_LOW_THRESHOLD"
        elif thrtype == "high":
            regname = "UFS_CONTROL"
            if status:
                bfname = "EFFICIENCY_LATENCY_CTRL_HIGH_THRESHOLD_ENABLE"
            else:
                bfname = "EFFICIENCY_LATENCY_CTRL_HIGH_THRESHOLD"
        else:
            raise Error(f"BUG: Bad ELC threshold type '{thrtype}'")

        return regname, bfname

    def _elc_threshold_raw2percent(self, raw_threshold: int) -> int:
        """
        Convert a raw TPMI ELC threshold value to a percentage.

        Args:
            raw_threshold: Raw TPMI ELC threshold value (0-127).

        Returns:
            int: Percentage representation of the threshold (0-100).
        """

        # TPMI represents the ELC threshold as an integer between 0 and 127, where 0 corresponds to
        # 0% and 127 corresponds to 100%.
        return math.ceil((raw_threshold * 100.0) / 127)

    def _elc_threshold_percent2raw(self, threshold: int) -> int:
        """
        Convert a TPMI ELC threshold value in percent to a raw value.

        Args:
            threshold: TPMI ELC threshold value in percent (0-100).

        Returns:
            int: Raw TPMI ELC threshold value (0-127).
        """

        # TPMI represents the ELC threshold as an integer between 0 and 127, where 0 corresponds to
        # 0% and 127 corresponds to 100%.
        return int((threshold * 127.0) / 100)

    def _get_elc_threshold_dies(self,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_elc_threshold_dies()'."""

        regname, bfname = self._get_elc_threshold_regname(thrtype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                threshold = self._tpmi.read_ufs_register(addr, instance, cluster, regname,
                                                         bfname=bfname)
                yield (package, die, self._elc_threshold_raw2percent(threshold))

    def _get_elc_threshold_status_dies(self,
                                       thrtype: _ELCThresholdType,
                                       dies: RelNumsType) -> Generator[tuple[int, int, bool],
                                                                       None, None]:
        """Refer to '_UncoreFreqBase._get_elc_threshold_status_dies()'."""

        regname, bfname = self._get_elc_threshold_regname(thrtype, status=True)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                status = self._tpmi.read_ufs_register(addr, instance, cluster, regname,
                                                      bfname=bfname)
                yield (package, die, bool(status))

    def _set_elc_threshold_dies(self,
                                threshold: int,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_dies()'."""

        regname, bfname = self._get_elc_threshold_regname(thrtype)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                self._validate_elc_threshold(threshold, thrtype, package, die)
                threshold_raw = self._elc_threshold_percent2raw(threshold)
                self._tpmi.write_ufs_register(threshold_raw, addr, instance, cluster, regname,
                                              bfname=bfname)

    def _set_elc_threshold_status_dies(self,
                                       status: bool,
                                       thrtype: _ELCThresholdType,
                                       dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_status_dies()'."""

        regname, bfname = self._get_elc_threshold_regname(thrtype, status=True)

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                addr, instance, cluster = self._get_tpmi_addr(package, die)
                self._tpmi.write_ufs_register(int(status), addr, instance, cluster, regname,
                                              bfname=bfname)
