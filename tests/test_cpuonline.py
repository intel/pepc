#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test for the 'CPUOnline' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
import pytest
import common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo, CPUOnline

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuonline: A 'CPUOnline.CPUOnline' object.
            cpuinfo: A 'CPUInfo.CPUInfo' object.
        """

        cpuonline: CPUOnline.CPUOnline
        cpuinfo: CPUInfo.CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str,
               username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required 'CPUInfo' tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        yield params

def test_cpuonline_good(params: _TestParamsTypedDict):
    """
    Test the 'CPUOnline' class methods with valid input parameters.

    Args:
        params: The test parameters.
    """

    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]

    # Online all CPUs.
    off_cpus = cpuinfo.get_offline_cpus()
    onl.online(off_cpus)

    cpus = cpuinfo.get_cpus()
    try:
        offline_cpus = set()
        # Offline every 2nd CPU.
        for cpu in cpus:
            if cpu % 2 == 0:
                with contextlib.suppress(ErrorNotSupported):
                    onl.offline(cpus=(cpu,))
                    offline_cpus.add(cpu)
        # Offline every 3rd CPU.
        for cpu in cpus:
            if cpu % 3 == 0:
                with contextlib.suppress(ErrorNotSupported):
                    onl.offline(cpus=(cpu,))
                    offline_cpus.add(cpu)
        # Verify online/offline status.
        for cpu in cpus:
            if cpu in offline_cpus:
                assert not onl.is_online(cpu)
            else:
                assert onl.is_online(cpu)
    finally:
        with contextlib.suppress(Error):
            # Online everything and verify.
            for cpu in cpus:
                onl.online(cpus=(cpu,))

def test_cpuonline_bad(params: _TestParamsTypedDict):
    """
    Test the 'CPUOnline' class methods with invalid input values.

    Args:
        params: The test parameters.
    """

    onl = params["cpuonline"]
    bad_cpus = [-1, "one", True, 99999]

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.online(cpus=[cpu]) # type: ignore

    with pytest.raises(Error):
        onl.offline(cpus=[0], skip_unsupported=False)

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.offline(cpus=[cpu]) # type: ignore

    for cpu in bad_cpus:
        with pytest.raises(Error):
            onl.is_online(cpu) # type: ignore
