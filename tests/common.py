#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Common bits for the 'pepc' tests."""

from pathlib import Path
import pytest
from pepclibs.helperlibs import EmulProcs, Procs, SSH

def get_proc(hostname):
    """Depending on the 'hostname' argument, return emulated 'Proc', real 'Proc' or 'SSH' object."""

    if hostname == "emulation":
        proc = EmulProcs.EmulProc()

        datapath = Path(__file__).parent.resolve() / "data"
        proc.init_testdata(datapath)

        return proc

    if hostname == "localhost":
        return Procs.Proc()

    return SSH.SSH(hostname=hostname, username='root', timeout=10)

@pytest.fixture(name="proc")
def fixture_proc(hostname, dataset): # pylint: disable=unused-argument
    """
    The test fixture is called before each test function. Yields the 'Proc' object, and closes it
    after the test function returns.
    """

    proc = get_proc(hostname)
    yield proc
    proc.close()
