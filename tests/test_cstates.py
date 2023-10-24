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

        params["siblings"] = props_common.get_siblings(cpuinfo, cpu=0)
        params["pobj"] = pobj

        cpu0_pinfo = {}
        for pname in pobj.props:
            cpu0_pinfo[pname] = pobj.get_cpu_prop(pname, 0)["val"]
        params["cpu0_pinfo"] = cpu0_pinfo

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_cstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    cpu0_pinfo = params["cpu0_pinfo"]

    bool_pnames = {"c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake"}
    for pname in bool_pnames:
        if props_common.is_prop_supported(pname, cpu0_pinfo):
            yield pname, "on"
            yield pname, "off"

    if props_common.is_prop_supported("governor", cpu0_pinfo):
        yield "governor", cpu0_pinfo["governors"][0]
        yield "governor", cpu0_pinfo["governors"][-1]

def test_cstates_set_and_verify(params):
    """This test verifies that 'get_prop()' returns same values set by 'set_prop()'."""

    for pname, value in _set_and_verify_data(params):
        sname = params["pobj"].get_sname(pname)
        siblings = params["siblings"][sname]

        props_common.set_and_verify(params["pobj"], pname, value, siblings)

def test_cstates_property_type(params):
    """This test verifies that 'get_prop()' returns values of the correct type."""

    props_common.verify_props_value_type(params["pobj"].props, params["cpu0_pinfo"])
