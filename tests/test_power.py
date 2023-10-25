#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""Tests for the public methods of the 'Power' module."""

import pytest
import common
import props_common
from pepclibs import CPUInfo, Power

def _get_enable_cache_param():
    """Yield each dataset with a bool. Used for toggling Power 'enable_cache'."""

    yield True
    yield False

@pytest.fixture(name="params", scope="module", params=_get_enable_cache_param())
def get_params(hostspec, request):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "Power"]
    enable_cache = request.param

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Power.Power(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["pobj"] = pobj

        yield params

def _get_set_and_verify_data(params, cpu):
    """Yield ('pname', 'value') tuples for the 'test_power_set_and_verify()' test-case."""

    bool_pnames = ("ppl1_clamp", "ppl2_clamp")
    for pname in bool_pnames:
        yield pname, "off"
        yield pname, "on"

    # For power limits, test with current value - 1W, and current value.
    power_pnames = {"ppl1", "ppl2"}
    for pname in power_pnames:

        pvinfo = params["pobj"].get_cpu_prop(pname, cpu)
        if pvinfo["val"] is None:
            continue

        yield pname, pvinfo["val"] - 1
        yield pname, pvinfo["val"]

def test_pstates_set_and_verify(params):
    """Verify that 'get_prop()' returns same values set by 'set_prop()'."""

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_power_property_type(params):
    """This test verifies that 'get_prop()' returns values of the correct type."""

    props_common.verify_props_value_type(params, 0)
