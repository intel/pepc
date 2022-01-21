#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Unittests for the public methods of the 'MSR' module."""

from common import fixture_proc, fixture_msr # pylint: disable=unused-import
from pepclibs.msr import PMEnable, HWPRequest, MiscFeatureControl

# The MSR addresses that will be tested.
_ADDRS = (PMEnable.MSR_PM_ENABLE, MiscFeatureControl.MSR_MISC_FEATURE_CONTROL,
          HWPRequest.MSR_HWP_REQUEST)

def test_read_cpu(msr):
    """Test the 'read_cpu()' method."""

    for addr in _ADDRS:
        for cpu in (0, 1, 99):
            msr.read_cpu(addr, cpu=cpu)
