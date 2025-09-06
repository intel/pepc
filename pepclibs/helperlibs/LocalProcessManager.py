# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API for executing commands and managing files and processes on the local host. Implement
the 'ProcessManagerBase' API, with the idea of having a unified API for executing commands locally
and remotely.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import os
import time
import errno
import shutil
import socket
import typing
import tempfile
import subprocess
from pathlib import Path
from typing import IO, cast
from operator import itemgetter
from pepclibs.helperlibs import Logging, _ProcessManagerBase, ClassHelpers
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType
from pepclibs.helperlibs.Exceptions import Error, ErrorTimeOut, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.helperlibs._ProcessManagerBase import LsdirTypedDict

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class LocalProcess(_ProcessManagerBase.ProcessBase):
    """A local process created and managed by 'LocalProcessManager'."""

    def __init__(self,
                 pman: LocalProcessManager,
                 pobj: subprocess.Popen,
                 cmd: str,
                 real_cmd: str,
                 streams: tuple[IO[bytes] | None, IO[bytes] | None, IO[bytes] | None]):
        """Refer to 'ProcessBase.__init__()'."""

        super().__init__(pman, pobj, cmd, real_cmd, streams)

        self.pman: LocalProcessManager
        self.pobj: subprocess.Popen
        self.stdin: IO[bytes]
        self.streams: list[IO[bytes]]

    def _fetch_stream_data(self, streamid: int, size: int) -> bytes:
        """Refer to 'ProcessBase._fetch_stream_data()'."""

        retries = 0
        max_retries = 16

        while retries < max_retries:
            retries += 1

            try:
                return self._streams[streamid].read(size)
            except BaseException as err:
                if getattr(err, "errno", None) == errno.EAGAIN:
                    continue
                raise

        raise Error(f"Received 'EAGAIN' error {retries} times")

    def _wait_timeout(self, timeout: int | float) -> int | None:
        """
        Wait for the process to finish within a specified timeout.

        Args:
            timeout: The maximum time to wait for the process to finish, in seconds.

        Returns:
            The exit code of the process if it finishes within the timeout, or None if the timeout
            expires.
        """

        self._dbg("LocalProcess._wait_timeout(): Waiting for exit status, timeout %s sec", timeout)

        try:
            exitcode = self.pobj.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._dbg("LocalProcess._wait_timeout(): Did not exit for %s secs", timeout)
            return None

        self._dbg("LocalProcess._wait_timeout: Exit status %d", exitcode)
        return exitcode

    def poll(self) -> int | None:
        """Refer to 'ProcessBase.poll()'."""

        return self.pobj.poll()

    def _wait(self,
              timeout: int | float = 0,
              capture_output: bool = True,
              output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
              lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Refer to 'ProcessBase._wait()'."""

        if not self.pobj.stdout and not self.pobj.stderr:
            self.exitcode = self._wait_timeout(timeout)
            return [[], []]

        self._dbg_log_buffered_output("LocalProcess._wait()")

        start_time = time.time()

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("LocalProcess._wait(): Process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                self._dbg("LocalProcess._wait(): Nothing in the queue for %d seconds", timeout)
                break

            if data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)
            else:
                # One of the output streams closed.
                self._dbg("LocalProcess._wait(): Stream %d closed", streamid)

                thread = self._threads[streamid]
                self._threads[streamid] = None
                self._streams[streamid] = None

                assert thread is not None
                thread.join()

                if not self._threads[0] and not self._threads[1]:
                    self._dbg("LocalProcess._wait(): Both streams closed")
                    self.exitcode = self._wait_timeout(timeout)
                    break

            if not timeout:
                self._dbg(f"LocalProcess._wait(): Timeout is {timeout}, exit immediately")
                break

            if time.time() - start_time >= timeout:
                self._dbg("LocalProcess._wait(): Stop waiting for the process - timeout")
                break

        return self._get_lines_to_return(lines)

class LocalProcessManager(_ProcessManagerBase.ProcessManagerBase):
    """
    Provide API for executing commands and managing files and processes on the local host.
    Implements the 'ProcessManagerBase' API, with the idea of having a unified API for executing
    commands locally and remotely.
    """

    def _run_async(self,
                  command: str | Path,
                  cwd: str | Path | None = None,
                  stdin: IO | int = subprocess.PIPE,
                  stdout: IO | int = subprocess.PIPE,
                  stderr: IO | int = subprocess.PIPE,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False) -> LocalProcess:
        """
        Run a command asynchronously. Implement 'run_async()' using 'subprocess.Popen()'.

        Args:
            command: The command to execute. Can be a string or a 'pathlib.Path' pointing to the
                     file to execute.
            cwd: The working directory for the process.
            stdin: The standard input stream to use. Defaults to a pipe.
            stdout: The standard output stream to use. Defaults to a pipe.
            stderr: The standard error stream to use. Defaults to a pipe.
            env: Environment variables for the process.
            newgrp: Create a new group for the process, as opposed to using the parent process
                    group.

        Returns:
            A 'LocalProcess' object representing the executed asynchronous process.
        """

        command = str(command)
        cmd: str | list[str]

        real_cmd = cmd = f"exec {command}"

        try:
            # pylint: disable=consider-using-with
            pobj = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd,
                                    bufsize=0, env=env, shell=True, start_new_session=newgrp)
        except FileNotFoundError as err:
            raise self._command_not_found(command, str(err))
        except OSError as err:
            raise Error(f"cannot execute the following command{self.hostmsg}:\n{real_cmd}\n"
                        f"The error is: {err}") from err

        streams = (pobj.stdin, pobj.stdout, pobj.stderr)

        proc = LocalProcess(self, pobj, command, real_cmd, streams)
        proc.pid = pobj.pid

        return proc

    def run_async(self,
                  cmd: str | Path,
                  cwd: str | Path | None = None,
                  intsh: bool = False,
                  stdin: IO | None = None,
                  stdout: IO | None = None,
                  stderr: IO | None = None,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False) -> LocalProcess:
        """Refer to 'ProcessManagerBase.run_async()'."""

        command = str(cmd)

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if cwd:
                cwd_msg = f"\nWorking directory: {cwd}"
            else:
                cwd_msg = ""
            _LOG.debug("Running the following local command asynchronously (newgrp %s):\n"
                       "%s%s", str(newgrp), command, cwd_msg)

        popen_stdin: IO | int = stdin if stdin is not None else subprocess.PIPE
        popen_stdout: IO | int = stdout if stdout is not None else subprocess.PIPE
        popen_stderr: IO | int = stderr if stderr is not None else subprocess.PIPE

        return self._run_async(command, cwd=cwd, stdin=popen_stdin, stdout=popen_stdout,
                               stderr=popen_stderr, env=env, newgrp=newgrp)

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = None,
            capture_output: bool = True,
            mix_output: bool = False,
            join: bool = True,
            output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
            cwd: str | Path | None = None,
            intsh: bool | None = None,
            env: dict[str, str] | None = None,
            newgrp: bool = False) -> ProcWaitResultType:
        """Refer to 'ProcessManagerBase.run()'."""

        cmd = str(cmd)

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if cwd:
                cwd_msg = f"\nWorking directory: {cwd}"
            else:
                cwd_msg = ""
            _LOG.debug("Running the following local command (newgrp %s):\n%s%s",
                       str(newgrp), cmd, cwd_msg)

        stdout = subprocess.PIPE
        if mix_output:
            stderr = subprocess.STDOUT
        else:
            stderr = subprocess.PIPE

        with self._run_async(cmd, stdout=stdout, stderr=stderr, cwd=cwd, env=env,
                             newgrp=newgrp) as proc:
            # Wait for the command to finish and handle the time-out situation.
            result = proc.wait(capture_output=capture_output, output_fobjs=output_fobjs,
                               timeout=timeout, join=join)

        if result.exitcode is None:
            msg = self.get_cmd_failure_msg(cmd, result.stdout, result.stderr, result.exitcode,
                                           timeout=timeout)
            raise ErrorTimeOut(msg)

        return result

    def run_verify(self,
                   cmd: str | Path,
                   timeout: int | float | None = None,
                   capture_output: bool = True,
                   mix_output: bool = False,
                   join: bool = True,
                   output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                   cwd: str | Path | None = None,
                   intsh: bool | None = None,
                   env: dict[str, str] | None = None,
                   newgrp: bool = False) -> tuple[str | list[str], str | list[str]]:
        """Refer to 'ProcessManagerBase.run_verify()'."""

        result = self.run(cmd, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs,
                          cwd=cwd, intsh=intsh, env=env, newgrp=newgrp)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        msg = self.get_cmd_failure_msg(cmd, result.stdout, result.stderr, result.exitcode,
                                       timeout=timeout)
        raise Error(msg)

    def rsync(self,
              src: str | Path,
              dst: str | Path,
              opts: str = "-rlD",
              remotesrc: bool = False,
              remotedst: bool = False):
        """Refer to 'ProcessManagerBase.rsync()'."""

        for arg in ("remotesrc", "remotedst"):
            if locals()[arg]:
                raise Error(f"The 'LocalProcessManager' class does not support 'rsync' "
                            f"from/to a remote host: the {arg} argument must be 'False'")

        opts = self._rsync_add_debug_opts(opts)

        cmd = f"rsync {opts} -- '{src}' '{dst}'"
        try:
            stdout, _ = self.run_verify(cmd)
        except Error as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to copy files '{src}' to '{dst}':\n{msg}") from err

        assert isinstance(stdout, str)

        self._rsync_debug_log(stdout)

    def get(self, src: str | Path, dst: str | Path):
        """Refer to 'ProcessManagerBase.get()'."""

        try:
            shutil.copy(src, dst)
        except (OSError, shutil.Error) as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to copy files '{src}' to '{dst}':\n{msg}") from err

    def put(self, src: str | Path, dst: str | Path):
        """Refer to 'ProcessManagerBase.put()'."""

        self.get(src, dst)

    def open(self, path: str | Path, mode: str) -> IO:
        """Refer to 'ProcessManagerBase.open()'."""

        # pylint: disable=consider-using-with,unspecified-encoding

        errmsg = f"failed to open file '{path}' with mode '{mode}': "
        try:
            # Binary mode doesn't take an encoding argument.
            if "b" in mode:
                fobj = open(path, mode)
            else:
                fobj = open(path, mode, encoding="utf-8")
        except PermissionError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"{errmsg}\n{msg}") from None

        # Make sure all file methods raise only exceptions derived from 'Error'.
        wfobj = ClassHelpers.WrapExceptions(fobj, get_err_prefix=_ProcessManagerBase.get_err_prefix)
        if "b" in mode:
            return cast(IO[bytes], wfobj)
        return cast(IO[str], wfobj)

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""

        try:
            return time.time()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to get the current time:\n{msg}") from None

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkdir()'."""

        try:
            Path(dirpath).mkdir(parents=parents, exist_ok=exist_ok)
        except FileExistsError:
            if not exist_ok:
                raise ErrorExists(f"Path '{dirpath}' already exists") from None
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create directory '{dirpath}':\n{msg}") from None

    def mksocket(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mksocket()'."""

        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(path))
        except OSError as err:
            if err.errno != errno.EADDRINUSE:
                msg = Error(str(err)).indent(2)
                raise Error(f"Failed to create socket '{path}':\n{msg}") from None
            if not exist_ok:
                raise ErrorExists(f"Path '{path}' already exists") from None

    def mkfifo(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkfifo()'."""

        try:
            os.mkfifo(path)
        except FileExistsError:
            if not exist_ok:
                raise ErrorExists(f"Path '{path}' already exists") from None
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create named pipe '{path}':\n{msg}") from None

    def lsdir(self, path: str | Path) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase.lsdir()'."""

        path = Path(path)

        try:
            entries = list(os.listdir(path))
        except FileNotFoundError:
            raise ErrorNotFound(f"Directory '{path}' does not exist") from None
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to get list of files in '{path}':\n{msg}") from None

        info: dict[str, LsdirTypedDict] = {}

        # For each directory entry, get its file type and ctime. Fill the entry dictionary value.
        for entry in entries:
            try:
                stinfo = path.joinpath(entry).lstat()
            except OSError as err:
                msg = Error(str(err)).indent(2)
                raise Error(f"'lstat()' failed for '{entry}':\n{msg}") from None

            info[entry] = {"name": entry,
                           "path": path / entry,
                           "ctime": stinfo.st_ctime,
                           "mode": stinfo.st_mode}

        yield from sorted(info.values(), key=itemgetter("ctime"), reverse=True)

    def exists(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.exists()'."""

        try:
            return Path(path).exists()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists:\n{msg}") from None

    def is_file(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_file()'."""

        try:
            return Path(path).is_file()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists and it is a regular file:\n{msg}") \
                        from None

    def is_dir(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_dir()'."""

        try:
            return Path(path).is_dir()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists and it is a directory:\n{msg}") \
                        from None

    def is_exe(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_exe()'."""

        try:
            return Path(path).is_file() and os.access(path, os.X_OK)
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists and it is an executable file:\n"
                        f"{msg}") from None

    def is_socket(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_socket()'."""

        try:
            return Path(path).is_socket()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists and it is a Unix socket file:\n"
                        f"{msg}") from None

    def is_fifo(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_fifo()'."""

        try:
            return Path(path).is_fifo()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to check if '{path}' exists and it is a named pipe (FIFO):\n"
                        f"{msg}") from None

    def get_mtime(self, path: str | Path) -> float:
        """Refer to 'ProcessManagerBase.get_mtime()'."""

        try:
            return Path(path).stat().st_mtime
        except FileNotFoundError:
            raise ErrorNotFound(f"'{path}' does not exist") from None
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"'stat()' failed for '{path}':\n{msg}") from None

    def unlink(self, path: str | Path):
        """Refer to 'ProcessManagerBase.unlink()'."""

        try:
            os.unlink(Path(path))
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to remove '{path}':\n{msg}") from None

    def rmtree(self, path: str | Path):
        """Refer to 'ProcessManagerBase.rmtree()'."""

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
                msg = Error(str(err)).indent(2)
                raise Error(f"Failed to remove {path}:\n{msg}") from err
            break

    def abspath(self, path: str | Path) -> Path:
        """Refer to 'ProcessManagerBase.abspath()'."""

        try:
            rpath = Path(path).resolve()
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to get real path for '{path}':\n{msg}") from None

        if not rpath.exists():
            raise ErrorNotFound(f"Path '{rpath}' does not exist")

        return rpath

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """Refer to 'ProcessManagerBase.mkdtemp()'."""

        try:
            path = tempfile.mkdtemp(prefix=prefix, dir=basedir)
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create a temporary directory:\n{msg}") from err

        _LOG.debug("Created a temporary directory '%s'", path)
        return Path(path)

    def get_envar(self, envar: str) -> str | None:
        """Refer to 'ProcessManagerBase.get_envar()'."""

        return os.environ.get(envar)

    def which(self, program: str | Path, must_find: bool = True):
        """Refer to 'ProcessManagerBase.which()'."""

        if os.access(program, os.F_OK | os.X_OK) and Path(program).is_file():
            return program

        envpaths = os.environ["PATH"]
        for path in envpaths.split(os.pathsep):
            path = path.strip('"')
            candidate = Path(f"{path}/{program}")
            if os.access(candidate, os.F_OK | os.X_OK) and candidate.is_file():
                return candidate

        if must_find:
            raise ErrorNotFound(f"Program '{program}' was not found in $PATH ({envpaths})")

        return None
