#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Test 'pepc topology' command-line options."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common, props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
        """

        cpuinfo: CPUInfo.CPUInfo

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
        yield params

def test_topology_info(params: _TestParamsTypedDict):
    """
    Test the 'pepc topology info' command with various valid and invalid options.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()

    good = ["",
            "--online-only",
            f"--cpus 0-{cpus[-1]} --cores all --packages all",
            "--order cpu --columns CPU,Hybrid",
            "--order core --columns core",
            "--order node --columns node",
            "--order die --columns die",
            "--order PaCkAgE",
            "--cpus all --core-siblings 0 --online-only"]

    bad = ["--order cpu,node",
           "--order Packages",
           "--order HELLO_WORLD",
           "--columns Alfredo"]

    try:
        cpus_per_core = len(cpuinfo.cores_to_cpus(cores=(1,), packages=(0,)))
        good += [f"--online-only --package 0 --core-siblings 0-{cpus_per_core - 1}"]
    except Error:
        # There might not be a core 1 on the system.
        pass

    for option in good:
        props_cmdl_common.run_pepc(f"topology info {option}", params["pman"])

    for option in bad:
        props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)
