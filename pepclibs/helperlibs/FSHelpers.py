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
from pepclibs.helperlibs import ProcessManager, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorExists

# Default debugfs mount point.
DEBUGFS_MOUNT_POINT = Path("/sys/kernel/debug")

# A unique object used as the default value for the 'default' key in some functions.
_RAISE = object()

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

def get_homedir(pman=None):
    """
    Return home directory path. By default returns current user's local home directory path.

    The 'pman' argument is the process manger object which defines the host to get the home
    directory on. By default, the home directory on the local host will be returned.
    """

    if pman and pman.is_remote:
        return Path(pman.run_verify("echo $HOME", shell=True)[0].strip())
    return Path("~").expanduser()

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

def get_mtime(path, pman=None):
    """
    Returns the modification time of file or directory on the host defined by the 'pman' process
    manager object (local host by default).
    """

    if not pman:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            raise ErrorNotFound(f"'{path}' does not exist") from None
        except OSError as err:
            raise Error(f"'stat()' failed for '{path}':\n{err}") from None

    cmd = f"stat -c %Y -- {path}"

    try:
        stdout, _ = pman.run_verify(cmd)
    except Error as err:
        if "No such file or directory" in str(err):
            raise ErrorNotFound(f"'{path}' does not exist{pman.hostmsg}") from None
        raise

    mtime = stdout.strip()
    if not Trivial.is_float(mtime):
        raise Error(f"got erroneous mtime of '{path}'{pman.hostmsg}:\n{mtime}")
    return float(mtime)

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

def mktemp(prefix=None, tmpdir=None, pman=None):
    """
    Create a temporary directory by running the 'mktemp' tool. The 'prefix' argument can be used to
    specify the temporary directory name prefix. The 'tmpdir' argument path to the base directory
    where the temporary directory should be created.

    The 'pman' argument is the process manger object which defines the host to create the temporary
    directory on. By default, the temporary directory will be created on the local host.
    """

    if not pman:
        import tempfile # pylint: disable=import-outside-toplevel

        try:
            path = tempfile.mkdtemp(prefix=prefix, dir=tmpdir)
        except OSError as err:
            raise Error(f"failed to create temporary directory: {err}") from err

        _LOG.debug("created local temporary directory '%s'", path)
        return Path(path)

    cmd = "mktemp -d -t '"
    if prefix:
        cmd += prefix
    cmd += "XXXXXX'"
    if tmpdir:
        cmd += " -p '{tmpdir}'"
    path, _ = pman.run_verify(cmd)

    path = path.strip()
    if not path:
        raise Error(f"cannot create a temporary directory{pman.hostmsg}, the following command "
                    f"returned an empty string:\n{cmd}")
    _LOG.debug("created a temporary directory '%s'%s", path, pman.hostmsg)
    return Path(path)

def shell_test(path, opt, pman=None):
    """
    Run the shell 'test' comman against path 'path'. The 'opt' argument specifies the the 'test'
    command options. For example, pass '-f' to run 'test -f' which returns 0 if 'path' exists and is
    a regular file and 1 otherwise.

    The 'pman' argument is the process manger object which defines the host to run the comman on.
    By default, the shell test command will be run on the local host.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        cmd = f"test {opt} '{path}'"
        stdout, stderr, exitcode = wpman.run(cmd, shell=True)
        if stderr and exitcode == 127:
            # There is some output in 'stderr' and exit code is 127, which happens when the 'test'
            # command is not in '$PATH'. Let's try running 'sh' with '-l', which will make it read
            # '/etc/profile' and possibly ensure that 'test' is in '$PATH'.
            cmd = f"sh -c -l 'test {opt} \"{path}\"'"
            stdout, stderr, exitcode = wpman.run(cmd, shell=True)

        if stdout or stderr or exitcode not in (0, 1):
            raise Error(wpman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

    return exitcode == 0

def mkdir(dirpath, parents=False, exist_ok=False, pman=None):
    """
    Create a directory. If 'parents' is 'True', the parent directories are created as well. If the
    directory already exists, this function raises an exception if 'exist_ok' is 'True', and it
    returns without an error if 'exist_ok' is 'False'.

    The 'pman' argument is the process manger object which defines the host to create the directory
    on. By default, the directory will be created on the local host.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        exists_err = f"path '{dirpath}' already exists{wpman.hostmsg}"
        if shell_test(dirpath, "-e", pman=wpman):
            if exist_ok:
                return
            raise ErrorExists(exists_err)

        if wpman.is_remote:
            cmd = "mkdir"
            if parents:
                cmd += " -p"
            cmd += f" -- '{dirpath}'"
            wpman.run_verify(cmd)
        else:
            try:
                dirpath.mkdir(parents=parents, exist_ok=exist_ok)
            except FileExistsError as err:
                if not exist_ok:
                    raise ErrorExists(exists_err) from None
            except OSError as err:
                raise Error(f"failed to create directory '{dirpath}':\n{err}") from None

def rm_minus_rf(path, pman=None):
    """
    Remove 'path' using 'rm -rf' on the host defined by the 'pman' process manager object
    (local host by default). If 'path' is a symlink, the link is removed, but the target of the link
    is not removed.
    """

    if pman and pman.is_remote:
        pman.run_verify(f"rm -rf -- {path}")
        return

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass
    except (OSError, shutil.Error) as err:
        raise Error(f"failed to remove {path}: {err}") from err

def exists(path, pman=None):
    """
    Return 'True' if path 'path' exists on the host defined by the 'pman' process manager object
    (local host by default).
    """

    if pman and pman.is_remote:
        return shell_test(path, "-e", pman=pman)

    try:
        return path.exists()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists on the local host: {err}") from None

def isfile(path, pman=None):
    """
    Return 'True' if path 'path' exists an it is a regular file on the host defined by the 'pman'
    process manager object (local host by default).
    """

    if pman and pman.is_remote:
        return shell_test(path, "-f", pman=pman)

    try:
        return path.is_file()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a regular file on the local "
                    f"host: {err}") from None

def isdir(path, pman=None):
    """
    Return 'True' if path 'path' exists an it is a directory on the host defined by the 'pman'
    process manager object (local host by default).
    """

    if pman and pman.is_remote:
        return shell_test(path, "-d", pman=pman)

    try:
        return path.is_dir()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a directory on local host: "
                    f"{err}") from None

def isexe(path, pman=None):
    """
    Return 'True' if path 'path' exists an it is an executable file on the host defined by the
    'pman' process manager object (local host by default).
    """

    if pman and pman.is_remote:
        return shell_test(path, "-x", pman=pman)

    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is an executable file on the local "
                    f"host: {err}") from None

def issocket(path, pman=None):
    """
    Return 'True' if path 'path' exists an it is a Unix socket file on the host defined by the
    'pman' process manager object (local host by default).
    """

    if pman and pman.is_remote:
        return shell_test(path, "-S", pman=pman)

    try:
        return path.is_socket()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a Unix socket file on the local "
                    f"host: {err}") from None

def which(program, default=_RAISE, pman=None):
    """
    Find full path of a program by searching it in '$PATH'. Return the full path if the program was
    found, otherwise retruns 'default' or rises an exception if the 'default' value was not
    provided.

    The 'pman' argument is the process manger object which defines the host to search on. By
    default, search on the local host.
    """

    if pman and pman.is_remote:
        cmd = f"which -- '{program}'"
        stdout, stderr, exitcode = pman.run(cmd)
        if not exitcode:
            # Which could return several paths. They may contain aliases. Refrain from using
            # '--skip-alias' to make sure we work with older 'which' programs too.
            for line in stdout.strip().splitlines():
                line = line.strip()
                if not line.startswith("alias"):
                    return Path(line)
            if default is _RAISE:
                raise ErrorNotFound(f"program '{program}' was not found in $PATH{pman.hostmsg}")
            return default

        # The 'which' tool exits with status 1 when the program is not found. Any other error code
        # is an real failure that we always want to report.
        if exitcode != 1:
            raise Error(pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

        if default is _RAISE:
            raise ErrorNotFound(pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))
        return default

    program = Path(program)
    if os.access(program, os.F_OK | os.X_OK) and Path(program).is_file():
        return program

    envpaths = os.environ["PATH"]
    for path in envpaths.split(os.pathsep):
        path = path.strip('"')
        candidate = Path(f"{path}/{program}")
        if os.access(candidate, os.F_OK | os.X_OK) and candidate.is_file():
            return candidate

    if default is _RAISE:
        raise ErrorNotFound(f"program '{program}' was not found in $PATH ({envpaths})")
    return default

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

    if not must_exist and not exists(path, pman=pman):
        return

    if pman and pman.is_remote:
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
            yield (einfo["name"], Path(path / einfo["name"]), einfo["ftype"])

def abspath(path, must_exist=True, pman=None):
    """
    Returns absolute real path for 'path' on the host defined by 'pman'. All the components of the
    path should exist by default, otherwise this function raises and exception. But if 'must_exist'
    is 'False', then it is acceptable for the components of the path not to exist.

    The 'pman' argument is the process manger object which defines the host 'path' resides on. By
    default, 'path' is assumed to be on the local host.
    """

    if not pman or not pman.is_remote:
        try:
            rpath = path.resolve()
        except OSError as err:
            raise Error(f"failed to get real path for '{path}': {err}") from None
        if must_exist and not rpath.exists():
            raise Error(f"path '{rpath}' does not exist")
        return rpath

    if must_exist:
        opt = "-e"
    else:
        opt = "-m"

    stdout, _ = pman.run_verify(f"readlink {opt} -- {path}")
    return Path(stdout.strip())

def read(path, default=_RAISE, pman=None):
    """
    Read file 'path'. If it fails return 'default' or rise an exception if the 'default' value
    was not provided.

    The 'pman' argument is the process manger object which defines the host 'path' resides on. By
    default, 'path' is assumed to be on the local host.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        try:
            with wpman.open(path, "r") as fobj:
                val = fobj.read().strip()
        except Error as err:
            if default is _RAISE:
                raise type(err)(f"failed to read file '{path}'{wpman.hostmsg}:\n{err}") from err
            return default

    return val

def read_int(path, default=_RAISE, pman=None):
    """Read an integer from file 'path'. Other arguments are same as in 'read()'."""

    with ProcessManager.pman_or_local(pman) as wpman:
        val = read(path, default=default, pman=wpman)
        if val is default:
            return val
        if not Trivial.is_int(val):
            if default is _RAISE:
                raise Error(f"unexpected non-integer value in file '{path}'{wpman.hostmsg}")
            return default
        return int(val)

def write(path, data, pman=None):
    """
    Write data 'data' to file 'path' on the host defined by the 'pman' process manager object
    (local host by default).
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        try:
            with wpman.open(path, "w") as fobj:
                fobj.write(str(data))
        except Error as err:
            raise type(err)(f"failed to write into file '{path}'{wpman.hostmsg}:\n{err}") from err

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
            if exists(path, pman=wpman):
                return
            time.sleep(interval)

        interval = Human.duration(timeout)
        raise Error(f"file '{path}' did not appear{wpman.hostmsg} within '{interval}'")
