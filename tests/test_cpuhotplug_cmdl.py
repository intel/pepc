#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc cpu-hotplug' command-line options."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
import pytest
from tests import common, props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuonline: A 'CPUOnline.CPUOnline' object.
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            cpus: All CPU numbers in the system.
            packages: All package numbers in the system.
            cores: A mapping of package numbers to lists of core numbers in the package.
        """

        cpuonline: CPUOnline.CPUOnline
        cpuinfo: CPUInfo.CPUInfo
        cpus: list[int]
        packages: list[int]
        cores: dict[int, list[int]]

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_package_cores(package=pkg)

        yield params

def _online_all_cpus(pman: ProcessManagerType):
    """
    Online all CPUs in the system.

    Args:
        pman: The process manager for the target system.
    """

    props_cmdl_common.run_pepc("cpu-hotplug online --cpus all", pman)

def test_cpuhotplug_info(params: _TestParamsTypedDict):
    """
    Run and verify the 'pepc cpu-hotplug info' command.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)
    props_cmdl_common.run_pepc("cpu-hotplug info", pman)

def _test_cpuhotplug(params: _TestParamsTypedDict):
    """
    Test CPU online/offline functionality.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]

    # Offline every 2nd core.
    for pkg, cores in params["cores"].items():
        for core in cores:
            if core % 2 == 0:
                cmd = f"cpu-hotplug offline --packages {pkg} --cores {core}"
                props_cmdl_common.run_pepc(cmd, pman)

    # Offline every 3nd core.
    for pkg, cores in params["cores"].items():
        cores_to_offline = []
        for core in cores:
            if core % 2 != 0 and core % 3 == 0:
                cores_to_offline.append(core)

        if not cores_to_offline:
            continue

        cores_str = ",".join([str(core) for core in cores_to_offline])
        cmd = f"cpu-hotplug offline --packages {pkg} --cores {cores_str}"
        props_cmdl_common.run_pepc(cmd, pman)

    # Make sure the 'info' sub-command works.
    props_cmdl_common.run_pepc("cpu-hotplug info", pman)

    # Online every 2nd core.
    cpus_to_online = []
    for pkg, cores in params["cores"].items():
        for core in cores:
            if core % 2 == 0:
                cpus_to_online += cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))

    cpus_str = ",".join([str(cpu) for cpu in cpus_to_online])
    props_cmdl_common.run_pepc(f"cpu-hotplug online --cpus {cpus_str}", pman)

    # Verify that the expected cores are offline, other cores are online.
    offline_cpus: list[int] = []
    online_cpus: list[int] = []
    for pkg, cores in params["cores"].items():
        for core in cores:
            cpus = cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))
            if core % 2 != 0 and core % 3 == 0:
                offline_cpus += cpus
            else:
                online_cpus += cpus

    for cpu in offline_cpus:
        assert not onl.is_online(cpu)
    for cpu in online_cpus:
        assert onl.is_online(cpu)

    # Online every CPU.
    _online_all_cpus(pman)

    if len(params["packages"]) == 1:
        return

    # Offline / online every package separately.
    for pkg in params["packages"]:
        # Offline all CPUs in the package.
        props_cmdl_common.run_pepc(f"cpu-hotplug offline --packages {pkg}", pman)

        # Make sure the 'info' sub-command works.
        props_cmdl_common.run_pepc("cpu-hotplug info", pman)

        # Online all CPUs in the package.
        cpus_str = ",".join(str(cpu) for cpu in cpuinfo.package_to_cpus(pkg))
        props_cmdl_common.run_pepc(f"cpu-hotplug online --cpus {cpus_str}", pman)

def test_cpuhotplug(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug online' and 'pepc cpu-hotplug offline' commands.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug(params)
    finally:
        with contextlib.suppress(Error):
            _online_all_cpus(pman)

def test_cpuhotplug_online_bad(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug online' command with invalid input options.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    bad = ["--cpus -1",
           f"--cpus {params['cpus'][-1] + 1}"]

    for option in bad:
        props_cmdl_common.run_pepc(f"cpu-hotplug online {option}", pman, exp_exc=Error)

def test_cpuhotplug_offline_bad(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug offline' sub-command with invalid CPU input options.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]

    bad = ["--cpus 0",
           "--cpus -1",
           f"--cpus {params['cpus'][-1] + 1}"]

    for option in bad:
        props_cmdl_common.run_pepc(f"cpu-hotplug offline {option}", pman, exp_exc=Error)
