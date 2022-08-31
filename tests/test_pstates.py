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
from common import build_params, get_pman, prop_is_supported, get_datasets
from pcstates_common import get_fellows, set_and_verify
from pepclibs import CPUInfo, PStates

def _get_params():
    """Yield each dataset with a bool. Used for toggling PStates 'enable_cache'."""

    for dataset in get_datasets():
        yield dataset, True
        yield dataset, False

@pytest.fixture(name="params", scope="module", params=_get_params())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset, enable_cache = request.param
    with get_pman(hostname, dataset) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as psobj:
        params = build_params(hostname, dataset, pman, cpuinfo)
        params["fellows"] = get_fellows(params, cpuinfo, cpu=0)

        params["psobj"] = psobj
        params["props"] = psobj.get_cpu_props(psobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields ('pname', 'value') tuples for the 'test_pstates_set_and_verify()' test-case. The current
    value of the property is not known, so we yield more than one value for each property. This
    makes sure the property actually gets changed.
    """

    props = params["props"]

    if prop_is_supported("turbo", props):
        yield "turbo", "off"
        yield "turbo", "on"

    if prop_is_supported("epp_policy", props):
        yield "epp_policy", props["epp_policy"]["epp_policies"][0]
        yield "epp_policy", props["epp_policy"]["epp_policies"][-1]
    elif prop_is_supported("epp", props):
        yield "epp", 0
        yield "epp", 128

    if prop_is_supported("epb_policy", props):
        yield "epb_policy", props["epb_policy"]["epb_policies"][0]
        yield "epb_policy", props["epb_policy"]["epb_policies"][-1]
    elif prop_is_supported("epb", props):
        yield "epb", 0
        yield "epb", 15

    if prop_is_supported("governor", props):
        yield "governor", props["governor"]["governors"][0]
        yield "governor", props["governor"]["governors"][-1]

    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        if prop_is_supported(pname_min, props):
            min_limit = props[f"{pname_min}_limit"][f"{pname_min}_limit"]
            max_limit = props[f"{pname_max}_limit"][f"{pname_max}_limit"]

            # Right now we do not know how the systems min. and max frequencies are configured, so
            # we have to be careful to avoid failures related to setting min. frequency higher than
            # the currently configured max. frequency.
            yield pname_min, min_limit
            yield pname_max, min_limit

            yield pname_max, max_limit
            yield pname_min, max_limit

def test_pstates_set_and_verify(params):
    """Test for if 'get_props()' returns the same values set by 'set_props()'."""

    for pname, value in _set_and_verify_data(params):
        scope = params["psobj"].props[pname]["scope"]
        fellows = params["fellows"][scope]

        set_and_verify(params["psobj"], pname, value, fellows)
