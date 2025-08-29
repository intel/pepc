#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test for the 'PStates' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
import common
import props_common
from pepclibs import CPUInfo, PStates

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
         PStates.PStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
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

    # The initial value of each property is unknown, so multiple values are yielded per property.
    # This ensures that the property is actually modified during testing.

    pvinfo = pobj.get_cpu_prop("driver", cpu)
    if pvinfo["val"] == "intel_pstate":
        yield "intel_pstate_mode", "active"
        yield "intel_pstate_mode", "passive"

    yield "turbo", "off"
    yield "turbo", "on"
    yield "turbo", "off"

    yield "epp", "1"
    yield "epp", "254"

    yield "epb", 0
    yield "epb", 15

    pvinfo = pobj.get_cpu_prop("governors", cpu)
    if pvinfo["val"] is not None:
        governors = cast(list[str], pvinfo["val"])
        yield "governor", governors[0]
        yield "governor", governors[-1]

    # TODO: add a test with base frequency too.
    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        min_limit = pobj.get_cpu_prop(f"{pname_min}_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop(f"{pname_max}_limit", cpu)["val"]
        if min_limit is None or max_limit is None:
            continue

        min_limit = "min"
        max_limit = "min"

        yield pname_min, min_limit
        yield pname_max, min_limit

        yield pname_max, max_limit
        yield pname_min, max_limit

def test_pstates_set_and_verify(params: PropsTestParamsTypedDict):
    """
    Verify that 'get_prop_cpus()' returns the same values as set by 'set_prop_cpus()'.

    Args:
        params: The test parameters.
    """

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_pstates_get_all_props(params: PropsTestParamsTypedDict):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_get_all_props(params, 0)

def test_pstates_set_props_mechanisms_bool(params: PropsTestParamsTypedDict):
    """
    Verify correct behavior of 'get_prop_cpus()' when using the 'mname' argument for boolean
    properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_set_bool_props(params, 0)
