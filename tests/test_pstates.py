#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Tests for the public methods of the 'PStates' module."""

import pytest
import common
import props_common
from pepclibs import CPUInfo, PStates

def _get_enable_cache_param():
    """Yield each dataset with a bool. Used for toggling PStates 'enable_cache'."""

    yield True
    yield False

@pytest.fixture(name="params", scope="module", params=_get_enable_cache_param())
def get_params(hostspec, request):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "PStates"]
    enable_cache = request.param

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["pobj"] = pobj

        yield params

def _get_set_and_verify_data(params, cpu):
    """Yield ('pname', 'value') tuples for the 'test_pstates_set_and_verify()' test-case."""

    pobj = params["pobj"]

    # Current value of the property is not known, so we yield more than one value for each #
    # property. This makes sure the property actually gets changed.

    pvinfo = pobj.get_cpu_prop("driver", cpu)
    if pvinfo["val"] == "intel_pstate":
        yield "intel_pstate_mode", "active"
        yield "intel_pstate_mode", "passive"

    yield "turbo", "off"
    yield "turbo", "on"

    yield "epp", "1"
    yield "epp", "254"

    yield "epb", 0
    yield "epb", 15

    pvinfo = pobj.get_cpu_prop("governors", cpu)
    if pvinfo["val"] is not None:
        yield "governor", pvinfo["val"][0]
        yield "governor", pvinfo["val"][-1]

    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        min_limit = pobj.get_cpu_prop(f"{pname_min}_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop(f"{pname_max}_limit", cpu)["val"]
        if min_limit is None or max_limit is None:
            continue

        yield pname_min, min_limit
        yield pname_max, min_limit

        yield pname_max, max_limit
        yield pname_min, max_limit

def test_pstates_set_and_verify(params):
    """Verify that 'get_prop()' returns same values as set by 'set_prop()'."""

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_pstates_property_type(params):
    """Verify that 'get_prop()' returns values of the correct type."""

    props_common.verify_props_value_type(params, 0)

def test_pstates_get_props_mechanisms(params):
    """Verify that the 'mname' arguments of 'get_prop()' works correctly."""

    props_common.verify_get_props_mechanisms(params, 0)

def test_pstates_set_props_mechanisms_bool(params):
    """Verify that the 'mname' arguments of 'get_prop()' works correctly for boolean properties."""

    props_common.verify_set_props_mechanisms_bool(params, 0)
