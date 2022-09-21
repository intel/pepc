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
from common import build_params, get_pman, get_datasets
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset = request.param
    with get_pman(hostname, dataset) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as onl:
        params = build_params(hostname, dataset, pman, cpuinfo)

        params["onl"] = onl
        params["cpu_onl_status"] = {}

        for cpu in params["cpus"]:
            params["cpu_onl_status"][cpu] = onl.is_online(cpu)

        yield params

def _restore_cpus_onl_status(params):
    """Restore CPUs to the original online/offline status."""

    for cpu, onl_status in params["cpu_onl_status"].items():
        if onl_status is True:
            params["onl"].online(cpu, skip_unsupported=True)
        else:
            params["onl"].offline(cpu, skip_unsupported=True)

def test_cpuonline_good(params):
    """Test public methods of 'CPUOnline' class with good option values."""

    onl = params["onl"]

    # Note: When using "all" or 'None' as 'cpus' argument value to 'online()' or 'offline()'
    # methods, offlined CPUs will be eventually read using 'lscpu' command. The output of
    # 'lscpu' command is emulated, but changed offline/online CPUs is not reflected to the
    # output.
    onl.online(cpus="all")
    for cpu in params["cpus"]:
        assert onl.is_online(cpu)

    if params["hostname"] != "emulation":
        _restore_cpus_onl_status(params)
        return

    if params["testcpus"].count(0):
        params["testcpus"].remove(0)

    onl.offline(cpus=params["testcpus"])
    for cpu in params["testcpus"]:
        assert not onl.is_online(cpu)

    onl.online(params["cpus"], skip_unsupported=True)
    for cpu in params["cpus"]:
        assert onl.is_online(cpu)

    onl.offline(cpus=params["cpus"], skip_unsupported=True)
    onl.restore()
    for cpu in params["cpus"]:
        assert onl.is_online(cpu)

def test_cpuonline_bad(params):
    """Test public methods of 'CPUOnline' class with bad option values."""

    onl = params["onl"]
    bad_cpus = [-1, "one", True, params["cpus"][-1] + 1]

    with pytest.raises(Error):
        onl.online(cpus=[0], skip_unsupported=False)

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

    _restore_cpus_onl_status(params)
