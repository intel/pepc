#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc pmqos' command-line options."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common, props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, PMQoS

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            pobj: A 'PMQoS.PMQoS' object.
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            cpus: All CPU numbers in the system.
        """

        pobj: PMQoS.PMQoS
        cpuinfo: CPUInfo.CPUInfo
        cpus: list[int]

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
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["pobj"] = pobj
        params["cpuinfo"] = cpuinfo

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus

        yield params

def test_pmqos_info(params: _TestParamsTypedDict):
    """
    Test the 'pepc pmqos info' command.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    props_cmdl_common.run_pepc("pmqos info", pman)
    props_cmdl_common.run_pepc("pmqos info --cpus 0", pman)

def _get_good_config_opts(params: _TestParamsTypedDict) -> Generator[str, None, None]:
    """
    Yield valid command-line options for testing 'pepc pmqos config'.

    Args:
        params: The test parameters.

    Yields:
        Valid command-line options for 'pepc pmqos config'.
    """

    cpu = 0
    pobj = params["pobj"]

    if pobj.prop_is_supported_cpu("latency_limit", cpu):
        yield "--latency-limit"
        yield "--latency-limit 100us"
        yield "--latency-limit 100ms"

def _get_bad_config_opts() -> Generator[str, None, None]:
    """
    Yield invalid command-line options for testing the 'pepc pmqos config'.

    Yields:
        Invalid options for 'pepc pmqos config'.
    """

    yield "--latency-limit 5mb"
    yield "--latency-limit 1Hz"

def test_pmqos_config_good(params: _TestParamsTypedDict):
    """
    Verify that the 'pepc pmqos config' command works correctly with valid options.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    for opt in _get_good_config_opts(params):
        cmd = f"pmqos config {opt} --cpus 0"
        props_cmdl_common.run_pepc(cmd, pman)

def test_pmqos_config_bad(params: _TestParamsTypedDict):
    """
    Verify that the 'pepc pmqos config' command works correctly with invalid options.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    for opt in _get_bad_config_opts():
        props_cmdl_common.run_pepc(f"pmqos config {opt}", pman, exp_exc=Error)
        props_cmdl_common.run_pepc(f"pmqos config --cpus 0 {opt}", pman, exp_exc=Error)
