# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide the base class for uncore frequency management classes.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import Literal, Generator
from pepclibs import CPUInfo
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.CPUInfo import AbsNumsType, RelNumsType
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Human
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorOutOfRange, ErrorBadOrder, Error

# An uncore frequency type. Possible values:
#   - "min": Minimum uncore frequency
#   - "max": Maximum uncore frequency
#   - "current": Current uncore frequency
FreqValueType = Literal["min", "max", "current"]

# The ELC threshold type.
#   - "low": Low ELC threshold
#   - "high": High ELC threshold
ELCThresholdType = Literal["low", "high"]

class UncoreFreqBase(ClassHelpers.SimpleCloseContext):
    """
    Provide the base class for uncore frequency management classes.
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

        vendor = self._cpuinfo.info["vendor"]
        if vendor != "GenuineIntel":
            raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor}'{self._pman.hostmsg}\nOnly"
                                    f"Intel CPU uncore frequency control is currently supported")

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

            _, _, freq = next(self._get_freq_dies(ftype, {package: [die]}, limit=limit))
            freq_cache[package][die] = freq
            yield cpu, freq

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

    def _validate_frequency(self,
                            freq: int,
                            ftype: FreqValueType,
                            package: int,
                            die: int,
                            min_freq_limit: int,
                            max_freq_limit: int,
                            min_freq: int | None = None,
                            max_freq: int | None = None):
        """
        Validate that a frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.
            min_freq_limit: The minimum uncore frequency limit in Hz.
            max_freq_limit: The maximum uncore frequency limit in Hz.
            min_freq: The minimum uncore frequency in Hz.
            max_freq: The maximum uncore frequency in Hz.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        if freq < min_freq_limit or freq > max_freq_limit:
            name = f"{ftype} package {package} die {die} uncore frequency"
            freq_str = Human.num2si(freq, unit="Hz", decp=4)
            min_limit_str = Human.num2si(min_freq_limit, unit="Hz", decp=4)
            max_limit_str = Human.num2si(max_freq_limit, unit="Hz", decp=4)
            raise ErrorOutOfRange(f"{name} value of '{freq_str}' is out of range, must be within "
                                  f"[{min_limit_str},{max_limit_str}]")

        if ftype == "min":
            assert max_freq is not None
            if freq > max_freq:
                name = f"{ftype} package {package} die {die} uncore frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                max_freq_str = Human.num2si(max_freq, unit="Hz", decp=4)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is greater than the currently "
                                    f"configured max frequency of {max_freq_str}")
        else:
            assert min_freq is not None
            if freq < min_freq:
                name = f"{ftype} package {package} die {die} uncore frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                min_freq_str = Human.num2si(min_freq, unit="Hz", decp=4)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is less than the currently "
                                    f"configured min frequency of {min_freq_str}")

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
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
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
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        self._set_freq_cpus(freq, "max", cpus)

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

        The ELC low threshold defines the aggregate CPU utilization percentage. When utilization
        falls below this threshold, the platform sets the uncore frequency floor to the low ELC
        frequency (subject to the global minimum uncore frequency limit - if the limit is higher
        than the low ELC frequency, the limit is used as the floor instead).

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

        The ELC high threshold defines the aggregate CPU utilization percentage at which the
        platform begins increasing the uncore frequency more enthusiastically than before. When
        utilization exceeds this threshold, the platform gradually raises the uncore frequency until
        utilization drops below the threshold or the frequency reaches its maximum limit. Further
        increases may be prevented by other constraints, such as thermal or power limits.

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
            ErrorBadOrder: If min. ELC threshold is greater than max. ELC threshold and vice
                           versa.
        """

        if threshold < 0 or threshold > 100:
            raise ErrorOutOfRange(f"Bad {thrtype} ELC threshold value '{threshold}', must be "
                                  f"between 0 and 100")

        if thrtype == "low":
            _, _, high_threshold = next(self._get_elc_threshold_dies("high", {package: [die]}))
            if threshold > high_threshold:
                raise ErrorBadOrder(f"Cannot set the ELC low threshold to {threshold}%: it is "
                                    f"higher than the currently configured high threshold of "
                                    f"{high_threshold}%")
        elif thrtype == "high":
            _, _, low_threshold = next(self._get_elc_threshold_dies("low", {package: [die]}))
            if threshold < low_threshold:
                raise ErrorBadOrder(f"Cannot set the ELC high threshold to {threshold}%: it is "
                                    f"lower than the currently configured low threshold of "
                                    f"{low_threshold}%")
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

        thrashold_cache: dict[int, dict[int, int]] = {}

        for cpu in cpus:
            tline = self._cpuinfo.get_tline_by_cpu(cpu, snames=("package", "die"))
            package = tline["package"]
            die = tline["die"]

            if package in thrashold_cache:
                if die in thrashold_cache[package]:
                    yield cpu, thrashold_cache[package][die]
                    continue
            else:
                thrashold_cache[package] = {}

            _, _, threshold = next(self._get_elc_threshold_dies(thrtype, {package: [die]}))
            thrashold_cache[package][die] = threshold
            yield cpu, threshold

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
            ErrorBadOrder: If min. ELC low threshold is greater than ELC high threshold and vice
                           versa.
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
            ErrorOutOfRange: If the ELC high threshold value is outside the alhighed range.
            ErrorBadOrder: If min. ELC high threshold is greater than ELC high threshold and vice
                           versa.
        """

        self._set_elc_threshold_cpus(threshold, "high", cpus)
