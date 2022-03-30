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

import os
from pathlib import Path
from pepclibs.helperlibs import EmulProcs, LocalProcessManager, SSHProcessManager

def get_pman(hostname, dataset):
    """
    Depending on the 'hostname' argument, return emulated 'LocalProcessManager', real
    'LocalProcessManager' or 'SSHProcessManager' object.
    """

    if hostname == "emulation":
        pman = EmulProcs.EmulProc()

        datapath = Path(__file__).parent.resolve() / "data" / dataset
        pman.init_testdata("CPUInfo", datapath)

        return pman

    if hostname == "localhost":
        return LocalProcessManager.LocalProcessManager()

    return SSHProcessManager.SSHProcessManager(hostname=hostname, username='root', timeout=10)

def get_datasets():
    """Find all directories in 'tests/data' directory and yield the directory name."""

    basepath = Path(__file__).parent.resolve() / "data"
    for dirname in os.listdir(basepath):
        if not Path(f"{basepath}/{dirname}").is_dir():
            continue
        yield dirname
