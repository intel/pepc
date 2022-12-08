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
from pcstates_common import get_siblings, is_prop_supported, set_and_verify, verify_props_value_type
from pepclibs import CPUInfo, PStates, BClock

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
        params["pinfo"] = psobj.get_cpu_props(psobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_pstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    pinfo = params["pinfo"]

    if is_prop_supported("intel_pstate_mode", pinfo):
        yield "intel_pstate_mode", "active"
        yield "intel_pstate_mode", "passive"

    if is_prop_supported("turbo", pinfo):
        yield "turbo", "off"
        yield "turbo", "on"

    if is_prop_supported("epp_policy", pinfo):
        yield "epp_policy", pinfo["epp_policy"]["epp_policies"][0]
        yield "epp_policy", pinfo["epp_policy"]["epp_policies"][-1]
    elif is_prop_supported("epp", pinfo):
        yield "epp", 0
        yield "epp", 128

    if is_prop_supported("epp_hw", pinfo):
        yield "epp_hw", 0
        yield "epp_hw", 255

    if is_prop_supported("epb", pinfo):
        yield "epb", 0
        yield "epb", 15

    if is_prop_supported("epb_hw", pinfo):
        yield "epb_hw", 0
        yield "epb_hw", 15

    if is_prop_supported("governor", pinfo):
        yield "governor", pinfo["governor"]["governors"][0]
        yield "governor", pinfo["governor"]["governors"][-1]

    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        if is_prop_supported(pname_min, pinfo):
            min_limit = pinfo[f"{pname_min}_limit"][f"{pname_min}_limit"]
            max_limit = pinfo[f"{pname_max}_limit"][f"{pname_max}_limit"]

            # Right now we do not know how the systems min. and max frequencies are configured, so
            # we have to be careful to avoid failures related to setting min. frequency higher than
            # the currently configured max. frequency.
            yield pname_min, min_limit
            yield pname_max, min_limit

            yield pname_max, max_limit
            yield pname_min, max_limit

def test_pstates_set_and_verify(params):
    """This test verifies that 'get_props()' returns same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        if pname == "epp_policy" and value == "default":
            # Setting an option to "default" will not read back "default", rather the default
            # system value. E.g. "default" EPP Policy might be "powersaver".
            continue

        sname = params["psobj"].props[pname]["sname"]
        siblings = params["siblings"][sname]

        set_and_verify(params["psobj"], pname, value, siblings)

def test_pstates_property_type(params):
    """This test verifies that 'get_props()' returns values of the correct type."""

    verify_props_value_type(params["psobj"].props, params["pinfo"])

def _set_freq_pairs(params, min_pname, max_pname):
    """
    Set min. and max frequencies to various values in order to verify that the 'PState' modules set
    them correctly. The arguments 'min_pname' and 'max_pname' are the frequency property names.
    """

    sname = params["psobj"].props[min_pname]["sname"]
    siblings = params["siblings"][sname]

    min_limit = params["pinfo"][f"{min_pname}_limit"][f"{min_pname}_limit"]
    max_limit = params["pinfo"][f"{max_pname}_limit"][f"{max_pname}_limit"]

    bclk_MHz = BClock.get_bclk(params["pman"], cpu=0, cpuinfo=params["cpuinfo"])
    bclk_Hz = int(bclk_MHz * 1000000)
    a_quarter = int((max_limit - min_limit) / 4)
    increment = a_quarter - a_quarter % bclk_Hz

    # [Min ------------------ Max ----------------------------------------------------------]
    params["psobj"].set_props({min_pname : min_limit, max_pname : min_limit + increment}, siblings)

    # [-------------------------------------------------------- Min -------------------- Max]
    params["psobj"].set_props({min_pname : max_limit - increment, max_pname : max_limit}, siblings)

    # [Min ------------------ Max ----------------------------------------------------------]
    params["psobj"].set_props({min_pname : min_limit, max_pname : min_limit + increment}, siblings)

def test_pstates_frequency_set_order(params):
    """
    Test min. and max frequency set order. We do not know how the systems min. and max frequencies
    are configured, so we have to be careful when setting min. and max frequency simultaneously.

    See 'PStates._validate_and_set_freq()' docstring, for more information.
    """

    # When Turbo is disabled the max frequency may be limited.
    if is_prop_supported("turbo", params["pinfo"]):
        sname = params["psobj"].props["turbo"]["sname"]
        cpus = params["siblings"][sname]
        params["psobj"].set_prop("turbo", "on", cpus)

    if is_prop_supported("min_freq", params["pinfo"]):
        _set_freq_pairs(params, "min_freq", "max_freq")

    if is_prop_supported("min_uncore_freq", params["pinfo"]):
        _set_freq_pairs(params, "min_uncore_freq", "max_uncore_freq")
