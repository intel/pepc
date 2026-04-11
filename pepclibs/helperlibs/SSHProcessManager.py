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

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import glob
import time
import stat
import types
import shlex
import random
import typing
import logging
import threading
import contextlib
from pathlib import Path
from collections.abc import Callable
try:
    import paramiko
except (ModuleNotFoundError, ImportError):
    from pepclibs.helperlibs import DummyParamiko as paramiko  # type: ignore[no-redef]
from pepclibs.helperlibs import DummyParamiko
from pepclibs.helperlibs import Logging, _ProcessManagerBase, ClassHelpers, Trivial
from pepclibs.helperlibs._ProcessManagerTypes import ProcWaitResultType
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorTimeOut, ErrorConnect
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

if typing.TYPE_CHECKING:
    from typing import Generator, IO, Iterable, Sequence, cast
    from pepclibs.helperlibs._ProcessManagerTypes import LsdirTypedDict, LsdirSortbyType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Paramiko is a bit too noisy, lower its log level.
logging.getLogger("paramiko").setLevel(logging.WARNING)

_FAKE_EXIT_CODE = 69696969

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
              run an asynchronous command ('run_async()') in the interactive shell and then run
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
                 streams: tuple[paramiko.ChannelFile,
                                Callable[[int], bytes],
                                Callable[[int], bytes]]):
        """Refer to 'ProcessBase.__init__()'."""

        super().__init__(pman, pobj, cmd, real_cmd, streams)

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
        # The incomplete last line of stdout/stderr: text after the last newline. Never contains a
        # newline character. The marker always occupies a single line, so it can only appear here.
        # Prior complete lines were already checked and flushed.
        self._ll = ["", ""]

        self._read_pid()

    def _reinit_marker(self):
        """
        Reinitialize the marker that indicates the completion of a command in the interactive shell.
        """

        # Generate a random string which will be used as the marker, which indicates that the
        # interactive shell command has finished.
        randbits = random.getrandbits(256)
        self._marker = f"--- {randbits:064x}"
        self._marker_regex = re.compile(rf"^{self._marker}, \d+ ---$")

    def _reinit(self, cmd: str, real_cmd: str):
        """Refer to 'ProcessBase._reinit()'."""

        super()._reinit(cmd, real_cmd)

        self._ll = ["", ""]
        self._lines_cnt = [0, 0]

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
        except BaseException as err:
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

        return not self._ll[0] and not self._ll[1] and super()._process_is_done()

    def _watch_for_marker(self, data: str, streamid: int) -> tuple[str, int | None]:
        """
        Check for the marker in the stdout or stderr data of the interactive shell to determine if
        process has exited.

        Args:
            data: A piece of stdout or stderr data from the process.
            streamid: The stream ID (0 for stdout, 1 for stderr) from which the data was received.

        Returns:
            A tuple ('cdata', 'exitcode').
                - 'cdata': The captured output from the stream, with the marker stripped out. If the
                           marker was not found, 'cdata' contains everything up to and including the
                           last newline. The partial last line (text after the last newline) is
                           saved in 'self._ll[streamid]' and prepended on the next call.
                - 'exitcode': The exit code extracted from the marker, or 'None' if the marker was
                              not found.
        """

        exitcode: int | None = None
        cdata: str = ""
        ll = self._ll[streamid]

        self._dbg("SSHProcess._watch_for_marker(): Starting with: streamid: %d\nll: %s\ndata:\n%s",
                  streamid, repr(ll), repr(data))

        # 'll' on entry is the incomplete last line from prior calls. Append the newly received
        # 'data' so the marker is detected even if it arrives split across two chunks (e.g. chunk
        # 1 ends with '--- <hash>' and chunk 2 starts with ', 0 ---').
        ll += data

        # The marker always ends with ' ---'. Use that as a cheap pre-check before running the
        # regex.
        if ll.endswith(" ---"):
            # 'self._marker' is the hash prefix only (e.g. '--- <hash>'). The full marker also
            # includes the exit code and the trailing ' ---' (e.g. '--- <hash>, 0 ---'). Find the
            # last occurrence of the prefix in 'll'. 'idx' is the character position within 'll'
            # where the marker starts (i.e., 'll[idx:]' is the marker, 'll[:idx]' is any output
            # on the same line that preceded it).
            idx = ll.rfind(self._marker)
            if idx >= 0 and re.match(self._marker_regex, ll[idx:]):
                # Extract the exit code. The marker format is: --- hash, <exitcode> ---
                status = ll[idx:].rsplit(", ", 1)[1].rstrip(" ---")
                if not Trivial.is_int(status):
                    raise Error(f"The process was running{self.hostmsg} under the interactive "
                                f"shell and finished with a correct marker, but an unexpected exit "
                                f"code '{status}'.\nThe command was: {self.cmd}")
                cdata = ll[:idx]
                exitcode = int(status)
                ll = ""

        if exitcode is None:
            # No marker yet. Extract everything up to and including the last newline as captured
            # output, and restore the invariant: keep only the text after the last '\n' in 'll',
            # so 'self._ll[streamid]' remains newline-free on the next call.
            idx = ll.rfind("\n")
            if idx >= 0:
                cdata = ll[:idx + 1]
                ll = ll[idx + 1:]

        self._ll[streamid] = ll

        self._dbg("SSHProcess._watch_for_marker(): Ending with: streamid %d, exitcode %s\n"
                  "ll: %s\ncdata:\n%s", streamid, str(exitcode), repr(ll), repr(cdata))

        return (cdata, exitcode)

    def poll(self) -> int | None:
        """Refer to 'ProcessBase.poll()'."""

        if self.exitcode is not None:
            return self.exitcode

        chan = self.pobj
        if chan.exit_status_ready():
            return chan.recv_exit_status()
        return None

    def _wait_intsh(self,
                    timeout: int | float = 0,
                    capture_output: bool = True,
                    output_fobjs: Sequence[IO[str] | None] = (None, None),
                    lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Implement '_wait()' for the interactive shell case. Refer to 'ProcessBase._wait()'."""

        start_time = time.time()

        self._dbg("SSHProcess._wait_intsh(): Starting with(): self._ll: %s", str(self._ll))
        self._dbg_log_buffered_output(pfx="SSHProcess._wait_intsh(): Starting with")

        exitcode: list[int | None] = [None, None]

        # If both markers were already consumed by a prior 'wait()' call (e.g. '_read_pid()' called
        # 'wait()' with 'lines=(1,-1)' and drained the entire queue including the markers), the
        # process is already done. Return the buffered output immediately. Entering the loop would
        # block indefinitely on '_get_next_queue_item()'.
        if self.exitcode is not None:
            self._dbg("SSHProcess._wait_intsh(): Process already exited with status %d, "
                      "returning buffered output", self.exitcode)
            result = self._get_lines_to_return(lines)
            if self._process_is_done():
                # pylint: disable=protected-access
                self.pman._release_intsh_lock(self.cmd)
            return result

        # The interactive shell ('sh -s') is started once and reused across multiple commands. Each
        # command is sent to the shell's stdin. The shell runs one command at a time.
        #
        # The challenge is detecting when a command finishes, since the shell itself keeps running.
        # The solution: each command is wrapped to print a unique marker to both stdout and stderr
        # upon completion.
        #
        # Both markers must be seen before concluding the command has finished. Seeing only the
        # stdout marker is not enough: stderr data may still be in flight. Stopping early would
        # leave the stderr marker in the stream, where the next command - running in the same
        # interactive shell on the same streams - would see it as its own output.
        #
        # Example: command "printf 'out1\nout2\n'; printf 'err1\nerr2\n' >&2"
        # Stream data in arrival order (interleaving is arbitrary):
        #   stdout: 'out1\nout2\n'
        #   stderr: 'err1\nerr2\n'
        #   stdout: '--- <hash>, 0 ---'          <- stdout marker carrying the real exit code
        #   stderr: '--- <hash>, <FAKE> ---'     <- stderr marker carrying _FAKE_EXIT_CODE
        #
        # Example iteration trace (stderr chunk arrived first):
        #   Iter 1: (1, 'err1\nerr2\n')           -> 'cdata'='err1\nerr2\n', 'exitcode[1]'=None
        #   Iter 2: (0, 'out1\nout2\n')           -> 'cdata'='out1\nout2\n', 'exitcode[0]'=None
        #   Iter 3: (0, '--- <hash>, 0 ---')      -> 'cdata'='',             'exitcode[0]'=0
        #   Iter 4: (1, '--- <hash>, <FAKE> ---') -> 'cdata'='',             'exitcode[1]'=<FAKE>
        #
        # The loop below drains the queue, watching for both markers before concluding.
        while True:
            assert self._queue is not None

            self._dbg("SSHProcess._wait_intsh(): New iteration, exitcode[0] %s, exitcode[1], %s",
                      str(exitcode[0]), str(exitcode[1]))

            # The caller might have requested only a limited number of output lines (e.g.
            # 'lines=(1,-1)', which means one stdout line and any number of stderr lines). Check if
            # enough lines were captured.
            if _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
                # Enough lines were captured. Return early only if no markers have been seen yet.
                # Once the first marker is observed, the process has already exited and the second
                # marker is in flight. Stopping here would leave the second marker in the stream,
                # where the next command - running in the same interactive shell on the same streams
                # - would see it as its own output.
                if exitcode[0] is None and exitcode[1] is None:
                    self._dbg("SSHProcess._wait_intsh(): Enough lines were captured, stop looping")
                    break

                self._dbg("SSHProcess._wait_intsh(): Enough lines were captured, but waiting "
                          "for the second marker")

            if exitcode[0] is not None and exitcode[1] is not None:
                # Both markers seen. The real exit code is in 'exitcode[0]' (stdout marker).
                # 'exitcode[1]' is always '_FAKE_EXIT_CODE' and is discarded.
                self.exitcode = exitcode[0]
                if self._queue.empty():
                    self._dbg("SSHProcess._wait_intsh(): Process exited with status %d",
                              self.exitcode)
                    break

                # The queue is not empty, which is an error/bug condition, because the process has
                # received both markers. Keep draining the queue, the code below will handle it.

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                # Timeout: nothing arrived in the queue within the timeout period. 'data' is 'None'
                # in this case.
                self._dbg("SSHProcess._wait_intsh(): Nothing in the queue for %d seconds", timeout)
            elif data is None:
                # The stream was closed, meaning the interactive shell itself exited (e.g., crashed
                # or was killed) before printing the markers.
                raise Error(f"The interactive shell process{self.hostmsg} closed stream {streamid} "
                            f"while running the following command:\n{self.cmd}")
            else:
                if exitcode[streamid] is not None:
                    raise Error(f"The marker for an interactive shell process{self.hostmsg} "
                                f"stream {streamid} was already observed, but new data were "
                                f"received, the data:\n{data}")

                # Normal situation: got some output from a stream. Check it for the marker.
                # '_watch_for_marker()' returns ('cdata', 'exitcode'):
                #   - No marker:            'cdata' = captured output,  'exitcode' = None
                #   - Marker only:          'cdata' = '',               'exitcode' = <int>
                #   - Output before marker: 'cdata' = captured output,  'exitcode' = <int>
                data, exitcode[streamid] = self._watch_for_marker(data, streamid)

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
            self.pman._release_intsh_lock(self.cmd)

        return result

    def _wait_nointsh(self,
                      timeout: int | float = 0,
                      capture_output: bool = True,
                      output_fobjs: Sequence[IO[str] | None] = (None, None),
                      lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Implement '_wait()' for the new SSH session case. Refer to 'ProcessBase._wait()'."""

        start_time = time.time()

        self._dbg_log_buffered_output(pfx="SSHProcess._wait_nointsh(): Starting with")

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("SSHProcess._wait_nointsh(): Process exited with status %d",
                          self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            self._dbg("SSHProcess._wait_nointsh(): _get_next_queue_item() returned: stream %d, "
                      "data:\n%s", streamid, repr(data))
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
              output_fobjs: Sequence[IO[str] | None] = (None, None),
              lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Refer to 'ProcessBase._wait()'."""

        # pylint: disable=protected-access
        if self.pman._intsh and self.pobj == self.pman._intsh.pobj:
            method = self._wait_intsh
        else:
            method = self._wait_nointsh

        return method(timeout=timeout, capture_output=capture_output, output_fobjs=output_fobjs,
                      lines=lines)

    def _read_pid(self):
        """
        Read the process ID (PID) of the executed command and store it in 'self.pid'.

        Notes:
            - The reason this method exists is that paramiko does not have a mechanism to get PID.
              So this is a workaround.
        """

        self._dbg("SSHProcess._read_pid(): Reading PID for the following command: %s", self.cmd)

        stdout, stderr, _ = self.wait(timeout=32, lines=(1, -1), join=False)

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
                 ipaddr: str = "",
                 port: int | None = None,
                 username: str = "",
                 password: str | None = None,
                 privkeypath: str | Path = "",
                 timeout: int | float | None = None):
        """
        Initialize a class instance and establish SSH connection to a remote host.

        Args:
            hostname: The name of the host to connect to.
            ipaddr: IP address of the host. If provided, it is used instead of 'hostname' for
                    establishing the TCP connection. 'hostname' is still used for looking up SSH
                    config file options ('User', 'IdentityFile', etc.) and for logging.
            port: The port number to connect to. Defaults to 22.
            username: Username for authentication. By default, try to search for the user name in
                      SSH configuration files, in case it is defined for 'hostname' in a "Host"
                      section. If not found, use the current user name from the 'USER' environment
                      variable. If 'USER' is not set, use the current user name from the system.
            password: Password for the specified username. Defaults to None (no password).
            privkeypath: Optional path to the private key for authentication. If no private key path
                         is provided, the method attempts to locate all configured paths from SSH
                         configuration files.
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
            username = self._get_ssh_cfg_host_opt(hostname, "User")
            if not username:
                username = os.getenv("USER") or Trivial.get_username()
        self.username = username

        self.password = password
        self.privkeypaths: list[str] = [str(privkeypath)] if privkeypath else []

        # The command to use for figuring out full paths in the 'which()' method.
        self._which_cmd: str | None = None

        self._sftp: paramiko.SFTPClient | DummyParamiko.SFTPClient | None = None

        # The interactive shell session.
        self._intsh: SSHProcess | None = None
        # True while a command is running in the interactive shell, False when the shell is idle.
        # Protected by '_intsh_lock': callers must hold the lock when reading or writing this flag.
        # The lock is released immediately after the flag is updated, so it is never held during
        # the actual command execution.
        self._intsh_busy = False
        # A short-lived mutex protecting '_intsh_busy'. It is held only for the brief moment of
        # reading and writing the flag, never for the duration of a running command.
        self._intsh_lock = threading.Lock()

        if ipaddr:
            connhost = ipaddr
            self._vhostname = f"{hostname} ({ipaddr})"
        else:
            name = self._get_ssh_cfg_host_opt(hostname, "HostName")
            if name:
                connhost = name
                self._vhostname = f"{hostname} ({connhost})"
            else:
                self._vhostname = connhost = hostname

        if not self.privkeypaths:
            try:
                self.privkeypaths = self._lookup_privkeys(hostname, self.username)
            except Exception as err: # pylint: disable=broad-except
                msg = Error(str(err)).indent(2)
                _LOG.debug(f"Private key lookup failed:\n{msg}")

        for path in self.privkeypaths:
            # Private SSH key sanity checks.
            try:
                mode = os.stat(path).st_mode
            except OSError as err:
                msg = Error(str(err)).indent(2)
                raise Error(f"'stat()' failed for private SSH key at '{path}':\n"
                            f"{msg}") from err

            if not stat.S_ISREG(mode):
                raise Error(f"Private SSH key at '{path}' is not a regular file")

            if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                raise Error(f"Private SSH key at '{path}' permissions are too wide: "
                            f"Make sure 'others' cannot read/write/execute it")
        look_for_keys = not self.privkeypaths

        _LOG.debug("Establishing SSH connection to %s, port %d, username '%s', timeout '%s', "
                   "password '%s', priv. keys '%s', look_for_keys '%s'",
                   self._vhostname, port, self.username, self.connection_timeout, self.password,
                   self.privkeypaths, look_for_keys)

        try:
            self.ssh = paramiko.SSHClient()
            auto_add_policy = paramiko.AutoAddPolicy()
            if not isinstance(auto_add_policy, DummyParamiko.AutoAddPolicy):
                self.ssh.set_missing_host_key_policy(auto_add_policy)

            # Paramiko accepts a list of private key paths via 'key_filename' argument. But mypy
            # does not know about this, here is a workaround.
            if self.privkeypaths:
                if typing.TYPE_CHECKING:
                    key_filename = cast(str, self.privkeypaths)
                else:
                    key_filename = self.privkeypaths
            else:
                key_filename = None
            self.ssh.connect(username=self.username, hostname=connhost, port=port,
                             key_filename=key_filename, timeout=self.connection_timeout,
                             password=self.password, allow_agent=True, look_for_keys=look_for_keys)
        except paramiko.AuthenticationException as err:
            msg = Error(str(err)).indent(2)
            raise ErrorConnect(f"SSH authentication failed when connecting to {self._vhostname} as "
                               f"'{self.username}':\n{msg}") from err
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise ErrorConnect(f"Cannot establish TCP connection to {self._vhostname} with "
                               f"{timeout} secs time-out:\n{msg}") from err

    def close(self):
        """Close the SSH connection."""

        _LOG.debug("Closing SSH connection to %s (port %d, username '%s', priv. keys '%s'",
                   self._vhostname, self.port, self.username, self.privkeypaths)

        if self._intsh:
            with contextlib.suppress(BaseException):
                self._intsh.pobj.send("exit\n".encode())

        ClassHelpers.close(self, close_attrs=("_sftp", "_intsh", "ssh",))

        super().close()

    def _get_ssh_cfg_host_opts(self,
                               hostalias: str,
                               optname: str,
                               cfgfiles: Sequence[str] = ()) -> Generator[str, None, None]:
        """
        Yield all values of a 'Host' block option from SSH config files.

        SSH config files (e.g. '~/.ssh/config') contain 'Host' blocks that map host aliases to
        connection parameters. Read those blocks and yield values of the requested option (e.g.
        'HostName', 'User', 'IdentityFile') for the given hostname alias. For multi-value options
        (e.g. 'IdentityFile'), yield each configured value individually.

        Args:
            hostalias: The alias to look up in SSH config 'Host' blocks (e.g. 'Host <hostalias>').
            optname: The SSH config option name to look up (e.g. 'User', 'HostName',
                     'IdentityFile'). Case-insensitive.
            cfgfiles: The SSH configuration file paths to search in. Use standard paths by default.

        Yields:
            Option values found across all SSH configuration files.

        Examples:
            Given the following SSH config snippet:

                Host myserver
                    User alice
                    IdentityFile ~/.ssh/alice_rsa
                    IdentityFile ~/.ssh/alice_ed25519

            list(_get_ssh_cfg_host_opts("myserver", "IdentityFile")) -> ["~/.ssh/alice_rsa",
                                                                          "~/.ssh/alice_ed25519"]
            list(_get_ssh_cfg_host_opts("myserver", "User"))         -> ["alice"]
            list(_get_ssh_cfg_host_opts("myserver", "Port"))         -> []
        """

        optname = optname.lower()

        _LOG.debug("Looking up SSH config option '%s' for host '%s' in files: %s",
                   optname, hostalias, cfgfiles)

        if not cfgfiles:
            cfgfiles = []
            for cfgfile in ["/etc/ssh/ssh_config", os.path.expanduser("~/.ssh/config")]:
                if os.path.exists(cfgfile):
                    cfgfiles.append(cfgfile)

        for cfgfile in cfgfiles:
            try:
                config = paramiko.SSHConfig().from_path(cfgfile)
            except paramiko.ConfigParseError as err:
                errmsg = Error(str(err)).indent(2)
                _LOG.debug("Cannot parse SSH config file '%s':\n%s", cfgfile, errmsg)
                continue

            # 'lookup()' returns a dict of all options that apply to 'hostalias', e.g.:
            # {'hostname': '10.54.97.143', 'user': 'labuser', 'serveraliveinterval': '60'}
            # Option names are lowercased. Values are strings or lists (for multi-value options).
            cfg = config.lookup(hostalias)
            if optname in cfg:
                vals = cfg[optname]
                vals_list: list[str]
                if isinstance(vals, list):
                    vals_list = vals
                else:
                    vals_list = [vals]
                for val in vals_list:
                    # Paramiko's 'lookup()' always injects 'hostname' into the result dict, using
                    # the input alias as the default value. This happens even when no 'Host' block
                    # in the file matched the alias at all. As a result, '"hostname" in cfg' is
                    # always 'True', making it impossible to tell from the key alone whether an
                    # explicit 'HostName' directive was found. A real 'HostName' directive would
                    # produce a value different from the alias (e.g. '10.54.97.143'), while the
                    # paramiko default produces the alias itself (e.g. 'wcl'). Skip the latter and
                    # continue to the next file in 'cfgfiles', which may have the real directive.
                    if optname != "hostname" or val != hostalias:
                        yield val

            if "include" in cfg:
                # The include directive may contain wildcards. Expand them. Sort the resulting
                # list to have a deterministic order.
                include_cfgfiles = sorted(glob.glob(cfg["include"]))
                if include_cfgfiles:
                    yield from self._get_ssh_cfg_host_opts(hostalias, optname,
                                                           cfgfiles=include_cfgfiles)

    def _get_ssh_cfg_host_opt(self,
                              hostalias: str,
                              optname: str,
                              cfgfiles: Sequence[str] = ()) -> str:
        """
        Return the first value yielded by '_get_ssh_cfg_host_opts()', or an empty string.
        """

        for val in self._get_ssh_cfg_host_opts(hostalias, optname, cfgfiles=cfgfiles):
            return val
        return ""

    def _lookup_privkeys(self,
                         hostalias: str,
                         username: str,
                         cfgfiles: Sequence[str] = ()) -> list[str]:
        """
        Look up all private SSH keys for a given host alias and user in SSH config files.

        Args:
            hostalias: The alias to look up in SSH config 'Host' blocks (e.g. 'Host <hostalias>').
            username: The username for '%u' token expansion in 'IdentityFile' paths.
            cfgfiles: The SSH configuration files to search in. Use standard files by default.

        Returns:
            A list of private key paths. Returns an empty list if no keys are found.

        Notes:
            SSH config files support the '%u' token in 'IdentityFile' paths (e.g.
            'IdentityFile ~/.ssh/%u_rsa' expands to '~/.ssh/bob_rsa' for user 'bob'). Paramiko
            resolves '%u' by reading the 'USER' environment variable, so temporarily set 'USER' to
            'username' during the lookup to ensure correct path expansion.
        """

        saved_user = os.getenv("USER")
        try:
            os.environ["USER"] = username or saved_user or Trivial.get_username()
            privkeypaths = list(self._get_ssh_cfg_host_opts(hostalias, "IdentityFile",
                                                            cfgfiles=cfgfiles))
        finally:
            if saved_user:
                os.environ["USER"] = saved_user
            else:
                os.environ.pop("USER", None)

        return privkeypaths

    @staticmethod
    def _format_cmd(cmd: str,
                    cwd: str | Path | None = None,
                    env: dict[str, str] | None = None) -> str:
        """
        Modify the command so that it prints own PID.

        Problem: paramiko does not provide a way of getting PID of the executed command.
        Solution: start shell first, print its PID, then exec the command in the shell. The command
                  will inherit the PID of the shell.

        Args:
            cmd: The command to be executed.
            cwd: The working directory to switch to before executing the command.
            env: Environment variables to set before executing the command.

        Returns:
            Command that prints the PID before executing the original command.
        """

        prefix = ""
        if env:
            for key, value in env.items():
                prefix += f'export {key}="{value}"; '
        prefix += r'printf "%s\n" "$$";'
        if cwd:
            prefix += f""" cd "{cwd}" &&"""
        return prefix + " exec sh -c " + shlex.quote(cmd)

    def _run_in_new_session(self,
                            command: str,
                            cwd: str | Path | None = None,
                            env: dict[str, str] | None = None,
                            mix_output: bool = False) -> SSHProcess:
        """
        Run a command in a new SSH session.

        Args:
            command: The command to execute on the remote host.
            cwd: The working directory to set for the command.
            env: Environment variables for the process.
            mix_output: If True, combine standard output and error streams into stdout.

        Returns:
            An 'SSHProcess' object representing the process running the command.
        """

        cmd = self._format_cmd(command, cwd=cwd, env=env)

        try:
            transport = self.ssh.get_transport()
            if not transport:
                raise Error(f"SSH transport is not available{self.hostmsg}")
            chan = transport.open_session(timeout=self.connection_timeout)
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot create a new SSH session for running the following "
                        f"command{self.hostmsg}:\n  {cmd}\nThe error is:\n{msg}") from err

        try:
            chan.exec_command(cmd)
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot execute the following command in a new SSH session"
                        f"{self.hostmsg}:\n  {cmd}\nThe error is:\n{msg}") from err

        try:
            stdin = chan.makefile("wb")
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create the stdin file-like object for the following "
                        f"command{self.hostmsg}:\n  {cmd}\nThe Error is:\n{msg}") from err

        if mix_output:
            try:
                chan.set_combine_stderr(True)
            except BaseException as err:
                msg = Error(str(err)).indent(2)
                raise Error(f"Failed combind stdout and stdert for the following "
                            f"command{self.hostmsg}:\n  {cmd}\nThe Error is:\n{msg}") from err

        streams = (stdin, chan.recv, chan.recv_stderr)
        return SSHProcess(self, chan, command, cmd, streams)

    def _run_in_intsh(self,
                      command: str,
                      cwd: str | Path | None = None,
                      env: dict[str, str] | None = None,
                      mix_output: bool = False) -> SSHProcess:
        """
        Execute a command in an interactive shell session.

        Args:
            command: The command to execute in the interactive shell.
            cwd: The current working directory for the command.
            env: Environment variables to set for the command.
            mix_output: If True, combine standard output and error streams into stdout.

        Returns:
            An SSHProcess object representing the interactive shell process running the command.
        """

        if not self._intsh:
            cmd = "sh -s"
            _LOG.debug("Starting interactive shell%s: %s", self.hostmsg, cmd)
            self._intsh = self._run_in_new_session(cmd)

        proc = self._intsh
        cmd = self._format_cmd(command, cwd=cwd, env=env)

        if mix_output:
            cmd += " 2>&1"

        cmd = "sh -c " + shlex.quote(cmd)

        # Pick a new marker for the new interactive shell command.
        # pylint: disable=protected-access
        proc._reinit_marker()

        # Print the marker as soon as the command is finished.
        cmd += f'; printf "%s, %d ---" "{proc._marker}" "$?"'
        cmd += f'; printf "%s, {_FAKE_EXIT_CODE} ---" "{proc._marker}" 1>&2\n'

        # Run the command.
        proc.pobj.send(cmd.encode())

        # Re-initialize the interactive shell process object to match the new command.
        proc._reinit(command, cmd)

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

        timeout = 10
        acquired = self._intsh_lock.acquire(timeout=timeout) # pylint: disable=consider-using-with
        if not acquired:
            msg = "Failed to acquire the interactive shell lock"
            if command:
                msg += f" for the following command:\n{command}\n"
            else:
                msg += "."
            msg += f"Waited for {timeout} seconds."
            _LOG.warning(msg)

        return acquired

    def _release_intsh_lock(self, command: str | None = None):
        """
        Mark the interactive shell as free.

        Args:
            command: Optional command string. Used for logging purposes if the lock cannot be
                     acquired.
        """

        acquired = self._acquire_intsh_lock(command)
        if not acquired:
            _LOG.warning("Failed to mark the interactive shell process as free")
        else:
            self._intsh_busy = False
            self._intsh_lock.release()

    def _do_run_async(self,
                      command: str | Path,
                      cwd: str | Path | None = None,
                      intsh: bool = False,
                      env: dict[str, str] | None = None,
                      mix_output: bool = False) -> SSHProcess:
        """
        Run a command asynchronously. Implement 'run_async()' without the 'su' argument.

        Args:
            command: The command to execute. Can be a string or a 'pathlib.Path' pointing to the
                     file to execute.
            cwd: The working directory for the process.
            intsh: Use an existing interactive shell if True, or a new shell if False. The former
                   requires less time to start a new process, as it does not require creating a new
                   shell.
            env: Environment variables for the process.
            mix_output: If True, combine standard output and error streams into stdout.

        Returns:
            A 'SSHProcess' object representing the executed remote asynchronous process.
        """

        command = str(command)

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if cwd:
                cwd_msg = f"\nWorking directory: {cwd}"
            else:
                cwd_msg = ""
            _LOG.debug("Running the following command asynchronously%s (intsh %s):\n%s%s",
                       self.hostmsg, str(intsh), command, cwd_msg)

        if not intsh:
            return self._run_in_new_session(command, cwd=cwd, env=env, mix_output=mix_output)

        acquired = False
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
            return self._run_in_new_session(command, cwd=cwd, env=env, mix_output=mix_output)

        try:
            return self._run_in_intsh(command, cwd=cwd, env=env, mix_output=mix_output)
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            _LOG.warning("Failed to run the following command in an interactive shell:  %s\n"
                         "The error was:\n%s", command, msg)

            # Close the interactive shell and try to run in a new session.
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

            return self._run_in_new_session(command, cwd=cwd, env=env, mix_output=mix_output)

    def _check_is_root(self) -> bool:
        """Refer to 'ProcessManagerBase._check_is_root()'."""

        timeout = 32
        with self._do_run_async("id -u", intsh=True) as proc:
            result = proc.wait(timeout=timeout, capture_output=True, join=True)

        if result.exitcode is None:
            msg = self.get_cmd_failure_msg("id -u", result.stdout, result.stderr,
                                           result.exitcode, timeout=timeout)
            raise ErrorTimeOut(f"Failed to check if the user is root{self.hostmsg}:\n{msg}")

        if result.exitcode != 0:
            msg = self.get_cmd_failure_msg("id -u", result.stdout, result.stderr,
                                           result.exitcode, timeout=timeout)
            raise Error(f"Failed to check if the user is root{self.hostmsg}:\n{msg}")

        if typing.TYPE_CHECKING:
            stdout = cast(str, result.stdout)
        else:
            stdout = result.stdout
        return stdout.strip() == "0"

    def _run_async(self,
                   command: str | Path,
                   cwd: str | Path | None = None,
                   intsh: bool = False,
                   env: dict[str, str] | None = None,
                   mix_output: bool = False,
                   su: bool = False) -> SSHProcess:
        """
        Run a command asynchronously. Implement 'run_async()'.

        Args:
            command: The command to execute. Can be a string or a 'pathlib.Path' pointing to the
                     file to execute.
            cwd: The working directory for the process.
            intsh: Use an existing interactive shell if True, or a new shell if False. The former
                   requires less time to start a new process, as it does not require creating a new
                   shell.
            env: Environment variables for the process.
            mix_output: If True, combine standard output and error streams into stdout.
            su: If True, execute the command with superuser privileges.

        Returns:
            A 'SSHProcess' object representing the executed remote asynchronous process.
        """

        if not su or self.is_superuser():
            return self._do_run_async(command=command, cwd=cwd, intsh=intsh, env=env,
                                      mix_output=mix_output)

        if self.has_passwdless_sudo():
            sudo_cmd = self._format_sudo_cmd(command, cwd=cwd, env=env)
            return self._do_run_async(command=sudo_cmd, intsh=intsh, mix_output=mix_output)

        raise ErrorPermissionDenied(f"Cannot run a command with superuser privileges without root "
                                    f"access or passwordless sudo{self.hostmsg}. The command is:\n"
                                    f"{command}\n")

    def run_async(self,
                  cmd: str | Path,
                  cwd: str | Path | None = None,
                  intsh: bool = False,
                  stdin: IO | None = None,
                  stdout: IO | None = None,
                  stderr: IO | None = None,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False,
                  su: bool = False) -> SSHProcess:
        """Refer to 'ProcessManagerBase.run_async()'."""

        # The 'newgrp' argument is ignored, because it makes no sense in a remote host case.
        # The 'stdin', 'stdout', and 'stderr' arguments are not supported.

        for arg, val in (("stdin", None), ("stdout", None), ("stderr", None)):
            if locals()[arg] != val:
                raise Error(f"'SSHProcessManager.run_async()' doesn't support the '{arg}' argument")

        cmd = str(cmd)

        return self._run_async(cmd, cwd=cwd, intsh=intsh, env=env, su=su)

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = None,
            capture_output: bool = True,
            mix_output: bool = False,
            join: bool = True,
            output_fobjs: Sequence[IO[str] | None] = (None, None),
            cwd: str | Path | None = None,
            intsh: bool = True,
            env: dict[str, str] | None = None,
            newgrp: bool = False,
            su: bool = False) -> ProcWaitResultType:
        """Refer to 'ProcessManagerBase.run()'."""

        # Execute the command on the remote host.
        with self._run_async(cmd, cwd=cwd, intsh=intsh, env=env, mix_output=mix_output,
                             su=su) as proc:
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
                   output_fobjs: Sequence[IO[str] | None] = (None, None),
                   cwd: str | Path | None = None,
                   intsh: bool = True,
                   env: dict[str, str] | None = None,
                   newgrp: bool = False,
                   su: bool = False) -> tuple[str | list[str], str | list[str]]:
        """Refer to 'ProcessManagerBase.run_verify()'."""

        result = self.run(cmd, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs, cwd=cwd,
                          intsh=intsh, env=env, su=su)
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
        for privkeypath in self.privkeypaths:
            ssh_opts += f" -o \"IdentityFile={privkeypath}\""
        return ssh_opts

    def rsync(self,
              src: str | Path,
              dst: str | Path,
              opts: str = _ProcessManagerBase.DEFAULT_RSYNC_OPTS,
              remotesrc: bool = False,
              remotedst: bool = False,
              exclude: Iterable[str] = (),
              output_fobjs: Sequence[IO[str] | None] = (None, None)):
        """Refer to 'ProcessManagerBase.rsync()'."""

        opts = self._rsync_add_debug_opts(opts)
        exclude_opts = "".join(f" --exclude='{p}'" for p in exclude)

        if remotesrc and remotedst:
            cmd = f"rsync {opts}{exclude_opts} -- '{src}' '{dst}'"
            result = self.run(cmd, output_fobjs=output_fobjs)
            is_local = False
        else:
            from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

            if remotesrc:
                src = f"{self.hostname}:{src}"
            else:
                src = str(src)
            if remotedst:
                dst = f"{self.hostname}:{dst}"
            else:
                dst = str(dst)

            cmd = f"rsync {opts}{exclude_opts} -e 'ssh {self.get_ssh_opts()}' -- '{src}' '{dst}'"
            result = LocalProcessManager.LocalProcessManager().run(cmd, output_fobjs=output_fobjs)
            is_local = True

        if result.exitcode == 0:
            self._rsync_debug_log(result.stdout)
            return

        if is_local and result.exitcode == 12 and "command not found" in result.stderr:
            # This is special case. We ran 'rsync' on the local system in order to copy files
            # to/from the remote system. The 'rsync' is available on the local system, but it is not
            # installed on the remote system.
            errmsg = str(result.stderr)
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
            raise type(err)(f"Failed to copy files '{src}' to '{dst}':\n{err.indent(2)}") from err

    def get(self, src: str | Path, dst: str | Path):
        """
        Copy a file or directory from remote source path to local destination path.

        Args:
            src: The remote source path of the file or directory to copy.
            dst: The local destination path where the file or directory will be copied.
        """

        self._scp(f"{self.hostname}:\"{src}\"", f"\"{dst}\"")

    def put(self, src: str | Path, dst: str | Path):
        """
        Copy a file or directory from a local source path to remote destination path.

        Args:
            src: The goal source path of the file or directory to copy.
            dst: The remote destination path where the file or directory will be copied.
        """

        self._scp(f"\"{src}\"", f"{self.hostname}:\"{dst}\"")

    def _get_sftp(self) -> paramiko.SFTPClient | DummyParamiko.SFTPClient:
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
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to establish SFTP session with {self.hostname}:\n{msg}") from err

        return self._sftp

    def _open(self, path: str | Path, mode: str) -> IO:
        """Refer to 'ProcessManagerBase._open()'."""

        def _read_(fobj: IO, size: int | None = None) -> bytes | str:
            """
            Read data from a file object with enhanced exception handling and text mode support.

            Args:
                fobj: The file object to read from.
                size: The number of bytes to read. If None, reads until EOF.

            Returns:
                The data read from the file object. Return a string if the file is in text mode,
                otherwise return bytes.
            """

            orig_fread = getattr(fobj, "_orig_fread_")
            # Paramiko SFTP file objects support only binary mode, and the "b" flag is ignored.
            data: bytes = orig_fread(size=size)

            orig_fmode = getattr(fobj, "_orig_fmode_")
            if "b" not in orig_fmode:
                try:
                    return data.decode("utf-8")
                except BaseException as err:
                    msg = Error(str(err)).indent(2)
                    errmsg = get_err_prefix(fobj, "read")
                    raise Error(f"{errmsg}: Failed to decode data after reading:\n{msg}") from err

            return data

        def _write_(fobj: IO, data: str | bytes):
            """
            Write data to a SFTP-backed file object with enhanced exception handling and text mode
            support.

            Args:
                fobj: The file object to write to.
                data: The data to write.

            Returns:
                Count of bytes or charaters written to the file object.
            """

            orig_fmode = getattr(fobj, "_orig_fmode_")

            if "b" not in orig_fmode:
                if not isinstance(data, str):
                    errmsg = get_err_prefix(fobj, "write")
                    raise Error(f"{errmsg}: The data to write must be a string, but not "
                                f"{type(data).__name__}") from None

                try:
                    data = data.encode("utf-8")
                except BaseException as err:
                    msg = Error(str(err)).indent(2)
                    errmsg = get_err_prefix(fobj, "write")
                    raise Error(f"{errmsg}:\nFailed to encode data before writing:\n"
                                f"{msg}") from err

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

        path = str(path)
        sftp = self._get_sftp()

        errmsg = f"Failed to open file '{path}' with mode '{mode}' on {self.hostname} via SFTP: "
        try:
            fobj = sftp.file(path, mode)
        except PermissionError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from err
        except FileNotFoundError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from err
        except BaseException as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"{errmsg}\n{msg}") from err

        # Save the path and the mode in the file object.
        setattr(fobj, "_orig_fpath_", path)
        setattr(fobj, "_orig_fmode_", mode)

        # Replace read and write methods.
        setattr(fobj, "_orig_fread_", fobj.read)
        setattr(fobj, "read", types.MethodType(_read_, fobj))
        setattr(fobj, "_orig_fwrite_", fobj.write)
        setattr(fobj, "write", types.MethodType(_write_, fobj))

        # Make sure methods of 'fobj' always raise the 'Error' exception.
        wfobj = ClassHelpers.WrapExceptions(fobj, get_err_prefix=get_err_prefix)
        if typing.TYPE_CHECKING:
            return cast(IO, wfobj)
        return wfobj

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""

        cmd = "date +%s"
        stdout, _ = self.run_verify_join(cmd)
        what = f"current time on {self.hostname} acquired via SSH using {cmd}"
        return Trivial.str_to_float(stdout, what=what)

    def _shell_test(self, path: str | Path, opt: str) -> bool:
        """
        Execute the shell 'test' command to check properties of a file or directory.

        Args:
            path: The path to the file or directory to test.
            opt: The option to pass to the 'test' command. For example:
                 '-f' check if the path exists and is a regular file,
                 '-d' check if the path exists and is a directory.

        Returns:
            True if the 'test' command succeeds (exit code 0), False otherwise.
        """

        cmd = f"sh -c 'test {opt} \"{path}\"'"
        try:
            stdout, stderr, exitcode = self.run(cmd)
        except ErrorNotFound:
            # For some reason the 'test' command was not recognized as a built-in shell command and
            # the external 'test' program was not fond in '$PATH'. Let's try running 'sh' with '-l',
            # which will make it read '/etc/profile' and possibly ensure that 'test' is in '$PATH'.
            cmd = f"sh -c -l 'test {opt} \"{path}\"'"
            stdout, stderr, exitcode = self.run(cmd)

        if stdout or stderr or exitcode not in (0, 1):
            raise Error(self.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

        return exitcode == 0

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkdir()'."""

        if self._shell_test(dirpath, "-e"):
            if exist_ok:
                return
            raise ErrorExists(f"Path '{dirpath}' already exists{self.hostmsg}")

        cmd = "mkdir"
        if parents:
            cmd += " -p"
        cmd += f" -- '{dirpath}'"
        self.run_verify(cmd)

    def mksocket(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mksocket()'."""

        python_path = self.get_python_path()

        cmd = f"""{python_path} -c 'import socket
try:
    with socket.socket(socket.AF_UNIX) as s:
        s.bind("{path}")
except OSError as err:
    import errno
    if err.errno != errno.EADDRINUSE:
        print(str(err), file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(2)'"""

        stdout, stderr, exitcode = self.run(cmd)

        if exitcode == 0:
            return

        if exitcode == 2:
            if not exist_ok:
                raise ErrorExists(f"Path '{path}' already exists{self.hostmsg}") from None
            return

        raise Error(self.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

    def mkfifo(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkfifo()'."""

        if self._shell_test(path, "-e"):
            if exist_ok:
                return
            raise ErrorExists(f"Path '{path}' already exists{self.hostmsg}")

        cmd = f"mkfifo -- '{path}'"
        self.run_verify(cmd)

    def _lsdir(self,
               path: Path,
               sort_by: LsdirSortbyType,
               reverse: bool) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase._lsdir()'."""

        yield from self._lsdir_cmdl(path, sort_by, reverse)

    def exists(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.exists()'."""

        return self._shell_test(path, "-e")

    def is_file(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_file()'."""

        return self._shell_test(path, "-f")

    def is_dir(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_dir()'."""

        return self._shell_test(path, "-d")

    def is_exe(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_exe()'."""

        return self._shell_test(path, "-x")

    def is_socket(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_socket()'."""

        return self._shell_test(path, "-S")

    def is_fifo(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_fifo()'."""

        return self._shell_test(path, "-p")

    def get_mtime(self, path: str | Path) -> float:
        """Refer to 'ProcessManagerBase.get_mtime()'."""

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'import os; print(os.stat(\"{path}\").st_mtime)'"
        try:
            stdout, _ = self.run_verify_join(cmd)
        except Error as err:
            if "FileNotFoundError" in str(err):
                raise ErrorNotFound(f"'{path}' does not exist{self.hostmsg}") from err
            raise

        mtime = stdout.strip()
        if not Trivial.is_float(mtime):
            raise Error(f"Got erroneous modification time of '{path}'{self.hostmsg}:\n{mtime}")
        return float(mtime)

    def unlink(self, path: str | Path):
        """Refer to 'ProcessManagerBase.unlink()'."""

        self.run_verify(f"unlink -- '{path}'")

    def rmtree(self, path: str | Path):
        """Refer to 'ProcessManagerBase.rmtree()'."""

        self.run_verify(f"rm -rf -- '{path}'")

    def abspath(self, path: str | Path) -> Path:
        """Refer to 'ProcessManagerBase.abspath()'."""

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'from pathlib import Path; print(Path(\"{path}\").resolve())'"
        stdout, _ = self.run_verify_join(cmd)

        rpath = stdout.strip()

        if not self.exists(rpath):
            raise ErrorNotFound(f"Path '{rpath}' does not exist")

        return Path(rpath)

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """Refer to 'ProcessManagerBase.mkdtemp()'."""

        cmd = f"mktemp -d -t '{prefix}XXXXXX'"
        if basedir:
            cmd += f" -p '{basedir}'"

        stdout, _ = self.run_verify_join(cmd)
        path = stdout.strip()
        if not path:
            raise Error(f"Cannot create a temporary directory{self.hostmsg}, the following command "
                        f"returned an empty string:\n{cmd}")

        _LOG.debug("Created a temporary directory '%s'%s", path, self.hostmsg)
        return Path(path)

    def get_envar(self, envar: str) -> str | None:
        """Refer to 'ProcessManagerBase.get_envar()'."""

        try:
            stdout, _ = self.run_verify_join(f"echo ${envar}")
        except ErrorNotFound:
            # See commentaries in '_shell_test()', this is a similar case.
            stdout, _ = self.run_verify_join(f"sh -c -l \"echo ${envar}\"")


        result = stdout.strip()
        if result:
            return result
        return None

    def which(self, program: str | Path, must_find: bool = True):
        """Refer to 'ProcessManagerBase.which()'."""

        def raise_or_return(): # pylint: disable=useless-return
            """Handle the situation when 'program' program was not found."""

            if must_find:
                raise ErrorNotFound(f"Program '{program}' was not found in $PATH{self.hostmsg}")
            return None

        which_cmds: tuple[str, ...]
        if self._which_cmd is None:
            which_cmds = ("which", "command -v")
        else:
            which_cmds = (self._which_cmd,)

        for which_cmd in which_cmds:
            cmd = f"{which_cmd} -- '{program}'"
            try:
                res = self.run_nojoin(cmd)
            except ErrorNotFound:
                if which_cmd != which_cmds[-1]:
                    # We have more commands to try.
                    continue
                raise

            self._which_cmd = which_cmd
            break
        else:
            return raise_or_return()

        if not res.exitcode:
            # Which could return several paths. They may contain aliases.
            for line in res.stdout:
                line = line.strip()
                if not line.startswith("alias"):
                    return Path(line)
            return raise_or_return()

        # The 'which' tool exits with status 1 when the program is not found. Any other error code
        # is an real failure.
        if res.exitcode != 1:
            raise Error(self.get_cmd_failure_msg(cmd, res.stdout, res.stderr, res.exitcode))

        return raise_or_return()
