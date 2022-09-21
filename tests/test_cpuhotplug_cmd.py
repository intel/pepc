#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'cpu-hotplug' command."""

from common import run_pepc
from common import get_params # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error

def test_cpuhotplug_info(params):
    """Test 'pepc cpu-hotplug info' command."""

    pman = params["pman"]
    run_pepc("cpu-hotplug info", pman)

def _test_cpuhotplug_online_good(params):
    """Test 'pepc cpu-hotplug online' command with good option values."""

    pman = params["pman"]

    good_options = ["--cpus all"]
    if len(params["cpus"]) > 2:
        good_options += ["--cpus 1"]
    if len(params["cpus"]) > 3:
        good_options += ["--cpus 1-2"]

    for option in good_options:
        run_pepc(f"cpu-hotplug offline {option}", pman)
        run_pepc(f"cpu-hotplug online {option}", pman)

def _test_cpuhotplug_online_bad(params):
    """Test 'pepc cpu-hotplug online' command with bad option values."""

    pman = params["pman"]

    bad_options = [
        "",
        "--siblings",
        "--packages 0 --cores all",
        f"--packages 0 --cores {params['cores'][0][0]}",
        f"--packages 0 --cores {params['cores'][0][-1]}",
        f"--packages {params['packages'][-1]}"]

    if len(params["cores"][0]) > 2:
        bad_options += [f"--packages 0 --cores {params['cores'][0][1]}"]
    if len(params["cores"][0]) > 3:
        bad_options += [f"--packages 0 --cores {params['cores'][0][1]}-{params['cores'][0][2]}"]

    for option in bad_options:
        run_pepc(f"cpu-hotplug online {option}", pman, exp_exc=Error)

def test_cpuhotplug_online(params):
    """Test 'pepc cpu-hotplug online' command."""

    _test_cpuhotplug_online_good(params)
    _test_cpuhotplug_online_bad(params)

def _test_cpuhotplug_offline_good(params):
    """Test 'pepc cpu-hotplug offline' command with good option values."""

    pman = params["pman"]

    good_options = [
        "--cpus all",
        f"--cpus all --cores {params['cores'][0][0]} --packages 0",
        "--packages 0",
        "--packages 0 --cores all",
        f"--packages {params['packages'][-1]}",
        f"--packages 0 --cores {params['cores'][0][0]}",
        f"--packages 0 --cores {params['cores'][0][-1]}"]

    if len(params["cpus"]) > 1:
        good_options += [f"--cpus {params['cpus'][-1]}"]
    if len(params["cpus"]) > 2:
        good_options += ["--cpus 1"]
    if len(params["cpus"]) > 3:
        good_options += ["--cpus 1-2"]
    if len(params["cores"][0]) > 2:
        good_options += [f"--packages 0 --cores {params['cores'][0][1]}"]
    if len(params["cores"][0]) > 3:
        good_options += [f"--packages 0 --cores {params['cores'][0][1]}-{params['cores'][0][2]}"]

    # 'cpu-hotplug online' does not support '--package', '--core' and '--siblings', hence we online
    # all CPUs 'cpu-hotplug online '--cpus all'.
    for option in good_options:
        run_pepc("cpu-hotplug online --cpus all", pman)
        run_pepc(f"cpu-hotplug offline {option}", pman)
        run_pepc("cpu-hotplug online --cpus all", pman)
        run_pepc(f"cpu-hotplug offline {option} --siblings", pman)

def _test_cpuhotplug_offline_bad(params):
    """Test 'pepc cpu-hotplug offline' command with bad option values."""

    pman = params["pman"]

    bad_options = ["--cpus 0"]
    if len(params["cpus"]) > 5:
        bad_options += ["--cpus 0-4"]

    for option in bad_options:
        run_pepc(f"cpu-hotplug offline {option}", pman, exp_exc=Error)

    for option in bad_options:
        # With '--siblings' CPU 0 will be excluded and all these "bad" options become OK.
        run_pepc("cpu-hotplug online --cpus all", pman)
        run_pepc(f"cpu-hotplug offline {option} --siblings", pman)

def test_cpuhotplug_offline(params):
    """Test 'pepc cpu-hotplug offline' command."""

    _test_cpuhotplug_offline_good(params)
    _test_cpuhotplug_offline_bad(params)

    # Make sure all CPUs are online for the next tests.
    if params["hostname"] != "emulation":
        run_pepc("cpu-hotplug online --cpus all", params["pman"])
