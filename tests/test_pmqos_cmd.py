#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'pmqos' command."""

import pytest
import common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, PMQoS

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    with common.get_pman(hostspec) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        params["pobj"] = pobj
        params["cpuinfo"] = cpuinfo
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus

        yield params

def test_pmqos_info(params):
    """Test 'pepc pmqos info' command."""

    pman = params["pman"]

    common.run_pepc(f"pmqos info", pman)
    common.run_pepc(f"pmqos info --cpus 0", pman)

def _get_good_config_opts(params):
    """Return good options for testing 'pepc pmqos config'."""

    cpu = 0
    opts = []
    pobj = params["pobj"]

    if pobj.prop_is_supported_cpu("latency_limit", cpu):
        opts += ["--latency-limit"]
        return opts

    return []

def _get_bad_config_opts():
    """Return bad options for testing 'pepc pmqos config'."""

    opts = ["--latency-limit 5mb",
            "--latency-limit 1Hz"]
    return opts

def test_pmqos_config_good(params):
    """Test 'pepc pmqos config' command with bad options."""

    pman = params["pman"]

    for opt in _get_good_config_opts(params):
            cmd = f"pmqos config {opt} --cpus 0"
            common.run_pepc(cmd, pman)

def test_pmqos_config_bad(params):
    """Test 'pepc pmqos config' command with bad options."""

    pman = params["pman"]

    for opt in _get_bad_config_opts():
        common.run_pepc(f"pmqos config {opt}", pman, exp_exc=Error)
        common.run_pepc(f"pmqos config --cpus 0 {opt}", pman, exp_exc=Error)
