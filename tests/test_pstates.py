#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test for the 'PStates' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
import common
import props_common
from pepclibs import CPUInfo, PStates

if typing.TYPE_CHECKING:
    from typing import Generator
    from props_common import PropsTestParamsTypedDict

@pytest.fixture(name="params", scope="module", params=props_common.get_enable_cache_param())
def get_params(hostspec: str,
               username: str,
               request: pytest.FixtureRequest) -> Generator[PropsTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.
        request: The pytest fixture request object.

    Yields:
        A dictionary with test parameters.
    """

    enable_cache = request.param

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
        params = common.build_params(pman)
        yield props_common.extend_params(params, pobj, cpuinfo)

def _get_set_and_verify_data(params: PropsTestParamsTypedDict,
                             cpu: int) -> Generator[tuple[str, str | int], None, None]:
    """
    Yield property name and value pairs running various tests for the property and the value.

    Args:
        params: The test parameters.
        cpu: CPU to test property with.

    Yields:
        tuple: A pair containing the property name and the value to run a test with.
    """

    pobj = params["pobj"]

    # The initial value of each property is unknown, so multiple values are yielded per property.
    # This ensures that the property is actually modified during testing.

    pvinfo = pobj.get_cpu_prop("driver", cpu)
    if pvinfo["val"] == "intel_pstate":
        yield "intel_pstate_mode", "active"
        yield "intel_pstate_mode", "passive"

    yield "turbo", "on"
    yield "turbo", "off"
    yield "turbo", "on"

    yield "epp", "1"
    yield "epp", "254"

    yield "epb", 0
    yield "epb", 15

    pvinfo = pobj.get_cpu_prop("governors", cpu)
    if pvinfo["val"] is not None:
        governors = cast(list[str], pvinfo["val"])
        yield "governor", governors[0]
        yield "governor", governors[-1]

    min_limit = pobj.get_cpu_prop("min_freq_limit", cpu)["val"]
    max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]
    if min_limit is not None or max_limit is not None:
        yield "min_freq", "min"
        yield "max_freq", "min"

        yield "max_freq", "max"
        yield "min_freq", "max"

def test_pstates_set_and_verify(params: PropsTestParamsTypedDict):
    """
    Verify that 'get_prop_cpus()' returns the same values as set by 'set_prop_cpus()'.

    Args:
        params: The test parameters.
    """

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_pstates_get_all_props(params: PropsTestParamsTypedDict):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_get_all_props(params, 0)

def test_pstates_set_props_mechanisms_bool(params: PropsTestParamsTypedDict):
    """
    Verify correct behavior of 'get_prop_cpus()' when using the 'mname' argument for boolean
    properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_set_bool_props(params, 0)

def test_freq_msr_vs_sysfs(params: PropsTestParamsTypedDict):
    """
    Verify that the frequency values read using the 'msr' and 'sysfs' mechanisms are consistent.

    Args:
        params: The test parameters.
    """

    pobj = params["pobj"]
    cpuinfo = params["cpuinfo"]

    # Verify the minimum frequency values.
    for cpu in cpuinfo.get_cpus():
        min_freq_sysfs = pobj.get_cpu_prop("min_freq_limit", cpu, mnames=("sysfs",))["val"]
        min_freq_msr = pobj.get_cpu_prop("min_oper_freq", cpu, mnames=("msr",))["val"]

        if min_freq_sysfs is None or min_freq_msr is None:
            continue

        min_freq_sysfs = cast(int, min_freq_sysfs)
        min_freq_msr = cast(int, min_freq_msr)

        if cpuinfo.info["hybrid"]:
            assert min_freq_sysfs == min_freq_msr, \
                   f"'min_freq_limit' ({min_freq_sysfs}) and 'min_oper_freq' ({min_freq_msr})' " \
                   f"mismatch on CPU {cpu}: "
        else:
            assert min_freq_sysfs >= min_freq_msr, \
                   f"'min_freq_limit' ({min_freq_sysfs}) is less than 'min_oper_freq' " \
                   f"({min_freq_msr}) on CPU {cpu}: "

    # Verify the maximum frequency values.
    for cpu in cpuinfo.get_cpus():
        driver = pobj.get_cpu_prop("driver", cpu)["val"]
        if driver == "acpi-cpufreq":
            # In case of the 'acpi-cpufreq' driver, the 'max_freq_limit' property is the TAR value
            # (at least on Intel platforms), which is the base frequency + a small value. It is not
            # the max. turbo frequency, so skip the check.
            continue

        max_freq_sysfs = pobj.get_cpu_prop("max_freq_limit", cpu, mnames=("sysfs",))["val"]
        if not max_freq_sysfs:
            continue

        max_freq_sysfs = cast(int, max_freq_sysfs)

        turbo = pobj.get_cpu_prop("turbo", cpu)["val"]
        if turbo is None:
            continue

        if turbo == "on":
            max_freq_msr = pobj.get_cpu_prop("max_turbo_freq", cpu, mnames=("msr",))["val"]
            if max_freq_msr is None:
                continue

            min_freq_msr = cast(int, min_freq_msr)

            assert max_freq_sysfs == max_freq_msr, \
                f"'max_freq_limit' ({max_freq_sysfs}) and 'max_turbo_freq' ({max_freq_msr})' " \
                f"mismatch on CPU {cpu}: "
        else:
            assert turbo == "off", f"Unexpected turbo value: {turbo}"

            base_freq = pobj.get_cpu_prop("base_freq", cpu)["val"]
            if base_freq is None:
                continue

            base_freq = cast(int, base_freq)

            assert max_freq_sysfs == base_freq, \
                f"'max_freq_limit' ({max_freq_sysfs}) and 'base_freq' ({base_freq})' " \
                f"mismatch on CPU {cpu}"

    # Verify the base frequency.
    for cpu in cpuinfo.get_cpus():
        base_freq_sysfs = pobj.get_cpu_prop("base_freq", cpu, mnames=("sysfs",))["val"]
        base_freq_msr = pobj.get_cpu_prop("base_freq", cpu, mnames=("msr",))["val"]

        base_freq_sysfs = cast(int, base_freq_sysfs)
        base_freq_msr = cast(int, base_freq_msr)

        if base_freq_sysfs is None or base_freq_msr is None:
            continue

        assert base_freq_sysfs == base_freq_msr, \
               f"'base_freq' ({base_freq_sysfs}) and 'base_freq' ({base_freq_msr})' mismatch " \
               f"on CPU {cpu}"
