#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Common functions to support MSR-related tests.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from importlib import import_module
import pytest
import common
from pepclibs.helperlibs.Exceptions import ErrorNotSupported
from pepclibs.msr import MSR
from pepclibs import CPUInfo

if typing.TYPE_CHECKING:
    from typing import Final, Generator, cast, Literal
    from pepclibs.msr import _FeaturedMSR
    from pepclibs.msr._FeaturedMSR import FeatureTypedDict
    from common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            cpus: All CPU numbers in the system.
            testcpus: A few CPU numbers to use for testing.
            msrs: A dictionary where keys are MSR addresses and values are dictionaries of MSR
                  features.
            feature_classes: A list of MSR feature classes to test.
        """

        cpuinfo: CPUInfo.CPUInfo
        cpus: list[int]
        testcpus: list[int]
        msrs: dict[int,  dict[str, FeatureTypedDict]]
        feature_classes: list[type[_FeaturedMSR.FeaturedMSR]]

_MSR_MODULES: Final[tuple[str, ...]] = ("PMEnable", "HWPRequest", "EnergyPerfBias", "FSBFreq",
                                        "HWPRequestPkg", "PCStateConfigCtl", "PlatformInfo",
                                        "PowerCtl", "TurboRatioLimit1", "TurboRatioLimit")

# The following features are considered safe to modify during testing on real hardware.
# All bits of each feature can be written to any value without causing instability or unpredictable
# behavior.
# Note: 'dcu_hw_prefetcher' was in the list, but then it was removed due to the value changing state
# randomly on some systems.
_SAFE_TO_SET_FEATURES: Final[tuple[str, ...]] = ("epb", "epp", "pkg_control", "c1e_autopromote",
                                                 "cstate_prewake", "c1_demotion", "c1_undemotion",
                                                 "l2_hw_prefetcher", "l2_adj_prefetcher",
                                                 "limit1_clamp", "limit2_clamp")

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

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
            if typing.TYPE_CHECKING:
                msr_feature_class = cast(type[_FeaturedMSR.FeaturedMSR], msr_feature_class)

            if msr_feature_class.vendor != cpuinfo.info["vendor"]:
                continue

            try:
                with msr_feature_class(pman=pman, cpuinfo=cpuinfo) as msr:
                    if typing.TYPE_CHECKING:
                        msr = cast(_FeaturedMSR.FeaturedMSR, msr)
                    for name, finfo in msr._features.items(): # pylint: disable=protected-access
                        if not msr.is_feature_supported(name):
                            continue
                        if not is_safe_to_set(name, params["hostname"]):
                            continue
                        if msr.regaddr not in params["msrs"]:
                            params["msrs"][msr.regaddr] = {}
                        params["msrs"][msr.regaddr]["name"] = finfo
            except ErrorNotSupported:
                continue

            if params["msrs"]:
                params["feature_classes"].append(msr_feature_class)

        if not params["feature_classes"]:
            pytest.skip("No supported MSRs to use for testing", allow_module_level=True)

        yield params

def get_bad_cpu_nums(params: _TestParamsTypedDict) -> Generator[int | str, None, None]:
    """
    Yield invalid CPU identifiers for testing purposes.

    Args:
        params: The test parameters.

    Yields:
        Invalid CPU identifiers such as out-of-range numbers, negative numbers, and strings.
    """

    for cpu in (params["cpus"][-1] + 1, -1, "ALL", "a"):
        yield cpu

def is_safe_to_set(name: str, hostname: str) -> bool:
    """
    Determine if a feature is safe to test and write, including on real hardware.

    Args:
        name: The name of the feature to check.
        hostname: The target host name.

    Returns:
        True if the feature is safe to set, False otherwise.
    """

    return hostname == "emulation" or name in _SAFE_TO_SET_FEATURES

def get_msr_objs(params: _TestParamsTypedDict) -> Generator[MSR.MSR, None, None]:
    """
    Yield initialized MSR objects for testing with different cache settings.

    Args:
        params: The test parameters.

    Yields:
        An initialized MSR object.
    """

    for enable_cache in (True, False):
        with MSR.MSR(params["cpuinfo"], pman=params["pman"], enable_cache=enable_cache) as msr:
            yield msr
