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
from tests import _Common, _PropsCommonCmdl
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from tests._Common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuonline: A 'CPUOnline.CPUOnline' object.
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            cpus: All CPU numbers in the system.
            packages: All package numbers in the system.
            cores: A mapping of package numbers to lists of core numbers in the package.
            modules: All module numbers in the system.
            dies: A mapping of package numbers to lists of compute die numbers in the package.
        """

        cpuonline: CPUOnline.CPUOnline
        cpuinfo: CPUInfo.CPUInfo
        cpus: list[int]
        packages: list[int]
        cores: dict[int, list[int]]
        modules: list[int]
        dies: dict[int, list[int]]

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

    with _Common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = _Common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        # Online all CPUs before capturing the topology, so test parameters reflect the complete
        # CPU set regardless of the initial system state.
        cpuonline.online(cpus="all")

        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_package_cores(package=pkg)
        params["modules"] = cpuinfo.get_modules()
        params["dies"] = cpuinfo.get_compute_dies()

        yield params

def _online_all_cpus(pman: ProcessManagerType):
    """
    Online all CPUs in the system.

    Args:
        pman: The process manager for the target system.
    """

    _PropsCommonCmdl.run_pepc("cpu-hotplug online --cpus all", pman)

def test_cpuhotplug_info(params: _TestParamsTypedDict):
    """
    Run and verify the 'pepc cpu-hotplug info' command.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

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
                _PropsCommonCmdl.run_pepc(cmd, pman)

    # Offline odd cores divisible by 3 (even ones are already offline).
    for pkg, cores in params["cores"].items():
        cores_to_offline = []
        for core in cores:
            if core % 2 != 0 and core % 3 == 0:
                cores_to_offline.append(core)

        if not cores_to_offline:
            continue

        cores_str = ",".join(str(core) for core in cores_to_offline)
        cmd = f"cpu-hotplug offline --packages {pkg} --cores {cores_str}"
        _PropsCommonCmdl.run_pepc(cmd, pman)

    # Make sure the 'info' sub-command works.
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

    # Online every 2nd core.
    cpus_to_online = []
    for pkg, cores in params["cores"].items():
        for core in cores:
            if core % 2 == 0:
                cpus_to_online += cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))

    cpus_str = ",".join(str(cpu) for cpu in cpus_to_online)
    _PropsCommonCmdl.run_pepc(f"cpu-hotplug online --cpus {cpus_str}", pman)

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
        _PropsCommonCmdl.run_pepc(f"cpu-hotplug offline --packages {pkg}", pman)

        # Make sure the 'info' sub-command works.
        _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

        # Online all CPUs in the package.
        cpus_str = ",".join(str(cpu) for cpu in cpuinfo.package_to_cpus(pkg))
        _PropsCommonCmdl.run_pepc(f"cpu-hotplug online --cpus {cpus_str}", pman)

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

def _test_cpuhotplug_offline_modules(params: _TestParamsTypedDict):
    """
    Test CPU offline functionality with module-based targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]
    all_cpus = params["cpus"]
    modules = params["modules"]

    if len(modules) < 2:
        pytest.skip("Less than 2 modules, cannot test module-based offline targeting")

    # Offline every other module using a comma-separated list.
    modules_to_offline = modules[::2]
    modules_str = ",".join(str(m) for m in modules_to_offline)
    _PropsCommonCmdl.run_pepc(f"cpu-hotplug offline --modules {modules_str}", pman)

    # Make sure the 'info' sub-command works with a mixed online/offline state.
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

    # Build the expected offline CPU set. CPU 0 cannot be offlined.
    offline_set = set(cpuinfo.modules_to_cpus(modules=modules_to_offline)) - {0}

    for cpu in all_cpus:
        if cpu in offline_set:
            assert not onl.is_online(cpu)
        else:
            assert onl.is_online(cpu)

def test_cpuhotplug_offline_modules(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug offline' command with module-based targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug_offline_modules(params)
    finally:
        with contextlib.suppress(Error):
            _online_all_cpus(pman)

def _test_cpuhotplug_offline_dies(params: _TestParamsTypedDict):
    """
    Test CPU offline functionality with die-based targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]
    all_cpus = params["cpus"]
    dies = params["dies"]

    if not any(len(pkg_dies) > 1 for pkg_dies in dies.values()):
        pytest.skip("No package has more than one die, cannot test die-based offline targeting")

    # For each package, offline every other die using a comma-separated list.
    offline_cpus: list[int] = []
    for pkg, pkg_dies in dies.items():
        if len(pkg_dies) < 2:
            continue
        dies_to_offline = pkg_dies[::2]
        dies_str = ",".join(str(d) for d in dies_to_offline)
        _PropsCommonCmdl.run_pepc(f"cpu-hotplug offline --packages {pkg} --dies {dies_str}", pman)
        offline_cpus += cpuinfo.dies_to_cpus(dies=dies_to_offline, packages=(pkg,))

    # Make sure the 'info' sub-command works with a mixed online/offline state.
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

    # Build the expected offline CPU set. CPU 0 cannot be offlined.
    offline_set = set(offline_cpus) - {0}

    for cpu in all_cpus:
        if cpu in offline_set:
            assert not onl.is_online(cpu)
        else:
            assert onl.is_online(cpu)

def test_cpuhotplug_offline_dies(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug offline' command with die-based targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug_offline_dies(params)
    finally:
        with contextlib.suppress(Error):
            _online_all_cpus(pman)

def _test_cpuhotplug_offline_core_siblings(params: _TestParamsTypedDict):
    """
    Test CPU offline functionality with core sibling index targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]
    all_cpus = params["cpus"]

    # Determine CPUs with core sibling index 1 (typically hyperthreads). Must be called while all
    # CPUs are online to ensure the complete sibling index map is available.
    cpus_to_offline = cpuinfo.select_core_siblings(all_cpus, (1,))
    if not cpus_to_offline:
        pytest.skip("No core has more than one CPU, cannot test core sibling offline targeting")

    _PropsCommonCmdl.run_pepc("cpu-hotplug offline --core-siblings 1", pman)

    # Make sure the 'info' sub-command works with a mixed online/offline state.
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

    # Build the expected offline CPU set. CPU 0 cannot be offlined.
    offline_set = set(cpus_to_offline) - {0}

    for cpu in all_cpus:
        if cpu in offline_set:
            assert not onl.is_online(cpu)
        else:
            assert onl.is_online(cpu)

def test_cpuhotplug_offline_core_siblings(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug offline' command with core sibling index targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug_offline_core_siblings(params)
    finally:
        with contextlib.suppress(Error):
            _online_all_cpus(pman)

def _test_cpuhotplug_offline_module_siblings(params: _TestParamsTypedDict):
    """
    Test CPU offline functionality with module sibling index targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]
    all_cpus = params["cpus"]

    # Determine CPUs with module sibling index 1. Must be called while all CPUs are online to
    # ensure the complete sibling index map is available.
    cpus_to_offline = cpuinfo.select_module_siblings(all_cpus, (1,))
    if not cpus_to_offline:
        pytest.skip("No module has more than one CPU, cannot test module sibling offline targeting")

    _PropsCommonCmdl.run_pepc("cpu-hotplug offline --module-siblings 1", pman)

    # Make sure the 'info' sub-command works with a mixed online/offline state.
    _PropsCommonCmdl.run_pepc("cpu-hotplug info", pman)

    # Build the expected offline CPU set. CPU 0 cannot be offlined.
    offline_set = set(cpus_to_offline) - {0}

    for cpu in all_cpus:
        if cpu in offline_set:
            assert not onl.is_online(cpu)
        else:
            assert onl.is_online(cpu)

def test_cpuhotplug_offline_module_siblings(params: _TestParamsTypedDict):
    """
    Test the 'pepc cpu-hotplug offline' command with module sibling index targeting.

    Args:
        params: The test parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug_offline_module_siblings(params)
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
        _PropsCommonCmdl.run_pepc(f"cpu-hotplug online {option}", pman, exp_exc=Error)

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
        _PropsCommonCmdl.run_pepc(f"cpu-hotplug offline {option}", pman, exp_exc=Error)
