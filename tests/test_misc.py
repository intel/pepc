#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Misc tests for pepc."""

import random
import pytest
import common
from pepclibs import CPUInfo, PStates, CStates, _PropsCache

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, username):
    """Yield a dictionary with information we need for testing."""

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo

        yield params

def test_unknown_cpu_model(params):
    """
    Test that property objects (such as 'PStates' and 'CStates') don't fail when getting a property
    on an unknown CPU model.
    """

    pman = params["pman"]

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        cpuinfo.info["model"] = 0

        with PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            pname = next(iter(pobj.props))
            pobj.get_cpu_prop(pname, 0)

        with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            pname = next(iter(pobj.props))
            pobj.get_cpu_prop(pname, 0)

def test_propscache_scope(params):
    """This function tests that the 'PropsCache' class caches a value to the correct CPUs."""

    siblings = {}
    pman = params["pman"]
    cpuinfo = params["cpuinfo"]

    mname = "sysfs"
    test_cpu = random.choice(cpuinfo.get_cpus())
    pcache = _PropsCache.PropsCache(cpuinfo=cpuinfo, pman=pman)

    for sname in CPUInfo.SCOPE_NAMES:
        # Value of 'val' and 'pname' do not matter, as long as they are unique.
        val = object()
        pname = object()

        pcache.add(pname, test_cpu, val, mname, sname=sname)

        if sname not in siblings:
            siblings[sname] = params["cpuinfo"].get_cpu_siblings(test_cpu, sname=sname)
        cpus = siblings[sname]

        for cpu in cpuinfo.get_cpus():
            res = pcache.is_cached(pname, cpu, mname)
            if cpu in cpus:
                assert pcache.get(pname, cpu, mname) == val
            else:
                assert res is False
