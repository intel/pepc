#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'aspm' command."""

from common import run_pepc, get_pman
# Fixtures need to be imported explicitly
from common import build_params, get_params # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error

def test_aspm_info(params):
    """Test 'pepc aspm info' command."""

    pman = get_pman(params["hostname"], params["dataset"], modules="ASPM")
    run_pepc("aspm info", pman)

def test_aspm_config(params):
    """Test 'pepc aspm config' command."""

    # The ASPM policy is changed by writing profile name to sysfs file
    # '/sys/module/pcie_aspm/parameters/policy'. The selected profile appears in square brackets
    # among all available profiles. For example, if "performance" profile is selected, the output
    # would be: 'default [performance] powersave powersupersave'. Emulating this behavior would need
    # wrapping file read/write methods, and is not supported for emulated hosts.
    good_options = ["", "--policy"]
    if params["hostname"] != "emulation":
        good_options = ["--policy performance", "--policy powersave", "--policy powersupersave"]

    pman = get_pman(params["hostname"], params["dataset"], modules="ASPM")
    for option in good_options:
        run_pepc(f"aspm config {option}", pman)

    run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)
