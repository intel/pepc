#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'pstates' command."""

from common import run_pepc, get_test_cpu_info

_CPUINFO = get_test_cpu_info()

# Good command scope options.
_GOOD_PKG_SCOPE_OPTIONS = [
    "--packages all",
    f"--packages 0-{_CPUINFO['max_package']}"]

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
_BAD_PKG_SCOPE_OPTIONS = [
    f"--packages {_CPUINFO['max_package'] + 1}"]

_BAD_SCOPE_OPTIONS = [
    f"--cpus {_CPUINFO['max_cpu'] + 1}",
    f"--cores {_CPUINFO['max_core'] + 1}",
    f"--packages {_CPUINFO['max_package'] + 1}"]

def test_pstates_info():
    """Test 'pepc pstates info' command."""

    for scope in _GOOD_SCOPE_OPTIONS:
        run_pepc(f"pstates info {scope}", exp_ret=0)

    for scope in _GOOD_SCOPE_OPTIONS:
        if "packages" not in scope:
            continue
        run_pepc(f"pstates info --uncore {scope}", exp_ret=0)

    for scope in _BAD_SCOPE_OPTIONS:
        run_pepc(f"pstates info {scope}", exp_ret=-1)

    for scope in _BAD_SCOPE_OPTIONS:
        if "packages" not in scope:
            continue
        run_pepc(f"pstates info --uncore {scope}", exp_ret=-1)

def test_pstates_set():
    """Test 'pepc pstates config' command."""


def test_pstates_config():
    """Test 'pepc pstates config' command."""

    # Test frequency settings supported by test configuration.
    good_options = [
        "--min-freq",
        "--max-freq",
        "--min-freq --max-freq",
        "--min-uncore-freq",
        "--max-uncore-freq",
        "--min-uncore-freq --max-uncore-freq",
        "--min-freq min",
        "--max-freq min",
        "--max-freq lfm",
        "--max-freq eff",
        "--max-freq base",
        "--max-freq hfm",
        "--max-freq max",
        "--min-freq lfm",
        "--min-freq eff",
        "--min-freq base",
        "--min-freq hfm",
        "--min-freq min --max-freq max",
        "--max-freq max --min-freq min",
        "--min-uncore-freq min",
        "--max-uncore-freq max",
        "--max-uncore-freq min --max-uncore-freq max"]

    for option in good_options:
        run_pepc(f"pstates config {option}", exp_ret=0)

    good_options = [
        "--min-freq",
        "--min-freq base",
        "--max-uncore-freq",
        "--max-uncore-freq max",
    ]

    for option in good_options:
        for scope in _GOOD_SCOPE_OPTIONS:
            if "uncore" in option and "package" not in scope:
                continue
            run_pepc(f"pstates config {option} {scope}", exp_ret=0)

        for scope in _BAD_SCOPE_OPTIONS:
            run_pepc(f"pstates config {option} {scope}", exp_ret=-1)

    # Test bad frequency settings.
    bad_options = [
        "--min-freq 1000ghz",
        "--max-freq 3",
        "--min-freq maximum",
        "--min-freq max --max-freq min",
        "--min-uncore-freq max --max-uncore-freq min"]

    # Test other config options.
    for option in bad_options:
        run_pepc(f"pstates config {option}", exp_ret=-1)

    good_options = [
        "--epb",
        "--epb 0",
        "--epb 15",
        "--epp",
        "--epp 0",
        "--epp 128",
        "--governor powersave",
        "--turbo",
        "--turbo on",
        "--turbo off"]

    for option in good_options:
        run_pepc(f"pstates config {option}", exp_ret=0)

        for scope in _GOOD_SCOPE_OPTIONS:
            run_pepc(f"pstates config {option} {scope}", exp_ret=0)

        for scope in _BAD_SCOPE_OPTIONS:
            run_pepc(f"pstates config {option} {scope}", exp_ret=-1)

    bad_options = [
        "--epb 16",
        "--epp 256",
        "--governor savepower"]

    for option in bad_options:
        run_pepc(f"pstates config {option}", exp_ret=-1)
