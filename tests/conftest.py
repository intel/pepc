#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Add custom options and parametrization rules for the tests.

Centralize the rules that decide where a test runs and which emulation datasets it uses. The
supported execution targets are the following.

- Local host: Run a test on the system where pytest executes.
- Remote host: Run a test on a real remote host reached over SSH.
- Emulation dataset: Run a test locally through the emulation layer using recorded host data in
  tests/emul-data. The test does not modify the local host, because operations such as offlining a
  CPU are redirected to the emulated host model instead.

Some tests need host capabilities such as C-states, ASPM, or other hardware-facing interfaces.
These tests can run on a real host or on emulation data providing the required files and
behavior. Other tests do not need host capabilities at all.

The test categories are the following.

- Host-independent tests run locally, but they neither depend on host-specific state nor modify host
  configuration.
  Example: 'tests/test_yaml.py'.
- Host-dependent tests need host capabilities and split into the following sub-groups.
  - Emulation-capable tests can run on a real host or on emulation datasets.
    Example: 'tests/test_cstates.py'.
  - Real-host-only tests can run on the local host or a remote host, but never on emulation.
    Example: 'tests/test_process_manager.py'.

The command line options map to execution targets as follows.

- '-H <hostname>' with optional '-U <username>': Run on a real remote host reached over SSH.
    This option can be combined with '-D' for emulation-capable tests to run the same test on the
    requested real host and on the requested emulation dataset selection.
- '-H localhost': Run on the local host.
    WARNING: This may modify the local host configuration, for example by offlining CPUs, which may
             affect the system's performance and stability. Without root access or passwordless
             sudo, many host-dependent tests will fail due to insufficient permissions.
- '-D <dataset>': Run on the named emulation dataset.
- '-D all': Run host-dependent tests on all emulation datasets.
- No option: Use the default execution target and dataset selection policy. This is the safest
  choice when you do not need to force a specific real host or dataset selection.

The "no option" behavior and '-D all' differ as follows.

- '-D all': Emulation-capable host-dependent tests run on all emulation datasets.
- No option: real-host-only tests run on 'localhost', while emulation-capable host-dependent
  tests either run on all emulation datasets or on one or a few representative datasets when they
  only need specific emulated features and broader dataset coverage adds little value.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import logging
from pathlib import Path
import pytest
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.emul.EmulCommon import EMUL_CONFIG_FNAME

if typing.TYPE_CHECKING:
    from typing import Generator, Final

# Host-independent tests.
_HOST_INDEPENDENT_MODULES: Final[frozenset[str]] = frozenset({
    "tests.test_human",
    "tests.test_kernel_version",
    "tests.test_logging_cmdl",
    "tests.test_tpmi_nohost",
    "tests.test_wrap_exceptions",
    "tests.test_yaml",
})

# Real-host-only host-dependent tests.
_REAL_HOST_ONLY_MODULES: Final[frozenset[str]] = frozenset({
    "tests.test_process_manager",
    "tests.test_python_prj_installer"
})

# The special '--dataset' option value meaning "run tests on all available datasets".
_ALL_DATASETS: Final[str] = "all"

# The default '--dataset' option value meaning the user did not explicitly request a dataset.
_NO_DATASET: Final[str] = ""

# Default emulation datasets for tests when the user did not explicitly provide '--dataset'.
_DEFAULT_DATASETS: Final[dict[str, tuple[str, ...]]] = {
    # 'cpx0' provides the global ASPM policy sysfs file and multiple PCI 'l1_aspm' files, which
    # is sufficient coverage for the 'test_aspm_cmdl' tests.
    "tests.test_aspm_cmdl": ("cpx0",),
    # Use one single-package topology and one larger topology with dies for the CPU hotplug
    # command tests.
    "tests.test_cpuhotplug_cmdl": ("bdwup0", "cpx0"),
    # Use a hybrid client platform and an SRF platform (which has modules) for the 'CPUOnline'
    # module tests. These cover different topologies than 'test_cpuhotplug_cmdl'.
    "tests.test_cpuonline": ("adl0", "srf2"),
    # '_OpTarget' maps CLI options to CPU sets based on topology shape, not CPU architecture. Four
    # datasets cover all meaningful shapes: simple single-package server, hybrid client, globally
    # unique die IDs (clxap1, unlike the per-package die IDs on cpx0/gnr0), and module topology
    # (srf2). 'clxap1' and 'srf2' are shared with 'test_topology_cmdl'.
    "tests.test_optarget": ("bdwup0", "adl0", "clxap1", "srf2"),
    # 'pepc topology' displays topology, not CPU-architecture features. Same reasoning as
    # 'test_optarget'. Uses different datasets where possible: multi-package with sysfs die IDs
    # (cpx0) and multi-package with MSR-enumerated die IDs that are not globally unique (gnr0),
    # plus the two shared quirk datasets.
    "tests.test_topology_cmdl": ("cpx0", "gnr0", "clxap1", "srf2"),
    # 'PerCPUCache' caches by CPU scope in pure Python. One simple and one complex topology
    # are enough: 'bdwup0' (single-package, no dies or modules) and 'srf2' (modules present).
    "tests.test_percpucache": ("bdwup0", "srf2"),
    # PM QoS is a Linux kernel feature, not CPU-architecture specific. One dataset is enough.
    "tests.test_pmqos_cmdl": ("bdwup0",),
}

def pytest_addoption(parser: pytest.Parser):
    """Add custom command-line options for pytest."""

    text = """Name of the host to run the tests on. By default, tests use emulation with the
              dataset-selection policy described by '--dataset'. Provide a hostname to run the
              tests on a real remote host instead. This option can be combined with '--dataset'
              for emulation-capable tests."""
    parser.addoption("-H", "--host", dest="hostname", default="emulation", help=text)

    text = """Name of the user to use for logging into the remote host over SSH. By default,
              the user name is looked up in SSH configuration files, and if not found, the
              current user name is used. This option applies to remote-host runs."""
    parser.addoption("-U", "--username", dest="username", default="", help=text)

    text = """Select the dataset to use for emulation. By default, dataset selection depends on
              the test: emulation-capable tests that benefit from broader coverage run on all
              datasets, while others may run on one or a few representative datasets providing the
              needed features. Provide '-D all' to force running emulation-capable tests on all
              datasets. This option can be combined with '--host' for emulation-capable tests.
              Find the available datasets in the "emul-data" subdirectory."""
    parser.addoption("-D", "--dataset", dest="dataset", default=_NO_DATASET, help=text)

def _get_all_datasets() -> Generator[str, None, None]:
    """
    Find and yield the names of all dataset directories in 'tests/emul-data'.

    Yields:
        The name of each valid dataset directory in 'tests/emul-data'.
    """

    basepath = Path(__file__).parent.resolve() / "emul-data"
    for datapath in basepath.iterdir():
        if datapath.is_dir() and (datapath / EMUL_CONFIG_FNAME).exists():
            yield datapath.name

def pytest_generate_tests(metafunc: pytest.Metafunc):
    """
    Parametrize test cases based on custom options.

    Here this means pytest may run the same test multiple times with different 'hostspec'
    values, for example a single run for 'localhost' or a single run per emulation dataset.
    The matching 'username' value is collected alongside it.

    Args:
        metafunc: The pytest object describing the test that is about to be run.
    """

    assert metafunc.module is not None

    test_name = metafunc.module.__name__

    # Host-independent tests do not use the 'hostspec' and 'username' parameters, so leave them
    # unparametrized and let pytest run each test only once.
    if test_name in _HOST_INDEPENDENT_MODULES:
        return

    hostname = metafunc.config.getoption("hostname")
    username = metafunc.config.getoption("username")
    dataset = metafunc.config.getoption("dataset")

    assert isinstance(hostname, str)
    assert isinstance(username, str)
    assert isinstance(dataset, str)

    # Choose which real host or emulation datasets pytest will run this test with.
    if hostname != "emulation" and test_name in _REAL_HOST_ONLY_MODULES:
        # A real host was requested for a real-host-only test, so parametrize only that host.
        # Ignore any accompanying '--dataset' request because these tests never run on emulation.
        metafunc.parametrize("hostspec", [hostname], scope="module")
    elif hostname != "emulation":
        # A real host was requested for an emulation-capable test. Run on the requested real host,
        # and if '--dataset' was also provided, add the requested emulation dataset selection.
        hostspecs = [hostname]

        if dataset == _ALL_DATASETS:
            for dset in _get_all_datasets():
                hostspecs.append(f"emulation:{dset}")
        elif dataset != _NO_DATASET:
            hostspecs.append(f"emulation:{dataset}")

        metafunc.parametrize("hostspec", hostspecs, scope="module")
    elif test_name in _REAL_HOST_ONLY_MODULES:
        # No real host was requested, but this test needs one. Skip explicit emulation runs, and
        # use the local host only for the default no-option case.
        if dataset == _NO_DATASET:
            metafunc.parametrize("hostspec", ["localhost"], scope="module")
        else:
            pytest.skip("Real-host-only tests do not run with emulation datasets.")
    else:
        # Either explicitly requested emulation or the no-option case for an emulation-capable
        # test.
        if dataset == _NO_DATASET:
            # The no-option case: use the default dataset selection policy.
            default_datasets = _DEFAULT_DATASETS.get(test_name, ())
            params: list[str] = []

            if default_datasets:
                for dset in default_datasets:
                    params.append(f"emulation:{dset}")
            else:
                for dset in _get_all_datasets():
                    params.append(f"emulation:{dset}")
        elif dataset == _ALL_DATASETS:
            # The '-D all' case: run on all datasets.
            params = []
            for dset in _get_all_datasets():
                params.append(f"emulation:{dset}")
        else:
            # The specified dataset case.
            params = [f"emulation:{dataset}"]

        metafunc.parametrize("hostspec", params, scope="module")

    metafunc.parametrize("username", [username], scope="module")

def pytest_configure(config: pytest.Config):
    """
    Configure pytest before running tests.

    Args:
        config: The pytest configuration object.

    Raises:
        pytest.exit: The specified dataset does not exist.
    """

    # Configure the pepc logger. Read the log level from the pytest config so that
    # '--log-cli-level=DEBUG' makes pepc emit debug messages.
    log_level_str = config.getoption("log_cli_level")
    if log_level_str and isinstance(log_level_str, str):
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    else:
        log_level = logging.INFO
    Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix="pepc", level=log_level,
                                                                    argv=[])

    hostname = config.getoption("hostname")
    dataset = config.getoption("dataset")

    assert isinstance(hostname, str)
    assert isinstance(dataset, str)

    if hostname == "emulation" and dataset not in (_NO_DATASET, _ALL_DATASETS):
        path = Path(__file__).parent.resolve() / "emul-data" / dataset

        if not path.exists():
            raise pytest.exit(f"Did not find dataset '{dataset}'.")
