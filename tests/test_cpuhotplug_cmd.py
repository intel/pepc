#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Test module for 'pepc' project 'cpu-hotplug' command."""

import pytest
import common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "CPUOnline", "Systemctl"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        params["cpuonline"] = cpuonline

        params["online"] = cpuinfo.get_cpus()
        params["offline"] = cpuinfo.get_offline_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

        yield params

def _restore_cpus_online_status(params, cpus, state):
    """Restore CPUs to the original online/offline status."""

    if state:
        params["cpuonline"].online(cpus=cpus, skip_unsupported=True)
    else:
        params["cpuonline"].offline(cpus=cpus, skip_unsupported=True)

def test_cpuhotplug_info(params):
    """Test 'pepc cpu-hotplug info' command."""

    pman = params["pman"]
    common.run_pepc("cpu-hotplug info", pman)

def _test_cpuhotplug_online_good(params):
    """Test 'pepc cpu-hotplug online' command with good option values."""

    pman = params["pman"]

    good = ["--cpus all"]
    if len(params["online"]) > 2:
        good += [f"--cpus {params['online'][1]}"]
    if len(params["offline"]) > 1:
        good += [f"--cpus {params['offline'][0]}"]
    if len(params["offline"]) > 2:
        good += [f"--cpus {params['offline'][0]}-{params['offline'][1]}"]

    for option in good:
        common.run_pepc(f"cpu-hotplug online {option}", pman)
        _restore_cpus_online_status(params, params["offline"], False)

def _test_cpuhotplug_online_bad(params):
    """Test 'pepc cpu-hotplug online' command with bad option values."""

    pman = params["pman"]

    bad = [
        "",
        "--cpus all --core-siblings 0",
        "--packages 0 --cores all",
        f"--packages 0 --cores {params['cores'][0][0]}",
        f"--packages 0 --cores {params['cores'][0][-1]}",
        f"--packages {params['packages'][-1]}"]

    if len(params["cores"][0]) > 2:
        bad += [f"--packages 0 --cores {params['cores'][0][1]}"]
    if len(params["cores"][0]) > 3:
        bad += [f"--packages 0 --cores {params['cores'][0][1]}-{params['cores'][0][2]}"]

    for option in bad:
        common.run_pepc(f"cpu-hotplug online {option}", pman, exp_exc=Error)

def test_cpuhotplug_online(params):
    """Test 'pepc cpu-hotplug online' command."""

    _test_cpuhotplug_online_good(params)
    _test_cpuhotplug_online_bad(params)

def _test_cpuhotplug_offline_good(params):
    """Test 'pepc cpu-hotplug offline' command with good option values."""

    pman = params["pman"]

    good = [
        "--cpus all",
        f"--cpus all --cores {params['cores'][0][0]} --packages 0",
        "--packages 0",
        "--packages 0 --cores all",
        f"--packages {params['packages'][-1]}",
        f"--packages 0 --cores {params['cores'][0][0]}",
        f"--packages 0 --cores {params['cores'][0][-1]}"]

    if len(params["online"]) > 1:
        good += [f"--cpus {params['online'][-1]}"]
    if len(params["online"]) > 2:
        good += [f"--cpus {params['online'][1]}"]
    if len(params["online"]) > 3:
        good += [f"--cpus {params['online'][1]}-{params['online'][2]}"]
    if len(params["cores"][0]) > 2:
        good += [f"--packages 0 --cores {params['cores'][0][1]}"]
    if len(params["cores"][0]) > 3:
        good += [f"--packages 0 --cores {params['cores'][0][1]}-{params['cores'][0][2]}"]

    for option in good:
        common.run_pepc(f"cpu-hotplug offline {option}", pman)
        _restore_cpus_online_status(params, params["online"], True)

def _test_cpuhotplug_offline_bad(params):
    """Test 'pepc cpu-hotplug offline' command with bad option values."""

    pman = params["pman"]

    bad = ["--cpus 0"]
    if len(params["online"]) > 5:
        bad += ["--cpus 0-4"]

    for option in bad:
        common.run_pepc(f"cpu-hotplug offline {option}", pman, exp_exc=Error)

def test_cpuhotplug_offline(params):
    """Test 'pepc cpu-hotplug offline' command."""

    _test_cpuhotplug_offline_good(params)
    _test_cpuhotplug_offline_bad(params)
