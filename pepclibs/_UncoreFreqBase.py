# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide the base class for uncore frequency management classes.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo, CPUModels
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Human
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorOutOfRange, ErrorBadOrder, Error

if typing.TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal, Generator, TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType

    # An uncore frequency type.
    #   - "min": Minimum uncore frequency
    #   - "max": Maximum uncore frequency
    #   - "current": Current uncore frequency
    FreqValueType = Literal["min", "max", "current"]

    # The ELC threshold type.
    #   - "low": Low ELC threshold
    #   - "high": High ELC threshold
    ELCThresholdType = Literal["low", "high"]

    # The ELC zone type.
    #   - "low": Low utilization zone, aggregate die utilization is less than the ELC low threshold
    #            value.
    #   - "mid": Middle utilization zone, aggregate die utilization is greater than or equal to the
    #            ELC low threshold value and less than the ELC high threshold value.
    ELCZoneType = Literal["low", "mid"]

    class UncoreDieInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary representing information about a die.

        Attributes:
            title: A short description of the die.
            path: The sysfs path of the the uncore frequency control interface for the die.
            addr: The TPMI PCI device address.
            instance: The TPMI instance number.
            cluster: The TPMI cluster number.
        """

        title: str
        path: Path | None
        addr: str
        instance: int
        cluster: int

class UncoreFreqBase(ClassHelpers.SimpleCloseContext):
    """
    Provide the base class for uncore frequency management classes.

    Overview of public methods:
    1. Per-die, uncore frequency related methods.
        1. Retrieve uncore frequency.
            - get_min_freq_dies()
            - get_max_freq_dies()
            - get_cur_freq_dies()
            - get_min_freq_limit_dies()
            - get_max_freq_limit_dies()
        2. Retrieve ELC zone uncore frequency.
            - get_elc_low_zone_min_freq_dies()
            - get_elc_mid_zone_min_freq_dies()
        3. Set uncore frequency.
            - set_min_freq_dies()
            - set_max_freq_dies()
        4. Set ELC zone uncore frequency.
            - set_elc_low_zone_min_freq_dies()
            - set_elc_mid_zone_min_freq_dies()
    2. Per-CPU, uncore frequency related methods.
        1. Retrieve uncore frequency.
            - get_min_freq_cpus()
            - get_max_freq_cpus()
            - get_cur_freq_cpus()
            - get_min_freq_limit_cpus()
            - get_max_freq_limit_cpus()
        2. Retrieve ELC zone uncore frequency.
            - get_elc_low_zone_min_freq_cpus()
            - get_elc_mid_zone_min_freq_cpus()
        3. Set uncore frequency.
            - set_min_freq_cpus()
            - set_max_freq_cpus()
        4. Set ELC zone uncore frequency.
            - set_elc_low_zone_min_freq_cpus()
            - set_elc_mid_zone_min_freq_cpus()
    3. Per-die, ELC threshold related methods.
        1. Retrieve ELC thresholds.
            - get_elc_low_threshold_dies()
            - get_elc_high_threshold_dies()
            - get_elc_high_threshold_status_dies()
        2. Set ELC thresholds.
            - set_elc_low_threshold_dies()
            - set_elc_high_threshold_dies()
            - set_elc_high_threshold_status_dies()
    4. Per-CPU, ELC threshold related methods.
        1. Retrieve ELC thresholds.
            - get_elc_low_threshold_cpus()
            - get_elc_high_threshold_cpus()
            - get_elc_high_threshold_status_cpus()
        2. Set ELC thresholds.
            - set_elc_low_threshold_cpus()
            - set_elc_high_threshold_cpus()
            - set_elc_high_threshold_status_cpus()
    5. Get dies information:
        - get_dies_info()
    """

    def __init__(self, cpuinfo: CPUInfo.CPUInfo, pman: ProcessManagerType | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()').
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            enable_cache: Enable caching if True. Used only if 'sysfs_io' is not provided.
        """

        self._cpuinfo = cpuinfo
        self.cache_enabled = enable_cache

        self._close_pman = pman is None
        self._pman: ProcessManagerType

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        proc_cpuinfo = self._cpuinfo.get_proc_cpuinfo()
        if not CPUModels.is_intel(proc_cpuinfo["vendor"]):
            raise ErrorNotSupported(f"Unsupported CPU model '{self._cpuinfo.cpudescr}'"
                                    f"{self._pman.hostmsg}\nOnly Intel CPU uncore frequency "
                                    f"control is currently supported")

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pman",)
        unref_attrs = ("_cpuinfo",)
        ClassHelpers.close(self, close_attrs=close_attrs, unref_attrs=unref_attrs)

    def _get_freq_dies(self,
                       ftype: FreqValueType,
                       dies: RelNumsType,
                       limit: bool = False) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield an uncore frequency for each die in the provided packages->dies mapping.

        Args:
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the uncore frequency.
            limit: If True, retrieve the frequency limit value instead of the current frequency
                   value.

        Yields:
            Tuple (package, die, value), where 'value' is the uncore frequency in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

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

    def get_min_freq_limit_dies(self,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the minimum uncore frequency limit for each die in the provided
        packages->dies mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the minimum uncore frequency limit.

        Yields:
            Tuples of (package, die, value), where 'value' is the minimum uncore frequency limit for
            the specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency limit sysfs file does not exist.
        """

        yield from self._get_freq_dies("min", dies, limit=True)

    def get_max_freq_limit_dies(self,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the maximum uncore frequency limit for each die in the provided
        packages->dies mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the maximum uncore frequency limit.

        Yields:
            Tuples of (package, die, value), where 'value' is the maximum uncore frequency limit for
            the specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_dies("max", dies, limit=True)

    def _get_elc_zone_freq_dies(self,
                                ztype: ELCZoneType,
                                ftype: FreqValueType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield an ELC zone frequency value for each die in the provided packages->dies
        mapping.

        Args:
            ztype: The type of ELC zone (e.g., "low").
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC threshold.

        Yields:
            Tuples of (package, die, frequency), where 'frequency' is the requested ELC zone
            frequency value for the specified die in the specified package.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def get_elc_low_zone_min_freq_dies(self,
                                       dies: RelNumsType) -> Generator[tuple[int, int, int],
                                                                       None, None]:
        """
        Retrieve and yield the ELC low zone minimum frequency for each die in the provided
        packages->dies mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC low zone minimum frequency.

        Yields:
            Tuples of (package, die, frequency), where 'frequency' is the ELC low zone minimum
            frequency value for the specified die in the specified package.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_elc_zone_freq_dies("low", "min", dies)

    def get_elc_mid_zone_min_freq_dies(self,
                                       dies: RelNumsType) -> Generator[tuple[int, int, int],
                                                                       None, None]:
        """
        Retrieve and yield the ELC middle zone minimum frequency for each die in the provided
        packages->dies mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC middle zone minimum frequency.

        Yields:
            Tuples of (package, die, frequency), where 'frequency' is the ELC middle zone minimum
            frequency value for the specified die in the specified package.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_elc_zone_freq_dies("mid", "min", dies)

    def _set_freq_dies(self, freq: int, ftype: FreqValueType, dies: RelNumsType):
        """
        Set the minimum or maximum uncore frequency for each die in the specified packages->dies
        mapping.

        Args:
            freq: The frequency value to set, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            dies: The package->dies mapping defining die numbers to set the uncore frequency for.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def set_min_freq_dies(self, freq: int, dies: RelNumsType):
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

    def _set_elc_zone_freq_dies(self,
                                freq: int,
                                ztype: ELCZoneType,
                                ftype: FreqValueType,
                                dies: RelNumsType):
        """
        Set the specified ELC zone uncore frequency to 'freq' for each die in the specified
        packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            ztype: The type of ELC zone (e.g., "low").
            ftype: The ELC zone uncore frequency value type (e.g., "min" for ELC zone minimum
                   uncore frequency).
            dies: The package->dies mapping defining die numbers to set the ELC zone uncore
                  frequency for.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def set_elc_low_zone_min_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set ELC low zone minimum uncore frequency to 'freq' for each die in the specified
        packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_elc_zone_freq_dies(freq, "low", "min", dies)

    def set_elc_mid_zone_min_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set ELC middle zone minimum uncore frequency to 'freq' for each die in the specified
        packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_elc_zone_freq_dies(freq, "mid", "min", dies)

    def _get_freq_cpus(self,
                       ftype: FreqValueType,
                       cpus: AbsNumsType,
                       limit: bool = False) -> Generator[tuple[int, int], None, None]:
        """
        Yield an uncore frequency value for each CPU in the provided collection of CPU numbers.

        Args:
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            cpus: A collection of integer CPU numbers to read the uncore frequency for.
            limit: If True, read the frequency limit value instead of the frequency.

        Yields:
            tuple: A tuple (cpu, frequency) for each CPU, where frequency is in Hz.
        """

        freq_cache: dict[int, dict[int, int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in freq_cache:
                if die in freq_cache[package]:
                    yield cpu, freq_cache[package][die]
                    continue
            else:
                freq_cache[package] = {}

            for _, _, freq in self._get_freq_dies(ftype, {package: [die]}, limit=limit):
                freq_cache[package][die] = freq
                yield cpu, freq
                break

    def get_min_freq_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the minimum uncore frequency for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the minimum uncore frequency for.

        Yields:
            Tuple (cpu, value), where 'value' is the minimum uncore frequency for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_cpus("min", cpus)

    def get_max_freq_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the maximum uncore frequency for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the maximum uncore frequency for.

        Yields:
            Tuple (cpu, value), where 'value' is the maximum uncore frequency for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_cpus("max", cpus)

    def get_cur_freq_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the current uncore frequency for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the current uncore frequency for.

        Yields:
            Tuple (cpu, value), where 'value' is the current uncore frequency for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_cpus("current", cpus)

    def get_min_freq_limit_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the minimum uncore frequency limit for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the minimum uncore frequency limit
                  for.

        Yields:
            Tuple (cpu, value), where 'value' is the minimum uncore frequency limit for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_cpus("min", cpus, limit=True)

    def get_max_freq_limit_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the maximum uncore frequency limit for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the maximum uncore frequency limit
                  for.

        Yields:
            Tuple (cpu, value), where 'value' is the maximum uncore frequency limit for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        yield from self._get_freq_cpus("max", cpus, limit=True)

    def _get_elc_zone_freq_cpus(self,
                                ztype: ELCZoneType,
                                ftype: FreqValueType,
                                cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield an ELC zone frequency value for each CPU in 'cpus'.

        Args:
            ztype: The type of ELC zone (e.g., "low").
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            cpus: A collection of integer CPU numbers to retrieve the ELC zone frequency values for.

        Yields:
            Tuples of (cpu, frequency), where 'frequency' is the requested ELC zone
            frequency value for the die corresponding to 'cpu'.
        """

        freq_cache: dict[int, dict[int, int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in freq_cache:
                if die in freq_cache[package]:
                    yield cpu, freq_cache[package][die]
                    continue
            else:
                freq_cache[package] = {}

            for _, _, freq in self._get_elc_zone_freq_dies(ztype, ftype, {package: [die]}):
                freq_cache[package][die] = freq
                yield cpu, freq
                break

    def get_elc_low_zone_min_freq_cpus(self,
                                       cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield an ELC low zone minimum frequency value for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the ELC low zone minimum frequency
                  values for.

        Yields:
            Tuples of (cpu, frequency), where 'frequency' is the ELC low zone minimum frequency
            value for the die corresponding to 'cpu'.

        Raises:
            ErrorNotSupported: If the ELC low zone minimum frequency operation is not supported.
        """

        yield from self._get_elc_zone_freq_cpus("low", "min", cpus)

    def get_elc_mid_zone_min_freq_cpus(self,
                                       cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield an ELC middle zone minimum frequency value for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the ELC middle zone minimum
                  frequency values for.

        Yields:
            Tuples of (cpu, frequency), where 'frequency' is the ELC middle zone minimum frequency
            value for the die corresponding to 'cpu'.

        Raises:
            ErrorNotSupported: If the ELC middle zone minimum frequency operation is not supported.
        """

        yield from self._get_elc_zone_freq_cpus("mid", "min", cpus)

    def _validate_frequency(self,
                            freq: int,
                            ftype: FreqValueType,
                            package: int,
                            die: int,
                            min_freq_limit: int,
                            max_freq_limit: int,
                            min_freq: int | None = None,
                            max_freq: int | None = None,
                            zname: str = ""):
        """
        Validate that a minimum or maximum uncore frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.
            min_freq_limit: The minimum uncore frequency limit in Hz.
            max_freq_limit: The maximum uncore frequency limit in Hz.
            min_freq: The minimum uncore frequency in Hz.
            max_freq: The maximum uncore frequency in Hz.
            zname: ELC zone name in case of ELC zone frequency validation.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency.
        """

        if freq < min_freq_limit or freq > max_freq_limit:
            name = f"Package {package} die {die} {zname}{ftype} uncore frequency"
            freq_str = Human.num2si(freq, unit="Hz", decp=2)
            min_limit_str = Human.num2si(min_freq_limit, unit="Hz", decp=2)
            max_limit_str = Human.num2si(max_freq_limit, unit="Hz", decp=2)
            raise ErrorOutOfRange(f"{name} value of '{freq_str}' is out of range, must be within "
                                  f"[{min_limit_str},{max_limit_str}]")

        if ftype == "min":
            assert max_freq is not None
            if freq > max_freq:
                name = f"Package {package} die {die} {zname}{ftype} uncore frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=2)
                max_freq_str = Human.num2si(max_freq, unit="Hz", decp=2)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is greater than the currently "
                                    f"configured max frequency of {max_freq_str}")
        else:
            assert min_freq is not None
            if freq < min_freq:
                name = f"Package {package} die {die} {zname}{ftype} uncore frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=2)
                min_freq_str = Human.num2si(min_freq, unit="Hz", decp=2)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is less than the currently "
                                    f"configured min frequency of {min_freq_str}")

    def _set_freq_cpus(self, freq: int, ftype: FreqValueType, cpus: AbsNumsType):
        """
        Set the minimum or maximum uncore frequency for each die corresponding to the specified
        CPUs.

        Args:
            freq: Frequency value to set, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            cpus: A collection of integer CPU numbers to set the uncore frequency for.
        """

        set_dies_cache: dict[int, set[int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in set_dies_cache:
                if die in set_dies_cache[package]:
                    continue
            else:
                set_dies_cache[package] = set()

            set_dies_cache[package].add(die)
            self._set_freq_dies(freq, ftype, {package: [die]})

    def set_min_freq_cpus(self, freq: int, cpus: AbsNumsType):
        """
        Set the minimum uncore frequency for the dies corresponding to the specified CPUs.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: A collection of integer CPU numbers to set the uncore frequency for.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency.
        """

        self._set_freq_cpus(freq, "min", cpus)

    def set_max_freq_cpus(self, freq: int, cpus: AbsNumsType):
        """
        Set the maximum uncore frequency for the dies corresponding to the specified CPUs.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: A collection of integer CPU numbers to set the uncore frequency for.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If max. uncore frequency is less than min. uncore frequency.
        """

        self._set_freq_cpus(freq, "max", cpus)

    def _set_elc_zone_freq_cpus(self,
                                freq: int,
                                ztype: ELCZoneType,
                                ftype: FreqValueType,
                                cpus: AbsNumsType):
        """
        Set the specified ELC zone uncore frequency to 'freq' for dies corresponding to the
        specified CPUs.

        Args:
            freq: The frequency value to set, in Hz.
            ztype: The type of ELC zone (e.g., "low").
            ftype: The ELC zone uncore frequency value type (e.g., "min" for ELC zone minimum
                   uncore frequency).
            cpus: A collection of integer CPU numbers to set the ELC zone uncore frequency for.
        """

        set_dies_cache: dict[int, set[int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in set_dies_cache:
                if die in set_dies_cache[package]:
                    continue
            else:
                set_dies_cache[package] = set()

            set_dies_cache[package].add(die)
            self._set_elc_zone_freq_dies(freq, ztype, ftype, {package: [die]})

    def set_elc_low_zone_min_freq_cpus(self, freq: int, cpus: AbsNumsType):
        """
        Set ELC low zone minimum uncore frequency to 'freq' for dies corresponding to the specified
        CPUs.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: A collection of integer CPU numbers to set the ELC zone uncore frequency for.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_elc_zone_freq_cpus(freq, "low", "min", cpus)

    def set_elc_mid_zone_min_freq_cpus(self, freq: int, cpus: AbsNumsType):
        """
        Set ELC middle zone minimum uncore frequency to 'freq' for dies corresponding to the
        specified CPUs.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: A collection of integer CPU numbers to set the ELC zone uncore frequency for.

        Raises:
            ErrorNotSupported: If the uncore frequency operation is not supported.
        """

        self._set_elc_zone_freq_cpus(freq, "mid", "min", cpus)

    def _get_elc_threshold_dies(self,
                                thrtype: ELCThresholdType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield ELC threshold for each die in the provided packages->dies mapping.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC threshold.

        Yields:
            Tuple (package, die, value), where 'value' is the ELC threshold value.

        Raises:
            ErrorNotSupported: If the ELC threshold operation is not supported.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def get_elc_low_threshold_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int],
                                                                               None, None]:
        """
        Retrieve and yield the ELC low threshold for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC low threshold.

        Yields:
            Tuples of (package, die, threshold), where 'threshold' is the ELC low threshold value
            for the specified die in the specified package.

        Raises:
            ErrorNotSupported: If the ELC low threshold operation is not supported.
        """

        yield from self._get_elc_threshold_dies("low", dies)

    def get_elc_high_threshold_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int],
                                                                                None, None]:
        """
        Retrieve and yield the ELC high threshold for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC high threshold.

        Yields:
            Tuples of (package, die, threshold), where 'threshold' is the ELC high threshold value
            for the specified die in the specified package.

        Raises:
            ErrorNotSupported: If the ELC high threshold operation is not supported.
        """

        yield from self._get_elc_threshold_dies("high", dies)

    def _get_elc_threshold_status_dies(self,
                                       thrtype: ELCThresholdType,
                                       dies: RelNumsType) -> Generator[tuple[int, int, bool],
                                                                       None, None]:
        """
        Retrieve and yield ELC threshold enabled/disabled statuses for each die in the provided
        packages->dies mapping.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC threshold.

        Yields:
            Tuple (package, die, status), where 'status' is the ELC threshold enabled/disabled
            status.

        Raises:
            ErrorNotSupported: If the ELC threshold operation is not supported.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def get_elc_high_threshold_status_dies(self,
                                           dies: RelNumsType) -> Generator[tuple[int, int, bool],
                                                                           None, None]:
        """
        Retrieve and yield the ELC high threshold enabled/disabled status for each die in the
        provided packages->dies mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the ELC high threshold status.

        Yields:
            Tuples of (package, die, status), where 'status' is the ELC high threshold
            enabled/disabled status for the specified die in the specified package.

        Raises:
            ErrorNotSupported: If the ELC high threshold status operation is not supported.
        """

        yield from self._get_elc_threshold_status_dies("high", dies)

    def _validate_elc_threshold(self,
                                threshold: int,
                                thrtype: ELCThresholdType,
                                package: int,
                                die: int):
        """
        Validate that an ELC threshold value is within the acceptable range.

        Args:
            threshold: The ELC threshold value to validate.
            thrtype: The type of ELC threshold ("low" or "high").
            package: Package number to validate the threshold for.
            die: Die number to validate the threshold for.

        Raises:
            ErrorOutOfRange: If the ELC threshold value is outside the allowed range.
            ErrorBadOrder: If ELC low threshold is greater than ELC high threshold.
        """

        if threshold < 0 or threshold > 100:
            raise ErrorOutOfRange(f"Bad {thrtype} ELC threshold value '{threshold}', must be "
                                  f"between 0 and 100")

        if thrtype == "low":
            for _, _, high_threshold in self._get_elc_threshold_dies("high", {package: [die]}):
                if threshold > high_threshold:
                    raise ErrorBadOrder(f"Cannot set the ELC low threshold to "
                                        f"{threshold}%{self._pman.hostmsg}: it is higher than the "
                                        f"currently configured high threshold of {high_threshold}%")
                break
        elif thrtype == "high":
            for _, _, low_threshold in self._get_elc_threshold_dies("low", {package: [die]}):
                if threshold < low_threshold:
                    raise ErrorBadOrder(f"Cannot set the ELC high threshold to "
                                        f"{threshold}%{self._pman.hostmsg}: it is lower than the "
                                        f"currently configured low threshold of {low_threshold}%")
                break
        else:
            raise Error(f"BUG: bad ELC threshold type '{thrtype}'")

    def _set_elc_threshold_dies(self,
                                threshold: int,
                                thrtype: ELCThresholdType,
                                dies: RelNumsType):
        """
        Set the ELC threshold for each die in the provided packages->dies mapping.

        Args:
            threshold: The ELC low threshold value to set, representing aggregate CPU utilization
                       as a percentage.
            thrtype: The type of ELC threshold ("low" or "high").
            dies: Dictionary mapping package numbers to die numbers.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def set_elc_low_threshold_dies(self, threshold: int, dies: RelNumsType):
        """
        Set the ELC low threshold for each die in the specified packages->dies mapping.

        Args:
            threshold: The ELC low threshold value to set, representing aggregate CPU utilization
                       as a percentage.
            dies: Dictionary mapping package numbers to sequences of die numbers.

        Raises:
            ErrorNotSupported: If setting the ELC low threshold is not supported.
        """

        self._set_elc_threshold_dies(threshold, "low", dies)

    def set_elc_high_threshold_dies(self, threshold: int, dies: RelNumsType):
        """
        Set the ELC high threshold for each die in the specified packages->dies mapping.

        Args:
            threshold: The ELC high threshold value to set, representing aggregate CPU utilization
                       as a percentage.
            dies: Dictionary mapping package numbers to sequences of die numbers.

        Raises:
            ErrorNotSupported: If setting the ELC high threshold is not supported.
        """

        self._set_elc_threshold_dies(threshold, "high", dies)

    def _set_elc_threshold_status_dies(self,
                                       status: bool,
                                       thrtype: ELCThresholdType,
                                       dies: RelNumsType):
        """
        Set the ELC threshold enabled/disable status for each die in the provided packages->dies
        mapping.

        Args:
            status: The ELC high threshold enabled/disabled status to set.
            thrtype: The type of ELC threshold ("low" or "high").
            dies: Dictionary mapping package numbers to die numbers.
        """

        raise NotImplementedError("BUG: The sub-class must implement this method")

    def set_elc_high_threshold_status_dies(self, status: bool, dies: RelNumsType):
        """
        Set the ELC high threshold enabled/disabled status for each die in the specified
        packages->dies mapping.

        Args:
            status: The ELC high threshold enabled/disabled status to set.
            dies: Dictionary mapping package numbers to sequences of die numbers.

        Raises:
            ErrorNotSupported: If setting the ELC high threshold status is not supported.
        """

        self._set_elc_threshold_status_dies(status, "high", dies)

    def _get_elc_threshold_cpus(self,
                                thrtype: ELCThresholdType,
                                cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield an ELC threshold value for each CPU in the provided collection of CPU numbers.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            cpus: A collection of integer CPU numbers to read the ELC threshold for.

        Yields:
            tuple: A tuple (cpu, threshold) for each CPU in 'cpus'.
        """

        threshold_cache: dict[int, dict[int, int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in threshold_cache:
                if die in threshold_cache[package]:
                    yield cpu, threshold_cache[package][die]
                    continue
            else:
                threshold_cache[package] = {}

            for _, _, threshold in self._get_elc_threshold_dies(thrtype, {package: [die]}):
                threshold_cache[package][die] = threshold
                yield cpu, threshold
                break

    def get_elc_low_threshold_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int],
                                                                         None, None]:
        """
        Retrieve and yield the ELC low threshold for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the ELC low threshold for.

        Yields:
            Tuple (cpu, value), where 'value' is the ELC low threshold for the die corresponding to
            'cpu'.

        Raises:
            ErrorNotSupported: If the ELC low threshold operation is not supported.
        """

        yield from self._get_elc_threshold_cpus("low", cpus)

    def get_elc_high_threshold_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int],
                                                                         None, None]:
        """
        Retrieve and yield the ELC high threshold for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the ELC high threshold for.

        Yields:
            Tuple (cpu, value), where 'value' is the ELC high threshold for the die corresponding to
            'cpu'.

        Raises:
            ErrorNotSupported: If the ELC high threshold operation is not supported.
        """

        yield from self._get_elc_threshold_cpus("high", cpus)

    def _get_elc_threshold_status_cpus(self,
                                       thrtype: ELCThresholdType,
                                       cpus: AbsNumsType) -> Generator[tuple[int, bool],
                                                                       None, None]:
        """
        Yield an ELC threshold enabled/disabled status value for each CPU in the provided collection
        of CPU numbers.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            cpus: A collection of integer CPU numbers to read the ELC threshold status for.

        Yields:
            tuple: A tuple (cpu, status) for each CPU in 'cpus'.
        """

        threshold_cache: dict[int, dict[int, bool]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in threshold_cache:
                if die in threshold_cache[package]:
                    yield cpu, threshold_cache[package][die]
                    continue
            else:
                threshold_cache[package] = {}

            for _, _, threshold in self._get_elc_threshold_status_dies(thrtype, {package: [die]}):
                threshold_cache[package][die] = threshold
                yield cpu, threshold
                break

    def get_elc_high_threshold_status_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, bool],
                                                                                 None, None]:
        """
        Retrieve and yield the ELC high threshold enabled/disabled status for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the ELC high threshold status for.

        Yields:
            Tuple (cpu, status), where 'status' is the ELC high threshold status for the die
            corresponding to 'cpu'.

        Raises:
            ErrorNotSupported: If the ELC high threshold status operation is not supported.
        """

        yield from self._get_elc_threshold_status_cpus("high", cpus)

    def _set_elc_threshold_cpus(self,
                                threshold: int,
                                thrtype: ELCThresholdType,
                                cpus: AbsNumsType):
        """
        Set the ELC threshold for each die corresponding to the specified CPUs.

        Args:
            threshold: The ELC threshold value to set, representing aggregate CPU utilization
                       as a percentage.
            thrtype: The type of ELC threshold ("low" or "high").
            cpus: A collection of integer CPU numbers to set the ELC threshold for.
        """

        set_dies_cache: dict[int, set[int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in set_dies_cache:
                if die in set_dies_cache[package]:
                    continue
            else:
                set_dies_cache[package] = set()

            set_dies_cache[package].add(die)

            self._set_elc_threshold_dies(threshold, thrtype, {package: [die]})

    def set_elc_low_threshold_cpus(self, threshold: int, cpus: AbsNumsType):
        """
        Set ELC low threshold for the dies corresponding to the specified CPUs.

        Args:
            threshold: The ELC low threshold value to set.
            cpus: A collection of integer CPU numbers to set the ELC low threshold for.

        Raises:
            ErrorNotSupported: If the ELC low threshold operation is not supported.
            ErrorOutOfRange: If the ELC low threshold value is outside the allowed range.
            ErrorBadOrder: If ELC low threshold is greater than ELC high threshold.
        """

        self._set_elc_threshold_cpus(threshold, "low", cpus)

    def set_elc_high_threshold_cpus(self, threshold: int, cpus: AbsNumsType):
        """
        Set ELC high threshold for the dies corresponding to the specified CPUs.

        Args:
            threshold: The ELC high threshold value to set.
            cpus: A collection of integer CPU numbers to set the ELC high threshold for.

        Raises:
            ErrorNotSupported: If the ELC high threshold operation is not supported.
            ErrorOutOfRange: If the ELC high threshold value is outside the allowed range.
            ErrorBadOrder: If ELC high threshold is less than ELC low threshold.
        """

        self._set_elc_threshold_cpus(threshold, "high", cpus)

    def _set_elc_threshold_status_cpus(self,
                                       status: bool,
                                       thrtype: ELCThresholdType,
                                       cpus: AbsNumsType):
        """
        Set the ELC threshold enabled/disabled status for each die corresponding to the specified
        CPUs.

        Args:
            status: The ELC threshold status to set.
            thrtype: The type of ELC threshold ("low" or "high").
            cpus: A collection of integer CPU numbers to set the ELC threshold status for.
        """

        set_dies_cache: dict[int, set[int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in set_dies_cache:
                if die in set_dies_cache[package]:
                    continue
            else:
                set_dies_cache[package] = set()

            set_dies_cache[package].add(die)

            self._set_elc_threshold_status_dies(status, thrtype, {package: [die]})

    def set_elc_high_threshold_status_cpus(self, status: bool, cpus: AbsNumsType):
        """
        Set ELC high threshold enabled/disabled status for the dies corresponding to the specified
        CPUs.

        Args:
            status: The ELC high threshold status to set.
            cpus: A collection of integer CPU numbers to set the ELC high threshold status for.

        Raises:
            ErrorNotSupported: If the ELC high threshold status operation is not supported.
        """

        self._set_elc_threshold_status_cpus(status, "high", cpus)

    def _fill_dies_info(self, dies_info: dict[int, dict[int, UncoreDieInfoTypedDict]]):
        """
        Fill in the dies information dictionary.

        Args:
            dies_info: The dies information dictionary to fill in.
        """

    def get_dies_info(self, dies: RelNumsType) -> dict[int, dict[int, UncoreDieInfoTypedDict]]:
        """
        Return information about the specified dies.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers to retrieve
                  information for.

        Returns:
            The dies information dictionary: {package: {die: DieInfoTypedDict}}.
        """

        all_dies_info = self._cpuinfo.get_all_dies_info()
        dies_info: dict[int, dict[int, UncoreDieInfoTypedDict]] = {}

        for package, pkg_dies in dies.items():
            dies_info.setdefault(package, {})
            for die in pkg_dies:
                if package not in all_dies_info:
                    raise Error(f"Package {package} does not exist{self._pman.hostmsg}")
                if die not in all_dies_info[package]:
                    raise Error(f"Package {package} die {die} does not exist{self._pman.hostmsg}")

                info = all_dies_info[package][die]
                dies_info[package][die] = {
                    "title": info["title"],
                    "path": None,
                    "addr": info["addr"],
                    "instance": info["instance"],
                    "cluster": info["cluster"],
                }

        self._fill_dies_info(dies_info)
        return dies_info
