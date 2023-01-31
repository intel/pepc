#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Test module for 'pepc' project 'topology' command."""

import pytest
from common import get_pman, run_pepc, build_params, is_emulated
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo"]

    with get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["cpus"] = cpuinfo.normalize_cpus("all", offlined_ok=True)

        yield params

def test_topology_info(params):
    """Test 'pepc topology info' command."""

    good_options = [
        "",
        "--online-only",
        f"--cpus 0-{params['cpus'][-1]} --cores all --packages all",
        "--order cpu --columns CPU",
        "--order core --columns core",
        "--order node --columns node",
        "--order die --columns die",
        "--order PaCkAgE"
    ]

    bad_options = [
        "--order cpu,node",
        "--order Packages",
        "--order HELLO_WORLD",
        "--columns Alfredo"
    ]

    if is_emulated(params["pman"]):
        good_options += ["--cpus all --core-siblings 0 --online-only"]

    try:
        cores = len(params["cpuinfo"].cores_to_cpus(cores="1", packages="0"))
        good_options += [f"--online-only --package 0 --core-siblings 0-{cores - 1}"]
        bad_options += [f"--online-only --package 0 --core-siblings {cores}"]
    except Error:
        # There might not be a core 1 on the system.
        pass

    for option in good_options:
        run_pepc(f"topology info {option}", params["pman"])

    for option in bad_options:
        run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)
