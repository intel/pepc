# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide functionality for reading and modifying uncore frequency and other properties on Intel CPUs
via TPMI.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import math
from typing import Generator, Final
from pepclibs import CPUInfo, Tpmi, _UncoreFreqBase
from pepclibs.PropsTypes import MechanismNameType
from pepclibs._UncoreFreqBase import FreqValueType as _FreqValueType
from pepclibs._UncoreFreqBase import ELCThresholdType as _ELCThresholdType
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.CPUInfoTypes import RelNumsType
from pepclibs.helperlibs import Logging, ClassHelpers

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Unfortunately TPMI does not provide the limit values. The way the Linux kernel driver
# works-around this is it assumes that the initial min/max values at the driver
# initialization time (boot time) are the actual limits. But in theory, these my not be the
# actual limits, these may be the limits the BIOS configured or even mis-configured. So just
# pick some reasonable numbers for the limits.
MIN_FREQ_LIMIT: Final[int] = 100_000_000   # 100MHz
MAX_FREQ_LIMIT: Final[int] = 5_000_000_000 # 5GHz

class UncoreFreqTpmi(_UncoreFreqBase.UncoreFreqBase):
    """
    Provide functionality for reading and modifying uncore frequency and other properties on Intel
    CPUs via TPMI.

    Overview of public methods:

    1. Get or set uncore frequency via the Linux TPMI debugfs interface:
        * Per-die:
            - get_min_freq_dies()
            - get_max_freq_dies()
            - set_min_freq_dies()
            - set_max_freq_dies()
            - get_cur_freq_dies()
        * Per-CPU:
            - get_min_freq_cpus()
            - get_max_freq_cpus()
            - set_min_freq_cpus()
            - set_max_freq_cpus()
            - get_cur_freq_cpus()
    2. Get or set ELC thresholds.
        * Per-die:
            - get_elc_low_threshold_dies()
            - get_elc_high_threshold_dies()
            - set_elc_low_threshold_dies()
            - set_elc_high_threshold_dies()
        * Per-CPU:
            - get_elc_low_threshold_cpus()
            - get_elc_high_threshold_cpus()
            - set_elc_low_threshold_cpus()
            - set_elc_high_threshold_cpus()

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

        self._tpmi = Tpmi.Tpmi(self._pman)

        # The package number -> uncore TPMI PCI device address map.
        self._addrmap: dict[int, str] = {}

        # The uncore frequency ratio -> uncore frequency Hz multiplier.
        self._ratio_multiplier: int = 100000000

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_tpmi",)
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_pci_addr(self, package: int) -> str:
        """
        Return the uncore TPMI device PCI address for a package.

        Args:
            package: The package number.

        Returns:
            The uncore TPMI device PCI address for the specified package.
        """

        if self._addrmap:
            return self._addrmap[package]

        for addr, pkg, _ in self._tpmi.iter_feature("uncore"):
            if pkg not in self._addrmap:
                self._addrmap[pkg] = addr

        return self._addrmap[package]

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

        assert limit is False
        regname, bfname = self._get_freq_regname(ftype)

        for package, pkg_dies in dies.items():
            addr = self._get_pci_addr(package)
            for die in pkg_dies:
                ratio = self._tpmi.read_register("uncore", addr, die, regname, bfname=bfname)
                yield (package, die, ratio * self._ratio_multiplier)

    def get_min_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the minimum uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the minimum uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the minimum uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_dies("min", dies)

    def get_max_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the maximum uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the maximum uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the maximum uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_dies("max", dies)

    def get_cur_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the current uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the current uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the current uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_dies("current", dies)

    def _validate_freq(self, freq: int, ftype: _FreqValueType, package: int, die: int):
        """
        Validate that a frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        min_freq: int | None = None
        max_freq: int | None = None

        addr = self._get_pci_addr(package)

        if ftype == "min":
            regname, bfname = self._get_freq_regname("max")
            ratio = self._tpmi.read_register("uncore", addr, die, regname, bfname=bfname)
            max_freq = ratio * self._ratio_multiplier
        else:
            regname, bfname = self._get_freq_regname("min")
            ratio = self._tpmi.read_register("uncore", addr, die, regname, bfname=bfname)
            min_freq = ratio * self._ratio_multiplier

        self._validate_frequency(freq, ftype, package, die, MIN_FREQ_LIMIT, MAX_FREQ_LIMIT,
                                 min_freq=min_freq, max_freq=max_freq)

    def _set_freq_dies(self, freq: int, ftype: _FreqValueType, dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_freq_dies()'."""

        ratio = int(freq / self._ratio_multiplier)
        regname, bfname = self._get_freq_regname(ftype)

        for package, pkg_dies in dies.items():
            addr = self._get_pci_addr(package)
            for die in pkg_dies:
                self._validate_freq(freq, ftype, package, die)
                self._tpmi.write_register(ratio, "uncore", addr, die, regname, bfname=bfname)

    def set_uncore_low_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set the minimum uncore frequency for each die in the provided packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_freq_dies(freq, "min", dies)

    def set_max_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set the maximum uncore frequency for each die in the provided packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_freq_dies(freq, "max", dies)

    @staticmethod
    def _get_elc_threshold_regname(thrtype: _ELCThresholdType) -> tuple[str, str]:
        """
        Return the TPMI register name and bit-field name corresponding to the ELC threshold type.

        Args:
            thrtype: The ELC threshold type.

        Returns:
            Tuple containing:
                - regname: TPMI register name.
                - bfname: TPMI bitfield name.
        """

        if thrtype == "low":
            regname = "UFS_CONTROL"
            bfname = "EFFICIENCY_LATENCY_CTRL_LOW_THRESHOLD"
        elif thrtype == "high":
            regname = "UFS_CONTROL"
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
            addr = self._get_pci_addr(package)
            for die in pkg_dies:
                threshold = self._tpmi.read_register("uncore", addr, die, regname, bfname=bfname)
                yield (package, die, self._elc_threshold_raw2percent(threshold))

    def _set_elc_threshold_dies(self,
                                threshold: int,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_dies()'."""

        regname, bfname = self._get_elc_threshold_regname(thrtype)

        for package, pkg_dies in dies.items():
            addr = self._get_pci_addr(package)
            for die in pkg_dies:
                self._validate_elc_threshold(threshold, thrtype, package, die)
                threshold_raw = self._elc_threshold_percent2raw(threshold)
                self._tpmi.write_register(threshold_raw, "uncore", addr, die, regname,
                                          bfname=bfname)
