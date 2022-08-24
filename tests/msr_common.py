#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Common bits for the 'pepc' MSR and MSR feature modules tests."""

from importlib import import_module
import pytest
from common import build_params, get_pman, get_datasets
from pepclibs.msr import MSR
from pepclibs import CPUInfo

_MSR_MODULES = (
    "PMEnable", "MiscFeatureControl", "HWPRequest", "EnergyPerfBias", "FSBFreq", "HWPRequestPkg",
    "PCStateConfigCtl", "PlatformInfo", "PowerCtl", "TurboRatioLimit1", "TurboRatioLimit")

# Following features are safe for testing on real HW. The bits of each feature can be written to any
# value.
_SAFE_TO_SET_FEATURES = ("epb", "epp", "pkg_control", "epp", "c1e_autopromote", "cstate_prewake",
                         "c1_demotion", "c1_undemotion", "l2_hw_prefetcher", "l1_adj_prefetcher",
                         "dcu_hw_prefetcher")

def get_bad_cpu_nums(params):
    """Yield CPU numbers which should not be accepted by any method."""

    for cpu in (params["cpus"][-1] + 1, -1, "ALL", "a"):
        yield cpu

def is_safe_to_set(name, hostname):
    """Return 'True' if feature 'name' is safe to test and write, also on real hardware."""

    return hostname == "emulation" or name in _SAFE_TO_SET_FEATURES

def get_msr_objs(params):
    """
    Yield the 'MSR' objects initialized with different parameters that we want to run tests with.
    """

    with get_pman(params["hostname"], params["dataset"]) as pman:
        for enable_cache in (True, False):
            with MSR.MSR(pman=pman, enable_cache=enable_cache) as msr:
                yield msr

def _build_msr_params(params, pman):
    """Implements the 'get_msr_params()' fixture."""

    # The MSR addresses that will be tested.
    params["msrs"] = {}
    params["feature_classes"] = []
    for modname in _MSR_MODULES:
        msr_feature_class = getattr(import_module(f"pepclibs.msr.{modname}"), modname)
        params["feature_classes"].append(msr_feature_class)
        with msr_feature_class(pman=pman) as msr:
            for name, finfo in msr._features.items(): # pylint: disable=protected-access
                if not msr.is_feature_supported(name):
                    continue
                if not is_safe_to_set(name, params["hostname"]):
                    continue
                if msr.regaddr not in params["msrs"]:
                    params["msrs"][msr.regaddr] = {}
                params["msrs"][msr.regaddr].update({name : finfo})

    return params

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_msr_params(hostname, request):
    """
    Yield a dictionary with information we need for testing. For example, to optimize the test
    duration, use only subset of all CPUs available on target system to run tests on.
    """

    dataset = request.param
    with get_pman(hostname, dataset) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = build_params(hostname, dataset, pman, cpuinfo)
        yield _build_msr_params(params, pman)
