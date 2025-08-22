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
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorOutOfRange, ErrorBadOrder

# An uncore frequency type. Possible values:
#   - "min": a minimum uncore frequency
#   - "max": a maximum uncore frequency
#   - "current": a current uncore frequency
FreqValueType = Literal["min", "max", "current"]

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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
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

        what = f"{ftype} uncore frequency"
        if limit:
            what += " limit"

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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
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
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        self._set_freq_cpus(freq, "max", cpus)
