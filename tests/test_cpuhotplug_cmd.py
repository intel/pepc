#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the 'pepc cpu-hotplug' command."""

import contextlib
import pytest
import common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """
    Build and yield the testing parameters dictionary. The arguments are as follows.
      * hostspec - the specification of the host to run the tests on.
    """

    emul_modules = ["CPUInfo", "CPUOnline"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        params = common.build_params(pman)

        params["cpuonline"] = cpuonline
        params["cpuinfo"] = cpuinfo

        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_package_cores(package=pkg)

        yield params

def _online_all_cpus(pman):
    """Online all CPUs."""

    common.run_pepc("cpu-hotplug online --cpus all", pman)

def test_cpuhotplug_info(params):
    """
    Test 'pepc cpu-hotplug info' sub-command. The arguments are as follows.
      * params - the testing parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)
    common.run_pepc("cpu-hotplug info", pman)

def _test_cpuhotplug(params):
    """Implement 'test_cpuhotplug()."""

    pman = params["pman"]
    onl = params["cpuonline"]
    cpuinfo = params["cpuinfo"]

    # Offline every 2nd core.
    for pkg, cores in params["cores"].items():
        for core in cores:
            if core % 2 == 0:
                common.run_pepc(f"cpu-hotplug offline --packages {pkg} --cores {core}", pman)

    # Offline every 3nd core.
    for pkg, cores in params["cores"].items():
        cores_to_offline = []
        for core in cores:
            if core % 2 != 0 and core % 3 == 0:
                cores_to_offline.append(core)

        cores = ",".join([str(core) for core in cores_to_offline])
        common.run_pepc(f"cpu-hotplug offline --packages {pkg} --cores {cores}", pman)

    # Make sure the 'info' sub-command works.
    common.run_pepc("cpu-hotplug info", pman)

    # Online every 2nd core.
    cpus_to_online = []
    for pkg, cores in params["cores"].items():
        for core in cores:
            if core % 2 == 0:
                cpus_to_online += cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))

    cpus = ",".join([str(cpu) for cpu in cpus_to_online])
    common.run_pepc(f"cpu-hotplug online --cpus {cpus}", pman)

    # Verify that the expected cores are offline, other cores are online.
    offline_cpus = []
    online_cpus = []
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
        common.run_pepc(f"cpu-hotplug offline --packages {pkg}", pman)

        # Make sure the 'info' sub-command works.
        common.run_pepc("cpu-hotplug info", pman)

        # Online all CPUs in the package.
        cpus = ",".join(str(cpu) for cpu in cpuinfo.package_to_cpus(pkg))
        common.run_pepc(f"cpu-hotplug online --cpus {cpus}", pman)

def test_cpuhotplug(params):
    """
    Test 'pepc cpu-hotplug online' and 'pepc cpu-hotplug offline' sub-commands. The arguments are as
    follows.
      * params - the testing parameters.
    """

    pman = params["pman"]
    _online_all_cpus(pman)

    try:
        _test_cpuhotplug(params)
    finally:
        with contextlib.suppress(Error):
            _online_all_cpus(pman)

def _test_cpuhotplug_online_bad(params):
    """Test 'pepc cpu-hotplug online' sub-command with bad input."""

    pman = params["pman"]

    bad = ["",
           "--cpus all --core-siblings 0",
           f"--packages {params['packages'][0]} --cores all",
           f"--packages {params['packages'][0]} --cores {params['cores'][0][0]}",
           f"--packages {params['packages'][0]} --cores {params['cores'][0][-1]}",
           f"--packages {params['packages'][-1]}"]

    if len(params["cores"][0]) > 2:
        bad += [f"--packages 0 --cores {params['cores'][0][1]}"]
    if len(params["cores"][0]) > 3:
        bad += [f"--packages 0 --cores {params['cores'][0][1]}-{params['cores'][0][2]}"]

    for option in bad:
        common.run_pepc(f"cpu-hotplug online {option}", pman, exp_exc=Error)

def _test_cpuhotplug_offline_bad(params):
    """Test 'pepc cpu-hotplug offline' sub-command with bad input."""

    pman = params["pman"]

    bad = ["--cpus 0",
           "--cpus -1",
           f"--cpus {params['cpus'][-1] + 1}"]

    for option in bad:
        common.run_pepc(f"cpu-hotplug offline {option}", pman, exp_exc=Error)

def test_cpuhotplug_bad(params):
    """
    Test 'pepc cpu-hotplug' commands. The arguments are as follows.
      * params - the testing parameters.
    """

    _test_cpuhotplug_online_bad(params)
    _test_cpuhotplug_offline_bad(params)
