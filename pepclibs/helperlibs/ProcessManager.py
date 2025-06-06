# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a unified way of creating a process manager object for local or remote hosts.

Historically, the process manager was about running processes on a local or remote hosts in a
uniform manner. However, over time, the process manager grew file I/O-related operations, such as
'open()' and 'exists()'. This is very useful because it allows for file operations on a remote host
as if it was a local host.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import contextlib
from typing import Union, Any, cast
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import LocalProcessManager, SSHProcessManager, EmulProcessManager
# pylint: disable-next=unused-import
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType, LsdirTypedDict

ProcessManagerType = Union[LocalProcessManager.LocalProcessManager,
                           SSHProcessManager.SSHProcessManager,
                           EmulProcessManager.EmulProcessManager]

ProcessType = Union[LocalProcessManager.LocalProcess, SSHProcessManager.SSHProcess]

def _check_for_none(hostname: str, kwargs: dict[str, Any]):
    """
    Ensure all keyword arguments in 'kwargs' are set to 'None'.

    Args:
        hostname: The hostname associated with the check, used for error messages.
        kwargs: Arbitrary keyword arguments to validate.

    Raises:
        Error: If any value in 'kwargs' is not 'None'.
    """

    for name, val in kwargs.items():
        if val is not None:
            raise Error(f"BUG: get_pman(): hostname is '{hostname}', but argument '{name}' is not "
                        f"'None'. Instead, it is '{val}'")

def get_pman(hostname: str,
             username: str | None = None,
             privkeypath: str | None =None,
             timeout: int | float | None = None) -> ProcessManagerType:
    """
    Create and return a process manager object for the specified host.

    Determine the appropriate process manager to use based on the `hostname` argument and return an
    instance of the corresponding process manager class. The following cases are handled:

    1. If 'hostname' is "localhost":
        - If 'username' is None, return a 'LocalProcessManager' object for efficient
          management of local processes.
        - If 'username' is not None, return an 'SSHProcessManager' object that connects
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
         timeout: The SSH connection timeout in seconds. Only used for
                  'SSHProcessManager'.

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

    pman: ProcessManagerType | None = None

    if hostname == "localhost" and username is None:
        kwargs = {"username": username, "privkeypath": privkeypath, "timeout": timeout}
        _check_for_none(hostname, kwargs)
        pman = LocalProcessManager.LocalProcessManager()
    elif hostname.startswith("emulation"):
        pman = EmulProcessManager.EmulProcessManager(hostname=hostname)
    else:
        pman = SSHProcessManager.SSHProcessManager(hostname, username=username,
                                                   privkeypath=privkeypath, timeout=timeout)

    return pman

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
        return cast(ProcessManagerType, contextlib.nullcontext(enter_result=pman))

    return LocalProcessManager.LocalProcessManager()
