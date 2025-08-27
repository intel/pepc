# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test the for the '_UncoreFreqSysfs' and '_UncoreFreqTpmi' modules.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

from typing import cast, Literal, Union, Generator
import pytest
import common
from common import CommonTestParamsTypedDict
from pepclibs import CPUInfo, _UncoreFreqSysfs, _UncoreFreqTpmi
from pepclibs.CPUInfo import RelNumsType
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder, ErrorNotSupported, ErrorOutOfRange

_UncoreFreqObjType = Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]

class TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
    """
    The test parameters dictionary.

    Attributes:
        cpuinfo: A 'CPUInfo.CPUInfo' object describing the CPU of the SUT.
        mechanism: The uncore frequency mechanism being tested.
        uncfreq_obj: The uncore frequency object being tested.
        cache_enabled: Whether the caching is enabled for 'uncfreq_obj'.
    """

    cpuinfo: CPUInfo.CPUInfo
    mechanism: Literal["sysfs", "tpmi"]
    uncfreq_obj: _UncoreFreqObjType
    cache_enabled: bool

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required 'CPUInfo' tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)
        params = cast(TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo
        yield params

def _iter_uncore_freq_objects(params: TestParamsTypedDict) -> Generator[_UncoreFreqObjType,
                                                                        None, None]:
    """
    Yield uncore frequency objects to test.

    Args:
        params: The test parameters.

    Yields:
        The uncore frequency objects to test.
    """

    uncfreq_obj: _UncoreFreqObjType

    for enable_cache in (True, False):
        try:
            with _UncoreFreqSysfs.UncoreFreqSysfs(pman=params["pman"],
                                                  cpuinfo=params["cpuinfo"],
                                                  enable_cache=enable_cache) as uncfreq_obj:
                yield uncfreq_obj
        except ErrorNotSupported:
            break

    try:
        with _UncoreFreqTpmi.UncoreFreqTpmi(pman=params["pman"],
                                            cpuinfo=params["cpuinfo"]) as uncfreq_obj:
            yield uncfreq_obj
    except ErrorNotSupported:
        return

def _test_freq_get_set_die_good(uncfreq_obj: _UncoreFreqObjType, all_dies: RelNumsType):
    """
    Test the per-die min/max uncore frequency get/set methods of an uncore frequency object. Use
    good input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        all_dies: The dictionary mapping all available packages to their dies.
    """

    min_freq_iter = uncfreq_obj.get_min_freq_dies(all_dies)
    max_freq_iter = uncfreq_obj.get_max_freq_dies(all_dies)

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    for (package, die, min_freq), (_, _, max_freq) in zip(min_freq_iter, max_freq_iter):
        # Calculate the middle uncore frequency value.
        mid_freq = (min_freq + max_freq) // 2
        # Round it up to 100MHz.
        round_hz = 100_000_000
        mid_freq = (mid_freq + round_hz - 1) // round_hz * round_hz

        # Set the min uncore frequency to the middle value and check it.
        uncfreq_obj.set_uncore_low_freq_dies(mid_freq, {package: [die]})
        read_pkg, read_die, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_pkg == package and read_die == die and read_freq == mid_freq, \
               f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
               f"{read_freq})\n{errmsg_suffix}"

        # Restore the original min uncore frequency.
        uncfreq_obj.set_uncore_low_freq_dies(min_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_freq == min_freq, f"Expected {min_freq}, but got {read_freq}\n{errmsg_suffix}"

        # Set the max uncore frequency to the middle value and check it.
        uncfreq_obj.set_max_freq_dies(mid_freq, {package: [die]})
        read_pkg, read_die, read_freq = next(uncfreq_obj.get_max_freq_dies({package: [die]}))
        assert read_pkg == package and read_die == die and read_freq == mid_freq, \
               f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
               f"{read_freq})\n{errmsg_suffix}"

        # Restore the original max uncore frequency.
        uncfreq_obj.set_max_freq_dies(max_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_max_freq_dies({package: [die]}))
        assert read_freq == max_freq, f"Expected {max_freq}, but got {read_freq}\n{errmsg_suffix}"

def _test_freq_get_set_die_bad(uncfreq_obj: _UncoreFreqObjType, all_dies: RelNumsType):
    """
    Test the per-die min/max uncore frequency get/set methods of an uncore frequency object. Use bad
    input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        all_dies: The dictionary mapping all available packages to their dies.
    """

    unc_freq_obj_sysfs: _UncoreFreqSysfs.UncoreFreqSysfs | None = None
    if uncfreq_obj.mname == "sysfs":
        unc_freq_obj_sysfs = cast(_UncoreFreqSysfs.UncoreFreqSysfs, uncfreq_obj)

    min_freq_iter = uncfreq_obj.get_min_freq_dies(all_dies)
    max_freq_iter = uncfreq_obj.get_max_freq_dies(all_dies)

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    for (package, die, min_freq), (_, _, max_freq) in zip(min_freq_iter, max_freq_iter):
        # Calculate the middle uncore frequency value.
        mid_freq = (min_freq + max_freq) // 2
        # Round it up to 100MHz.
        round_hz = 100_000_000
        mid_freq = (mid_freq + round_hz - 1) // round_hz * round_hz

        # Set the min uncore frequency to the middle value and check it.
        uncfreq_obj.set_uncore_low_freq_dies(mid_freq, {package: [die]})
        read_pkg, read_die, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_pkg == package and read_die == die and read_freq == mid_freq, \
               f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
               f"{read_freq})\n{errmsg_suffix}"

        # Set the max uncore frequency to the middle value and check it.
        uncfreq_obj.set_max_freq_dies(mid_freq, {package: [die]})
        read_pkg, read_die, read_freq = next(uncfreq_obj.get_max_freq_dies({package: [die]}))
        assert read_pkg == package and read_die == die and read_freq == mid_freq, \
               f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
               f"{read_freq})\n{errmsg_suffix}"

        # Try to set min uncore frequency to a value higher than the max frequency. This should
        # fail.
        try:
            uncfreq_obj.set_uncore_low_freq_dies(mid_freq + 100_000_000, {package: [die]})
        except ErrorBadOrder:
            pass
        else:
            raise Error(f"Expected 'ErrorBadOrder', but no exception was raised\n{errmsg_suffix}")

        # Try to set max uncore frequency to a value lower than the min frequency. This should
        # fail.
        try:
            uncfreq_obj.set_max_freq_dies(mid_freq - 100_000_000, {package: [die]})
        except ErrorBadOrder:
            pass
        else:
            raise Error(f"Expected 'ErrorBadOrder', but no exception was raised\n{errmsg_suffix}")

        # Try to set min uncore frequency to a value lower than the minimum allowed and higher than
        # the maximum allowed. This should fail.
        if unc_freq_obj_sysfs:
            *_, min_freq_limit = next(unc_freq_obj_sysfs.get_min_freq_limit_dies({package: [die]}))
            *_, max_freq_limit = next(unc_freq_obj_sysfs.get_max_freq_limit_dies({package: [die]}))
        else:
            min_freq_limit = _UncoreFreqTpmi.MIN_FREQ_LIMIT
            max_freq_limit = _UncoreFreqTpmi.MAX_FREQ_LIMIT

        try:
            try_min = min_freq_limit - 100_000_000
            uncfreq_obj.set_uncore_low_freq_dies(try_min, {package: [die]})
        except ErrorOutOfRange:
            pass
        else:
            raise Error(f"Tried to set min. uncore frequency to {try_min}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        try:
            try_max = max_freq_limit + 100_000_000
            uncfreq_obj.set_max_freq_dies(try_max, {package: [die]})
        except ErrorOutOfRange:
            pass
        else:
            raise Error(f"Tried to set max. uncore frequency to {try_max}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        # Restore the original min uncore frequency.
        uncfreq_obj.set_uncore_low_freq_dies(min_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_freq == min_freq, f"Expected {min_freq}, but got {read_freq}\n{errmsg_suffix}"

        # Restore the original max uncore frequency.
        uncfreq_obj.set_max_freq_dies(max_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_max_freq_dies({package: [die]}))
        assert read_freq == max_freq, f"Expected {max_freq}, but got {read_freq}\n{errmsg_suffix}"

def test_min_max_get_set_methods(params: TestParamsTypedDict):
    """
    Test the per-die min/max uncore frequency get/set methods for uncore frequency objects of
    different mechanisms and configurations. The tested methods are:
      - 'get_min_freq_dies()'
      - 'get_max_freq_dies()'
      - 'set_min_freq_dies()'
      - 'set_max_freq_dies()'

    Args:
        params: The test parameters.
    """

    all_dies = params["cpuinfo"].get_dies()

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        _test_freq_get_set_die_good(uncfreq_obj, all_dies)
        _test_freq_get_set_die_bad(uncfreq_obj, all_dies)

def _test_freq_get_set_cpu_good(uncfreq_obj: _UncoreFreqObjType, cpu: int):
    """
    Test the per-CPU min/max uncore frequency get/set methods of an uncore frequency object. Use
    good input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        cpu: The CPU number to test.
    """

    _, min_freq = next(uncfreq_obj.get_min_freq_cpus((cpu,)))
    _, max_freq = next(uncfreq_obj.get_max_freq_cpus((cpu,)))

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    # Calculate the middle uncore frequency value.
    mid_freq = (min_freq + max_freq) // 2
    # Round it up to 100MHz.
    round_hz = 100_000_000
    mid_freq = (mid_freq + round_hz - 1) // round_hz * round_hz

    # Set the min uncore frequency to the middle value and check it.
    uncfreq_obj.set_min_freq_cpus(mid_freq, (cpu,))
    read_cpu, read_freq = next(uncfreq_obj.get_min_freq_cpus((cpu,)))
    assert read_cpu == cpu and read_freq == mid_freq, \
            f"Expected ({cpu}, {mid_freq}), but got ({read_cpu}, {read_freq})\n{errmsg_suffix}"

    # Restore the original min uncore frequency.
    uncfreq_obj.set_min_freq_cpus(min_freq, (cpu,))
    _, read_freq = next(uncfreq_obj.get_min_freq_cpus((cpu,)))
    assert read_freq == min_freq, f"Expected {min_freq}, but got {read_freq}\n{errmsg_suffix}"

    # Set the max uncore frequency to the middle value and check it.
    uncfreq_obj.set_max_freq_cpus(mid_freq, (cpu,))
    read_cpu, read_freq = next(uncfreq_obj.get_max_freq_cpus((cpu,)))
    assert read_cpu == cpu and read_freq == mid_freq, \
            f"Expected ({cpu}, {mid_freq}), but got ({read_cpu}, {read_freq})\n{errmsg_suffix}"

    # Restore the original max uncore frequency.
    uncfreq_obj.set_max_freq_cpus(max_freq, (cpu,))
    _, read_freq = next(uncfreq_obj.get_max_freq_cpus((cpu,)))
    assert read_freq == max_freq, f"Expected {max_freq}, but got {read_freq}\n{errmsg_suffix}"

def test_min_max_get_set_cpu_methods(params: TestParamsTypedDict):
    """
    Test the per-CPU min/max uncore frequency get/set methods for uncore frequency objects of
    different mechanisms and configurations. The tested methods are:
      - 'get_min_freq_cpus()'
      - 'get_max_freq_cpus()'
      - 'set_min_freq_cpus()'
      - 'set_max_freq_cpus()'

    Args:
        params: The test parameters.
    """

    cpu = params["cpuinfo"].get_cpus()[-1]

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        _test_freq_get_set_cpu_good(uncfreq_obj, cpu)
