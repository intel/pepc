# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
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

from __future__ import annotations # Remove when switching to Python 3.10+.
import contextlib
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import LocalProcessManager, SSHProcessManager, EmulProcessManager

ProcessManagerType = LocalProcessManager.LocalProcessManager | \
                     SSHProcessManager.SSHProcessManager | \
                     EmulProcessManager.EmulProcessManager

def _check_for_none(hostname, **kwargs):
    """
    A helper function that makes sure that argument 'kwargs' are all set to 'None'.
    """

    for name, val in kwargs.items():
        if val is not None:
            raise Error(f"BUG: get_pman: hostname is '{hostname}', but argument '{name}' is not "
                        f"'None'. Instead, it is '{val}'")

def get_pman(hostname, username=None, privkeypath=None, timeout=None) -> ProcessManagerType:
    """
    Creates and returns a process manager object for host 'hostname'. At the moment there are
    basically 3 possibilities.
     1. 'hostname' is "localhost".
        1.1. If 'username' is 'None', then create and return a 'LocalProcessManager' object, which
             provides an efficient way of managing local processes.
        1.2 If 'username' is not 'None', then create and return an 'SSHProcessManager' object,
            which will connect to local host over SSH and manage processes over a local SSH
            connection. This is a less efficient way of managing processes, but may be useful for,
            say, debugging purposes.
     2. 'hostname' starts with "emulation". Create and return an 'EmulProcessManager' object. This
        object is used for testing purposes only.
     3. 'hostname' is not "localhost" and does not start with "emulation". Create and return an
        'SSHProcessManager' object, which will be connected to the 'hostname' host over SSH and
        will manage processes on the 'hostname' host over SSH.


    The arguments are as follows.
      * hostname - the host name to create a process manager object for.
      * username - the user name to use for logging into the 'hostname' host over SSH.
      * privkeypath - path to SSH private key to use for logging into the host.
      * timeout - the SSH connection time out in seconds.

    The 'hostname' argument is used for all types of process managers. The 'username',
    'privkeypath', and 'timeout' arguments are used only for 'SSHProcessManager'. Have to be 'None'
    for everything else.

    Notes.
    1. The preferred way of using this method is with the 'with' statement:
          with get_pman() as pman:
              do_something(pman)
       The context manager then closes the object.
    2. The alternative way is to close the object after it had been used.
          pman = get_pman()
          try:
              do_something()
          finally:
              pman.close()
    """

    pman: ProcessManagerType | None = None

    if hostname == "localhost" and username is None:
        _check_for_none(hostname, username=username, privkeypath=privkeypath, timeout=timeout)
        pman = LocalProcessManager.LocalProcessManager()
    elif hostname.startswith("emulation"):
        pman = EmulProcessManager.EmulProcessManager(hostname=hostname)
    else:
        pman = SSHProcessManager.SSHProcessManager(hostname=hostname, username=username,
                                                   privkeypath=privkeypath, timeout=timeout)

    return pman

def pman_or_local(pman):
    """
    Return 'pman' if it is not 'None', otherwise return a new instance of 'LocalProcessManager'.

    This helper is designed for situations when you have a function, which takes a 'pman' object on
    input. However, your function allows for 'pman == None', in which case it falls back to a
    'LocalProcessManager' object.

    Here is how this helper is supposed to be used:

      with pman_or_local(pman) as wpman:
          do_stuff()

    If user provided a process manager object ('pman != None'), 'wpman' will be 'pman'. In this
    case, the 'pman.__exit__()' will not be called, which is the right thing to do because 'pman'
    came from a user, who is responsible for closing the process manager.

    If user did not provide a process manager ('pman == None'), then a 'LocalProcessManager()'
    instance will be created and closed upon exiting the 'with' context.
    """

    if pman:
        return contextlib.nullcontext(enter_result=pman)

    return LocalProcessManager.LocalProcessManager()
