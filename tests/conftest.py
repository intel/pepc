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
import pytest

# The test modules that are host-agnostic.
_NOHOST_MODULES = {"test_human"}

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
        # The "common" dataset contains data for all SUTs and does not represent a single host, so
        # skip it.
        if dirname == "common":
            continue

        datapath = Path(f"{basepath}/{dirname}")
        if datapath.is_dir():
            yield dirname

def pytest_generate_tests(metafunc):
    """Generate tests with custom options."""

    if metafunc.module.__name__ in _NOHOST_MODULES:
        return

    hostname = metafunc.config.getoption("hostname")
    dataset = metafunc.config.getoption("dataset")

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

def pytest_configure(config):
    """Verify the existence of requested dataset."""

    hostname = config.getoption("hostname")
    dataset = config.getoption("dataset")

    if hostname == "emulation" and dataset != "all":
        path = Path(__file__).parent.resolve() / "data" / dataset

        if not path.exists():
            raise pytest.exit(f"Did not find dataset '{dataset}'.")

    print(f"Test parameters: hostname: {hostname}, dataset: '{dataset}'")
