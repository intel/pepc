#!/usr/bin/env python3
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

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
import common
import props_common
from pepclibs import CPUInfo, Uncore

if typing.TYPE_CHECKING:
    from typing import Generator
    from props_common import PropsTestParamsTypedDict

@pytest.fixture(name="params", scope="module", params=props_common.get_enable_cache_param())
def get_params(hostspec: str,
               request: pytest.FixtureRequest) -> Generator[PropsTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required 'CPUInfo' tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.

    Yields:
        A dictionary with test parameters.
    """

    enable_cache = request.param

    with common.get_pman(hostspec) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Uncore.Uncore(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = common.build_params(pman)
        yield props_common.extend_params(params, pobj, cpuinfo)

def _get_set_and_verify_data(params: PropsTestParamsTypedDict,
                             cpu: int) -> Generator[tuple[str, str | int], None, None]:
    """
    Yield property name and value pairs running various tests for the property and the value.

    Args:
        params: Dictionary containing test parameters and objects required for property retrieval.
        cpu: CPU to test property with.

    Yields:
        tuple: A pair containing the property name and the value to run a test with.
    """

    pobj = params["pobj"]

    min_limit = pobj.get_cpu_prop("min_freq_limit", cpu)["val"]
    max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]
    if min_limit is not None or max_limit is not None:
        yield "min_freq", "min"
        yield "max_freq", "min"

        yield "max_freq", "max"
        yield "min_freq", "max"

    yield "elc_high_threshold_status", "off"

    yield "elc_low_threshold", 0
    yield "elc_high_threshold", 100

    yield "elc_high_threshold_status", "on"

    yield "elc_low_threshold", 80
    yield "elc_high_threshold", 81

    yield "elc_low_threshold", 10
    yield "elc_high_threshold", 90

def test_uncore_set_and_verify(params: PropsTestParamsTypedDict):
    """
    Verify that 'get_prop_cpus()' returns the same values as set by 'set_prop_cpus()'.

    Args:
        params: The test parameters.
    """

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_uncore_get_all_props(params: PropsTestParamsTypedDict):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_get_all_props(params, 0)

def test_uncore_set_props_mechanisms_bool(params: PropsTestParamsTypedDict):
    """
    Verify correct behavior of 'get_prop_cpus()' when using the 'mname' argument for boolean
    properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_set_bool_props(params, 0)
