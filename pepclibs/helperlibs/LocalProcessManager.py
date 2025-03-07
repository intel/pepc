# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module implements a process manager for running and monitoring local processes.
"""

# pylint: disable=arguments-differ

# TODO: finish adding type hints to this module.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import os
import time
import shlex
import errno
import shutil
import subprocess
from pathlib import Path
from operator import itemgetter
from pepclibs.helperlibs import Logging, _ProcessManagerBase, ClassHelpers
from pepclibs.helperlibs._ProcessManagerBase import ProcResult # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error, ErrorTimeOut, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class LocalProcess(_ProcessManagerBase.ProcessBase):
    """
    This class represents a process that was executed by 'LocalProcessManager'.
    """

    def _fetch_stream_data(self, streamid, size):
        """Fetch up to 'size' bytes from stdout or stderr of the process."""

        retries = 0
        max_retries = 16

        while retries < max_retries:
            retries += 1

            try:
                return self._streams[streamid].read(size)
            except Exception as err:
                if getattr(err, "errno", None) == errno.EAGAIN:
                    continue
                raise

        raise Error(f"received 'EAGAIN' error {retries} times")

    def _wait_timeout(self, timeout):
        """Wait for process to finish with a timeout."""

        pobj = self.pobj
        self._dbg("_wait_timeout: waiting for exit status, timeout %s sec", timeout)
        try:
            exitcode = pobj.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._dbg("_wait_timeout: exit status not ready for %s seconds", timeout)
            return None

        self._dbg("_wait_timeout: exit status %d", exitcode)
        return exitcode

    def _wait(self, timeout=None, capture_output=True, output_fobjs=(None, None),
              lines=(None, None)):
        """
        Implements 'wait()'. The arguments are the same as in 'wait()', but returns a list of two
        lists: '[stdout_lines, stderr_lines]' (lists of stdout/stderr lines).
        """

        if not self.pobj.stdout and not self.pobj.stderr:
            self.exitcode = self._wait_timeout(timeout)
            return [[], []]

        start_time = time.time()

        self._dbg("_wait: starting with partial: %s, output:\n%s", self._partial, str(self._output))

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("_wait: process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                self._dbg("_wait: nothing in the queue for %d seconds", timeout)
                break
            if data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)
            else:
                self._dbg("_wait: stream %d closed", streamid)
                # One of the output streams closed.
                self._threads[streamid].join()
                self._threads[streamid] = self._streams[streamid] = None

                if not self._streams[0] and not self._streams[1]:
                    self._dbg("_wait: both streams closed")
                    self.exitcode = self._wait_timeout(timeout)
                    break

            if not timeout:
                self._dbg(f"_wait: timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time >= timeout:
                self._dbg("_wait: stop waiting for the process - timeout")
                break

        return self._get_lines_to_return(lines)

    def poll(self):
        """
        Check if the process is still running. If it is, return 'None', else return exit status.
        """
        return self.pobj.poll()

class LocalProcessManager(_ProcessManagerBase.ProcessManagerBase):
    """
    This class implements a process manager for running and monitoring local processes. The
    implementation is based on 'Popen()'.
    """

    def _run_async(self, command, cwd=None, shell=True, stdin=None, stdout=None, stderr=None,
                   bufsize=0, env=None, newgrp=False) -> LocalProcess:
        """Implements 'run_async()'."""

        # pylint: disable=consider-using-with
        try:
            if stdin and isinstance(stdin, str):
                fname = stdin
                stdin = open(fname, "r", encoding="utf-8")

            if stdout and isinstance(stdout, str):
                fname = stdout
                stdout = open(fname, "w+", encoding="utf-8")

            if stderr and isinstance(stderr, str):
                fname = stderr
                stderr = open(fname, "w+", encoding="utf-8")
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"cannot open file '{fname}':\n{msg}") from None

        if not stdin:
            stdin = subprocess.PIPE
        if not stdout:
            stdout = subprocess.PIPE
        if not stderr:
            stderr = subprocess.PIPE

        if shell:
            real_cmd = cmd = f"exec {command}"
        else:
            real_cmd = command
            cmd = shlex.split(command)

        try:
            pobj = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr, bufsize=bufsize,
                                    cwd=cwd, env=env, shell=shell, start_new_session=newgrp)
        except FileNotFoundError as err:
            raise self._command_not_found(command, str(err))
        except OSError as err:
            raise Error(f"cannot execute the following command{self.hostmsg}:\n{real_cmd}\n"
                        f"The error is: {err}") from err

        streams = (pobj.stdin, pobj.stdout, pobj.stderr)
        proc = LocalProcess(self, pobj, command, real_cmd, shell, streams)
        proc.pid = pobj.pid
        return proc

    def run_async(self, command, cwd=None, shell=True, intsh=False, stdin=None, stdout=None,
                  stderr=None, bufsize=0, env=None, newgrp=False,):
        """
        Run command 'command' on the local host using 'Popen'. Refer to
        'ProcessManagerBase.run_async()' for more information.

        Notes.

        1. The 'bufsize' and 'env' arguments are the same as in 'Popen()'.
        2. If the 'newgrp' argument is 'True', then executed process gets a new session ID.
        3. The 'intsh' argument is ignored.
        """

        # pylint: disable=unused-argument,arguments-differ
        if cwd:
            cwd_msg = f"\nWorking directory: {cwd}"
        else:
            cwd_msg = ""
        _LOG.debug("running the following local command asynchronously (shell %s, newgrp %s):\n"
                   "%s%s", str(shell), str(newgrp), command, cwd_msg)

        # Allow for 'command' to be a 'pathlib.Path' object which Paramiko does not accept.
        command = str(command)

        return self._run_async(command, cwd=cwd, shell=shell, stdin=stdin, stdout=stdout,
                               stderr=stderr, bufsize=bufsize, env=env, newgrp=newgrp)

    def run(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
            output_fobjs=(None, None), cwd=None, shell=True, intsh=None, bufsize=0, env=None,
            newgrp=False):
        """
        Run command 'command' on the local host and wait for it to finish. Refer to
        'ProcessManagerBase.run()' for more information.

        Notes.

        1. The 'bufsize' and 'env' arguments are the same as in 'Popen()'.
        2. If the 'newgrp' argument is 'True', then executed process gets a new session ID.
        3. The 'intsh' argument is ignored.
        """

        # pylint: disable=unused-argument,arguments-differ
        if cwd:
            cwd_msg = f"\nWorking directory: {cwd}"
        else:
            cwd_msg = ""
        _LOG.debug("running the following local command (shell %s, newgrp %s):\n%s%s",
                   str(shell), str(newgrp), command, cwd_msg)

        stdout = subprocess.PIPE
        if mix_output:
            stderr = subprocess.STDOUT
        else:
            stderr = subprocess.PIPE

        with self._run_async(command, stdout=stdout, stderr=stderr, cwd=cwd, shell=shell,
                             bufsize=bufsize, env=env, newgrp=newgrp) as proc:
            # Wait for the command to finish and handle the time-out situation.
            result = proc.wait(capture_output=capture_output, output_fobjs=output_fobjs,
                               timeout=timeout, join=join)

        if result.exitcode is None:
            msg = self.get_cmd_failure_msg(command, *tuple(result), timeout=timeout)
            raise ErrorTimeOut(msg)

        if output_fobjs[0]:
            output_fobjs[0].flush()
        if output_fobjs[1]:
            output_fobjs[1].flush()

        return result

    def run_verify(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
                   output_fobjs=(None, None), cwd=None, shell=True, intsh=None, bufsize=0, env=None,
                   newgrp=False):
        """
        Same as 'run()' but verifies the command's exit code and raises an exception if it is not 0.
        """

        # pylint: disable=unused-argument,arguments-differ
        result = self.run(command, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs,
                          cwd=cwd, shell=shell, intsh=intsh, bufsize=bufsize, env=env,
                          newgrp=newgrp)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        raise Error(self.get_cmd_failure_msg(command, *tuple(result), timeout=timeout))

    def rsync(self, src, dst, opts="-rlD", remotesrc=False, remotedst=False):
        """
        Copy data from path 'src' to path 'dst' using the 'rsync' tool with options specified in
        'opts'. Refer to '_ProcessManagerBase.rsync() for more information.

        Limitation: the 'remotedst' and 'remotesrc' options must be 'False'. Copying from/to a
        remote host is not supported.
        """

        for arg in ("remotesrc", "remotedst"):
            if locals()[arg]:
                raise Error(f"BUG: the 'LocalProcessManager' class does not support 'rsync' "
                            f"from/to a remote host: the {arg} argument must be 'False'")

        opts = self._rsync_add_debug_opts(opts)

        # pylint: disable=unused-argument
        cmd = f"rsync {opts} -- '{src}' '{dst}'"
        try:
            stdout, _ = self.run_verify(cmd)
        except Error as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to copy files '{src}' to '{dst}':\n{msg}") from err

        self._rsync_debug_log(stdout)

    @staticmethod
    def open(path, mode):
        """
        Open a file. Refer to '_ProcessManagerBase.ProcessManagerBase().open()' for more
        information.
        """

        def get_err_prefix(fobj, method):
            """Return the error message prefix."""
            return f"method '{method}()' failed for file '{fobj.name}'"

        errmsg = f"failed to open file '{path}' with mode '{mode}': "
        try:
            # Binary mode doesn't take an encoding argument.
            if "b" in mode:
                fobj = open(path, mode) # pylint: disable=consider-using-with,unspecified-encoding
            else:
                fobj = open(path, mode, encoding="utf-8") # pylint: disable=consider-using-with
        except PermissionError as err:
            msg = Error(err).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(err).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
        except Exception as err:
            msg = Error(err).indent(2)
            raise Error(f"{errmsg}\n{msg}") from None

        # Make sure all file methods raise only exceptions derived from 'Error'.
        return ClassHelpers.WrapExceptions(fobj, get_err_prefix=get_err_prefix)

    @staticmethod
    def time_time():
        """
        Return the time in seconds since the epoch as a floating point number (just as the standard
        python 'time.time()' function).
        """
        return time.time()

    @staticmethod
    def mkdir(dirpath, parents=False, exist_ok=False):
        """
        Create a directory. Refer to '_ProcessManagerBase.ProcessManagerBase().mkdir()' for more
        information.
        """

        try:
            Path(dirpath).mkdir(parents=parents, exist_ok=exist_ok)
        except FileExistsError:
            if not exist_ok:
                raise ErrorExists(f"path '{dirpath}' already exists") from None
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to create directory '{dirpath}':\n{msg}") from None

    @staticmethod
    def lsdir(path, must_exist=True):
        """
        List directory entries in 'path'. Refer to
        '_ProcessManagerBase.ProcessManagerBase().lsdir()' for more information.
        """

        path = Path(path)

        if not must_exist and not path.exists():
            return

        # Get list of directory entries. For a dummy dictionary out of it. We'll need it later for
        # sorting by ctime.
        try:
            entries = {entry : None for entry in os.listdir(path)}
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to get list of files in '{path}':\n{msg}") from None

        # For each directory entry, get its file type and ctime. Fill the entry dictionary value.
        for entry in entries:
            try:
                stinfo = path.joinpath(entry).lstat()
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"'stat()' failed for '{entry}':\n{msg}") from None

            entries[entry] = {"name": entry, "ctime": stinfo.st_ctime, "mode": stinfo.st_mode}

        for einfo in sorted(entries.values(), key=itemgetter("ctime"), reverse=True):
            yield (einfo["name"], path / einfo["name"], einfo["mode"])

    @staticmethod
    def exists(path):
        """Returns 'True' if path 'path' exists."""

        try:
            return Path(path).exists()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to check if '{path}' exists:\n{msg}") from None

    @staticmethod
    def is_file(path):
        """Return 'True' if path 'path' exists an it is a regular file."""

        try:
            return Path(path).is_file()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to check if '{path}' exists and it is a regular file:\n{msg}") \
                        from None

    @staticmethod
    def is_dir(path):
        """Return 'True' if path 'path' exists an it is a directory."""

        try:
            return Path(path).is_dir()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to check if '{path}' exists and it is a directory:\n{msg}") \
                        from None

    @staticmethod
    def is_exe(path):
        """Return 'True' if path 'path' exists an it is an executable file."""

        try:
            return Path(path).is_file() and os.access(path, os.X_OK)
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to check if '{path}' exists and it is an executable file:\n"
                        f"{msg}") from None

    @staticmethod
    def is_socket(path):
        """Return 'True' if path 'path' exists an it is a Unix socket file."""

        try:
            return Path(path).is_socket()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to check if '{path}' exists and it is a Unix socket file:\n"
                        f"{msg}") from None

    @staticmethod
    def get_mtime(path):
        """Returns the modification time of a file or directory at path 'path'."""

        try:
            return Path(path).stat().st_mtime
        except FileNotFoundError:
            raise ErrorNotFound(f"'{path}' does not exist") from None
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"'stat()' failed for '{path}':\n{msg}") from None

    @staticmethod
    def rmtree(path):
        """
        Create a temporary directory. Refer to '_ProcessManagerBase.ProcessManagerBase().rmtree()'
        for more information.
        """

        path = Path(path)

        # Sometimes shutil.rmtree() fails to remove non empty directory, in such case, retry few
        # times.
        retry = 3
        while True:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except FileNotFoundError:
                pass
            except (OSError, shutil.Error) as err:
                if retry:
                    retry -= 1
                    continue
                msg = Error(err).indent(2)
                raise Error(f"failed to remove {path}:\n{msg}") from err
            break

    @staticmethod
    def abspath(path, must_exist=True):
        """
        Create a temporary directory. Refer to '_ProcessManagerBase.ProcessManagerBase().abspath()'
        for more information.
        """

        try:
            rpath = Path(path).resolve()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to get real path for '{path}':\n{msg}") from None

        if must_exist and not rpath.exists():
            raise ErrorNotFound(f"path '{rpath}' does not exist")

        return rpath

    @staticmethod
    def mkdtemp(prefix=None, basedir=None):
        """
        Create a temporary directory. Refer to '_ProcessManagerBase.ProcessManagerBase().mkdtemp()'
        for more information.
        """

        import tempfile # pylint: disable=import-outside-toplevel

        try:
            path = tempfile.mkdtemp(prefix=prefix, dir=basedir)
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to create a temporary directory:\n{msg}") from err

        _LOG.debug("created a temporary directory '%s'", path)
        return Path(path)

    @staticmethod
    def get_homedir():
        """Return return the home directory of the current user."""
        return Path("~").expanduser()

    @staticmethod
    def get(src, dst):
        """Copy a file or directory from 'src' to 'dst'."""

        try:
            shutil.copy(src, dst)
        except (OSError, shutil.Error) as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to copy files '{src}' to '{dst}':\n{msg}") from err

    @staticmethod
    def which(program, must_find=True):
        """
        Find and return full path to a program 'program'. Refer to
        '_ProcessManagerBase.ProcessManagerBase().which()' for more information.
        """

        program = Path(program)
        if os.access(program, os.F_OK | os.X_OK) and Path(program).is_file():
            return program

        envpaths = os.environ["PATH"]
        for path in envpaths.split(os.pathsep):
            path = path.strip('"')
            candidate = Path(f"{path}/{program}")
            if os.access(candidate, os.F_OK | os.X_OK) and candidate.is_file():
                return candidate

        if must_find:
            raise ErrorNotFound(f"program '{program}' was not found in $PATH ({envpaths})")
        return None

    def __init__(self):
        """Initialize a class instance."""

        super().__init__()

        self.is_remote = False
        self.hostname = "localhost"
        self.hostmsg = ""
