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

import pytest
from common import get_pman, run_pepc, build_params
from pcstates_common import is_prop_supported
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Human
from pepclibs import CPUInfo, PStates

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "PStates", "Systemctl"]

    with get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:
        params = build_params(pman)

        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

        params["psobj"] = psobj
        params["pinfo"] = psobj.get_cpu_props(psobj.props, 0)

        yield params

def _get_scope_options(params):
    """Return dictionary of good and bad scope options to be used for testing."""

    pkg0_core_ranges = Human.rangify(params['cores'][0])

    good_options = [
        "",
        "--packages 0 --cpus all",
        f"--cpus 0-{params['cpus'][-1]}",
        "--packages 0 --cores all",
        f"--packages 0 --cores {pkg0_core_ranges}",
        "--packages all",
        f"--packages 0-{params['packages'][-1]}"]

    bad_options = [
        f"--cpus {params['cpus'][-1] + 1}",
        f"--cores {pkg0_core_ranges}",
        f"--packages 0 --cores {params['cores'][0][-1] + 1}",
        f"--packages {params['packages'][-1] + 1}"]

    good_global_options = [
        "",
        "--cpus all",
        "--packages all",
        f"--cpus  0-{params['cpus'][-1]}"]

    return {"good" : good_options, "bad" : bad_options, "good_global" : good_global_options}

def _get_config_options(params):
    """Return dictionary of good and bad 'pepc pstates config' option values."""

    options = {}

    good_options = []
    bad_options = []

    if is_prop_supported("min_freq", params["pinfo"]):
        good_options += [
            "--min-freq",
            "--max-freq",
            "--min-freq --max-freq",
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
            "--max-freq max --min-freq min"]

        bad_options += [
            "--min-freq 1000ghz",
            "--max-freq 3",
            "--min-freq maximum",
            "--min-freq max --max-freq min"]

    if is_prop_supported("min_uncore_freq", params["pinfo"]):
        good_options += [
            "--min-uncore-freq",
            "--max-uncore-freq",
            "--min-uncore-freq --max-uncore-freq",
            "--min-uncore-freq min",
            "--max-uncore-freq max",
            "--max-uncore-freq min --max-uncore-freq max"]
        bad_options += ["--min-uncore-freq max --max-uncore-freq min"]

    options["freq"] = { "good" : good_options, "bad" : bad_options }

    good_options = []
    bad_options = []

    if is_prop_supported("governor", params["pinfo"]):
        good_options += ["--governor powersave"]
        bad_options += ["--governor savepower"]

    if is_prop_supported("epp", params["pinfo"]):
        good_options += ["--epp", "--epp 0", "--epp 128"]
        bad_options += ["--epp 256"]

    if is_prop_supported("epb", params["pinfo"]):
        good_options += ["--epb", "--epb 0", "--epb 15"]
        bad_options += ["--epb 16"]

    options["config"] = { "good" : good_options, "bad" : bad_options }

    good_options = []
    bad_options = []
    if is_prop_supported("turbo", params["pinfo"]):
        good_options += ["--turbo", "--turbo on", "--turbo off"]
        bad_options += ["--turbo 1", "--turbo enable", "--turbo OFF"]

    options["turbo"] = { "good" : good_options, "bad" : bad_options }

    return options

def test_pstates_info(params):
    """Test 'pepc pstates info' command."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    for option in scope_options["good"]:
        run_pepc(f"pstates info {option}", pman)

    for option in scope_options["bad"]:
        run_pepc(f"pstates info {option}", pman, exp_exc=Error)

def _test_pstates_config_good(params):
    """Test 'pepc pstates config' command with good argument values."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)
    config_options = _get_config_options(params)

    # Test frequency settings supported by test configuration.
    for option in config_options["freq"]["good"]:
        run_pepc(f"pstates config {option}", pman)

    for option in config_options["freq"]["good"]:
        run_pepc(f"pstates config {option}", pman)

        for scope in scope_options["good"]:
            if "uncore" in option and ("package" not in scope or "core" in scope):
                continue
            run_pepc(f"pstates config {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["config"]["good"]:
        run_pepc(f"pstates config {option}", pman)

        for scope in scope_options["good"]:
            run_pepc(f"pstates config {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["turbo"]["good"]:
        run_pepc(f"pstates config {option}", pman)

        for scope in scope_options["good_global"]:
            run_pepc(f"pstates config {option} {scope}", pman)

def _test_pstates_config_bad(params):
    """Test 'pepc pstates config' command with bad argument values."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)
    config_options = _get_config_options(params)

    # Test other config options.
    for option in config_options["freq"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

    for option in config_options["freq"]["good"]:
        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["turbo"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

    for option in config_options["config"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

def test_pstates_config(params):
    """Test 'pepc pstates config' command."""

    _test_pstates_config_good(params)
    _test_pstates_config_bad(params)
