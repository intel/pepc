#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Test for the 'CStates' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
import pytest
from tests import common, props_common
from pepclibs import CPUInfo, CStates
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.props_common import PropsTestParamsTypedDict

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
         CStates.CStates(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache) as pobj:
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

    # Current value of the property is not known, so we yield more than one value for each
    # property. This makes sure the property actually gets changed.

    bool_pnames = ("c1_demotion", "c1_undemotion", "c1e_autopromote", "cstate_prewake")
    for pname in bool_pnames:
        yield pname, "on"
        yield pname, "off"

    with contextlib.suppress(ErrorNotSupported):
        pvinfo = pobj.get_cpu_prop("governors", cpu)

        if typing.TYPE_CHECKING:
            governors = cast(list[str], pvinfo["val"])
        else:
            governors = pvinfo["val"]
        yield "governor", governors[0]
        yield "governor", governors[-1]

def test_cstates_set_and_verify(params: PropsTestParamsTypedDict):
    """
    Test setting and C-state properties.

    Args:
        params: The test parameters.
    """

    props_vals = _get_set_and_verify_data(params, 0)
    props_common.set_and_verify(params, props_vals, 0)

def test_cstates_get_all_props(params: PropsTestParamsTypedDict):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Args:
        params: The test parameters.
    """

    props_common.verify_get_all_props(params, 0)

def test_cstates_set_props_mechanisms_bool(params: PropsTestParamsTypedDict):
    """
    Verify that 'set_prop_cpus()' works correctly for boolean.

    Args:
        params: The test parameters.
    """

    props_common.verify_set_bool_props(params, 0)

def test_req_cstates(params: PropsTestParamsTypedDict):
    """
    Test requestable C-states API.

    Args:
        params: The test parameters.
    """

    if typing.TYPE_CHECKING:
        pobj = cast(CStates.CStates, params["pobj"])
    else:
        pobj = params["pobj"]

    cpu = params["cpuinfo"].get_cpus()[-1]

    try:
        driver = pobj.get_cpu_prop("idle_driver", cpu)["val"]
    except ErrorNotSupported:
        return

    csinfo = pobj.get_cpu_cstates_info(cpu)
    if driver == "intel_idle":
        assert "POLL" in csinfo, "'POLL' C-state is missing for the 'intel_idle' driver"
        assert csinfo["POLL"]["index"] == 0, "'POLL' C-state index is not 0"

    # Enable all C-states.
    pobj.enable_cstates(csnames="all", cpus="all")

    # Verify all C-states are enabled.
    for _, csinfo in pobj.get_cstates_info():
        for csname, info in csinfo.items():
            assert not info["disable"], f"C-state '{csname}' is not enabled"

    # Disable 'POLL' on one CPU.
    pobj.disable_cstates(csnames=("POLL",), cpus=[cpu])
    csinfo = pobj.get_cpu_cstates_info(cpu, csnames=("POLL",))
    assert csinfo["POLL"]["disable"], "'POLL' C-state is not disabled"
    assert len(csinfo) == 1, "More C-states returned than requested"
