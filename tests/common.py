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

from  __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path
from typing import TypedDict, Mapping
from pepclibs.helperlibs import ProcessManager, EmulProcessManager, TestRunner
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.helperlibs.Exceptions import Error, ExceptionType
from pepctool import _Pepc

class CommonTestParamsTypedDict(TypedDict):
    """
    A dictionary of common test parameters.

    Attributes:
        hostname: The hostname of the target system.
        pman: The process manager instance for managing processes on the target system.
    """

    hostname: str
    pman: ProcessManagerType

def _get_datapath(dataset: str) -> Path:
    """
    Get the path to the test data for the specified dataset.

    Args:
        dataset: Name of the dataset for which to retrieve the path.

    Returns:
        Path to the test data directory for the specified dataset.
    """

    return Path(__file__).parent.resolve() / "data" / dataset

def is_emulated(pman: ProcessManagerType) -> bool:
    """
    Determine if the provided process manager corresponds to an emulated system.

    Args:
        pman: The process manager instance to check.

    Returns:
        True if the process manager corresponds to an emulated system, False otherwise.
    """

    return hasattr(pman, "datapath")

def get_pman(hostspec: str, modules: list[str] | None = None) -> ProcessManagerType:
    """
    Create and return a process manager for the specified host.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        modules: A list of Python module names to initialize for testing in an emulated environment.

    Returns:
        A process manager instance for the specified host. 'EmulProcessManager' in case of
        emulation, 'LocalProcessManager' for the localhost, and 'SSHProcessManager' for remote
        hosts.
    """

    datapath: Path | None = None
    username: str | None = None
    if hostspec.startswith("emulation:"):
        dataset = hostspec.split(":", maxsplit=2)[1]
        datapath = _get_datapath(dataset)
    elif hostspec != "localhost":
        username = "root"

    pman = ProcessManager.get_pman(hostspec, username=username)

    if modules and datapath:
        assert isinstance(pman, EmulProcessManager.EmulProcessManager)

        try:
            for module in modules:
                pman.init_module(module, datapath)
        except Error:
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

    return CommonTestParamsTypedDict(hostname=pman.hostname, pman=pman)

def run_pepc(arguments: str,
             pman: ProcessManagerType,
             exp_exc: ExceptionType | None = None,
             ignore: Mapping[ExceptionType, str] | None = None):
    """
    Execute the 'pepc' command and validate its outcome.

    Args:
        arguments: The command-line arguments to execute the 'pepc' command with, e.g.,
                   'pstate info --cpus 0-43'.
        pman: The process manager object that specifies the host to run the command on.
        exp_exc: The expected exception. If set, the test fails if the command does not raise the
                 expected exception. By default, any exception is considered a failure.
        ignore: A dictionary mapping error types to command argument strings. Can be used for
                ignoring ceratin exceptions.

    Raises:
        AssertionError: If the command execution does not match the expected outcome.
    """

    TestRunner.run_tool(_Pepc, _Pepc.TOOLNAME, arguments, pman=pman, exp_exc=exp_exc,
                        ignore=ignore)
