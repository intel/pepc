#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test public methods of the 'CPUOnline' module."""

import contextlib
import pytest
import common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo, CPUOnline

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """
    Build and yield the testing parameters dictionary. The arguments are as follows.
      * hostspec - the specification of the host to run the tests on.
    """

    emul_modules = ["CPUInfo", "CPUOnline"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        yield params

def test_cpuonline_good(params):
    """
    Test public methods of the 'CPUOnline' class with good input. The arguments are as follows.
      * params - the testing parameters.
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

def test_cpuonline_bad(params):
    """
    Test public methods of the 'CPUOnline' class with bad input. The arguments are as follows.
      * params - the testing parameters.
    """

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
