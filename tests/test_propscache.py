#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Tests for the methods of the '_PropsCache' module."""

import random
import pytest
from common import build_params, get_pman, get_datasets
from pcstates_common import get_fellows
from pepclibs import CPUInfo, _PropsCache

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset = request.param
    with get_pman(hostname, dataset) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = build_params(hostname, dataset, pman, cpuinfo)
        params["cpuinfo"] = cpuinfo

        params["test_cpu"] = random.choice(params["cpus"])
        params["fellows"] = get_fellows(params, cpuinfo, cpu=params["test_cpu"])

        yield params

def test_propscache_scope(params):
    """This functions tests that the PropsCache class caches a value to the correct CPUs."""

    test_cpu = params["test_cpu"]
    pcache = _PropsCache.PropsCache(cpuinfo=params["cpuinfo"], pman=params["pman"])

    snames = {"global", "package", "die", "core", "CPU"}

    for sname in snames:
        # Value of 'val' and 'pname' do not matter, as long as they are unique.
        val = sname
        pname = sname

        pcache.add(pname, test_cpu, val, sname=sname)

        for cpu in params["cpus"]:
            res = pcache.is_cached(pname, cpu)
            if cpu in params["fellows"][sname]:
                assert pcache.get(pname, cpu) == val
            else:
                assert res is False
