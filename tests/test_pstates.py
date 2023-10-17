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
from props_common import get_siblings, is_prop_supported, set_and_verify, verify_props_value_type
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
         PStates.PStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as psobj:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["siblings"] = get_siblings(cpuinfo, cpu=0)
        params["psobj"] = psobj

        cpu0_pinfo = {}
        for pname in psobj.props:
            cpu0_pinfo[pname] = psobj.get_cpu_prop(pname, 0)
        params["cpu0_pinfo"] = cpu0_pinfo

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_pstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    cpu0_pinfo = params["cpu0_pinfo"]

    if is_prop_supported("intel_pstate_mode", cpu0_pinfo):
        yield "intel_pstate_mode", "active"
        yield "intel_pstate_mode", "passive"

    if is_prop_supported("turbo", cpu0_pinfo):
        yield "turbo", "off"
        yield "turbo", "on"

    if is_prop_supported("epp", cpu0_pinfo):
        yield "epp", "1"
        yield "epp", "254"

    if is_prop_supported("epp_hw", cpu0_pinfo):
        yield "epp_hw", 0
        yield "epp_hw", 255

    if is_prop_supported("epb", cpu0_pinfo):
        yield "epb", 0
        yield "epb", 15

    if is_prop_supported("epb_hw", cpu0_pinfo):
        yield "epb_hw", 0
        yield "epb_hw", 15

    if is_prop_supported("governor", cpu0_pinfo):
        yield "governor", cpu0_pinfo["governors"][0]
        yield "governor", cpu0_pinfo["governors"][-1]

    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        if is_prop_supported(pname_min, cpu0_pinfo):
            min_limit = cpu0_pinfo[f"{pname_min}_limit"]
            max_limit = cpu0_pinfo[f"{pname_max}_limit"]

            # Right now we do not know how the systems min. and max frequencies are configured, so
            # we have to be careful to avoid failures related to setting min. frequency higher than
            # the currently configured max. frequency.
            yield pname_min, min_limit
            yield pname_max, min_limit

            yield pname_max, max_limit
            yield pname_min, max_limit

def test_pstates_set_and_verify(params):
    """This test verifies that 'get_props()' returns same values set by 'set_prop()'."""

    for pname, value in _set_and_verify_data(params):
        sname = params["psobj"].get_sname(pname)
        siblings = params["siblings"][sname]

        set_and_verify(params["psobj"], pname, value, siblings)

def test_pstates_property_type(params):
    """This test verifies that 'get_props()' returns values of the correct type."""

    verify_props_value_type(params["psobj"].props, params["cpu0_pinfo"])
