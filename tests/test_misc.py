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

import sys
import random
import common
import props_common
from pepclibs import CPUInfo, PStates, CStates, _PropsCache
from pepctool import _Pepc

def test_unknown_cpu_model(hostspec):
    """
    This function tests that property objects (such as 'PStates' and 'CStates') don't fail when
    getting a property on an unknown CPU model.
    """

    emul_modules = ["CPUInfo", "PStates", "CStates"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        cpuinfo.info["model"] = 0

        with PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            pname = next(iter(pobj.props))
            pobj.get_cpu_prop(pname, 0)

        with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            pname = next(iter(pobj.props))
            pobj.get_cpu_prop(pname, 0)

def test_propscache_scope(hostspec):
    """This function tests that the 'PropsCache' class caches a value to the correct CPUs."""

    emul_modules = ["CPUInfo"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:

        test_cpu = random.choice(cpuinfo.get_cpus())
        siblings = props_common.get_siblings(cpuinfo, cpu=test_cpu)

        pcache = _PropsCache.PropsCache(cpuinfo=cpuinfo, pman=pman)

        snames = {"global", "package", "die", "core", "CPU"}

        for sname in snames:
            # Value of 'val' and 'pname' do not matter, as long as they are unique.
            val = sname
            pname = sname

            pcache.add(pname, test_cpu, val, sname=sname)

            for cpu in cpuinfo.get_cpus():
                res = pcache.is_cached(pname, cpu)
                if cpu in siblings[sname]:
                    assert pcache.get(pname, cpu) == val
                else:
                    assert res is False

def test_parse_arguments(hostspec): # pylint: disable=unused-argument
    """This function tests 'parse_arguments()' with options that should raise 'SystemExit'."""

    for option in ("", "-h", "--version", "--hello"):
        sys.argv = [_Pepc.__file__, option]
        try:
            _Pepc.parse_arguments()
        except Exception: # pylint: disable=broad-except
            assert False, f"'pepc {option}' raised an exception"
        except SystemExit:
            continue
        assert False, f"'pepc {option}' didn't system exit"
