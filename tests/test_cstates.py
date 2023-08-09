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
from props_common import get_siblings, set_and_verify, verify_props_value_type, is_prop_supported
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
         CStates.CStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as csobj:
        params = common.build_params(pman)

        params["siblings"] = get_siblings(cpuinfo, cpu=0)
        params["csobj"] = csobj
        params["pinfo"] = csobj.get_cpu_props(csobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_cstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    pinfo = params["pinfo"]

    bool_pnames = {"c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake"}
    for pname in bool_pnames:
        if is_prop_supported(pname, pinfo):
            yield pname, "on"
            yield pname, "off"

    if is_prop_supported("governor", pinfo):
        yield "governor", pinfo["governors"][0]
        yield "governor", pinfo["governors"][-1]

def test_cstates_set_and_verify(params):
    """This test verifies that 'get_props()' returns same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        sname = params["csobj"].get_sname(pname)
        siblings = params["siblings"][sname]

        set_and_verify(params["csobj"], pname, value, siblings)

def test_cstates_property_type(params):
    """This test verifies that 'get_props()' returns values of the correct type."""

    verify_props_value_type(params["csobj"].props, params["pinfo"])
