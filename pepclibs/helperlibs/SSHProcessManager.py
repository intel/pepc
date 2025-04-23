# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API for executing commands and managing files and processes on a remote host via SSH.
Implement the 'ProcessManagerBase' API, with the idea of having a unified API for executing commands
locally and remotely.

SECURITY NOTICE: this module and any part of it should only be used for debugging and development
purposes. No security audit had been done. Not for production use.
"""

# TODO: finish adding type hints to this module.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import glob
import time
import stat
import types
import shlex
import random
import logging
import threading
import contextlib
from pathlib import Path
from operator import itemgetter
from typing import IO, cast, Generator
from collections.abc import Callable
try:
    import paramiko
except (ModuleNotFoundError, ImportError):
    from pepclibs.helperlibs import DummyParamiko as paramiko  # type: ignore[no-redef]
from pepclibs.helperlibs import Logging, _ProcessManagerBase, ClassHelpers, Trivial
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType, LsdirTypedDict
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorTimeOut, ErrorConnect
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Paramiko is a bit too noisy, lower its log level.
logging.getLogger("paramiko").setLevel(logging.WARNING)

class SSHProcess(_ProcessManagerBase.ProcessBase):
    """
    A remote process created and managed by 'SSHProcessManager'.

    Notes about 'intsh' argument in the "run" methods.
        * There are two ways run commands remotely over SSH: in a new paramiko SSH session, and in
          the existing interactive shell session.
        * Running in a new SSH session is straight-forward, but takes time to establish a new SSH
          session.
        * Running in the interactive shell is faster, because it does not require establishing a new
          SSH session. But the implementation is more complicated.
        * The interactive shell implementation:
            - Run 'sh -s' process run in a new paramiko session.
            - Run commands in this shell. One command can run at a time. This means that one cannot
              run an asychronous command ('run_async()') in the interactive shell and then run
              another command in the same interactive shell.
            - No need to create a new SSH session between the commands
            - The complication with this method is to detect when command has finished.
            - This is solved by making each command print a unique random hash to 'stdout' when it
              finishes.
    """

    def __init__(self,
                 pman: SSHProcessManager,
                 pobj: paramiko.Channel,
                 cmd: str,
                 real_cmd: str,
                 shell: bool,
                 streams: tuple[paramiko.ChannelFile, Callable[[int], bytes], Callable[[int], bytes]]):
        """Refer to 'ProcessBase.__init__()'."""

        super().__init__(pman, pobj, cmd, real_cmd, shell, streams)

        self.pman: SSHProcessManager
        self.pobj: paramiko.Channel
        self.stdin: paramiko.ChannelFile
        self.streams: list[Callable[[int], bytes]]

        # The below attributes are used when the process runs in an interactive shell.
        #
        # The marker indicating that the command has finished.
        self._marker = ""
        # The regular expression the last line of the command output should match.
        self._marker_regex = re.compile("")
        # The last line printed by the command to stdout observed so far.
        self._ll = ""
        # Whether the last line ('ll') should be checked against the marker. Used as an optimization
        # in order to avoid matching the 'll' against the marker too often.
        self._check_ll = True

        if shell:
            self._read_pid()

    def _reinit_marker(self):
        """
        Reinitialize the marker indicates the completion of a command in the interactive shell. The
        marker ensures reliable detection of command completion in the interactive shell.
        """

        # Generate a random string which will be used as the marker, which indicates that the
        # interactive shell command has finished.
        randbits = random.getrandbits(256)
        self._marker = f"--- {randbits:064x}"
        self._marker_regex = re.compile(f"^{self._marker}, \\d+ ---$")

    def _reinit(self, cmd: str, real_cmd: str, shell: bool):
        """Refer to 'ProcessBase._reinit()'."""

        super()._reinit(cmd, real_cmd, shell)

        self._ll = ""
        self._check_ll = True
        self._lines_cnt = [0, 0]

        if shell:
            self._read_pid()

    def close(self):
        """Free allocated resources."""

        self._dbg("SSHProcessManager.close()")

        # If this is the an interactive shell process - do not close it. It'll be closed in
        # 'SSHProcessManager.close()' instead.
        if not self._marker:
            super().close()

    def _fetch_stream_data(self, streamid, size):
        """Fetch up to 'size' bytes from stdout or stderr of the process."""

        try:
            return self._streams[streamid](size)
        except BaseException as err: # pylint: disable=broad-except
            raise Error(str(err)) from err

    def _recv_exit_status_timeout(self, timeout: int | float) -> int | None:
        """
        Wait for the exit status of a remote process with a timeout.

        Args:
            timeout: Maximum time in seconds to wait for the exit status.

        Returns:
            The exit status of the remote process, or None if the timeout expires.
        """

        chan = self.pobj
        self._dbg("SSHProcess._recv_exit_status_timeout(): Waiting for exit status, timeout %s sec",
                  timeout)

#        This is non-hacky, but polling implementation.
#        if timeout:
#            start_time = time.time()
#            while not chan.exit_status_ready():
#                if time.time() - start_time > timeout:
#                    self._dbg("exit status not ready for %s seconds", timeout)
#                    return None
#                time.sleep(1)
#        exitcode = chan.recv_exit_status()

        # This is hacky, but non-polling implementation.
        if not chan.status_event.wait(timeout=timeout):
            self._dbg("SSHProcess._recv_exit_status_timeout(): Exit status not ready for %s "
                      "seconds", timeout)
            return None

        exitcode = chan.exit_status
        self._dbg("SSHProcess._recv_exit_status_timeout(): Exit status %d", exitcode)
        return exitcode

    def _process_is_done(self) -> bool:
        """Refer to 'ProcessBase._process_is_done()'."""

        return not self._ll and super()._process_is_done()

    def _watch_for_marker(self, data: str) -> tuple[str, int | None]:
        """
        Check for the marker in the stdout data of the interactive shell to determine if process has
        exited.

        Should be used only when running a command in the interactive shell session. Processes a
        piece of stdout data from the process and check for a marker that indicates that the process
        has exited.

        Returns:
            A tuple containing the captured stdout data ('cdata') and process exit code
            ('exitcode'), or 'None' if the marker is not found.
                - 'cdata': A portion of stdout data that without the marker. If the marker was
                           found, 'cdata' is 'data' minus the marker. If the marker was not found,
                           'cdata' is going to be just some portion of 'data', because part of
                           'data' might be saved in 'self._ll' if it resembles the beginning of the
                           marker.
                - 'exitcode': The exit code of the command if the marker is found. If the marker was
                              not found, alwayse return 'None' for the exit code.
        """

        exitcode = None
        cdata = None

        self._dbg("SSHProcess._watch_for_marker(): Starting with: self._check_ll: %s\n"
                  "self._ll: %s\ndata:\n%s", str(self._check_ll), str(self._ll), data)

        split = data.rsplit("\n", 1)
        if len(split) > 1:
            # Got a new marker suspect. Keep it in 'self._ll', while old 'self._ll' and the rest of
            # 'data' can be returned up for capturing. Set 'self._check_ll' to 'True' to indicate
            # that 'self._ll' has to be checked for the marker.
            cdata = self._ll + split[0] + "\n"
            self._check_ll = True
            self._ll = split[1]
        else:
            # Got a continuation of the previous line. The 'check_ll' flag is 'True' when 'self._ll'
            # being a marker is a real possibility. If we already checked 'self._ll' and it starts
            # with data that is different to the marker, there is not reason to check it again, and
            # we can send it up for capturing.
            if not self._ll:
                self._check_ll = True
            if self._check_ll:
                self._ll += split[0]
                cdata = ""
            else:
                cdata = self._ll + data
                self._ll = ""

        if self._check_ll:
            # 'self._ll' is a real suspect, check if it looks like the marker.
            self._check_ll = self._ll.startswith(self._marker) or self._marker.startswith(self._ll)

        # OK, if 'self._ll' is still a real suspect, do a full check using the regex: full marker #
        # line should contain not only the hash, but also the exit status.
        if self._check_ll and re.match(self._marker_regex, self._ll):
            # Extract the exit code from the 'self._ll' string that has the following form:
            # --- hash, <exitcode> ---
            split = self._ll.rsplit(", ", 1)
            assert len(split) == 2
            status = split[1].rstrip(" ---")
            if not Trivial.is_int(status):
                raise Error(f"The process was running{self.hostmsg} under the interactive "
                            f"shell and finished with a correct marker, but an unexpected exit "
                            f"code '{status}'.\nThe command was: {self.cmd}")

            self._ll = ""
            self._check_ll = False
            exitcode = int(status)

        self._dbg("SSHProcess._watch_for_marker(): Ending with: exitcode %s, self._check_ll: %s\n"
                  "self._ll: %s\ncdata:\n%s", str(exitcode), str(self._check_ll), self._ll, cdata)

        return (cdata, exitcode)

    def _wait_intsh(self,
                    timeout: int | float = 0,
                    capture_output: bool = True,
                    output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                    lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Implement '_wait()' for the interactive shell case. Refer to 'ProcessBase._wait()'."""

        start_time = time.time()

        self._dbg("SSHProcess._wait_intsh(): Starting with(): self._check_ll: %s\nself._ll: %s",
                  str(self._check_ll), str(self._ll))
        self._dbg_log_buffered_output(pfx="SSHProcess._wait_intsh(): Starting with")

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None and self._queue.empty():
                self._dbg("SSHProcess._wait_intsh(): Process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                # Note, 'data' is going to be 'None' in this case.
                self._dbg("SSHProcess._wait_intsh(): Nothing in the queue for %d seconds", timeout)
            elif data is None:
                raise Error(f"The interactive shell process{self.hostmsg} closed stream {streamid} "
                            f"while running the following command:\n{self.cmd}")
            elif streamid == 0:
                # The indication that the process has exited is the marker in stdout (stream 0).The
                # goal is to watch for this marker, hide it from the user, because it does not
                # belong to the output of the process. The marker always starts at the beginning of
                # line.
                data, self.exitcode = self._watch_for_marker(data)

            if data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)

            if not timeout:
                self._dbg(f"SSHProcess._wait_intsh(): Timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time > timeout:
                self._dbg("SSHProcess._wait_intsh(): Stop waiting for the process - timeout")
                break

        result = self._get_lines_to_return(lines)

        if self._process_is_done():
            # Mark the interactive shell process as vacant.
            # pylint: disable=protected-access
            acquired = self.pman._acquire_intsh_lock(self.cmd)
            if not acquired:
                _LOG.warning("Failed to mark the interactive shell process as free")
            else:
                self.pman._intsh_busy = False
                self.pman._intsh_lock.release()

        return result

    def _wait_nointsh(self,
                      timeout: int | float = 0,
                      capture_output: bool = True,
                      output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                      lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Implement '_wait()' for the new SSH session case. Refer to 'ProcessBase._wait()'."""

        start_time = time.time()

        self._dbg_log_buffered_output(pfx="SSHProcess._wait_nointsh(): Starting with")

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("SSHProcess._wait_nointsh(): Process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            self._dbg("SSHProcess._wait_nointsh(): _get_next_queue_item() returned: stream %d, "
                      "data:\n %s", streamid, data)
            if streamid == -1:
                self._dbg("SSHProcess._wait_nointsh(): Nothing in the queue for %d secs", timeout)
            elif data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)
            else:
                self._dbg("SSHProcess._wait_nointsh(): Stream %d closed", streamid)
                # One of the output streams closed.

                thread = self._threads[streamid]
                self._threads[streamid] = None

                assert thread is not None
                thread.join()

                if not self._threads[0] and not self._threads[1]:
                    self._dbg("SSHProcess._wait_nointsh(): Both streams closed")
                    self.exitcode = self._recv_exit_status_timeout(timeout)
                    break

            if not timeout:
                self._dbg(f"SSHProcess._wait_nointsh(): Timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time > timeout:
                self._dbg("SSHProcess._wait_nointsh(): Stop waiting for the process - timeout")
                break

        return self._get_lines_to_return(lines)

    def _wait(self,
              timeout: int | float = 0,
              capture_output: bool = True,
              output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
              lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Refer to 'ProcessBase._wait()'."""

        # pylint: disable=protected-access
        if self.pman._intsh and self.pobj == self.pman._intsh.pobj:
            method = self._wait_intsh
        else:
            method = self._wait_nointsh

        return method(timeout=timeout, capture_output=capture_output, output_fobjs=output_fobjs,
                      lines=lines)

    def poll(self) -> int | None:
        """Refer to 'ProcessBase.poll()'."""

        chan = self.pobj
        if chan.exit_status_ready():
            return chan.recv_exit_status()
        return None

    def _read_pid(self):
        """
        Read the process ID (PID) of the executed command and store it in 'self.pid'.

        Notes:
            - The reason this method exists is that paramiko does not have a mechanism to get PID.
              So this is a workaround.
        """

        self._dbg("SSHProcess._read_pid(): Reading PID for the following command: %s", self.cmd)
        assert self.shell

        stdout, stderr, _ = self.wait(timeout=60, lines=(1, 0), join=False)

        msg = f"\nThe command{self.hostmsg} was:\n{self.cmd}" \
              f"\nThe actual (real) command was:\n{self.real_cmd}"

        if len(stdout) != 1:
            raise Error(f"Expected only one line with PID in stdout, got {len(stdout)} lines "
                        f"instead.{msg}")
        if stderr:
            raise Error(f"Expected only one line with PID in stdout and no lines in stderr, got "
                        f"{len(stderr)} lines in stderr instead.{msg}")

        pid = stdout[0].strip()

        # The 'PID' line does not belong to the process output, it was printed by the shell. So
        # decrement the lines counter.
        self._lines_cnt[0] -= 1

        if len(pid) > 128:
            raise Error(f"Received too long and probably bogus PID: {pid}{msg}")
        if not Trivial.is_int(pid):
            raise Error(f"Received a bogus non-integer PID: {pid}{msg}")

        self._dbg("SSHProcess._read_pid(): PID is %s for the following command: %s", pid, self.cmd)
        self.pid = int(pid)

class SSHProcessManager(_ProcessManagerBase.ProcessManagerBase):
    """
    Provide API for executing commands and managing files and processes on a remote host via SSH.
    Implement the 'ProcessManagerBase' API, with the idea of having a unified API for executing
    commands locally and remotely.
    """

    def __init__(self,
                 hostname: str,
                 ipaddr: str | None = None,
                 port: int | None = None,
                 username: str | None = None,
                 password: str | None = None,
                 privkeypath: str | None = None,
                 timeout: int | float | None = None):
        """
        Initialize a class instance and establish SSH connection to a remote host.

        Args:
            hostname: The name of the host to connect to.
            ipaddr: IP address of the host. If provided, it is used instead of `hostname` for
                    connecting, and `hostname` is used for logging purposes.
            port: The port number to connect to. Defaults to 22.
            username: Username for authentication. Defaults to the current system user.
            password: Password for the specified username. Defaults to an empty string.
            privkeypath: Optional path to the private key for authentication. If no private key path
                         is provided, the method attempts to locate one using SSH configuration files.
            timeout: Timeout value for the establishing the SSH connection in seconds. Defaults to
                     60 seconds.

        Raises:
            ErrorConnect: If SSH connection cannot be established (e.g., authentication fails).
        """

        super().__init__()

        self.is_remote = True
        self.hostname = hostname
        self.hostmsg = f" on host '{hostname}'"

        if not timeout:
            timeout = 60
        self.connection_timeout = float(timeout)

        if not port:
            port = 22
        self.port = port

        if not username:
            username = os.getenv("USER")
            if not username:
                username = Trivial.get_username()
        self.username = username

        if not password:
            password = ""
        self.password = password
        self.privkeypath = privkeypath

        # The command to use for figuring out full paths in the 'which()' method.
        self._which_cmd: str | None = None

        self._sftp: paramiko.SFTPClient | None = None

        # The interactive shell session.
        self._intsh: SSHProcess | None = None
        # Whether we already run a process in the interactive shell.
        self._intsh_busy = False
        # A lock protecting 'self._intsh_busy' and 'self._intsh'. Basically this lock makes sure we
        # always run exactly one process in the interactive shell.
        self._intsh_lock = threading.Lock()

        if ipaddr:
            connhost = ipaddr
            self._vhostname = f"{hostname} ({ipaddr})"
        else:
            connhost = self._cfg_lookup("hostname", hostname, self.username)
            if connhost:
                self._vhostname = f"{hostname} ({connhost})"
            else:
                self._vhostname = connhost = hostname

        look_for_keys = False
        if not self.privkeypath:
            # Try finding the key filename from the SSH configuration files.
            look_for_keys = True
            try:
                self.privkeypath = self._lookup_privkey(hostname, self.username)
            except Exception as err: # pylint: disable=broad-except
                msg = Error(str(err)).indent(2)
                _LOG.debug(f"Private key lookup falied:\n{msg}")

        key_filename = str(self.privkeypath) if self.privkeypath else None

        if key_filename:
            # Private SSH key sanity checks.
            try:
                mode = os.stat(key_filename).st_mode
            except OSError:
                raise Error(f"'stat()' failed for private SSH key at '{key_filename}'") from None

            if not stat.S_ISREG(mode):
                raise Error(f"Private SSH key at '{key_filename}' is not a regular file")

            if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                raise Error(f"Private SSH key at '{key_filename}' permissions are too wide: Make "
                            f" sure 'others' cannot read/write/execute it")

        _LOG.debug("Establishing SSH connection to %s, port %d, username '%s', timeout '%s', "
                   "priv. key '%s', SSH pman object ID: %s", self._vhostname, port, self.username,
                   self.connection_timeout, self.privkeypath, id(self))

        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # We expect to be authenticated either with the key or an empty password.
            self.ssh.connect(username=self.username, hostname=connhost, port=port,
                             key_filename=key_filename, timeout=self.connection_timeout,
                             password=self.password, allow_agent=False, look_for_keys=look_for_keys)
        except paramiko.AuthenticationException as err:
            msg = Error(str(err)).indent(2)
            raise ErrorConnect(f"SSH authentication failed when connecting to {self._vhostname} as "
                               f"'{self.username}':\n{msg}") from err
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise ErrorConnect(f"Cannot establish TCP connection to {self._vhostname} with "
                               f"{timeout} secs time-out:\n{msg}") from err

    def close(self):
        """Close the SSH connection."""

        _LOG.debug("Closing SSH connection to %s (port %d, username '%s', priv. key '%s', SSH pman "
                   "object ID: %s", self._vhostname, self.port, self.username, self.privkeypath,
                   id(self))

        if self._intsh:
            with contextlib.suppress(BaseException):
                self._intsh.pobj.send("exit\n".encode())

        ClassHelpers.close(self, close_attrs=("_sftp", "_intsh", "ssh",))

        super().close()

    @staticmethod
    def _format_cmd_for_pid(cmd: str, cwd: Path | None = None) -> str:
        """
        Modify the command so that it prints own PID.

        Problem: paramiko does not provide a way of getting PID of the executed command.
        Soulution: start shell first, print its PID, then exec the command in the shell. The command
                   will inherit the PID of the shell.

        Args:
            cmd: The command to be executed.
            cwd: The working directory to switch to before executing the command.

        Returns:
            string that prints the PID before executing the original command.
        """

        prefix = r'printf "%s\n" "$$";'
        if cwd:
            prefix += f""" cd "{cwd}" &&"""
        return prefix + " exec " + cmd

    def _run_in_new_session(self,
                            command: str,
                            cwd: Path | None = None,
                            shell: bool = True) -> SSHProcess:
        """
        Run a command in a new SSH session.

        Args:
            command: The command to execute on the remote host.
            cwd: The working directory to set for the command.
            shell: Whether to execute the command via shell.

        Returns:
            An `SSHProcess` object representing the process running the command.
        """

        cmd = command
        if shell:
            cmd = self._format_cmd_for_pid(command, cwd=cwd)

        try:
            transport = self.ssh.get_transport()
            if not transport:
                raise Error(f"SSH transport is not available{self.hostmsg}")
            chan = transport.open_session(timeout=self.connection_timeout)
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot create a new SSH session for running the following "
                        f"command{self.hostmsg}:\n{cmd}\nThe error is:\n{msg}") from err

        try:
            chan.exec_command(cmd)
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot execute the following command in a new SSH session"
                        f"{self.hostmsg}:\n{cmd}\nThe error is:\n{msg}") from err

        try:
            stdin = chan.makefile("wb")
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create the stdin file-like object:\n{msg}") from err

        streams = (stdin, chan.recv, chan.recv_stderr)
        return SSHProcess(self, chan, command, cmd, shell, streams)

    def _run_in_intsh(self, command: str, cwd: Path | None = None) -> SSHProcess:
        """
        Execute a command in an interactive shell session.

        Args:
            command: The command to execute in the interactive shell.
            cwd: The current working directory for the command.

        Returns:
            An SSHProcess object representing the interactive shell process running the command.
        """

        if not self._intsh:
            cmd = "sh -s"
            _LOG.debug("Starting interactive shell%s: %s", self.hostmsg, cmd)
            self._intsh = self._run_in_new_session(cmd, shell=False)

        proc = self._intsh
        cmd = self._format_cmd_for_pid(command, cwd=cwd)

        # Pick a new marker for the new interactive shell command.
        # pylint: disable=protected-access
        proc._reinit_marker()

        # Run the command.
        cmd = "sh -c " + shlex.quote(cmd) + "\n" + f'printf "%s, %d ---" "{proc._marker}" "$?"\n'
        proc.pobj.send(cmd.encode())

        # Re-initialize the interactive shell process object to match the new command.
        proc._reinit(command, cmd, True)

        return proc

    def _acquire_intsh_lock(self, command: str | None = None):
        """
        Acquire the interactive shell lock.

        Args:
            command: Optional command string for which the lock is being acquired. Used for logging
                     purposes.

        Returns:
            True if the lock was successfully acquired, False otherwise.
        """

        timeout = 5
        acquired = self._intsh_lock.acquire(timeout=timeout) # pylint: disable=consider-using-with
        if not acquired:
            msg = "Failed to acquire the interactive shell lock"
            if command:
                msg += f" for for the following command:\n{command}\n"
            else:
                msg += "."
            msg += f"Waited for {timeout} seconds."
            _LOG.warning(msg)

        return acquired

    def _run_async(self,
                  command: str | Path,
                  cwd: Path | None = None,
                  shell: bool = True,
                  intsh: bool = False) -> SSHProcess:
        """
        Run a command asynchronously. Implemen 'run_async()'.

        Args:
            command: The command to execute. Can be a string or a 'pathlib.Path' pointing to the
                     file to execute.
            cwd: The working directory for the process.
            shell: Whether to execute the command through a shell.
            intsh: Use an existing interactive shell if True, or a new shell if False. The former
                   requires less time to start a new process, as it does not require creating a new
                   shell. The default value is the value of 'shell'.

        Returns:
            A 'SSHProcess' object representing the executed remote asynchronous process.
        """

        if not shell and intsh:
            raise Error("The 'shell' argument must be 'True' when 'intsh' is 'True'")

        command = str(command)
        if not shell or not intsh:
            return self._run_in_new_session(command, cwd=cwd, shell=shell)

        try:
            acquired = self._acquire_intsh_lock(command=command)
            if not acquired or self._intsh_busy:
                intsh = False

            if intsh:
                self._intsh_busy = True
        finally:
            # Release the interactive shell lock if we acquired it.
            if acquired:
                self._intsh_lock.release()

        if not intsh:
            _LOG.warning("The interactive shell is busy, running the following command in a new "
                         "SSH session:\n%s", command)
            return self._run_in_new_session(command, cwd=cwd, shell=shell)

        try:
            return self._run_in_intsh(command, cwd=cwd)
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            _LOG.warning("Failed to run the following command in an interactive shell:  %s\n"
                         "The error was:\n%s", command, msg)

            # Close the internal shell and try to run in a new session.
            with contextlib.suppress(BaseException):
                acquired = self._acquire_intsh_lock(command=command)

            if acquired:
                self._intsh_busy = False
                self._intsh_lock.release()
                if self._intsh:
                    with contextlib.suppress(BaseException):
                        self._intsh.pobj.send("exit\n".encode())
                        self._intsh.close()
                    self._intsh = None
            else:
                _LOG.warning("Failed to acquire the interactive shell process lock")

            return self._run_in_new_session(command, cwd=cwd, shell=shell)

    def run_async(self,
                  cmd: str | Path,
                  cwd: Path | None = None,
                  shell: bool = True,
                  intsh: bool = False,
                  stdin: IO | None = None,
                  stdout: IO | None = None,
                  stderr: IO | None = None,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False) -> SSHProcess:
        """Refer to 'ProcessManagerBase.run_async()'."""

        # pylint: disable=unused-argument
        for arg, val in (("stdin", None), ("stdout", None), ("stderr", None), ("env", None),
                         ("newgrp", False)):
            if locals()[arg] != val:
                raise Error(f"'SSHProcessManager.run_async()' doesn't support the '{arg}' argument")

        cmd = str(cmd)

        if cwd:
            if not shell:
                raise Error(f"cannot set working directory to '{cwd}' - using shell is disallowed")
            cwd_msg = f"\nWorking directory: {cwd}"
        else:
            cwd_msg = ""

        _LOG.debug("Running the following command asynchronously%s (shell %s, intsh %s):\n%s%s",
                   self.hostmsg, str(shell), str(intsh), cmd, cwd_msg)

        return self._run_async(cmd, cwd=cwd, shell=shell, intsh=intsh)

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = None,
            capture_output: bool = True,
            mix_output: bool = False,
            join: bool = True,
            output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
            cwd: Path | None = None,
            shell: bool = True,
            intsh: bool | None = None,
            env: dict[str, str] | None = None,
            newgrp: bool = False) -> ProcWaitResultType:
        """Refer to 'ProcessManagerBase.run()'."""

        # pylint: disable=unused-argument
        for arg, val in (("env", None), ("newgrp", False)):
            if locals()[arg] != val:
                raise Error(f"'SSHProcessManager.run()' doesn't support the '{arg}' argument")

        msg = f"Running the following command{self.hostmsg} (shell {shell}, intsh {intsh}):\n{cmd}"
        if cwd:
            msg += f"\nWorking directory: {cwd}"
        _LOG.debug(msg)

        if intsh is None:
            intsh = shell

        # Execute the command on the remote host.
        with self._run_async(cmd, cwd=cwd, shell=shell, intsh=intsh) as proc:
            if mix_output:
                proc.pobj.set_combine_stderr(True)

            # Wait for the command to finish and handle the time-out situation.
            result = proc.wait(timeout=timeout, capture_output=capture_output,
                               output_fobjs=output_fobjs, join=join)

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
                   cwd: Path | None = None,
                   shell: bool = True,
                   intsh: bool | None = None,
                   env: dict[str, str] | None = None,
                   newgrp: bool = False) -> tuple[str | list[str], str | list[str]]:
        """Refer to 'ProcessManagerBase.run_verify()'."""

        # pylint: disable=unused-argument
        for arg, val in (("env", None), ("newgrp", False)):
            if locals()[arg] != val:
                raise Error(f"'SSHProcessManager.run_verify()' doesn't support the '{arg}' "
                            f"argument")

        result = self.run(cmd, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs, cwd=cwd,
                          shell=shell, intsh=intsh)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        msg = self.get_cmd_failure_msg(cmd, result.stdout, result.stderr, result.exitcode,
                                       timeout=timeout)
        raise Error(msg)

    def get_ssh_opts(self) -> str:
        """
        Generate SSH command-line options for establishing a connection.

        Returns:
            str: A string containing SSH options, including port, username, and optionally the
                 private key file path if specified.
        """

        ssh_opts = f"-o \"Port={self.port}\" -o \"User={self.username}\""
        if self.privkeypath:
            ssh_opts += f" -o \"IdentityFile={self.privkeypath}\""
        return ssh_opts

    def rsync(self,
              src: Path,
              dst: Path,
              opts: str = "-rlD",
              remotesrc: bool = False,
              remotedst: bool = False):
        """Refer to 'ProcessManagerBase.rsync()'."""

        opts = self._rsync_add_debug_opts(opts)

        if remotesrc and remotedst:
            cmd = f"rsync {opts} -- '{src}' '{dst}'"
            result = self.run(cmd)
            is_local = False
        else:
            from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

            if remotesrc:
                source = f"{self.hostname}:{src}"
            else:
                source = str(src)
            if remotedst:
                destination = f"{self.hostname}:{dst}"
            else:
                destination = str(dst)

            cmd = f"rsync {opts} -e 'ssh {self.get_ssh_opts()}' -- '{source}' '{destination}'"
            result = LocalProcessManager.LocalProcessManager().run(cmd)
            is_local = True

        if result.exitcode == 0:
            self._rsync_debug_log(result.stdout)
            return

        if is_local and result.exitcode == 12 and "command not found" in result.stderr:
            # This is special case. We ran 'rsync' on the local system in order to copy files
            # to/from the remote system. The 'rsync' is available on the local system, but it is not
            # installed on the remote system.
            errmsg = cast(str, result.stderr)
            raise self._command_not_found(cmd, errmsg=errmsg, toolname="rsync")

        msg = self.get_cmd_failure_msg(cmd, result.stdout, result.stderr, result.exitcode)
        raise Error(msg)

    def _scp(self, src: str, dst: str):
        """
        Copy a file or directory from 'src' to 'dst' using 'scp'.

        Args:
            src: The source file or directory path.
            dst: The destination file or directory path.
        """

        from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

        cmd = f"scp -r {self.get_ssh_opts()} -- {src} {dst}"

        try:
            LocalProcessManager.LocalProcessManager().run_verify(cmd)
        except Error as err:
            raise Error(f"Failed to copy files '{src}' to '{dst}':\n{err.indent(2)}") from err

    def get(self, src: Path, dst: Path):
        """
        Copy a file or directory from remote source path to local destination path.

        Args:
            src: The remote source path of the file or directory to copy.
            dst: The local destination path where the file or directory will be copied.
        """

        self._scp(f"{self.hostname}:\"{src}\"", f"\"{dst}\"")

    def put(self, src: Path, dst: Path):
        """
        Copy a file or directory from a local source path to remote destination path.

        Args:
            src: The loal source path of the file or directory to copy.
            dst: The remote destination path where the file or directory will be copied.
        """

        self._scp(f"\"{src}\"", f"{self.hostname}:\"{dst}\"")

    def _get_sftp(self) -> paramiko.SFTPClient:
        """
        Get an SFTP server object. If an SFTP session is already established, return the existing
        session. Otherwise, create a new SFTP session using the SSH connection.

        Returns:
            An 'SFTPClient' object representing the SFTP session.
        """

        if self._sftp:
            return self._sftp

        try:
            self._sftp = self.ssh.open_sftp()
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to establish SFTP session with {self.hostname}:\n{msg}") from err

        return self._sftp

    def open(self, path: Path, mode: str) -> IO:
        """Refer to 'ProcessManagerBase.open()'."""

        def _read_(fobj: IO, size: int | None = None) -> bytes | str:
            """
            This wrapper improves exceptions message and adds text mode support (SFTP file objects
            support only binary mode).
            """

            orig_fread = getattr(fobj, "_orig_fread_")
            # Note, paramiko SFTP file objects support only binary mode, and the "b" flag is ignored.
            data: bytes = orig_fread(size=size)

            orig_fmode = getattr(fobj, "_orig_fmode_")
            if "b" not in orig_fmode:
                try:
                    return data.decode("utf-8")
                except BaseException as err: # pylint: disable=broad-except
                    msg = Error(str(err)).indent(2)
                    errmsg = get_err_prefix(fobj, "read")
                    raise Error(f"{errmsg}: Failed to decode data after reading:\n{msg}") from None

            return data

        def _write_(fobj: IO, data: str | bytes):
            """
            Write data to a SFTP-backed file object with enhanced exception handling and text mode
            support.

            Args:
                fobj: The file object to write to.
                data: The data to write.
            """

            orig_fmode = getattr(fobj, "_orig_fmode_")

            if "b" not in orig_fmode:
                if not isinstance(data, str):
                    errmsg = get_err_prefix(fobj, "write")
                    raise Error(f"{errmsg}: The data to write must be a string, but not "
                                f"{type(data).__name__}") from None

                try:
                    data = data.encode("utf-8")
                except BaseException as err: # pylint: disable=broad-except
                    msg = Error(str(err)).indent(2)
                    errmsg = get_err_prefix(fobj, "write")
                    raise Error(f"{errmsg}:\nFailed to encode data before writing:\n{msg}") from None

            orig_fwrite = getattr(fobj, "_orig_fwrite_")
            return orig_fwrite(data)

        def get_err_prefix(fobj: IO, method: str) -> str:
            """
            Generate an error message prefix for a failed file operation.

            Args:
                fobj: The file object associated with the failed operation.
                method: The name of the method that failed.

            Returns:
                An error message prefix containing the method name and the original file path.
            """

            orig_fpath = getattr(fobj, "_orig_fpath_")
            return f"Method '{method}()' failed for file '{orig_fpath}'"

        path_str = str(path)
        sftp = self._get_sftp()

        errmsg = f"Failed to open file '{path_str}' with mode '{mode}' on {self.hostname} via SFTP: "
        try:
            fobj = sftp.file(path_str, mode)
        except PermissionError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
        except BaseException as err:
            msg = Error(err).indent(2)
            raise Error(f"{errmsg}\n{msg}") from err

        # Save the path and the mode in the file object.
        setattr(fobj, "_orig_fpath_", path_str)
        setattr(fobj, "_orig_fmode_", mode)

        # Replace read and write methods.
        setattr(fobj, "_orig_fread_", fobj.read)
        setattr(fobj, "read", types.MethodType(_read_, fobj))
        setattr(fobj, "_orig_fwrite_", fobj.write)
        setattr(fobj, "write", types.MethodType(_write_, fobj))

        # Make sure methods of 'fobj' always raise the 'Error' exception.
        wfobj = ClassHelpers.WrapExceptions(fobj, get_err_prefix=get_err_prefix)
        if "b" in mode:
            return cast(IO[bytes], wfobj)
        return cast(IO[str], wfobj)

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""

        cmd = "date +%s"
        stdout, _ = self.run_verify(cmd, shell=True)
        time = cast(str, stdout).strip()
        what = f"current time on {self.hostname} acquired via SSH using {cmd}"
        return Trivial.str_to_float(time, what=what)

    def mkdir(self, dirpath: Path, parents: bool = False, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkdir()'."""

        if self.shell_test(dirpath, "-e"):
            if exist_ok:
                return
            raise ErrorExists(f"Path '{dirpath}' already exists{self.hostmsg}")

        cmd = "mkdir"
        if parents:
            cmd += " -p"
        cmd += f" -- '{dirpath}'"
        self.run_verify(cmd)

    def mkfifo(self, path: Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkfifo()'."""

        if self.shell_test(path, "-e"):
            if exist_ok:
                return
            raise ErrorExists(f"Path '{path}' already exists{self.hostmsg}")

        cmd = f"mkfifo -- '{path}'"
        self.run_verify(cmd)

    def lsdir(self, path: Path, must_exist: bool = True) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase.lsdir()'."""

        path = Path(path)

        if not must_exist and not self.exists(path):
            return

        # A small python program to get the list of directories with some metadata.
        python_path = self.get_python_path()
        cmd = f"""{python_path} -c 'import os
path = "{path}"
for entry in os.listdir(path):
    stinfo = os.lstat(os.path.join(path, entry))
    print(entry, stinfo.st_mode, stinfo.st_ctime)'"""

        stdout, _ = self.run_verify(cmd, shell=True)

        info: dict[str, LsdirTypedDict] = {}

        for line in cast(str, stdout).splitlines():
            entry = Trivial.split_csv_line(line.strip(), sep=" ")
            if len(entry) != 3:
                raise Error(f"Failed to list directory '{path}': received the following "
                            f"unexpected line:\n{line}\nExpected line format: 'entry mode ctime'")

            info[entry[0]] = {"name": entry[0],
                              "path": path / entry[0],
                              "ctime": float(entry[2]),
                              "mode": int(entry[1])}

        yield from sorted(info.values(), key=itemgetter("ctime"), reverse=True)

    def exists(self, path: Path) -> bool:
        """Refer to 'ProcessManagerBase.exists()'."""

        return self.shell_test(path, "-e")

    def is_file(self, path: Path) -> bool:
        """Refer to 'ProcessManagerBase.is_file()'."""

        return self.shell_test(path, "-f")

    def is_dir(self, path: Path) -> bool:
        """Refer to 'ProcessManagerBase.is_dir()'."""

        return self.shell_test(path, "-d")

    def is_exe(self, path: Path) -> bool:
        """Refer to 'ProcessManagerBase.is_exe()'."""

        return self.shell_test(path, "-x")

    def is_socket(self, path: Path) -> bool:
        """Refer to 'ProcessManagerBase.is_socket()'."""

        return self.shell_test(path, "-S")

    def get_mtime(self, path: Path) -> float:
        """Refer to 'ProcessManagerBase.get_mtime()'."""

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'import os; print(os.stat(\"{path}\").st_mtime)'"
        try:
            stdout, _ = self.run_verify(cmd)
        except Error as err:
            if "FileNotFoundError" in str(err):
                raise ErrorNotFound(f"'{path}' does not exist{self.hostmsg}") from None
            raise

        mtime = cast(str, stdout).strip()
        if not Trivial.is_float(mtime):
            raise Error(f"Got erroneous modification time of '{path}'{self.hostmsg}:\n{mtime}")
        return float(mtime)

    def unlink(self, path: Path):
        """Refer to 'ProcessManagerBase.unlink()'."""

        self.run_verify(f"unlink -- '{path}'")

    def rmtree(self, path: Path):
        """Refer to 'ProcessManagerBase.rmtree()'."""

        self.run_verify(f"rm -rf -- '{path}'")

    def abspath(self, path: Path, must_exist: bool = True) -> Path:
        """Refer to 'ProcessManagerBase.abspath()'."""

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'from pathlib import Path; print(Path(\"{path}\").resolve())'"
        stdout, _ = self.run_verify(cmd)

        rpath = cast(str, stdout).strip()

        if must_exist and not self.exists(rpath):
            raise ErrorNotFound(f"path '{rpath}' does not exist")

        return Path(rpath)

    def mkdtemp(self, prefix: str | None  = None, basedir: Path | None = None) -> Path:
        """
        Create a temporary directory and return its path. The arguments are as follows.
          * prefix - specifies the temporary directory name prefix.
          * basedir - path to the base directory where the temporary directory should be created.
        """

        cmd = "mktemp -d -t '"
        if prefix:
            cmd += prefix
        cmd += "XXXXXX'"
        if basedir:
            cmd += f" -p '{basedir}'"

        path = self.run_verify(cmd)[0].strip()
        if not path:
            raise Error(f"cannot create a temporary directory{self.hostmsg}, the following command "
                        f"returned an empty string:\n{cmd}")

        _LOG.debug("created a temporary directory '%s'%s", path, self.hostmsg)
        return Path(path)

    def get_envar(self, envar):
        """Return the value of the environment variable 'envar'."""

        try:
            return Path(self.run_verify(f"echo ${envar}")[0].strip())
        except ErrorNotFound:
            # See commentaries in 'shell_test()', this is a similar case.
            return Path(self.run_verify(f"sh -c -l \"echo ${envar}\"")[0].strip())

    def which(self, program, must_find=True):
        """
        Find and return full path to a program 'program' by searching it in '$PATH'. The arguments
        are as follows.
          * program - name of the program to find the path to.
          * must_find - if 'True', raises the 'ErrorNotFound' exception if the program was not
                        found, otherwise returns 'None' without raising the exception.
        """

        def raise_or_return(): # pylint: disable=useless-return
            """This helper is called when the 'program' program was not found."""

            if must_find:
                raise ErrorNotFound(f"program '{program}' was not found in $PATH{self.hostmsg}")
            return None

        if self._which_cmd is None:
            which_cmds = ("which", "command -v")
        else:
            which_cmds = (self._which_cmd,)

        for which_cmd in which_cmds:
            cmd = f"{which_cmd} -- '{program}'"
            try:
                stdout, stderr, exitcode = self.run(cmd)
            except ErrorNotFound:
                if which_cmd != which_cmds[-1]:
                    # We have more commands to try.
                    continue
                raise

            self._which_cmd = which_cmd
            break

        if not exitcode:
            # Which could return several paths. They may contain aliases.
            for line in stdout.strip().splitlines():
                line = line.strip()
                if not line.startswith("alias"):
                    return Path(line)
            return raise_or_return()

        # The 'which' tool exits with status 1 when the program is not found. Any other error code
        # is an real failure.
        if exitcode != 1:
            raise Error(self.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

        return raise_or_return()

    def _cfg_lookup(self, optname, hostname, username, cfgfiles=None):
        """
        Search for option 'optname' in SSH configuration files. Only consider host 'hostname'
        options.
        """

        old_username = None
        try:
            old_username = os.getenv("USER")
            os.environ["USER"] = username

            if not cfgfiles:
                cfgfiles = []
                for cfgfile in ["/etc/ssh/ssh_config", os.path.expanduser('~/.ssh/config')]:
                    if os.path.exists(cfgfile):
                        cfgfiles.append(cfgfile)

            # Sort configuration file paths to make the order somewhat predictable, as opposed to
            # random.
            for cfgfile in sorted(cfgfiles):
                config = paramiko.SSHConfig().from_path(cfgfile)

                cfg = config.lookup(hostname)
                if optname in cfg:
                    return cfg[optname]

                if "include" in cfg:
                    cfgfiles = glob.glob(cfg['include'])
                    return self._cfg_lookup(optname, hostname, username, cfgfiles=cfgfiles)
        finally:
            os.environ["USER"] = old_username

        return None

    def _lookup_privkey(self, hostname, username, cfgfiles=None):
        """Lookup for private SSH authentication keys for host 'hostname'."""

        privkeypath = self._cfg_lookup("identityfile", hostname, username, cfgfiles=cfgfiles)
        if isinstance(privkeypath, list):
            privkeypath = privkeypath[0]

        if privkeypath:
            privkeypath = Path(privkeypath)
        return privkeypath
