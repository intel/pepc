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

def test_v1_aspm_info():
    """Test 'pepc aspm info' command."""
    run_pepc("aspm info", exp_ret=0)

def test_v1_aspm_config():
    """Test 'pepc aspm config' command."""

    good_options = [
        "",
        "--policy",
        "--policy default",
        "--policy performance",
        "--policy powersave",
        "--policy powersupersave"]

    for option in good_options:
        run_pepc(f"aspm config {option}", exp_ret=0)

    run_pepc("aspm config --policy badpolicyname", exp_ret=-1)
