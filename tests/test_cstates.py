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
from common import build_params, get_datasets, get_pman, prop_is_supported
from pcstates_common import get_fellows, set_and_verify
from pepclibs import CPUInfo, CStates

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset = request.param
    with get_pman(hostname, dataset) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo) as csobj:
        params = build_params(hostname, dataset, pman, cpuinfo)
        params["fellows"] = get_fellows(params, cpuinfo, cpu=0)

        params["csobj"] = csobj
        params["props"] = csobj.get_cpu_props(csobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_cstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    props = params["props"]

    bool_pnames = {"c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake"}
    for pname in bool_pnames:
        if prop_is_supported(pname, props):
            yield pname, "on"
            yield pname, "off"

    if prop_is_supported("governor", props):
        yield "governor", props["governor"]["governors"][0]
        yield "governor", props["governor"]["governors"][-1]

def test_cstates_set_and_verify(params):
    """Test for if 'get_props()' returns the same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        scope = params["csobj"].props[pname]["scope"]
        fellows = params["fellows"][scope]

        set_and_verify(params["csobj"], pname, value, fellows)
