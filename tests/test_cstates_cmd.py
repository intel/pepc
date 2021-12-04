#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'cstates' command."""

from common import run_pepc, get_test_cpu_info

_CPUINFO = get_test_cpu_info()

# Good command scope options.
_GOOD_SCOPE_OPTIONS = [
    "",
    "--cpus all",
    f"--cpus 0-{_CPUINFO['max_cpu']}",
    "--cores all",
    "--cores 0-50",
    f"--cores 0-{_CPUINFO['max_core']}",
    "--packages all",
    f"--packages 0-{_CPUINFO['max_package']}"]

# Bad command scope options.
_BAD_SCOPE_OPTIONS = [
    f"--cpus {_CPUINFO['max_cpu'] + 1}",
    f"--cores {_CPUINFO['max_core'] + 1}",
    f"--packages {_CPUINFO['max_package'] + 1}"]

def test_cstates_info():
    """Test 'pepc cstates info' command."""

    for option in _GOOD_SCOPE_OPTIONS:
        run_pepc(f"cstates info {option}", exp_ret=0)

    for option in _BAD_SCOPE_OPTIONS:
        run_pepc(f"cstates info {option}", exp_ret=-1)

def test_cstates_config():
    """Test 'pepc cstates config' command."""

    good_options = [
        "--enable all",
        "--disable all",
        "--enable C6",
        "--disable C6",
        "--cstate-prewake",
        "--cstate-prewake on",
        "--cstate-prewake off",
        "--c1e-autopromote",
        "--c1e-autopromote on",
        "--c1e-autopromote off",
        "--pkg-cstate-limit",
        "--c1-demotion",
        "--c1-demotion on",
        "--c1-demotion off",
        "--c1-undemotion",
        "--c1-undemotion on",
        "--c1-undemotion off"]

    for option in good_options:
        run_pepc(f"cstates config {option}", exp_ret=0)

        for scope in _GOOD_SCOPE_OPTIONS:
            run_pepc(f"cstates config {option} {scope}", exp_ret=0)

        for scope in _BAD_SCOPE_OPTIONS:
            run_pepc(f"cstates config {option} {scope}", exp_ret=-1)

    bad_options = [
        "--enable CC0",
        "--disable CC0"
        "--cstate-prewake meh"]

    for option in bad_options:
        run_pepc(f"cstates config {option}", exp_ret=-1)

        for scope in _GOOD_SCOPE_OPTIONS:
            run_pepc(f"cstates config {option} {scope}", exp_ret=-1)

        for scope in _BAD_SCOPE_OPTIONS:
            run_pepc(f"cstates config {option} {scope}", exp_ret=-1)
