#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>
#         Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Common functions for pepc tests."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path
import typing
from pepclibs.helperlibs import ProcessManager, EmulProcessManager

if typing.TYPE_CHECKING:
    from typing import TypedDict, cast
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
