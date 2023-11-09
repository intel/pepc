#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Tests for the public methods of the 'CStates' module."""

import pytest
import common
import props_common
from pepclibs import CPUInfo, CStates

def _get_enable_cache_param():
    """Yield each dataset with a bool. Used for toggling CStates 'enable_cache'."""

    yield True
    yield False

@pytest.fixture(name="params", scope="module", params=_get_enable_cache_param())
def get_params(hostspec, request):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "CStates"]
    enable_cache = request.param

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["pobj"] = pobj

        yield params

def _get_set_and_verify_data(params, cpu):
    """Yield ('pname', 'value') tuples for the 'test_cstates_set_and_verify()' test-case."""

    pobj = params["pobj"]

    # Current value of the property is not known, so we yield more than one value for each
    # property. This makes sure the property actually gets changed.

    bool_pnames = ("c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake")
    for pname in bool_pnames:
        yield pname, "on"
        yield pname, "off"

    pvinfo = pobj.get_cpu_prop("governors", cpu)
    if pvinfo["val"] is not None:
        yield "governor", pvinfo["val"][0]
        yield "governor", pvinfo["val"][-1]

def test_cstates_set_and_verify(params):
    """Verify that 'get_prop_cpus()' returns same values set by 'set_prop()'."""

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_cstates_property_type(params):
    """This test verifies that 'get_prop_cpus()' returns values of the correct type."""

    props_common.verify_props_value_type(params, 0)

def test_cstates_get_props_mechanisms(params):
    """Verify that the 'mname' arguments of 'get_prop_cpus()' works correctly."""

    props_common.verify_get_props_mechanisms(params, 0)

def test_cstates_set_props_mechanisms_bool(params):
    """
    Verify that the 'mname' arguments of 'get_prop_cpus()' works correctly for boolean properties.
    """

    props_common.verify_set_props_mechanisms_bool(params, 0)
