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
from common import build_params, get_params # pylint: disable=unused-import
from pepclibs import CPUOnline
from pepclibs.helperlibs.Exceptions import Error

def test_cpuonline_good(params):
    """Test public methods of 'CPUOnline' class with good option values."""

    with CPUOnline.CPUOnline(pman=params["pman"]) as onl:
        # Note: When using "all" or 'None' as 'cpus' argument value to 'online()' or 'offline()'
        # methods, offlined CPUs will be eventually read using 'lscpu' command. The output of
        # 'lscpu' command is emulated, but changed offline/online CPUs is not reflected to the
        # output.
        onl.online(cpus="all")
        for cpu in params["cpus"]:
            if cpu == 0:
                continue
            assert onl.is_online(cpu)

        if params["hostname"] != "emulation":
            return

        if params["testcpus"].count(0):
            params["testcpus"].remove(0)

        onl.offline(cpus=params["testcpus"])
        for cpu in params["testcpus"]:
            assert not onl.is_online(cpu)

        onl.online(params["cpus"], skip_unsupported=True)
        for cpu in params["cpus"]:
            if cpu == 0:
                continue
            assert onl.is_online(cpu)

        onl.offline(cpus=params["cpus"], skip_unsupported=True)
        onl.restore()
        for cpu in params["cpus"]:
            if cpu == 0:
                continue
            assert onl.is_online(cpu)

def test_cpuonline_bad(params):
    """Test public methods of 'CPUOnline' class with bad option values."""

    bad_cpus = [-1, "one", True, params["cpus"][-1] + 1]

    with CPUOnline.CPUOnline(pman=params["pman"]) as onl:
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

        bad_cpus.append(0)
        for cpu in bad_cpus:
            with pytest.raises(Error):
                onl.is_online(cpu)
