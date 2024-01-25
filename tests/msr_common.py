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
import common
from pepclibs.helperlibs.Exceptions import ErrorNotSupported
from pepclibs.msr import MSR
from pepclibs import CPUInfo

_MSR_MODULES = (
    "PMEnable", "MiscFeatureControl", "HWPRequest", "EnergyPerfBias", "FSBFreq", "HWPRequestPkg",
    "PCStateConfigCtl", "PlatformInfo", "PowerCtl", "TurboRatioLimit1", "TurboRatioLimit",
    "PackagePowerLimit", "PackagePowerInfo")

# Following features are safe for testing on real HW. The bits of each feature can be written to any
# value.
_SAFE_TO_SET_FEATURES = ("epb", "epp", "pkg_control", "c1e_autopromote", "cstate_prewake",
                         "c1_demotion", "c1_undemotion", "l2_hw_prefetcher", "l2_adj_prefetcher",
                         "limit1_clamp", "limit2_clamp")
                         # dcu_hw_prefetcher was removed due to the value changing state randomly.
                         # The issue could be caused by old firmware on our test systems.

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

    for enable_cache in (True, False):
        with MSR.MSR(params["cpuinfo"], pman=params["pman"], enable_cache=enable_cache) as msr:
            yield msr

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus
        medidx = int(len(allcpus)/2)
        params["testcpus"] = [allcpus[0], allcpus[medidx], allcpus[-1]]

        # The MSR addresses that will be tested.
        params["msrs"] = {}
        params["feature_classes"] = []
        for modname in _MSR_MODULES:
            msr_feature_class = getattr(import_module(f"pepclibs.msr.{modname}"), modname)
            if msr_feature_class.vendor != cpuinfo.info["vendor"]:
                continue

            try:
                with msr_feature_class(pman=pman, cpuinfo=cpuinfo) as msr:
                    for name, finfo in msr._features.items(): # pylint: disable=protected-access
                        if not msr.is_feature_supported(name):
                            continue
                        if not is_safe_to_set(name, params["hostname"]):
                            continue
                        if msr.regaddr not in params["msrs"]:
                            params["msrs"][msr.regaddr] = {}
                        params["msrs"][msr.regaddr].update({name : finfo})
            except ErrorNotSupported:
                continue

            if params["msrs"]:
                params["feature_classes"].append(msr_feature_class)

        if not params["feature_classes"]:
            pytest.skip("No supported MSRs to use for testing", allow_module_level=True)

        yield params
