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
import common
import pcstates_common
from pepclibs import CPUInfo, _PropsCache

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["test_cpu"] = random.choice(cpuinfo.get_cpus())
        params["fellows"] = pcstates_common.get_fellows(cpuinfo, cpu=params["test_cpu"])

        yield params

def test_propscache_scope(params):
    """This functions tests that the PropsCache class caches a value to the correct CPUs."""

    test_cpu = params["test_cpu"]
    cpuinfo = params["cpuinfo"]

    pcache = _PropsCache.PropsCache(cpuinfo=cpuinfo, pman=params["pman"])

    snames = {"global", "package", "die", "core", "CPU"}

    for sname in snames:
        # Value of 'val' and 'pname' do not matter, as long as they are unique.
        val = sname
        pname = sname

        pcache.add(pname, test_cpu, val, sname=sname)

        for cpu in cpuinfo.get_cpus():
            res = pcache.is_cached(pname, cpu)
            if cpu in params["fellows"][sname]:
                assert pcache.get(pname, cpu) == val
            else:
                assert res is False
