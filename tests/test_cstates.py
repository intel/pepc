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
from common import build_params, get_pman, is_prop_supported, get_datasets
from pcstates_common import get_fellows, set_and_verify, verify_props_value_type
from pepclibs import CPUInfo, CStates

def _get_params():
    """Yield each dataset with a bool. Used for toggling CStates 'enable_cache'."""

    for dataset in get_datasets():
        yield dataset, True
        yield dataset, False

@pytest.fixture(name="params", scope="module", params=_get_params())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset, enable_cache = request.param
    with get_pman(hostname, dataset) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as csobj:
        params = build_params(hostname, dataset, pman, cpuinfo)
        params["fellows"] = get_fellows(params, cpuinfo, cpu=0)

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
        yield "governor", pinfo["governor"]["governors"][0]
        yield "governor", pinfo["governor"]["governors"][-1]

def test_cstates_set_and_verify(params):
    """This test verifies that 'get_props()' returns same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        sname = params["csobj"].props[pname]["sname"]
        fellows = params["fellows"][sname]

        set_and_verify(params["csobj"], pname, value, fellows)

def test_cstates_property_type(params):
    """This test verifies that 'get_props()' returns values of the correct type."""

    verify_props_value_type(params["csobj"].props, params["pinfo"])
