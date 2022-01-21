#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'cpu-hotplug' command."""

from common_v1 import run_pepc
from MockedStuff import get_test_cpu_info

_CPUINFO = get_test_cpu_info()

_GOOD_SCOPE_OPTIONS = [
    "",
    "--cpus all",
    f"--cpus 0-{_CPUINFO['max_cpu']}",
    "--packages 0 --cores all",
    "--packages 0 --cores 0-50",
    f"--packages 0 --cores 0-{_CPUINFO['max_core']}",
    "--packages all",
    f"--packages 0-{_CPUINFO['max_package']}"]

_BAD_SCOPE_OPTIONS = [
    f"--cpus {_CPUINFO['max_cpu'] + 1}",
    f"--packages 0 --cores {_CPUINFO['max_core'] + 1}",
    f"--packages {_CPUINFO['max_package'] + 1}"]

def test_v1_cpuhotplug_info():
    """Test 'pepc cpu-hotplug info' command."""

    run_pepc("cpu-hotplug info", exp_ret=0)

def test_v1_cpuhotplug_online():
    """Test 'pepc cpu-hotplug online' command."""

    good_options = [
        "--cpus all",
        "--cpus 1",
        "--cpus 1-2"]

    for option in good_options:
        run_pepc(f"cpu-hotplug online {option}", exp_ret=0)

    bad_options = [""]
    for option in bad_options:
        run_pepc(f"cpu-hotplug online {option}", exp_ret=-1)

def test_v1_cpuhotplug_offline():
    """Test 'pepc cpu-hotplug offline' command."""

    good_options = [
        "--cpus all",
        "--cpus all --cores 0 --packages 0",
        "--packages 0 --cores 0",
        "--packages 0 --cores all",
        "--cpus 1",
        "--cpus 1-2",
        f"--cpus {_CPUINFO['max_cpu']}",
        "--packages 0 --cores 1",
        "--packages 0 --cores 1-2",
        f"--packages 0 --cores {_CPUINFO['max_core']}",
        f"--packages {_CPUINFO['max_package']}"]

    for option in good_options:
        run_pepc(f"cpu-hotplug offline {option}", exp_ret=0)
        run_pepc(f"cpu-hotplug offline {option} --siblings", exp_ret=0)

    bad_options = [
        "--cpus 0",
        "--cpus 0-4"]

    for option in bad_options:
        run_pepc(f"cpu-hotplug offline {option}", exp_ret=-1)

    for option in bad_options:
        # With '--siblings' CPU 0 will be excluded and all these "bad" options become OK.
        run_pepc(f"cpu-hotplug offline {option} --siblings", exp_ret=0)
