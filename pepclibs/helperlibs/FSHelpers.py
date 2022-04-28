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
import stat
import time
import shutil
import logging
from pathlib import Path
from operator import itemgetter
from collections import namedtuple
from pepclibs.helperlibs import ProcessManager, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorExists

# Default debugfs mount point.
DEBUGFS_MOUNT_POINT = Path("/sys/kernel/debug")

_LOG = logging.getLogger()

def set_default_perm(path):
    """
    Set access mode for a 'path'. Mode is 666 for file and 777 for directory, and current umask
    value is first masked out.
    """

    try:
        curmode = os.stat(path).st_mode
        # umask() returns existing umask, but requires new mask as an argument. Restore original
        # mask immediately.
        curumask = os.umask(0o022)
        os.umask(curumask)

        if stat.S_ISDIR(curmode):
            mode = 0o0777
        else:
            mode = 0o0666

        mode = ~curumask & mode
        if stat.S_IMODE(curmode) != mode:
            os.chmod(path, mode)
    except OSError as err:
        raise Error(f"cannot change '{path}' permissions to {oct(mode)}:\n{err}") from None

def _copy_dir(src: Path, dst: Path, ignore=None):
    """Implements the 'copy_dir()' function."""

    try:
        if not dst.parent.exists():
            dst.parent.mkdir(parents=True)

        if src.resolve() in dst.resolve().parents:
            raise Error(f"cannot do recursive copy from '{src}' to '{dst}'")

        ignore_names = None
        if ignore:
            ignore_names = lambda path, content: ignore

        shutil.copytree(src, dst, ignore=ignore_names)
    except (OSError, shutil.Error) as err:
        raise Error(f"cannot copy '{src}' to '{dst}':\n{err}") from err

def copy_dir(src: Path, dst: Path, exist_ok: bool = False, ignore=None):
    """
    Copy 'src' directory to 'dst'. The 'ignore' argument is a list of file or directory
    names which will be ignored and not copied.
    """

    exists_err = f"cannot copy '{src}' to '{dst}', the destination path already exists"
    if dst.exists():
        if exist_ok:
            return
        raise ErrorExists(exists_err)

    if not src.is_dir():
        raise Error("cannot copy '{src}' to '{dst}', the destination path is not directory.")

    _copy_dir(src, dst, ignore)

def move_copy_link(src, dst, action="symlink", exist_ok=False):
    """
    Moves, copy. or link the 'src' file or directory to 'dst' depending on the 'action' contents
    ('move', 'copy', 'symlink').
    """

    exists_err = f"cannot {action} '{src}' to '{dst}', the destination path already exists"
    if dst.exists():
        if exist_ok:
            return
        raise ErrorExists(exists_err)

    # Type cast in shutil.move() can be removed when python is fixed. See
    # https://bugs.python.org/issue32689
    try:
        if action == "move":
            if src.is_dir():
                try:
                    dst.mkdir(parents=True, exist_ok=True)
                except FileExistsError as err:
                    if not exist_ok:
                        raise ErrorExists(exists_err) from None
                for item in src.iterdir():
                    shutil.move(str(item), dst)
            else:
                shutil.move(str(src), dst)
        elif action == "copy":
            if not dst.parent.exists():
                dst.parent.mkdir(parents=True)

            if src.is_dir():
                _copy_dir(src, dst)
            else:
                shutil.copyfile(src, dst)
        elif action == "symlink":
            if not dst.is_dir():
                dstdir = dst.parent
            else:
                dstdir = dst

            if not dst.parent.exists():
                dst.parent.mkdir(parents=True)

            os.symlink(os.path.relpath(src.resolve(), dstdir.resolve()), dst)
        else:
            raise Error(f"unrecognized action '{action}'")
    except (OSError, shutil.Error) as err:
        raise Error(f"cannot {action} '{src}' to '{dst}':\n{err}") from err

def mount_points(pman=None):
    """
    This generator parses '/proc/mounts' and for each mount point yields the following named tuples:
      * device - name of the mounted device
      * mntpoint - mount point
      * fstype - file-system type
      * options - list of options

    The 'pman' argument is the process manger object which defines the host to parse '/proc/mounts'
    on. By default, local host's '/proc/mounts' will be parsed.
    """

    mounts_file = "/proc/mounts"
    mntinfo = namedtuple("mntinfo", ["device", "mntpoint", "fstype", "options"])

    with ProcessManager.pman_or_local(pman) as wpman:
        with wpman.open(mounts_file, "r") as fobj:
            try:
                contents = fobj.read()
            except OSError as err:
                raise Error(f"cannot read '{mounts_file}': {err}") from err

    for line in contents.splitlines():
        if not line:
            continue

        device, mntpoint, fstype, options, _ = line.split(maxsplit=4)
        yield mntinfo(device, mntpoint, fstype, options.split(","))

def mount_debugfs(mnt=None, pman=None):
    """
    Mount the debugfs file-system to 'mnt' on the host. By default it is mounted to
    'DEBUGFS_MOUNT_POINT'. The 'pman' argument defines the host to mount debugfs on (default is the
    local host). Returns the mount point path.
    """

    if not mnt:
        mnt = DEBUGFS_MOUNT_POINT
    else:
        try:
            mnt = Path(os.path.realpath(mnt)).resolve()
        except OSError as err:
            raise Error(f"cannot resolve path '{mnt}': {err}") from None

    for mntinfo in mount_points(pman=pman):
        if mntinfo.fstype == "debugfs" and Path(mntinfo.mntpoint) == mnt:
            # Already mounted.
            return mnt

    pman.run_verify(f"mount -t debugfs none '{mnt}'")
    return mnt

def lsdir(path, must_exist=True, pman=None):
    """
    For each directory entry in 'path', yield the ('name', 'path', 'type') tuple, where 'name' is
    the direntry name, 'path' is full directory entry path, and 'type' is the file type indicator
    (see 'ls --file-type' for details).

    The directory entries are yielded in ctime (creation time) order.

    If 'path' does not exist, this function raises an exception. However, this behavior can be
    changed with the 'must_exist' argument. If 'must_exist' is 'False, this function just returns
    and does not yield anything.

    The 'pman' argument is the process manger object which defines the host 'path' resides on. By
    default, 'path' is assumed to be on the local host.
    """

    path = Path(path)

    if pman and pman.is_remote:
        if not must_exist and not pman.exists(path):
            return

        stdout, _ = pman.run_verify(f"ls -c -1 --file-type -- '{path}'", join=False)
        if not stdout:
            return

        for entry in (entry.strip() for entry in stdout):
            ftype = ""
            if entry[-1] in "/=>@|":
                ftype = entry[-1]
                entry = entry[:-1]
            yield (entry, Path(f"{path}/{entry}"), ftype)
    else:
        if not must_exist and not path.exists():
            return

        # Get list of directory entries. For a dummy dictionary out of it. We'll need it later for
        # sorting by ctime.
        try:
            entries = {entry : None for entry in os.listdir(path)}
        except OSError as err:
            raise Error(f"failed to get list of files in '{path}':\n{err}") from None

        # For each directory entry, get its file type and ctime. Fill the entry dictionary value.
        for entry in entries:
            try:
                stinfo = path.joinpath(entry).lstat()
            except OSError as err:
                raise Error(f"'stat()' failed for '{entry}':\n{err}") from None

            entries[entry] = {"name" : entry, "ctime" : stinfo.st_ctime}

            if stat.S_ISDIR(stinfo.st_mode):
                ftype = "/"
            elif stat.S_ISLNK(stinfo.st_mode):
                ftype = "@"
            elif stat.S_ISSOCK(stinfo.st_mode):
                ftype = "="
            elif stat.S_ISFIFO(stinfo.st_mode):
                ftype = "|"
            else:
                ftype = ""

            entries[entry]["ftype"] = ftype

        for einfo in sorted(entries.values(), key=itemgetter("ctime"), reverse=True):
            yield (einfo["name"], path / einfo["name"], einfo["ftype"])

def wait_for_a_file(path, interval=1, timeout=60, pman=None):
    """
    Wait for a file or directory defined by path 'path' to get created. This function just
    periodically polls for the file every 'interval' seconds. If the file does not get created
    within 'timeout' seconds, then this function fails with an exception.

    The 'pman' argument is the process manger object which defines the host 'path' resides on. By
    default, 'path' is assumed to be on the local host.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if wpman.exists(path):
                return
            time.sleep(interval)

        interval = Human.duration(timeout)
        raise Error(f"file '{path}' did not appear{wpman.hostmsg} within '{interval}'")
