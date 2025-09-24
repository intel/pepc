#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""
Test for the '_OpTarget' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
import pytest
import common
from pepclibs import CPUInfo, CPUOnline
from pepctool import _OpTarget
from pepctool._OpTarget import ErrorNoTarget, Error

if typing.TYPE_CHECKING:
    from typing import Generator, cast, Sequence
    from common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
        """

        cpuinfo: CPUInfo.CPUInfo

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
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo

        yield params

def test_all(params: _TestParamsTypedDict):
    """
    Test that the '_OpTarget' class handles "all" on various levels correctly.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    pman = params["pman"]

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus="all") as optar:
        assert optar.cpus == cpuinfo.get_cpus(), \
               "cpus='all' did not select all CPUs"
        assert optar.get_cpus() == cpuinfo.get_cpus(), \
               "cpus='all' did not select all CPUs"
        assert optar.get_dies() == cpuinfo.get_dies(io_dies=False), \
               "cpus='all' did not select all dies"
        assert optar.get_packages() == cpuinfo.get_packages(), \
               "cpus='all' did not select all packages"

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cores="all") as optar:
        assert optar.cores == cpuinfo.get_cores(), \
               "cores='all' did not select all cores"
        assert optar.get_cpus() == cpuinfo.get_cpus(order="package"), \
               "cores='all' did not select all CPUs"
        assert optar.get_dies() == cpuinfo.get_dies(io_dies=False), \
               "cores='all' did not select all dies"
        assert optar.get_packages() == cpuinfo.get_packages(), \
               "cores='all' did not select all packages"

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, dies="all") as optar:
        assert optar.dies == cpuinfo.get_dies(), \
               "dies='all' did not select all dies"
        assert optar.get_cpus() == cpuinfo.get_cpus(order="package"), \
               "dies='all' did not select all CPUs"
        assert optar.get_dies() == cpuinfo.get_dies(io_dies=True), \
               "dies='all' did not select all dies"
        assert optar.get_packages() == cpuinfo.get_packages(), \
               "dies='all' did not select all packages"

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, packages="all") as optar:
        assert optar.packages == cpuinfo.get_packages(), \
               "packages='all' did not select all packages"
        assert optar.get_cpus() == cpuinfo.get_cpus(), \
               "packages='all' did not select all CPUs"
        assert optar.get_dies() == cpuinfo.get_dies(io_dies=True), \
               "packages='all' did not select all dies"
        assert optar.get_packages() == cpuinfo.get_packages(), \
               "packages='all' did not select all packages"

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus="all", cores="all", dies="all",
                            packages="all") as optar:
        assert optar.cpus == cpuinfo.get_cpus(), \
               "*='all' did not select all CPUs"
        assert optar.cores == cpuinfo.get_cores(), \
               "*='all' did not select all cores"
        assert optar.dies == cpuinfo.get_dies(io_dies=True), \
               "*='all' did not select all dies"
        assert optar.packages == cpuinfo.get_packages(), \
               "*='all' did not select all packages"
        assert optar.get_cpus() == cpuinfo.get_cpus(), \
               "*='all' did not select all CPUs"
        assert optar.get_dies() == cpuinfo.get_dies(io_dies=True), \
               "*='all' did not select all dies"
        assert optar.get_packages() == cpuinfo.get_packages(), \
               "*='all' did not select all packages"

def test_core_siblings(params: _TestParamsTypedDict):
    """
    Test that the '_OpTarget' class handles core siblings correctly.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    pman = params["pman"]

    # Run the test for the first and the last cores.
    tlines = cpuinfo.get_topology()
    for tline in (tlines[0], tlines[cpuinfo.get_cpus_count() - 1]):
        core = tline["core"]
        package = tline["package"]

        cpus = cpuinfo.cores_to_cpus(cores=(core,), packages=(package,), order="core")
        if len(cpus) < 2:
            continue

        for indices in ((0,), (len(cpus) - 1,), (0, len(cpus) - 1)):
            with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, packages=(package,),
                                    cores=(core,), core_siblings=indices) as optar:
                sib_cpus = [cpus[i] for i in indices]
                assert optar.cores == {package: [core]}, \
                    f"core_siblings={indices} did not select the specified core"
                assert optar.packages == [package], \
                    f"core_siblings={indices} did not select the specified package"
                assert optar.core_sib_cpus  == sib_cpus, \
                    f"core_siblings={indices} did not select the specified CPU"
                assert optar.get_cpus() == sib_cpus, \
                    f"core_siblings={indices} did not select the specified CPU"

def test_module_siblings(params: _TestParamsTypedDict):
    """
    Test that the '_OpTarget' class handles module siblings correctly.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    pman = params["pman"]

    # Run the test for the first and the last modules.
    tlines = cpuinfo.get_topology()
    for tline in (tlines[0], tlines[cpuinfo.get_cpus_count() - 1]):
        module = tline["module"]

        module_cpus = cpuinfo.modules_to_cpus(modules=(module,), order="module")
        if len(module_cpus) < 2:
            continue

        module_indices: Sequence[int]
        for module_indices in ((0,), (len(module_cpus) - 1,), (0, len(module_cpus) - 1)):
            with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, modules=(module,),
                                    module_siblings=module_indices) as optar:
                module_sibling_cpus = [module_cpus[i] for i in module_indices]
                assert optar.modules == [module], \
                    f"module_siblings={module_indices} did not select the specified module"
                assert optar.module_sib_cpus  == module_sibling_cpus, \
                    f"module_siblings={module_indices} did not select the specified CPU"
                assert optar.get_cpus() == module_sibling_cpus, \
                    f"module_siblings={module_indices} did not select the specified CPU"

            if module_cpus[-1] == 0:
                continue # Cannot offline CPU 0.
            if module_cpus[-1] not in module_sibling_cpus:
                # The CPU that is going to be offlined is not in the selection, skip the test.
                continue

            # Offline the last CPU in the module and check that the selection still works.
            with CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as onl:
                onl.offline((module_cpus[-1],))
                # The 'offline_ok' argument should be ignored since we are not specifying target
                # CPUs directly.
                with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, modules=(module,),
                                        module_siblings=module_indices, offline_ok=False) as optar:
                    try:
                        selected_cpus = optar.get_cpus()
                    except ErrorNoTarget:
                        pass
                    else:
                        cpus = [cpu for cpu in module_sibling_cpus if cpu != module_cpus[-1]]
                        assert selected_cpus == cpus, \
                            f"module_siblings={module_indices} did not select the specified CPU"

                # Now specify target CPUs directly and check that an exception is raised when one of
                # them is offline.
                with contextlib.suppress(Error):
                    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, modules=(module,),
                                            module_siblings=module_indices,
                                            cpus=module_sibling_cpus, offline_ok=False) as optar:
                        pass
                onl.online((module_cpus[-1],))
