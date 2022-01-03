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

from pathlib import Path
from common import get_proc
from pepclibs.msr import MSR, PMEnable, HWPRequest, MiscFeatureControl

# The MSR addresses that will be tested.
_ADDRS = (PMEnable.MSR_PM_ENABLE, MiscFeatureControl.MSR_MISC_FEATURE_CONTROL,
          HWPRequest.MSR_HWP_REQUEST)

def test_read_cpu(hostname):
    """Test the 'read_cpu()' method."""

    proc = get_proc(hostname)

    testdatapath = Path(__file__).parent.resolve() / "data"

    for cmd, datafile in (("lscpu --all -p=socket,node,core,cpu,online", "lscpu_info_cpus.txt"),
                              ("lscpu", "lscpu_info.txt"), ):
        with open(testdatapath / datafile) as fobj:
            proc._cmds[cmd] = fobj.readlines()

    for cmd, value in (("test -e '/dev/cpu/0/msr'", ""), ):
        proc._cmds[cmd] = value

    with MSR.MSR(proc=proc) as msr:
        for addr in _ADDRS:
            for cpu in (0, 1, 99):
                msr.read_cpu(addr, cpu=cpu)
