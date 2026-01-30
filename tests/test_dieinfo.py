#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the public methods of the '_DieInfo' module."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest

from tests import common

from pepclibs import ProcCpuinfo, CPUModels, _DieInfo, CPUInfo

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.common import CommonTestParamsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            dieinfo: A '_DieInfo' instance.
        """

        dieinfo: _DieInfo.DieInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman:
        proc_cpuinfo = ProcCpuinfo.get_proc_cpuinfo(pman)
        if proc_cpuinfo["vfm"] not in CPUModels.MODELS_WITH_NONCOMP_DIES:
            pytest.skip(f"The CPU model '{proc_cpuinfo['vfm']}' does not support non-compute dies")
            # TODO: Cover compute dies as well

        params = common.build_params(pman)
        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        with _DieInfo.DieInfo(pman) as dieinfo:
            params["dieinfo"] = dieinfo
            yield params

def test_get_noncomp_dies(params: _TestParamsTypedDict):
    """Test the 'get_noncomp_dies()' method returns properly sorted package and die numbers."""

    dieinfo = params["dieinfo"]

    noncomp_dies = dieinfo.get_noncomp_dies()

    # Ensure the ascending package and die numbers.
    assert list(noncomp_dies) == sorted(noncomp_dies), \
           "The package numbers returned by 'get_noncomp_dies()' are not in ascending order"
    for package, dies in noncomp_dies.items():
        assert dies == sorted(dies), \
               f"The die numbers for package {package} returned by 'get_noncomp_dies()' are not " \
               f"in ascending order"

    # Verify that all packages are present by comparing with cpuinfo. Test 'get_tpmi()' at the same
    # time.
    with CPUInfo.CPUInfo(pman=params["pman"], dieinfo=dieinfo) as cpuinfo:
        packages = cpuinfo.get_packages()
        assert set(noncomp_dies) == set(packages), \
               "Package numbers from 'get_noncomp_dies()' don't match packages from CPUInfo"

        compute_dies = cpuinfo.get_compute_dies()

        for package, dies in noncomp_dies.items():
            compute_dies_set = set(compute_dies[package])
            noncomp_dies_set = set(dies)
            overlap = compute_dies_set.intersection(noncomp_dies_set)
            assert not overlap, f"Non-compute die numbers overlap with compute die numbers " \
                                 f"in package {package}: {overlap}"

def test_get_noncomp_dies_info(params: _TestParamsTypedDict):
    """
    Test the 'get_noncomp_dies_info()' method returns consistent information with
    'get_noncomp_dies()'.
    """

    dieinfo = params["dieinfo"]

    # Verify that the returned information is consistent with 'get_noncomp_dies()'.
    noncomp_dies = dieinfo.get_noncomp_dies()
    noncomp_dies_info = dieinfo.get_noncomp_dies_info()

    assert list(noncomp_dies) == list(noncomp_dies_info), \
           "The package numbers returned by 'get_noncomp_dies()' and 'get_noncomp_dies_info()' " \
           "do not match"

    for package, dies_info in noncomp_dies_info.items():
        dies: list[int] = []
        for die, die_info in dies_info.items():
            dies.append(die)
            assert die_info["package"] == package, \
                   f"The package number in the die info for package {package}, die {die} is " \
                   f"incorrect"
            assert die_info["die"] == die, \
                   f"The die number in the die info for package {package}, die {die} is incorrect"

        assert list(noncomp_dies[package]) == dies, \
               f"The die numbers for package {package} returned by 'get_noncomp_dies()' and " \
               f"'get_noncomp_dies_info()' do not match"
