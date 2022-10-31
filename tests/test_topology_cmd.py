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
from common import get_pman, run_pepc, build_params
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo"]

    with get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = build_params(pman)

        params["cpus"] = cpuinfo.normalize_cpus("all", offlined_ok=True)

        yield params

def test_topology_info(params):
    """Test 'pepc topology info' command."""

    good_options = [
        "",
        "--online-only",
        f"--cpus 0-{params['cpus'][-1]} --cores all --packages all",
        "--order cpu",
        "--order core",
        "--order node",
        "--order die",
        "--order package"
    ]

    for option in good_options:
        run_pepc(f"topology info {option}", params["pman"])

    bad_options = [
        "--order cpu,node",
        "--order packages"
        "--order HELLO_WORLD"
    ]

    for option in bad_options:
        run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)
