# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains misc. helper functions related to file-system operations.
"""

import os
import time
from pathlib import Path
from collections import namedtuple
from pepclibs.helperlibs import Logging, ProcessManager, Human
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"pepc.{__name__}")

# The debugfs mount point path.
DEBUGFS_MOUNT_POINT = Path("/sys/kernel/debug")

def get_mount_points(pman=None):
    """
    Parse mount points in '/proc/mounts' for each mount point yield the following named tuple.
      * device - name of the mounted device.
      * mntpoint - mount point path.
      * fstype - file-system type.
      * options - list of options.

    The arguments are as follows.
      * pman - the process manager object defining the host to parse '/proc/mounts' on (local host
               by default).
    """

    mounts_file = "/proc/mounts"
    mntinfo = namedtuple("mntinfo", ["device", "mntpoint", "fstype", "options"])

    with ProcessManager.pman_or_local(pman) as wpman:
        with wpman.open(mounts_file, "r") as fobj:
            try:
                contents = fobj.read()
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"cannot read '{mounts_file}':\n{msg}") from err

    for line in contents.splitlines():
        if not line:
            continue

        device, mntpoint, fstype, options, _ = line.split(maxsplit=4)
        yield mntinfo(device, mntpoint, fstype, options.split(","))

def mount_debugfs(mnt=None, pman=None):
    """
    Mount the debugfs file-system. The arguments are as follow.
      * mnt - the mount point path (default is 'DEBUGFS_MOUNT_POINT').
      * pman - the process manager object defining the host to mount debugfs on (local host by
               default).

    Return a tuple of the following elements.
      * the mount point path.
      * 'True' if debugfs was mounted by this function, 'False' it has already been mounted.
    """

    if not mnt:
        mnt = DEBUGFS_MOUNT_POINT
    else:
        try:
            mnt = Path(os.path.realpath(mnt)).resolve()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"cannot resolve path '{mnt}':\n{msg}") from None

    for mntinfo in get_mount_points(pman=pman):
        if mntinfo.fstype == "debugfs" and Path(mntinfo.mntpoint) == mnt:
            # Already mounted.
            return mnt, False

    pman.run_verify(f"mount -t debugfs none '{mnt}'")
    return mnt, True

def wait_for_a_file(path, interval=1, timeout=60, pman=None):
    """
    Wait for a file or directory to get created. The arguments are as follows.
      * path - path to the file of directory to wait for.
      * interval - the interval in seconds to poll for 'path'.
      * timeout - for how many seconds to poll until raising an exception.
      * pman - the process manager object defining the host 'path' resides on (local host by
               default).

    Periodically poll for the file or directory at 'path' every 'interval' seconds. If the file does
    not get created within 'timeout' seconds, raise an exception.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if wpman.exists(path):
                return
            time.sleep(interval)

        interval = Human.duration(timeout)
        raise Error(f"file '{path}' did not appear{wpman.hostmsg} within '{interval}'")
