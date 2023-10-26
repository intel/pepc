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

import pytest
import common
from pepclibs.helperlibs.Exceptions import Error

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["ASPM", "Systemctl"]

    with common.get_pman(hostspec, modules=emul_modules) as pman:
        params = common.build_params(pman)
        yield params

def test_aspm_info(params):
    """Test 'pepc aspm info' command."""

    common.run_pepc("aspm info", params["pman"])

def test_aspm_config(params):
    """Test 'pepc aspm config' command."""

    pman = params["pman"]

    good = [
        "",
        "--policy",
        "--policy performance",
        "--policy powersave",
        "--policy powersupersave"]

    for option in good:
        common.run_pepc(f"aspm config {option}", pman)

    common.run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)
