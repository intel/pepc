#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#         Antti Laakso <antti.laakso@linux.intel.com>

"""Common functions for pepc tests."""

from __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path
import typing
from pepclibs import CPUInfo, CPUOnline
from pepclibs.helperlibs import ProcessManager, EmulProcessManager

if typing.TYPE_CHECKING:
    from typing import TypedDict, cast, Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class CommonTestParamsTypedDict(TypedDict):
        """
        A dictionary of common test parameters.

        Attributes:
            hostname: The hostname of the target system.
            pman: The process manager instance for managing processes on the target system.
        """

        hostname: str
        pman: ProcessManagerType

def get_test_data_path(testpath: str) -> Path:
    """
    Get the path to the test data for the specified test.

    Args:
        testpath: Path to the test for which to retrieve the data path. The intention is that the
                  caller passes __file__ as the argument.

    Returns:
        Path to the test data directory for the specified test.
    """

    path = Path(testpath).resolve()
    # Test name is the file name without the '.py' suffix.
    return path.parent / "test-data" / path.stem

def _get_emul_data_path(dataset: str) -> Path:
    """
    Get the path to the emulation data for the specified dataset.

    Args:
        dataset: Name of the dataset for which to retrieve the path.

    Returns:
        Path to the emulation data directory for the specified dataset.
    """

    return Path(__file__).parent.resolve() / "emul-data" / dataset

def is_emulated(pman: ProcessManagerType) -> bool:
    """
    Determine if the provided process manager corresponds to an emulated system.

    Args:
        pman: The process manager instance to check.

    Returns:
        True if the process manager corresponds to an emulated system, False otherwise.
    """

    return pman.hostname.startswith("emulation:")

def get_pman(hostspec: str, username: str = "") -> ProcessManagerType:
    """
    Create and return a process manager for the specified host.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: Name of the user to use for logging into the remote host over SSH.

    Returns:
        A process manager instance for the specified host. 'EmulProcessManager' in case of
        emulation, 'LocalProcessManager' for the localhost, and 'SSHProcessManager' for remote
        hosts.
    """

    dspath: Path | None = None
    if hostspec.startswith("emulation:"):
        dataset = hostspec.split(":", maxsplit=2)[1]
        dspath = _get_emul_data_path(dataset)

    pman = ProcessManager.get_pman(hostspec, username=username)

    if dspath:
        if typing.TYPE_CHECKING:
            pman = cast(EmulProcessManager.EmulProcessManager, pman)
        try:
            pman.init_emul_data(dspath)
        except:
            pman.close()
            raise

    return pman

def build_params(pman: ProcessManagerType) -> CommonTestParamsTypedDict:
    """
    Build and return a dictionary containing common test parameters.

    Args:
        pman: The process manager object that defines the host where the tests will be run.

    Returns:
        A 'CommonTestParams' object initialized with the hostname and process manager.
    """

    return {"hostname": pman.hostname, "pman": pman}

# TODO: Most if not all tests should use this, to stress-test the online/offline handling.
def get_cpuinfos(pman: ProcessManagerType) -> Generator[CPUInfo.CPUInfo, None, None]:
    """
    Yield 'CPUInfo' objects for testing based on the host type.

    Args:
        pman: Process manager object that defines the target host.

    Yields:
        'CPUInfo' objects configured according to the host type for use in tests.
    """

    # Ensure that all CPUs are online.
    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        cpuonline.online()

        # Pattern 0: All CPUs online
        yield cpuinfo

        # Pattern 1: Take odd-numbered CPUs offline.
        all_cpus = cpuinfo.get_cpus()
        odd_cpus = [cpu for cpu in all_cpus if cpu % 2 == 1]

        if odd_cpus:
            cpuonline.offline(cpus=odd_cpus)
            yield cpuinfo
            cpuonline.online(cpus=odd_cpus)

        # Pattern 2: Take even-numbered CPUs offline, excluding CPU 0, which can't be offlined.
        even_cpus = [cpu for cpu in all_cpus if cpu % 2 == 0 and cpu != 0]
        if even_cpus:
            cpuonline.offline(cpus=even_cpus)
            yield cpuinfo
            cpuonline.online(cpus=even_cpus)

        # Pattern 3: Take the second core offline.
        cores = cpuinfo.get_package_cores(package=0)
        if len(cores) > 1:
            cpus = cpuinfo.cores_to_cpus(cores=(cores[1],), packages=(0,))
            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)

        # Pattern 4: Take the second module offline.
        modules = cpuinfo.get_modules()
        if len(modules) > 1:
            cpus = cpuinfo.modules_to_cpus(modules=(modules[1],))
            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)

        # Pattern 4: Take the second die offline.
        dies = cpuinfo.get_package_dies(package=0)
        if len(dies) > 1:
            cpus = cpuinfo.dies_to_cpus(dies=(dies[1],), packages=(0,))
            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)

        # Pattern 5: Take the second package offline.
        packages = cpuinfo.get_packages()
        if len(packages) > 1:
            cpus = cpuinfo.packages_to_cpus(packages=(packages[1],))
            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)
