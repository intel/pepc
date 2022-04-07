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
from pepclibs.helperlibs import ProcessManager

def get_pman(hostname, dataset):
    """
    Returns the process manager for host 'hostname' using the 'dataset' data for emulation.
    """

    datapath = None
    username = None
    if hostname == "emulation":
        datapath = Path(__file__).parent.resolve() / "data" / dataset
    elif hostname != "localhost":
        username = "root"

    return ProcessManager.get_pman(hostname, username=username, datapath=datapath)

def get_datasets():
    """Find all directories in 'tests/data' directory and yield the directory name."""

    basepath = Path(__file__).parent.resolve() / "data"
    for dirname in os.listdir(basepath):
        if not Path(f"{basepath}/{dirname}").is_dir():
            continue
        yield dirname
