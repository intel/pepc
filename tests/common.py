#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>
#         Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Common bits for the 'pepc' tests."""

from pathlib import Path
from pepclibs.helperlibs import ProcessManager, TestRunner
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied, Error
from pepctool import _Pepc

def _get_datapath(dataset):
    """Return path to test data for the dataset 'dataset'."""

    return Path(__file__).parent.resolve() / "data" / dataset

def is_emulated(pman):
    """Returns 'True' if 'pman' corresponds to an emulated system."""

    return hasattr(pman, "datapath")

def get_pman(hostspec, modules=None):
    """
    Create and return process manager, the arguments are as follows.
      * hostspec - the host to create a process manager for.
      * modules - the list of python module names to be initialized before testing. Refer to
                  'EmulProcessManager.init_testdata()' for more information.
    """

    datapath = None
    username = None
    if hostspec.startswith("emulation:"):
        dataset = hostspec.split(":", maxsplit=2)[1]
        datapath = _get_datapath(dataset)

    elif hostspec != "localhost":
        username = "root"

    pman = ProcessManager.get_pman(hostspec, username=username)

    if datapath and modules is not None:
        try:
            for module in modules:
                pman.init_testdata(module, datapath)
        except Error:
            pman.close()
            raise

    return pman

def build_params(pman):
    """Build the test parameters dictionary (the common part of it)."""

    params = {}
    params["hostname"] = pman.hostname
    params["pman"] = pman

    return params

# A map of error type and command argument strings to look for in case of error. For matching
# exceptions print warning instead of asserting.
_WARN_ONLY = {
    ErrorPermissionDenied : "aspm config --policy ",
    # On a non-emulated hardware CPUs can't be offlined in some cases (e.g., if an interrupt can't
    # be migrated to another CPU).
    Error : "cpu-hotplug offline"
}

def run_pepc(arguments, pman, exp_exc=None):
    """
    Run pepc command and verify the outcome. The arguments are as follows.
      * arguments - the arguments to run the command with, e.g. 'pstate info --cpus 0-43'.
      * pman - the process manager object that defines the host to run the measurements on.
      * exp_exc - the expected exception, by default, any exception is considered to be a failure.
                  But when set if the command did not raise the expected exception then the test is
                  considered to be a failure.
    """

    warn_only = {}
    if pman.is_remote:
        warn_only = _WARN_ONLY

    TestRunner.run_tool(_Pepc, _Pepc.TOOLNAME, arguments, pman, exp_exc, warn_only)
