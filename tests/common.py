#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Common bits for the 'pepc' tests."""

from pathlib import Path
import pytest
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.helperlibs import EmulProcs, Procs, SSH

def get_proc(hostname, dataset):
    """Depending on the 'hostname' argument, return emulated 'Proc', real 'Proc' or 'SSH' object."""

    if hostname == "emulation":
        proc = EmulProcs.EmulProc()

        datapath = Path(__file__).parent.resolve() / "data" / dataset
        proc.init_testdata("CPUInfo", datapath)

        return proc

    if hostname == "localhost":
        return Procs.Proc()

    return SSH.SSH(hostname=hostname, username='root', timeout=10)

@pytest.fixture(name="proc")
def fixture_proc(hostname, dataset):
    """
    The test fixture is called before each test function. Yields the 'Proc' object, and closes it
    after the test function returns.
    """

    proc = get_proc(hostname, dataset)
    yield proc
    proc.close()

@pytest.fixture(name="cpuinfo")
def fixture_cpuinfo(proc):
    """Same as the 'fixture_proc()', but yields the 'CPUInfo' object."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        yield cpuinfo

@pytest.fixture(name="msr", params=[True, False], ids=["cache_enabled", "cache_disabled"])
def fixture_msr(request, proc): # pylint: disable=unused-argument
    """Same as the 'fixture_proc()', but yields the 'MSR' object."""

    with MSR.MSR(proc=proc, enable_cache=request.param) as msr:
        yield msr
