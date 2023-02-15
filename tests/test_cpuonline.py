#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Tests for the public methods of the 'CPUOnline' module."""

import pytest
import common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "CPUOnline"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        params["online"] = cpuinfo.get_cpus()
        params["offline"] = cpuinfo.get_offline_cpus()
        yield params

def test_cpuonline_good(params):
    """Test public methods of 'CPUOnline' class with good option values."""

    if not common.is_emulated(params["pman"]):
        # On real hardware some CPUs might not support offlining/onlining.
        return

    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]

    # We need to initialize the topology, otherwise the topology will be re-created instead of
    # updated.
    cpuinfo.get_topology(levels=("CPU", ))
    # Skip first online CPU, because CPU 0 does not support offlining.
    onl.offline(cpus=params["online"][1:])
    offline = set(params["online"][1:])
    # When a CPU is offlined/onlined, CPUInfo topology should reflect the changes.
    for tline in cpuinfo.get_topology():
        if tline["CPU"] in offline:
            raise Error(f"CPU{tline['CPU']} was not updated in 'CPUInfo._topology'")

    onl.online(cpus="all")
    onl.offline(cpus=params["offline"])

    for cpu in params["online"]:
        assert onl.is_online(cpu)
    for cpu in params["offline"]:
        assert not onl.is_online(cpu)

def test_cpuonline_bad(params):
    """Test public methods of 'CPUOnline' class with bad option values."""

    onl = params["cpuonline"]
    bad_cpus = [-1, "one", True, 99999]

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.online(cpus=[cpu])

    with pytest.raises(Error):
        onl.offline(cpus=[0], skip_unsupported=False)

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.offline(cpus=[cpu])

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.is_online(cpu)
