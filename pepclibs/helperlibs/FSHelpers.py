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
import sys
import stat
import time
import shutil
import logging
from pathlib import Path
from hashlib import sha512
from operator import itemgetter
from collections import namedtuple
from pepclibs.helperlibs import Procs, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorExists

# Default debugfs mount point.
DEBUGFS_MOUNT_POINT = Path("/sys/kernel/debug")

# A unique object used as the default value for the 'default' key in some functions.
_RAISE = object()

_LOG = logging.getLogger()

def get_sha512(path, default=_RAISE, proc=None, skip_lines=0):
    """
    Calculate sha512 checksum of the file 'path' on the host defined by 'proc'. The'default'
    argument can be used as an return value instead of raising an error. The 'skip_lines' argument
    tells how many lines from the beginning will be excluded from checksum calculation.
    """

    if not proc:
        proc = Procs.Proc()

    try:
        with proc.open(path, "rb") as fobj:
            while skip_lines:
                skip_lines -= 1
                fobj.readline()

            data = fobj.read()
            checksum = sha512(data).hexdigest()
    except Error as err:
        if default is _RAISE:
            raise Error(f"cannot calculate sha512 checksum for the file '{path}'{proc.hostmsg}:\n"
                        f"{err}") from err
        return default

    return checksum

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

def get_homedir(proc=None):
    """
    Return home directory path. By default returns current user's local home directory path.
    If the 'procs' argument contains a connected "SSH" object, then this function returns home
    directory path of the connected user on the remote host.
    """

    if proc and proc.is_remote:
        return Path(proc.run_verify("echo $HOME", shell=True)[0].strip())
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

def move_copy_link(src: Path, dst: Path, action: str = "symlink", exist_ok: bool = False):
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

def find_app_data(appname, subpath: Path, pre: str = None, descr: str = None, default=_RAISE):
    """
    Search for application 'appname' data. The data are searched for
    in 'subpath' sub-path of the following directories (and in the following order):
      * in the directory the of the running process (sys.argv[0])
      * the the directories in the 'pre' list, if it was specified
      * in the directory specified by the f'{appname}_DATA_PATH' environment variable
      * $HOME/.local/share/<appname>/, if it exists
      * /usr/local/share/<appname>/, if it exists
      * /usr/share/<appname>/, if it exists

    By default this function raises an exception if 'subpath' was not found. The'default' argument
    can be used as an return value instead of raising an error.
    The 'descr' argument is a human-readable description of 'subpath', which will be used in the
    error message if error is raised.
    """

    searched = []
    paths = pre
    if not paths:
        paths = []

    paths.append(Path(sys.argv[0]).parent)

    path = os.environ.get(f"{appname}_DATA_PATH".upper())
    if path:
        paths.append(Path(path))

    for path in paths:
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    path = Path("~").expanduser() / Path(f".local/share/{appname}/{subpath}")
    if path.exists():
        return path

    searched.append(path)

    for path in (Path(f"/usr/local/share/{appname}"), Path(f"/usr/share/{appname}")):
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    if default is _RAISE:
        if not descr:
            descr = f"'{subpath}'"
        searched = [str(s) for s in searched]
        dirs = " * " + "\n * ".join(searched)

        raise Error(f"cannot find {descr}, searched in the following directories on local host:\n"
                    f"{dirs}")
    return default

def get_mtime(path: Path, proc=None):
    """Returns file or directory mtime."""

    if not proc:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            raise ErrorNotFound(f"'{path}' does not exist") from None
        except OSError as err:
            raise Error(f"'stat()' failed for '{path}':\n{err}") from None

    cmd = f"stat -c %Y -- {path}"

    try:
        stdout, _ = proc.run_verify(cmd)
    except Error as err:
        if "No such file or directory" in str(err):
            raise ErrorNotFound(f"'{path}' does not exist{proc.hostmsg}") from None
        raise

    mtime = stdout.strip()
    if not Trivial.is_float(mtime):
        raise Error(f"got erroneous mtime of '{path}'{proc.hostmsg}:\n{mtime}")
    return float(mtime)

def mount_points(proc=None):
    """
    This generator parses '/proc/mounts' and for each mount point yields the following named tuples:
      * device - name of the mounted device
      * mntpoint - mount point
      * fstype - file-system type
      * options - list of options

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    mounts_file = "/proc/mounts"
    mntinfo = namedtuple("mntinfo", ["device", "mntpoint", "fstype", "options"])

    if not proc:
        proc = Procs.Proc()

    try:
        with proc.open(mounts_file, "r") as fobj:
            contents = fobj.read()
    except OSError as err:
        raise Error(f"cannot read '{mounts_file}': {err}") from err

    for line in contents.splitlines():
        if not line:
            continue

        device, mntpoint, fstype, options, _ = line.split(maxsplit=4)
        yield mntinfo(device, mntpoint, fstype, options.split(","))

def mount_debugfs(mnt: Path = None, proc=None):
    """
    Mount the debugfs file-system to 'mnt' on the host. By default it is mounted to
    'DEBUGFS_MOUNT_POINT'. The 'proc' argument defines the host to mount debugfs on (default is the
    local host). Returns the mount point path.
    """

    if not mnt:
        mnt = DEBUGFS_MOUNT_POINT
    else:
        try:
            mnt = Path(os.path.realpath(mnt)).resolve()
        except OSError as err:
            raise Error(f"cannot resolve path '{mnt}': {err}") from None

    for mntinfo in mount_points(proc=proc):
        if mntinfo.fstype == "debugfs" and Path(mntinfo.mntpoint) == mnt:
            # Already mounted.
            return mnt

    proc.run_verify(f"mount -t debugfs none '{mnt}'")
    return mnt

def mktemp(prefix: str = None, tmpdir: Path = None, proc=None):
    """
    Create a temporary directory by running the 'mktemp' tool. The 'prefix' argument can be used to
    specify the temporary directory name prefix. The 'tmpdir' argument path to the base directory
    where the temporary directory should be created.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not proc:
        import tempfile # pylint: disable=import-outside-toplevel

        try:
            path = tempfile.mkdtemp(prefix=prefix, dir=tmpdir)
        except OSError as err:
            raise Error("failed to create temporary directory: {err}") from err

        _LOG.debug("created local temporary directory '%s'", path)
        return Path(path)

    cmd = "mktemp -d -t '"
    if prefix:
        cmd += prefix
    cmd += "XXXXXX'"
    if tmpdir:
        cmd += " -p '{tmpdir}'"
    path, _ = proc.run_verify(cmd)

    path = path.strip()
    if not path:
        raise Error(f"cannot create a temporary directory{proc.hostmsg}, the following command "
                    f"returned an empty string:\n{cmd}")
    _LOG.debug("created a temporary directory '%s'%s", path, proc.hostmsg)
    return Path(path)

def shell_test(path: Path, opt: str, proc=None):
    """
    Run a shell test against path 'path'. The 'opt' argument specifies the the 'test' command
    options. For example, pass '-f' to run 'test -f' which returns 0 if 'path' exists and is a
    regular file and 1 otherwise.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not proc:
        proc = Procs.Proc()

    cmd = f"test {opt} '{path}'"
    stdout, stderr, exitcode = proc.run(cmd, shell=True)
    if stderr and exitcode == 127:
        # There is some output in 'stderr' and exit code is 127, which happens when the 'test'
        # command is not in '$PATH'. Let's try running 'sh' with '-l', which will make it read
        # '/etc/profile' and possibly ensure that 'test' is in '$PATH'.
        cmd = f"sh -c -l 'test {opt} \"{path}\"'"
        stdout, stderr, exitcode = proc.run(cmd, shell=True)

    if stdout or stderr or exitcode not in (0, 1):
        raise Error(proc.cmd_failed_msg(cmd, stdout, stderr, exitcode))

    return exitcode == 0

def mkdir(dirpath: Path, parents: bool = False, exist_ok: bool = False, proc=None):
    """
    Create a directory. If 'parents' is 'True', the parent directories are created as well. If the
    directory already exists, this function raises an exception if 'exist_ok' is 'True', and it
    returns without an error if 'exist_ok' is 'False'.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not proc:
        proc = Procs.Proc()

    exists_err = f"path '{dirpath}' already exists{proc.hostmsg}"
    if shell_test(dirpath, "-e", proc=proc):
        if exist_ok:
            return
        raise ErrorExists(exists_err)

    if proc.is_remote:
        cmd = "mkdir"
        if parents:
            cmd += " -p"
        cmd += f" -- '{dirpath}'"
        proc.run_verify(cmd)
    else:
        try:
            dirpath.mkdir(parents=parents, exist_ok=exist_ok)
        except FileExistsError as err:
            if not exist_ok:
                raise ErrorExists(exists_err) from None
        except OSError as err:
            raise Error(f"failed to create directory '{dirpath}':\n{err}") from None

def rm_minus_rf(path: Path, proc=None):
    """
    Remove 'path' using 'rm -rf' on the host definec by 'Proc' (local host by default). If 'path' is
    a symlink, the link is removed, but the target of the link is not removed.
    """

    if proc and proc.is_remote:
        proc.run_verify(f"rm -rf -- {path}")
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

def exists(path: Path, proc=None):
    """
    Return 'True' if path 'path' exists on the host defined by 'proc' (local host by default).
    """

    if proc and proc.is_remote:
        return shell_test(path, "-e", proc=proc)

    try:
        return path.exists()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists on the local host: {err}") from None

def isfile(path: Path, proc=None):
    """
    Return 'True' if path 'path' exists an it is a regular file. The check is done on the host
    defined by 'proc' (local host by default).
    """

    if proc and proc.is_remote:
        return shell_test(path, "-f", proc=proc)

    try:
        return path.is_file()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a regular file on the local "
                    f"host: {err}") from None

def isdir(path: Path, proc=None):
    """
    Return 'True' if path 'path' exists an it is a directory. The check is done on the host
    defined by 'proc' (local host by default).
    """

    if proc and proc.is_remote:
        return shell_test(path, "-d", proc=proc)

    try:
        return path.is_dir()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a directory on local host: "
                    f"{err}") from None

def isexe(path: Path, proc=None):
    """
    Return 'True' if path 'path' exists an it is an executable file. The check is done on the host
    defined by 'proc' (local host by default).
    """

    if proc and proc.is_remote:
        return shell_test(path, "-x", proc=proc)

    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is an executable file on the local "
                    f"host: {err}") from None

def issocket(path: Path, proc=None):
    """
    Return 'True' if path 'path' exists an it is a Unix socket file. The check is done on the host
    defined by 'proc' (local host by default).
    """

    if proc and proc.is_remote:
        return shell_test(path, "-S", proc=proc)

    try:
        return path.is_socket()
    except OSError as err:
        raise Error(f"failed to check if '{path}' exists and it is a Unix socket file on the local "
                    f"host: {err}") from None

def which(program: str, default=_RAISE, proc=None):
    """
    Find full path of a program by searching it in '$PATH'. Return the full path if the program was
    found, otherwise retruns 'default' or rises an exception if the 'default' value was not
    provided.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if proc and proc.is_remote:
        cmd = f"which -- '{program}'"
        stdout, stderr, exitcode = proc.run(cmd)
        if not exitcode:
            # Which could return several paths. They may contain aliases. Refrain from using
            # '--skip-alias' to make sure we work with older 'which' programs too.
            for line in stdout.strip().splitlines():
                line = line.strip()
                if not line.startswith("alias"):
                    return Path(line)
            if default is _RAISE:
                raise ErrorNotFound(f"program '{program}' was not found in $PATH{proc.hostmsg}")
            return default

        # The 'which' tool exits with status 1 when the program is not found. Any other error code
        # is an real failure that we always want to report.
        if exitcode != 1:
            raise Error(proc.cmd_failed_msg(cmd, stdout, stderr, exitcode))

        if default is _RAISE:
            raise ErrorNotFound(proc.cmd_failed_msg(cmd, stdout, stderr, exitcode))
        return default

    program = Path(program)
    if Path(program).is_file() and os.access(program, os.X_OK):
        return program

    envpaths = os.environ["PATH"]
    for path in envpaths.split(os.pathsep):
        path = path.strip('"')
        candidate = Path(f"{path}/{program}")
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    if default is _RAISE:
        raise ErrorNotFound(f"program '{program}' was not found in $PATH ({envpaths})")
    return default

def lsdir(path: Path, must_exist: bool = True, proc=None):
    """
    For each directory entry in 'path', yield the ('name', 'path', 'type') tuple, where 'name' is
    the direntry name, 'path' is full directory entry path, and 'type' is the file type indicator
    (see 'ls --file-type' for details).

    The directory entries are yielded in ctime (creation time) order.

    If 'path' does not exist, this function raises an exception. However, this behavior can be
    changed with the 'must_exist' argument. If 'must_exist' is 'False, this function just returns
    and does not yield anything.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not must_exist and not exists(path, proc=proc):
        return

    if not proc:
        proc = Procs.Proc()

    if proc and proc.is_remote:
        stdout, _ = proc.run_verify(f"ls -c -1 --file-type -- '{path}'", join=False)
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

def abspath(path: Path, must_exist: bool = True, proc=None):
    """
    Returns absolute real path for 'path' on the host define by 'proc'. All the components of the
    path should exist by default, otherwise this function raises and exception. But if 'must_exist'
    is 'False', then it is acceptable for the components of the path not to exist.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not proc or not proc.is_remote:
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

    stdout, _ = proc.run_verify(f"readlink {opt} -- {path}")
    return Path(stdout.strip())

def read(path, default=_RAISE, proc=None):
    """
    Read file 'path'. If it fails return 'default' or rise an exception if the 'default' value
    was not provided. By default this function operates on the local host, but the 'proc' argument
    can be used to pass a connected 'SSH' object in which case this function will operate on the
    remote host.
    """

    if not proc:
        proc = Procs.Proc()

    try:
        with proc.open(path, "r") as fobj:
            val = fobj.read().strip()
    except Error as err:
        if default is _RAISE:
            raise Error(f"failed to read file '{path}'{proc.hostmsg}:\n{err}") from err
        return default

    return val

def read_int(path, default=_RAISE, proc=None):
    """Read an integer from file 'path'. Other arguments are same as in 'read()'."""

    if not proc:
        proc = Procs.Proc()

    val = read(path, default=default, proc=proc)
    if val is default:
        return val
    if not Trivial.is_int(val):
        if default is _RAISE:
            raise Error(f"unexpected non-integer value in file '{path}'{proc.hostmsg}")
        return default
    return int(val)

def write(path, data, proc=None):
    """Write data 'data' into file 'path'."""

    if not proc:
        proc = Procs.Proc()

    try:
        with proc.open(path, "w") as fobj:
            fobj.write(str(data))
    except Error as err:
        raise Error(f"failed to write into file '{path}'{proc.hostmsg}:\n{err}") from err

def wait_for_a_file(path: Path, interval: int = 1, timeout: int = 60, proc=None):
    """
    Wait for a file or directory defined by path 'path' to get created. This function just
    periodically polls for the file every 'interval' seconds. If the file does not get created
    within 'timeout' seconds, then this function fails with an exception.

    By default this function operates on the local host, but the 'proc' argument can be used to pass
    a connected 'SSH' object in which case this function will operate on the remote host.
    """

    if not proc:
        proc = Procs.Proc()

    start_time = time.time()
    while time.time() - start_time < timeout:
        if exists(path, proc=proc):
            return
        time.sleep(interval)

    interval = Human.duration(timeout)
    raise Error(f"file '{path}' did not appear{proc.hostmsg} within '{interval}'")
