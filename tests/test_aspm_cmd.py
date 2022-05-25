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

from common import run_pepc
# Fixtures need to be imported explicitly
from common import build_params, get_params # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error

def test_aspm_info(params):
    """Test 'pepc aspm info' command."""

    run_pepc("aspm info", params["pman"])

def test_aspm_config(params):
    """Test 'pepc aspm config' command."""

    pman = params["pman"]

    good_options = [
        "",
        "--policy",
        "--policy performance",
        "--policy powersave",
        "--policy powersupersave"]

    for option in good_options:
        run_pepc(f"aspm config {option}", pman)

    run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)
