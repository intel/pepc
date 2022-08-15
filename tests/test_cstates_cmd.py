#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'cstates' command."""

from common import run_pepc, prop_is_supported
# Fixtures need to be imported explicitly
from common import build_params, get_params # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Human

def _get_scope_options(params):
    """Return dictionary of good and bad scope options to be used for testing."""

    pkg0_core_ranges = Human.rangify(params['cores'][0])

    good_scope_options = [
        "",
        "--packages 0 --cpus all",
        f"--cpus 0-{params['cpus'][-1]}",
        "--packages 0 --cores all",
        f"--packages 0 --cores {pkg0_core_ranges}",
        "--packages all",
        f"--packages 0-{params['packages'][-1]}"]

    bad_scope_options = [
        f"--cpus {params['cpus'][-1] + 1}",
        f"--cores {pkg0_core_ranges}",
        f"--packages 0 --cores {params['cores'][0][-1] + 1}",
        f"--packages {params['packages'][-1] + 1}"]

    return {"good" : good_scope_options, "bad" : bad_scope_options}

def test_cstates_info(params):
    """
    Test 'pepc cstates info' command. The 'caplog' argument is standard pytest fixture allowing
    access to the captured logs.
    """

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    for option in scope_options["good"]:
        run_pepc(f"cstates info {option}", pman)

    for option in scope_options["bad"]:
        run_pepc(f"cstates info {option}", pman, exp_exc=Error)

    for cstate in params["cstates"]:
        run_pepc(f"cstates info --cpus 0 --cstates {cstate}", pman)

def test_cstates_config(params):
    """Test 'pepc cstates config' command."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    good_options = [
        "--enable all",
        "--disable all",
        f"--enable {params['cstates'][-1]}",
        f"--disable {params['cstates'][-1]}",
        "--pkg-cstate-limit"]
    if prop_is_supported("c1_demotion", params["cstate_props"]):
        good_options += ["--c1-demotion", "--c1-demotion on", "--c1-demotion off"]
    if prop_is_supported("c1_undemotion", params["cstate_props"]):
        good_options += ["--c1-undemotion", "--c1-undemotion on", "--c1-undemotion off"]
    if prop_is_supported("c1e_autopromote", params["cstate_props"]):
        good_options += ["--c1e-autopromote", "--c1e-autopromote on", "--c1e-autopromote off"]
    if prop_is_supported("cstate_prewake", params["cstate_props"]):
        good_options += ["--cstate-prewake", "--cstate-prewake on", "--cstate-prewake off"]

    for option in good_options:
        run_pepc(f"cstates config {option}", pman)

        for scope in scope_options["good"]:
            run_pepc(f"cstates config {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"cstates config {option} {scope}", pman, exp_exc=Error)

    bad_options = [
        "--enable CC0",
        "--disable CC0"
        "--cstate-prewake meh"]

    for option in bad_options:
        run_pepc(f"cstates config {option}", pman, exp_exc=Error)

        for scope in scope_options["good"]:
            run_pepc(f"cstates config {option} {scope}", pman, exp_exc=Error)

        for scope in scope_options["bad"]:
            run_pepc(f"cstates config {option} {scope}", pman, exp_exc=Error)

    # Options tested without 'scope_options'.
    good_options = []
    bad_options = []

    if prop_is_supported("governor", params["pstate_props"]):
        good_options += ["--governor menu"]
        bad_options += ["--governor reardenmetal"]

    for option in good_options:
        run_pepc(f"cstates config {option}", pman)
    for option in bad_options:
        run_pepc(f"cstates config {option}", pman, exp_exc=Error)
