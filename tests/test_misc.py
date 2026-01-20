#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Misc tests for pepc."""

# TODO: Add a test that --force-color works as expected.
# TODO: Add test for KernelVersion module - it is not covered anywhere.

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import random
import pytest
from tests import common
from pepclibs import CPUInfo, PStates, CStates, _PropsCache

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
        """

        cpuinfo: CPUInfo.CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo

        yield params

def test_unknown_cpu_model(params: _TestParamsTypedDict):
    """
    Test behavior of property objects when querying properties on an unknown CPU model.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        cpuinfo.proc_cpuinfo["model"] = 0

        with PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            for pname in pobj.props:
                if pobj.prop_is_supported_cpu(pname, 0):
                    pobj.get_cpu_prop(pname, 0)
                    break

        with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as pobj:
            for pname in pobj.props:
                if pobj.prop_is_supported_cpu(pname, 0):
                    pobj.get_cpu_prop(pname, 0)
                    break

def test_propscache_scope(params: _TestParamsTypedDict):
    """
    Test that the 'PropsCache' class correctly caches values according to CPU scope.

    Args:
        params: The test parameters.
    """

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
