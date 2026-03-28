#!/usr/bin/env python
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Add custom options for the tests."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import typing
from pathlib import Path
import pytest
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.emul.EmulCommon import EMUL_CONFIG_FNAME

if typing.TYPE_CHECKING:
    from typing import Generator, Final

# Configure the 'main.pepc' logger with an empty argv so the log level defaults to INFO,
# regardless of how pytest was invoked (e.g., 'pytest -q' would otherwise set it to WARNING).
Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix="pepc", argv=[])

# The test modules that are host-agnostic.
_NOHOST_MODULES: Final[frozenset[str]] = frozenset({
    "tests.test_human",
    "tests.test_kernel_version",
    "tests.test_tpmi_nohost",
    "tests.test_wrap_exceptions",
    "tests.test_yaml",
})

# The test modules that work only on the local host or a remote host, but not emulation.
_NOEMULATION_MODULES: Final[frozenset[str]] = frozenset({"tests.test_process_manager"})

# The special '--dataset' option value meaning "run tests on all available datasets".
_ALL_DATASETS: Final[str] = "all"

def pytest_addoption(parser: pytest.Parser):
    """Add custom command-line options for pytest."""

    text = """Name of the host to run the test on. The default value is "emulation", which means
              running on emulated system. Emulation requires a dataset, and there are many datasets
              available in the "emul-data" subdirectory."""
    parser.addoption("-H", "--host", dest="hostname", default="emulation", help=text)

    text = """Name of the user to use for logging into the remote host over SSH. The default user
              name is 'root'."""
    parser.addoption("-U", "--username", dest="username", default="", help=text)

    text = """This option specifies the dataset to use for emulation. By default, all datasets are
              used. Please, find the available datasets in the "emul-data" subdirectory."""
    parser.addoption("-D", "--dataset", dest="dataset", default=_ALL_DATASETS, help=text)

def _get_datasets() -> Generator[str, None, None]:
    """
    Find and yield the names of all dataset directories in 'tests/emul-data'.

    Yields:
        The name of each valid dataset directory in 'tests/emul-data'.
    """

    basepath = Path(__file__).parent.resolve() / "emul-data"
    for dirname in os.listdir(basepath):
        datapath = Path(f"{basepath}/{dirname}")
        if datapath.is_dir() and (datapath / EMUL_CONFIG_FNAME).exists():
            yield dirname

def pytest_generate_tests(metafunc: pytest.Metafunc):
    """
    Parametrize test cases based on custom options.

    Args:
        metafunc: The pytest 'Metafunc' object that provides information about the test function
                  being collected.
    """

    assert metafunc.module is not None

    if metafunc.module.__name__ in _NOHOST_MODULES:
        return

    hostname = metafunc.config.getoption("hostname")
    username = metafunc.config.getoption("username")
    dataset = metafunc.config.getoption("dataset")
    assert isinstance(hostname, str)
    assert isinstance(username, str)
    assert isinstance(dataset, str)

    if username and hostname == "emulation":
        raise pytest.UsageError("The '--username' option can only be used with real hosts")

    if hostname != "emulation":
        metafunc.parametrize("hostspec", [hostname], scope="module")
        if not username:
            username = "root"
        metafunc.parametrize("username", [username], scope="module")
    elif metafunc.module.__name__ in _NOEMULATION_MODULES:
        # This is the emulation case, but the test is supposed to run with the local process
        # manager, not with the emulation process manager.
        metafunc.parametrize("hostspec", ["localhost"], scope="module")
        metafunc.parametrize("username", [username], scope="module")
    else:
        if dataset == _ALL_DATASETS:
            params: list[str] = []
            for dataset in _get_datasets():
                params.append(f"emulation:{dataset}")
        else:
            params = [f"emulation:{dataset}"]

        metafunc.parametrize("hostspec", params, scope="module")
        metafunc.parametrize("username", [username], scope="module")

def pytest_configure(config: pytest.Config):
    """
    Configure pytest before running tests.

    Args:
        config: The pytest configuration object.

    Raises:
        pytest.exit: If the specified dataset does not exist.
    """

    hostname = config.getoption("hostname")
    dataset = config.getoption("dataset")
    assert isinstance(hostname, str)
    assert isinstance(dataset, str)

    if hostname == "emulation" and dataset != _ALL_DATASETS:
        path = Path(__file__).parent.resolve() / "emul-data" / dataset

        if not path.exists():
            raise pytest.exit(f"Did not find dataset '{dataset}'.")

    print(f"Test parameters: hostname: {hostname}, dataset: '{dataset}'")
