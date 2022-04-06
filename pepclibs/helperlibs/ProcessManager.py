# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a unified way of creating a process manager object for local or remote hosts.
"""

from pepclibs.helperlibs.Exceptions import Error

def _check_for_none(hostname, **kwargs):
    """
    A helper function that makes sure that argument 'kwargs' are all set to 'None'.
    """

    for name, val in kwargs.items():
        if val is not None:
            raise Error(f"BUG: get_pmon: hostname is '{hostname}', but argument '{name}' is not "
                        f"'None'. Instead, it is '{val}'")

def get_pman(hostname, username=None, privkeypath=None, timeout=None, datapath=None):
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
     2. 'hostname' is any string except for "localhost" and "emulation". Create and return an
        'SSHProcessManager' object, which will be connected to the 'hostname' host over SSH and will
        manage processes on the 'hostname' host over SSH.
     3. 'hostname is "emulation". Create and return an 'EmulProcessManager' object. This object
        is used for testing purposes only. However, if 'datapath' is 'None', then this is treated as
        case #2.

    The arguments are as follows.
      * hostname - the host name to create a process manager object for.
      * username - the user name to use for logging into the 'hostname' host over SSH.
      * privkeypath - path to SSH private key to use for logging into the host.
      * timeout - the SSH connection time out in seconds.
      * datapath - path to the emulation data.

    The 'hostname' argument is used for all types of process managers. The 'username',
    'privkeypath', and 'timeout' arguments are used only for 'SSHProcessManager'. Have to be 'None'
    for everything else. The 'datapath' argument is used only for the 'EmulProcessManager' process
    manager, and it defines the emulated host data. Must be 'None' for everything else.

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

    # pylint: disable=import-outside-toplevel

    if hostname == "localhost" and username is None:
        _check_for_none(hostname, username=username, privkeypath=privkeypath, timeout=timeout,
                        datapath=datapath)

        from pepclibs.helperlibs import LocalProcessManager

        pman = LocalProcessManager.LocalProcessManager()
    elif hostname == "emulation" and datapath is not None:
        _check_for_none(hostname, username=username, privkeypath=privkeypath, timeout=timeout)

        from pepclibs.helperlibs import EmulProcessManager

        pman = EmulProcessManager.EmulProcessManager()
        pman.init_testdata("CPUInfo", datapath)

    else:
        _check_for_none(hostname, datapath=datapath)

        from pepclibs.helperlibs import SSHProcessManager

        pman = SSHProcessManager.SSHProcessManager(hostname=hostname, username=username,
                                                   privkeypath=privkeypath, timeout=timeout)

    return pman
