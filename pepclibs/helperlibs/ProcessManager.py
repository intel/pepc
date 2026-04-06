# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide helpers for creating a process manager object for a local or remote host.

The process manager abstracts running commands and performing file I/O operations uniformly on both
local and remote hosts.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import LocalProcessManager, SSHProcessManager, EmulProcessManager
# pylint: disable-next=unused-import
from pepclibs.helperlibs._ProcessManagerTypes import ProcWaitResultType

if typing.TYPE_CHECKING:
    from typing import cast
    from pepclibs.helperlibs._ProcessManagerTypes import LsdirTypedDict, LsdirSortbyType
    from pepclibs.helperlibs._ProcessManagerTypes import ProcessManagerProtocol, ProcessProtocol

    ProcessManagerType = ProcessManagerProtocol
    ProcessType = ProcessProtocol

def get_pman(hostname: str,
             username: str = "",
             privkeypath: str | Path = "",
             timeout: int | float | None = None) -> ProcessManagerType:
    """
    Create and return a process manager object for the specified host.

    Determine the appropriate process manager to use based on the 'hostname' argument and return an
    instance of the corresponding process manager class. The following cases are handled:

    1. If 'hostname' is "localhost":
        - If 'username' is empty, return a 'LocalProcessManager' object for efficient
          management of local processes.
        - If 'username' is not empty, return an 'SSHProcessManager' object that connects
          to the local host over SSH. This is less efficient but useful for debugging.
    2. If 'hostname' starts with "emulation":
        - Return an 'EmulProcessManager' object, which is used for testing purposes.
    3. For all other cases:
        - Return an 'SSHProcessManager' object that connects to the specified host
          over SSH and manages processes on the remote host.

    Args:
        hostname: The host name to create a process manager object for.
        username: The user name for logging into the host over SSH. Only used for
                  'SSHProcessManager'.
        privkeypath: Path to the SSH private key for authentication. Only used for
                     'SSHProcessManager'.
        timeout: The SSH connection timeout in seconds. Only used for 'SSHProcessManager'.

    Returns:
        An instance of the appropriate process manager class.

    Usage examples:
        1.  with get_pman(hostname) as pman:
                pman.run_verify(command)

        2.  pman = get_pman(hostname)
            try:
                pman.run_verify(command)
            finally:
                pman.close()
    """

    if hostname == "localhost" and not username:
        return LocalProcessManager.LocalProcessManager()
    if hostname.startswith("emulation"):
        return EmulProcessManager.EmulProcessManager(hostname=hostname)
    return SSHProcessManager.SSHProcessManager(hostname, username=username,
                                               privkeypath=privkeypath, timeout=timeout)

def pman_or_local(pman: ProcessManagerType | None) -> ProcessManagerType:
    """
    Return the provided process manager or a new 'LocalProcessManager' instance.

    Problem:
        A method accepts a 'pman=None' argument (a process manager object, with default value
        'None'). By default, the 'LocalProcessManager' should be used. And 'pman' is used with
        'with' statement, so it should be closed automatically, but only if it was created
        internally, not when the caller passed it.

    Solution:
        The 'pman_or_local()' function takes the process manager object as an argument. If the
        argument is 'None', it creates a new 'LocalProcessManager' instance and returns it.
        Otherwise, it returns the provided process manager object, but wrapped in a context manager
        that does not call the '__exit__()' method. This way, the caller is responsible for
        managing the lifecycle of the provided process manager.

    Args:
        pman: The process manager object to use. If 'None', a new 'LocalProcessManager' instance
              will be created.

    Returns:
        ProcessManagerType: The provided process manager object if it is not 'None', otherwise a
                            new instance of 'LocalProcessManager', wrapped into a "nullcontext"
                            context manager.
    """

    if pman:
        if typing.TYPE_CHECKING:
            return cast(ProcessManagerType, contextlib.nullcontext(enter_result=pman))
        return contextlib.nullcontext(enter_result=pman)

    return LocalProcessManager.LocalProcessManager()
