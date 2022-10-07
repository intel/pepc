#!/usr/bin/env python
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>
#         Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This configuration file adds the custom '--host' option for the tests."""

import os
from pathlib import Path

def pytest_addoption(parser):
    """Add custom pytest options."""

    text = """Name of the host to run the test on. The default value is "emulation", which means
              running on emulated system. Emulation requires a dataset, and there are many datasets
              available in the "data" subdirectory."""
    parser.addoption("-H", "--host", dest="hostname", default="emulation", help=text)

    text = """This option specifies the dataset to use for emulation. By default, all datasets are
              used. Please, find the available datasets in the "data" subdirectory."""
    parser.addoption("-D", "--dataset", dest="dataset", default="all", help=text)

def get_datasets():
    """Find all directories in 'tests/data' directory and yield the directory name."""

    basepath = Path(__file__).parent.resolve() / "data"
    for dirname in os.listdir(basepath):
        datapath = Path(f"{basepath}/{dirname}")
        if datapath.is_dir():
            yield dirname

def pytest_generate_tests(metafunc):
    """Generate tests with custom options."""

    hostname = metafunc.config.getoption("hostname")
    dataset = metafunc.config.getoption("dataset")

    print(f"Test parameters: hostname: {hostname}, dataset: '{dataset}'")

    if hostname != "emulation":
        metafunc.parametrize("hostspec", [hostname], scope="module")
    else:
        if dataset == "all":
            params = []
            for dataset in get_datasets():
                params.append(f"emulation:{dataset}")
        else:
            params = [f"emulation:{dataset}"]

        metafunc.parametrize("hostspec", params, scope="module")
