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
from pcstates_common import get_siblings, verify_props_value_type, is_prop_supported
from pepclibs import CPUInfo, Power
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

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

        params["siblings"] = get_siblings(cpuinfo, cpu=0)
        params["pobj"] = pobj
        params["pinfo"] = pobj.get_cpu_props(pobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_power_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    pinfo = params["pinfo"]

    bool_pnames_pat = {"1_enable", "1_clamp", "2_enable", "2_clamp"}

    for pat in bool_pnames_pat:
        pname = f"ppl{pat}"
        if is_prop_supported(pname, pinfo):
            if pinfo[pname] == "off":
                val = "on"
            else:
                val = "off"
            yield pname, val
            yield pname, pinfo[pname]

    power_pnames_pat = {"1", "2"}

    # For power limits, test with current value - 1W, and current value.
    for pat in power_pnames_pat:
        pname = f"ppl{pat}"
        if is_prop_supported(pname, pinfo):
            yield pname, pinfo[pname] - 1
            yield pname, pinfo[pname]

def _set_and_verify(pobj, pname, value, cpus):
    """
    Set property 'pname' to value 'value' for CPUs in 'cpus', then read it back and verify that the
    read value is 'value'.

    The argument are as follows.
     * pobj - 'Power' object.
     * pname - name of the property.
     * value - the new value.
     * cpus - list of CPUs.
    """

    try:
        pobj.set_prop(pname, value, cpus)
    except ErrorVerifyFailed:
        # If modification is not supported, do not verify new value.
        return

    minval = None
    maxval = None

    # For floating point params (window size, power limit), allow some range for
    # the value.
    if isinstance(value, float):
        minval = value * 0.8
        maxval = value * 1.2

    for cpu, pinfo in pobj.get_props((pname, ), cpus):
        failed = False

        if minval is not None:
            if pinfo[pname] < minval or pinfo[pname] > maxval:
                failed = True
        elif pinfo[pname] != value:
            failed = True

        if failed:
            assert False, f"Failed to set property '{pname}' for CPU {cpu}\nSet to '{value}' and " \
                          f"received '{pinfo[pname]}'."

def test_power_set_and_verify(params):
    """This test verifies that 'get_props()' returns same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        sname = params["pobj"].props[pname]["sname"]
        siblings = params["siblings"][sname]

        _set_and_verify(params["pobj"], pname, value, siblings)

def test_power_property_type(params):
    """This test verifies that 'get_props()' returns values of the correct type."""

    verify_props_value_type(params["pobj"].props, params["pinfo"])
