# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains misc. helper functions related to file-system operations.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import time
import typing
from pathlib import Path
from pepclibs.helperlibs import Logging, ProcessManager, Human
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Final, TypedDict, Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class MountInfoTypedDict(TypedDict, total=False):
        """
        Typed dictionary for mount point information.

        Attributes:
            device: Name of the mounted device.
            mntpoint: Mount point path.
            fstype: File-system type.
            options: List of mount options.
        """

        device: str
        mntpoint: str
        fstype: str
        options: list[str]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# The debugfs mount point path.
DEBUGFS_MOUNT_POINT: Final[Path] = Path("/sys/kernel/debug")

def get_mount_points(pman: ProcessManagerType | None = None) -> Generator[MountInfoTypedDict,
                                                                          None, None]:
    """
    Parse and yield mount points information from '/proc/mounts' on a local or remote host.

    Args:
        pman: The process manager object for the host to read '/proc/mounts' from. If not provided,
              the local host is used.

    Yields:
        Instances of 'MountInfoTypedDict' for each mount point found in '/proc/mounts'.
    """

    mounts_file = Path("/proc/mounts")

    with ProcessManager.pman_or_local(pman) as wpman:
        with wpman.open(mounts_file, "r") as fobj:
            try:
                contents: str = fobj.read()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read '{mounts_file}'{wpman.hostmsg}:\n{errmsg}") from err

    for line in contents.splitlines():
        if not line:
            continue

        device, mntpoint, fstype, options, _ = line.split(maxsplit=4)

        mntinfo: MountInfoTypedDict = {}
        mntinfo["device"] = device
        mntinfo["mntpoint"] = mntpoint
        mntinfo["fstype"] = fstype
        mntinfo["options"] = options.split(",")
        yield mntinfo

def mount_debugfs(mnt: Path | None = None,
                  pman: ProcessManagerType | None = None) -> tuple[Path, bool]:
    """
    Mount the debugfs file system at the specified mount point.

    Args:
        mnt: The mount point path, use 'DEBUGFS_MOUNT_POINT' if not provided.
        pman: The process manager object specifying the host to mount debugfs on. If not provided,
              the local host is used.

    Returns:
        A tuple containing:
            - The mount point path.
            - True if debugfs was mounted by this function, False if it was already mounted.

    Notes:
        - If debugfs is already mounted at the specified mount point, do not remount it.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        if not mnt:
            mount_point = DEBUGFS_MOUNT_POINT
        else:
            try:
                mount_point = wpman.abspath()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to resolve path '{mount_point}'{wpman.hostmsg}:\n"
                            f"{errmsg}") from err

        for mntinfo in get_mount_points(pman=wpman):
            if mntinfo["fstype"] == "debugfs" and Path(mntinfo["mntpoint"]) == mount_point:
                # Already mounted.
                return mount_point, False

        wpman.run_verify(f"mount -t debugfs none '{mount_point}'")
        return mount_point, True

def wait_for_a_file(path: Path,
                    interval: int = 1,
                    timeout: int | float = 60,
                    pman: ProcessManagerType | None = None):
    """
    Wait for a file or directory to be created within a specified timeout.

    Args:
        path: Path to the file or directory to wait for.
        interval: Number of seconds to wait between polling attempts.
        timeout: Maximum number of seconds to wait before raising an exception.
        pman: The process manager object specifying the host where 'path' resides. If not provided,
               the local host is used.

    Raises:
        Error: If the file or directory does not appear within the specified timeout.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if wpman.exists(path):
                return
            time.sleep(interval)

        interval_str = Human.duration(timeout)
        raise Error(f"File '{path}' did not appear{wpman.hostmsg} within '{interval_str}'")
