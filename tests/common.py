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
import sys
import logging
from pathlib import Path
import pytest
from pepclibs import CPUInfo, CStates
from pepclibs.helperlibs import ProcessManager
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied
from pepctool import _Pepc

logging.basicConfig(level=logging.DEBUG)
_LOG = logging.getLogger()

_REQUIRED_MODULES = ["ASPM", "CPUInfo", "CPUOnline", "CStates", "PStates", "Systemctl"]

def _get_datapath(dataset):
    """Return path to test data for the dataset 'dataset'."""
    return Path(__file__).parent.resolve() / "data" / dataset

def prop_is_supported(prop, props):
    """
    Return 'True' if property 'prop' is supported by properties 'props', otherwise return 'False'.
    """

    if prop in props:
        return props[prop].get(prop) is not None
    return False

def get_pman(hostname, dataset, modules=None):
    """
    Create and return process manager, the arguments are as follows.
      * hostname - the hostn name to create a process manager object for.
      * dataset - the name of the dataset used to emulate the real hardware.
      * modules - the list of python module names to be initialized before testing. Refer to
                  'EmulProcessManager.init_testdata()' for more information.
    """

    datapath = None
    username = None
    if hostname == "emulation":
        datapath = _get_datapath(dataset)
    elif hostname != "localhost":
        username = "root"

    pman = ProcessManager.get_pman(hostname, username=username, datapath=datapath)

    if hostname == "emulation" and modules is not None:
        if not isinstance(modules, list):
            modules = [modules]

        for module in modules:
            pman.init_testdata(module, datapath)

    return pman

def _has_required_modules(datapath):
    """Returns 'True' if datapath has all required modules to run tests."""

    for module in _REQUIRED_MODULES:
        if not Path(datapath / f"{module}.yaml").exists():
            return False

    return True

def get_datasets():
    """Find all directories in 'tests/data' directory and yield the directory name."""

    basepath = Path(__file__).parent.resolve() / "data"
    for dirname in os.listdir(basepath):
        datapath = Path(f"{basepath}/{dirname}")

        if not datapath.is_dir():
            continue

        if not _has_required_modules(datapath):
            _LOG.warning("excluding dataset '%s', incomplete test data", datapath)
            continue

        yield dirname

def build_params(hostname, dataset, pman, cpuinfo):
    """Implements the 'get_params()' fixture."""

    params = {}
    params["hostname"] = hostname
    params["dataset"] = dataset
    params["pman"] = pman

    if hostname == "emulation":
        datapath = _get_datapath(dataset)
        for module in _REQUIRED_MODULES:
            pman.init_testdata(module, datapath)

    with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as csobj:
        allcpus = cpuinfo.get_cpus()
        medidx = int(len(allcpus)/2)
        params["testcpus"] = [allcpus[0], allcpus[medidx], allcpus[-1]]
        params["cpus"] = allcpus
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)
        params["cpumodel"] = cpuinfo.info["model"]

        params["cstates"] = []
        for _, csinfo in csobj.get_cstates_info(cpus=[allcpus[0]]):
            for csname in csinfo:
                params["cstates"].append(csname)

        params["cstate_props"] = csobj.get_cpu_props(csobj.props, 0)

    return params

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_params(hostname, request):
    """
    Yield a dictionary with information we need for testing. For example, to optimize the test
    duration, use only subset of all CPUs available on target system to run tests on.
    """

    dataset = request.param
    with get_pman(hostname, dataset) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        yield build_params(hostname, dataset, pman, cpuinfo)

# A map of error type and command argument strings to look for in case of error. For matching
# exceptions print warning instead of asserting.
_WARN_ONLY = {
    ErrorPermissionDenied : "aspm config --policy ",
}

def run_pepc(arguments, pman, exp_exc=None):
    """
    Run the 'pepc' command with arguments 'arguments' and with process manager 'pman'. The 'exp_exc'
    is expected exception type. By default, any exception is considered to be a failure.
    """

    cmd = f"{_Pepc.__file__} {arguments}"
    _LOG.debug("running: %s", cmd)
    sys.argv = cmd.split()
    try:
        args = _Pepc.parse_arguments()
        ret = args.func(args, pman)
    except Exception as err: # pylint: disable=broad-except
        if exp_exc is None:
            err_type = type(err)
            errmsg = f"command '{cmd}' raised the following exception:\n\ttype: {err_type}\n\t" \
                     f"message: {err}"

            if pman.is_remote and err_type in _WARN_ONLY and _WARN_ONLY[err_type] in arguments:
                _LOG.warning(errmsg)
                return None

            assert False, errmsg

        if isinstance(err, exp_exc):
            return None

        assert False, f"command '{cmd}' raised the following exception:\n\t" \
                      f"type: {type(err)}\n\tmessage: {err}\n" \
                      f"but it was expected to raise the following exception type: {type(exp_exc)}"

    return ret
