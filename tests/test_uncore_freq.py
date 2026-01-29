# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the public methods of the '_UncoreFreqSysfs' and '_UncoreFreqTPMI' modules."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common
from pepclibs import CPUInfo, _UncoreFreqSysfs, _UncoreFreqTPMI
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder, ErrorNotSupported, ErrorOutOfRange

if typing.TYPE_CHECKING:
    from typing import Union, Generator, cast
    from tests.common import CommonTestParamsTypedDict
    from pepclibs.CPUInfoTypes import RelNumsType

    _UncoreFreqObjType = Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTPMI.UncoreFreqTpmi]

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            ncompd: A 'NonCompDies.NonCompDies' object.
        """

        cpuinfo: CPUInfo.CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo
        yield params

def _iter_uncore_freq_objects(params: _TestParamsTypedDict) -> Generator[_UncoreFreqObjType,
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
        with _UncoreFreqTPMI.UncoreFreqTpmi(pman=params["pman"],
                                            cpuinfo=params["cpuinfo"]) as uncfreq_obj:
            yield uncfreq_obj
    except ErrorNotSupported:
        pass

def _test_freq_methods_dies_good(uncfreq_obj: _UncoreFreqObjType, all_dies: RelNumsType):
    """
    Test the per-die uncore frequency get/set methods. Use good input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        all_dies: The dictionary mapping all available packages to their dies.
    """

    try:
        for _, _, _ in uncfreq_obj.get_min_freq_limit_dies(all_dies):
            pass
        min_freq_iter = uncfreq_obj.get_min_freq_limit_dies(all_dies)
        max_freq_iter = uncfreq_obj.get_max_freq_limit_dies(all_dies)
    except ErrorNotSupported:
        # The frequency limits are not supported, use the actual frequencies instead.
        min_freq_iter = uncfreq_obj.get_min_freq_dies(all_dies)
        max_freq_iter = uncfreq_obj.get_max_freq_dies(all_dies)

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    for (package, die, min_freq), (_, _, max_freq) in zip(min_freq_iter, max_freq_iter):
        mid_freq = _get_mid_freq(min_freq, max_freq)

        # Sometimes min and max limits are equal. In this case, skip the test for this die.
        if min_freq == max_freq:
            continue

        # Set min and max frequencies to known values.
        uncfreq_obj.set_min_freq_dies(min_freq, {package: [die]})
        uncfreq_obj.set_max_freq_dies(max_freq, {package: [die]})

        # Set the min uncore frequency to the middle value and check it.
        uncfreq_obj.set_min_freq_dies(mid_freq, {package: [die]})
        read_pkg, read_die, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_pkg == package and read_die == die and read_freq == mid_freq, \
               f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
               f"{read_freq})\n{errmsg_suffix}"

        # Restore the original min uncore frequency.
        uncfreq_obj.set_min_freq_dies(min_freq, {package: [die]})
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

        try:
            # Set the ELC low zone min uncore frequency to the middle value and check it.
            uncfreq_obj.set_elc_low_zone_min_freq_dies(mid_freq, {package: [die]})
            iterator = uncfreq_obj.get_elc_low_zone_min_freq_dies({package: [die]})
            read_pkg, read_die, read_freq = next(iterator)
            assert read_pkg == package and read_die == die and read_freq == mid_freq, \
                f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
                f"{read_freq})\n{errmsg_suffix}"

            # Set the ELC middle zone min uncore frequency to the middle value and check it.
            uncfreq_obj.set_elc_mid_zone_min_freq_dies(mid_freq, {package: [die]})
            iterator = uncfreq_obj.get_elc_mid_zone_min_freq_dies({package: [die]})
            read_pkg, read_die, read_freq = next(iterator)
            assert read_pkg == package and read_die == die and read_freq == mid_freq, \
                f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
                f"{read_freq})\n{errmsg_suffix}"
        except ErrorNotSupported:
            pass

def _test_freq_methods_dies_bad(uncfreq_obj: _UncoreFreqObjType, all_dies: RelNumsType):
    """
    Test the per-die uncore frequency get/set methods. Use bad input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        all_dies: The dictionary mapping all available packages to their dies.
    """

    try:
        for _, _, _ in uncfreq_obj.get_min_freq_limit_dies(all_dies):
            pass
        min_freq_iter = uncfreq_obj.get_min_freq_limit_dies(all_dies)
        max_freq_iter = uncfreq_obj.get_max_freq_limit_dies(all_dies)
        limits_supported = True
    except ErrorNotSupported:
        # The frequency limits are not supported, use the actual frequencies instead.
        min_freq_iter = uncfreq_obj.get_min_freq_dies(all_dies)
        max_freq_iter = uncfreq_obj.get_max_freq_dies(all_dies)
        limits_supported = False

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    for (package, die, min_freq), (_, _, max_freq) in zip(min_freq_iter, max_freq_iter):
        mid_freq = _get_mid_freq(min_freq, max_freq)

        # Sometimes min and max limits are equal. In this case, skip the test for this die.
        if min_freq == max_freq:
            continue

        # Set min and max frequencies to known values.
        uncfreq_obj.set_min_freq_dies(min_freq, {package: [die]})
        uncfreq_obj.set_max_freq_dies(max_freq, {package: [die]})

        # Set the min uncore frequency to the middle value and check it.
        uncfreq_obj.set_min_freq_dies(mid_freq, {package: [die]})
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

        try:
            # Set the ELC low zone min uncore frequency to the middle value and check it.
            uncfreq_obj.set_elc_low_zone_min_freq_dies(mid_freq, {package: [die]})
            iterator = uncfreq_obj.get_elc_low_zone_min_freq_dies({package: [die]})
            read_pkg, read_die, read_freq = next(iterator)
            assert read_pkg == package and read_die == die and read_freq == mid_freq, \
                f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
                f"{read_freq})\n{errmsg_suffix}"

            # Set the ELC middle zone min uncore frequency to the middle value and check it.
            uncfreq_obj.set_elc_mid_zone_min_freq_dies(mid_freq, {package: [die]})
            iterator = uncfreq_obj.get_elc_mid_zone_min_freq_dies({package: [die]})
            read_pkg, read_die, read_freq = next(iterator)
            assert read_pkg == package and read_die == die and read_freq == mid_freq, \
                f"Expected ({package}, {die}, {mid_freq}), but got ({read_pkg}, {read_die}, " \
                f"{read_freq})\n{errmsg_suffix}"
        except ErrorNotSupported:
            pass

        # Try to set min uncore frequency to a value higher than the max frequency. This should
        # fail.
        try:
            uncfreq_obj.set_min_freq_dies(mid_freq + 100_000_000, {package: [die]})
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

        # Try to set min uncore frequency to a value lower than the minimum allowed or higher than
        # the maximum allowed. This should fail.
        if limits_supported:
            *_, min_freq_limit = next(uncfreq_obj.get_min_freq_limit_dies({package: [die]}))
            *_, max_freq_limit = next(uncfreq_obj.get_max_freq_limit_dies({package: [die]}))
        else:
            min_freq_limit = _UncoreFreqTPMI.MIN_FREQ_LIMIT
            max_freq_limit = _UncoreFreqTPMI.MAX_FREQ_LIMIT

        try:
            try_min = min_freq_limit - 100_000_000
            uncfreq_obj.set_min_freq_dies(try_min, {package: [die]})
        except ErrorOutOfRange:
            pass
        else:
            raise Error(f"Tried to set min. uncore frequency to {try_min}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        try:
            uncfreq_obj.set_elc_low_zone_min_freq_dies(try_min, {package: [die]})
        except (ErrorNotSupported, ErrorOutOfRange):
            pass
        else:
            raise Error(f"Tried to set ELC low zone min. uncore frequency to {try_min}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        try:
            uncfreq_obj.set_elc_mid_zone_min_freq_dies(try_min, {package: [die]})
        except (ErrorNotSupported, ErrorOutOfRange):
            pass
        else:
            raise Error(f"Tried to set ELC middle zone min. uncore frequency to {try_min}, "
                        f"expected 'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        try:
            try_max = max_freq_limit + 100_000_000
            uncfreq_obj.set_max_freq_dies(try_max, {package: [die]})
        except ErrorOutOfRange:
            pass
        else:
            raise Error(f"Tried to set max. uncore frequency to {try_max}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

        # Restore the original min uncore frequency.
        uncfreq_obj.set_min_freq_dies(min_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_min_freq_dies({package: [die]}))
        assert read_freq == min_freq, f"Expected {min_freq}, but got {read_freq}\n{errmsg_suffix}"

        # Restore the original max uncore frequency.
        uncfreq_obj.set_max_freq_dies(max_freq, {package: [die]})
        _, _, read_freq = next(uncfreq_obj.get_max_freq_dies({package: [die]}))
        assert read_freq == max_freq, f"Expected {max_freq}, but got {read_freq}\n{errmsg_suffix}"

def test_freq_methods_dies_good(params: _TestParamsTypedDict):
    """
    Test the per-die uncore frequency get/set methods. Use good input.

    Args:
        params: The test parameters.
    """

    all_dies = params["cpuinfo"].get_all_dies()

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        _test_freq_methods_dies_good(uncfreq_obj, all_dies)

def test_freq_methods_dies_bad(params: _TestParamsTypedDict):
    """
    Test the per-die uncore frequency get/set methods. Use bad input.

    Args:
        params: The test parameters.
    """

    all_dies = params["cpuinfo"].get_all_dies()

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        _test_freq_methods_dies_bad(uncfreq_obj, all_dies)

def _get_mid_freq(min_freq: int, max_freq: int) -> int:
    """
    Calculate the middle frequency value between 'min_freq' and 'max_freq', rounded up to 100MHz.

    Args:
        min_freq: The minimum frequency.
        max_freq: The maximum frequency.

    Returns:
        The middle frequency value rounded up to 100MHz.
    """

    if min_freq == max_freq:
        return min_freq

    mid_freq = (min_freq + max_freq) // 2
    # Round it up to 100MHz.
    round_hz = 100_000_000
    mid_freq = (mid_freq + round_hz - 1) // round_hz * round_hz
    return mid_freq

def _test_freq_methods_cpu_good(uncfreq_obj: _UncoreFreqObjType, cpu: int):
    """
    Test the per-CPU uncore frequency get/set methods. Use good input.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        cpu: The CPU number to test.
    """

    _, min_freq = next(uncfreq_obj.get_min_freq_cpus((cpu,)))
    _, max_freq = next(uncfreq_obj.get_max_freq_cpus((cpu,)))

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    mid_freq = _get_mid_freq(min_freq, max_freq)

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

    try:
        # Set the ELC low zone min uncore frequency to the middle value and check it.
        uncfreq_obj.set_elc_low_zone_min_freq_cpus(mid_freq, (cpu,))
        read_cpu, read_freq = next(uncfreq_obj.get_elc_low_zone_min_freq_cpus((cpu,)))
        assert read_cpu == cpu and read_freq == mid_freq, \
                f"Expected ({cpu}, {mid_freq}), but got ({read_cpu}, {read_freq})\n{errmsg_suffix}"

        # Set the ELC middle zone min uncore frequency to the middle value and check it.
        uncfreq_obj.set_elc_mid_zone_min_freq_cpus(mid_freq, (cpu,))
        read_cpu, read_freq = next(uncfreq_obj.get_elc_mid_zone_min_freq_cpus((cpu,)))
        assert read_cpu == cpu and read_freq == mid_freq, \
                f"Expected ({cpu}, {mid_freq}), but got ({read_cpu}, {read_freq})\n{errmsg_suffix}"
    except ErrorNotSupported:
        pass

def test_freq_methods_cpu_good(params: _TestParamsTypedDict):
    """
    Test the per-CPU uncore frequency get/set methods. Use good input.

    Args:
        params: The test parameters.
    """

    cpu = params["cpuinfo"].get_cpus()[-1]

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        _test_freq_methods_cpu_good(uncfreq_obj, cpu)

def _test_elc_threshold_methods_dies(uncfreq_obj: _UncoreFreqObjType, all_dies: RelNumsType):
    """
    Test the per-die ELC threshold get/set methods of an uncore frequency object.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        all_dies: The dictionary mapping all available packages to their dies.
    """

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    lo_thresh_iter = uncfreq_obj.get_elc_low_threshold_dies(all_dies)
    hi_thresh_iter = uncfreq_obj.get_elc_high_threshold_dies(all_dies)
    hi_thresh_status_iter = uncfreq_obj.get_elc_high_threshold_status_dies(all_dies)

    # Save current threshold values.
    saved_thresh: dict[int, dict[int, tuple[int, int, bool]]] = {}
    iterator = zip(lo_thresh_iter, hi_thresh_iter, hi_thresh_status_iter)
    for (package, die, lo_thresh), (_, _, hi_thresh), (_, _, status) in iterator:
        if package not in saved_thresh:
            saved_thresh[package] = {}
        saved_thresh[package][die] = (lo_thresh, hi_thresh, status)

    # Set low/high thresholds to new values, using unique values for each die.
    for package, dies in all_dies.items():
        for die in dies:
            # Enable the high threshold.
            val = 25 + package + die
            uncfreq_obj.set_elc_high_threshold_status_dies(bool(val % 2), {package: [die]})
            # In case high threshold happens to be lower than 'val', which would cause a failure,
            # set it to 100% first.
            uncfreq_obj.set_elc_high_threshold_dies(100, {package: [die]})
            uncfreq_obj.set_elc_low_threshold_dies(val, {package: [die]})
            uncfreq_obj.set_elc_high_threshold_dies(val + 1, {package: [die]})

    # Verify the values.
    lo_thresh_iter = uncfreq_obj.get_elc_low_threshold_dies(all_dies)
    hi_thresh_iter = uncfreq_obj.get_elc_high_threshold_dies(all_dies)
    hi_thresh_status_iter = uncfreq_obj.get_elc_high_threshold_status_dies(all_dies)
    iterator = zip(lo_thresh_iter, hi_thresh_iter, hi_thresh_status_iter)
    for (package, die, lo_thresh), (_, _, hi_thresh), (_, _, status) in iterator:
        val = 25 + package + die
        expected_lo_thresh = val
        expected_hi_thresh = val + 1
        expected_status = bool(val % 2)
        assert lo_thresh == expected_lo_thresh, \
               f"Expected ELC low threshold {expected_lo_thresh}%, but got {lo_thresh}%\n" \
               f"{errmsg_suffix}"
        assert hi_thresh == expected_hi_thresh, \
               f"Expected ELC high threshold {expected_hi_thresh}%, but got {hi_thresh}%\n" \
               f"{errmsg_suffix}"
        assert status == expected_status, \
               f"Expected ELC high threshold status {expected_status}, but got {status}\n" \
               f"{errmsg_suffix}"

    # Test setting and getting various threshold values.
    for package, dies in all_dies.items():
        for die in dies:
            for lo_thresh, hi_thresh in ((0, 0), (0, 1), (1, 1), (99, 100), (100, 100)):
                uncfreq_obj.set_elc_low_threshold_dies(0, {package: [die]})
                uncfreq_obj.set_elc_high_threshold_dies(hi_thresh, {package: [die]})
                uncfreq_obj.set_elc_low_threshold_dies(lo_thresh, {package: [die]})

                read_pkg, read_die, read_lo_thresh = \
                                    next(uncfreq_obj.get_elc_low_threshold_dies({package: [die]}))
                assert read_pkg == package and read_die == die and read_lo_thresh == lo_thresh, \
                    f"Expected ({package}, {die}, {lo_thresh}), " \
                    f"but got ({read_pkg}, {read_die}, {read_lo_thresh})\n{errmsg_suffix}"

                read_pkg, read_die, read_hi_thresh = \
                    next(uncfreq_obj.get_elc_high_threshold_dies({package: [die]}))
                assert read_pkg == package and read_die == die and read_hi_thresh == hi_thresh, \
                    f"Expected ({package}, {die}, {hi_thresh}), " \
                    f"but got ({read_pkg}, {read_die}, {read_hi_thresh})\n{errmsg_suffix}"

    # Pick the first die.
    package = die = 0
    for package, dies in all_dies.items():
        for die in dies:
            break

    # Test values that are out of range.
    for lo_thresh in -1, 101:
        try:
            uncfreq_obj.set_elc_low_threshold_dies(lo_thresh, {package: [die]})
        except ErrorOutOfRange:
            pass
        else:
            raise Error(f"Tried to set ELC lo threshold to {lo_thresh}, expected "
                        f"'ErrorOutOfRange', but no exception was raised\n{errmsg_suffix}")

    # Test setting low/high thresholds to values that violate the ordering requirement.
    uncfreq_obj.set_elc_low_threshold_dies(0, {package: [die]})
    uncfreq_obj.set_elc_high_threshold_dies(50, {package: [die]})

    try:
        uncfreq_obj.set_elc_low_threshold_dies(51, {package: [die]})
    except ErrorBadOrder:
        pass
    else:
        raise Error(f"Expected 'ErrorBadOrder', but no exception was raised\n{errmsg_suffix}")

    uncfreq_obj.set_elc_low_threshold_dies(50, {package: [die]})

    try:
        uncfreq_obj.set_elc_high_threshold_dies(49, {package: [die]})
    except ErrorBadOrder:
        pass
    else:
        raise Error(f"Expected 'ErrorBadOrder', but no exception was raised\n{errmsg_suffix}")

    # Restore saved thresholds.
    for package, info in saved_thresh.items():
        for die, (lo_thresh, hi_thresh, status) in info.items():
            uncfreq_obj.set_elc_low_threshold_dies(0, {package: [die]})
            uncfreq_obj.set_elc_high_threshold_dies(hi_thresh, {package: [die]})
            uncfreq_obj.set_elc_low_threshold_dies(lo_thresh, {package: [die]})
            uncfreq_obj.set_elc_high_threshold_status_dies(status, {package: [die]})

def test_elc_threshold_methods_dies(params: _TestParamsTypedDict):
    """
    Test the per-die ELC threshold get/set methods for uncore frequency objects of different
    mechanisms and configurations. Use good input. The tested methods are:
      - 'get_elc_low_threshold_dies()'
      - 'get_elc_high_threshold_dies()'
      - 'set_elc_low_threshold_dies()'
      - 'set_elc_high_threshold_dies()'

    Args:
        params: The test parameters.
    """

    all_dies = params["cpuinfo"].get_all_dies()

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        if uncfreq_obj.mname != "tpmi":
            continue

        _test_elc_threshold_methods_dies(uncfreq_obj, all_dies)

def _test_elc_threshold_methods_cpu(uncfreq_obj: _UncoreFreqObjType, cpu: int):
    """
    Test the per-CPU ELC threshold get/set methods of an uncore frequency object.

    Args:
        uncfreq_obj: The uncore frequency object to test.
        cpu: The CPU to test.
    """

    errmsg_suffix = f"Mechanism: {uncfreq_obj.mname}, cache enabled: {uncfreq_obj.cache_enabled}"

    # Save thresholds.
    _, saved_lo_thresh = next(uncfreq_obj.get_elc_low_threshold_cpus((cpu,)))
    _, saved_hi_thresh = next(uncfreq_obj.get_elc_high_threshold_cpus((cpu,)))

    uncfreq_obj.set_elc_low_threshold_cpus(0, (cpu,))
    uncfreq_obj.set_elc_high_threshold_cpus(50, (cpu,))
    uncfreq_obj.set_elc_low_threshold_cpus(20, (cpu,))

    _, lo_thresh = next(uncfreq_obj.get_elc_low_threshold_cpus((cpu,)))
    assert lo_thresh == 20, f"Expected ELC low threshold 20%, but got {lo_thresh}%\n{errmsg_suffix}"

    _, hi_thresh = next(uncfreq_obj.get_elc_high_threshold_cpus((cpu,)))
    assert hi_thresh == 50, f"Expected ELC high threshold 50%, but got {hi_thresh}%\n" \
                            f"{errmsg_suffix}"

    # Restore saved thresholds.
    uncfreq_obj.set_elc_low_threshold_cpus(0, (cpu,))
    uncfreq_obj.set_elc_high_threshold_cpus(saved_hi_thresh, (cpu,))
    uncfreq_obj.set_elc_low_threshold_cpus(saved_lo_thresh, (cpu,))

def test_elc_threshold_methods_cpu(params: _TestParamsTypedDict):
    """
    Test the per-CPU ELC threshold get/set methods for uncore frequency objects of different
    mechanisms and configurations. Use good input. The tested methods are:
      - 'get_elc_low_threshold_cpus()'
      - 'get_elc_high_threshold_cpus()'
      - 'set_elc_low_threshold_cpus()'
      - 'set_elc_high_threshold_cpus()'

    Args:
        params: The test parameters.
    """

    cpu = params["cpuinfo"].get_cpus()[-1]

    for uncfreq_obj in _iter_uncore_freq_objects(params):
        if uncfreq_obj.mname != "tpmi":
            continue

        _test_elc_threshold_methods_cpu(uncfreq_obj, cpu)
