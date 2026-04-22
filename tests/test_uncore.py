#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test for the 'Uncore' module.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import _Common, _PropsCommon
from pepclibs import CPUInfo, Uncore
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator
    from tests._PropsCommon import PropsTestParamsTypedDict

@pytest.fixture(name="params", scope="module", params=_PropsCommon.get_enable_cache_param())
def get_params(hostspec: str,
               username: str,
               request: pytest.FixtureRequest) -> Generator[PropsTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.
        request: The pytest fixture request object.

    Yields:
        A dictionary with test parameters.
    """

    enable_cache = request.param

    with _Common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Uncore.Uncore(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = _Common.build_params(pman)
        yield _PropsCommon.extend_params(params, pobj, cpuinfo)

def _get_set_and_verify_data() -> Generator[tuple[str, str | int], None, None]:
    """
    Yield property name and value pairs running various tests for the property and the value.

    Yields:
        tuple: A pair containing the property name and the value to run a test with.
    """

    yield "min_freq", "min"
    yield "max_freq", "min"
    yield "max_freq", "max"
    yield "min_freq", "max"

    yield "min_freq", "min"
    yield "elc_low_zone_min_freq", "min"
    yield "elc_low_zone_min_freq", "max"
    yield "min_freq", "max"

    yield "elc_high_threshold_status", "off"

    yield "elc_low_threshold", 0
    yield "elc_high_threshold", 100

    yield "elc_high_threshold_status", "on"

    yield "elc_low_threshold", 80
    yield "elc_high_threshold", 81

    yield "elc_low_threshold", 10
    yield "elc_high_threshold", 90

    # Reset frequencies to safe state for subsequent tests to avoid leaving min_freq at maximum
    # which would cause validation failures when trying to lower max_freq.
    yield "min_freq", "min"
    yield "max_freq", "max"

def test_uncore_set_and_verify(params: PropsTestParamsTypedDict):
    """
    Verify that 'get_prop_cpus()' returns the same values as set by 'set_prop_cpus()'.

    Args:
        params: The test parameters.
    """

    props_vals = _get_set_and_verify_data()
    _PropsCommon.set_and_verify(params, props_vals, 0)

def test_uncore_get_all_props(params: PropsTestParamsTypedDict):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Args:
        params: The test parameters.
    """

    _PropsCommon.verify_get_all_props(params, 0)

def test_uncore_set_props_mechanisms_bool(params: PropsTestParamsTypedDict):
    """
    Verify correct behavior of 'get_prop_cpus()' when using the 'mname' argument for boolean
    properties.

    Args:
        params: The test parameters.
    """

    _PropsCommon.verify_set_bool_props(params, 0)

def test_uncore_set_prop_cpus(params: PropsTestParamsTypedDict):
    """
    Test the 'set_prop_cpus()' method for uncore properties.

    Uncore properties are die-scoped. The 'set_prop_cpus()' method translates CPU numbers to die
    numbers. This test verifies that the translation works correctly and that properties can be set
    and retrieved using CPU numbers.

    Args:
        params: The test parameters.
    """

    pobj = params["pobj"]
    cpuinfo = params["cpuinfo"]
    packages = cpuinfo.get_packages()

    if not packages:
        return

    pkg = packages[0]
    dies = cpuinfo.get_all_package_dies(pkg)

    if not dies:
        return

    die = dies[0]
    die_cpus = cpuinfo.dies_to_cpus(dies=[die], packages=[pkg])

    if not die_cpus or not pobj.prop_is_supported_cpu("max_freq", die_cpus[0]):
        return

    # Get the current max frequency for this die
    orig_val = pobj.get_cpu_prop("max_freq", die_cpus[0])["val"]

    # Get the limits to determine a safe value to set
    try:
        min_limit = pobj.get_cpu_prop("min_freq_limit", die_cpus[0])["val"]
        max_limit = pobj.get_cpu_prop("max_freq_limit", die_cpus[0])["val"]
    except ErrorNotSupported:
        return

    # Set max_freq using CPU numbers (all CPUs from the die)
    test_val = "max"
    pobj.set_prop_cpus("max_freq", test_val, cpus=die_cpus)

    # Verify the value was set correctly by reading it back.
    for cpu in die_cpus:
        result = pobj.get_cpu_prop("max_freq", cpu)
        assert result["val"] == max_limit, \
            f"Expected max_freq={max_limit} for CPU {cpu}, got {result['val']}"

    # Set back to a different value using a subset of CPUs (should still work for
    # complete die).
    test_val = "min"
    pobj.set_prop_cpus("max_freq", test_val, cpus=die_cpus)

    # Verify again.
    for cpu in die_cpus:
        result = pobj.get_cpu_prop("max_freq", cpu)
        assert result["val"] == min_limit, \
            f"Expected max_freq={min_limit} for CPU {cpu}, got {result['val']}"

    # Restore original value.
    pobj.set_prop_cpus("max_freq", orig_val, cpus=die_cpus)

    # Test that incomplete die (single CPU) is rejected by validation.
    try:
        pobj.set_prop_cpus("max_freq", "max", cpus=[die_cpus[0]])
        assert False, "Expected Error when calling set_prop_cpus() with incomplete die " \
                      "(single CPU)"
    except Error as err:
        # Expected - validation should reject incomplete die.
        assert "must include all CPUs" in str(err), \
               f"Expected validation error about complete dies, got: {err}"

    # Test that incomplete die (partial CPUs) is rejected by validation.
    if len(die_cpus) > 2:
        try:
            pobj.set_prop_cpus("max_freq", "max", cpus=die_cpus[:2])
            assert False, "Expected Error when calling set_prop_cpus() with incomplete " \
                          "die (partial CPUs)"
        except Error as err:
            # Expected - validation should reject incomplete die.
            assert "must include all CPUs" in str(err), \
                   f"Expected validation error about complete dies, got: {err}"
