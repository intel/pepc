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

from  __future__ import annotations # Remove when switching to Python 3.10+.

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
from operator import itemgetter
from typing import IO, cast
from collections.abc import Callable
try:
    import paramiko
except (ModuleNotFoundError, ImportError):
    from pepclibs.helperlibs import DummyParamiko as paramiko  # type: ignore[no-redef]
from pepclibs.helperlibs import Logging, _ProcessManagerBase, ClassHelpers, Trivial
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorTimeOut, ErrorConnect
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.helperlibs._ProcessManagerBase import LsdirTypedDict

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
        # The last line printed by the command to stdout or stderr observed so far.
        self._ll = ["", ""]
        # Whether the last line ('ll[0]' for stdout and 'll[1] for stderr) should be checked against
        # the marker. Used as an optimization in order to avoid matching the 'll' against the marker
        # too often.
        self._check_ll = [True, True]

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
        self._marker_regex = re.compile(rf"^{self._marker}, \d+ ---$")

    def _reinit(self, cmd: str, real_cmd: str):
        """Refer to 'ProcessBase._reinit()'."""

        super()._reinit(cmd, real_cmd)

        self._ll = ["", ""]
        self._check_ll = [True, True]
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

        return not self._ll[0] and not self._ll[1] and super()._process_is_done()

    def _watch_for_marker(self, data: str, streamid: int) -> tuple[str, int | None]:
        """
        Check for the marker in the stdout or stderr data of the interactive shell to determine if
        process has exited.

        Args:
            data: A piece of stdout or stderr data from the process.
            streamid: The stream ID (0 for stdout, 1 for stderr) from which the data was received.

        Returns:
            A tuple containing the captured stdout data ('cdata') and process exit code
            ('exitcode'), or 'None' if the marker is not found.
                - 'cdata': A portion of data without the marker. If the marker was found, 'cdata' is
                           'data' minus the marker. If the marker was not found, 'cdata' is going to
                           be just some portion of 'data', because part of 'data' might be saved in
                           'self._ll[streamid]' if it resembles the beginning of the marker.
                - 'exitcode': The exit code of the command if the marker is found. If the marker was
                              not found, always return 'None' for the exit code.
        """

        exitcode: int | None = None
        cdata: str = ""
        ll = self._ll[streamid]
        check_ll = self._check_ll[streamid]

        self._dbg("SSHProcess._watch_for_marker(): Starting with: streamid: %d, check_ll: %s\n"
                  "ll: %s\ndata:\n%s", streamid, str(check_ll), repr(ll), repr(data))

        split = data.rsplit("\n", 1)
        if len(split) > 1:
            # Got a new marker suspect. Keep it in 'll', while old 'll' and the rest of
            # 'data' can be returned up for capturing. Set 'check_ll' to 'True' to indicate
            # that 'll' has to be checked for the marker.
            cdata = ll + split[0] + "\n"
            check_ll = True
            ll = split[1]
        else:
            # Got a continuation of the previous line. The 'check_ll' flag is 'True' when 'll'
            # being a marker is a real possibility. If we already checked 'll' and it starts
            # with data that is different to the marker, there is not reason to check it again, and
            # we can send it up for capturing.
            if not ll:
                check_ll = True
            if check_ll:
                ll += split[0]
                cdata = ""
            else:
                cdata = ll + data
                ll = ""

        if check_ll:
            # 'll' is a real suspect, check if it looks like the marker.
            check_ll = ll.startswith(self._marker) or self._marker.startswith(ll)

        # OK, if 'll' is still a real suspect, do a full check using the regex: full marker #
        # line should contain not only the hash, but also the exit status.
        if check_ll and re.match(self._marker_regex, ll):
            # Extract the exit code from stdout, the 'll' string should have the following format:
            # --- hash, <exitcode> ---
            split = ll.rsplit(", ", 1)
            assert len(split) == 2
            status = split[1].rstrip(" ---")
            if not Trivial.is_int(status):
                raise Error(f"The process was running{self.hostmsg} under the interactive "
                            f"shell and finished with a correct marker, but an unexpected exit "
                            f"code '{status}'.\nThe command was: {self.cmd}")

            ll = ""
            check_ll = False
            exitcode = int(status)

        self._ll[streamid] = ll
        self._check_ll[streamid] = check_ll

        self._dbg("SSHProcess._watch_for_marker(): Ending with: streamid %d, exitcode %s, "
                  "check_ll: %s\nll: %s\ncdata:\n%s",
                  streamid, str(exitcode), str(check_ll), ll, repr(cdata))

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
                    output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                    lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """Implement '_wait()' for the interactive shell case. Refer to 'ProcessBase._wait()'."""

        start_time = time.time()

        self._dbg("SSHProcess._wait_intsh(): Starting with(): self._check_ll: %s\nself._ll: %s",
                  str(self._check_ll), str(self._ll))
        self._dbg_log_buffered_output(pfx="SSHProcess._wait_intsh(): Starting with")

        exitcode: list[int | None] = [None, None]

        while True:
            assert self._queue is not None

            self._dbg("SSHProcess._wait_intsh(): New iteration, exitcode[0] %s, exitcode[1], %s",
                      str(exitcode[0]), str(exitcode[1]))

            if _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
                # Enough lines were captured, return them, but only if no markers were yet found. If
                # at least one was found, keep waiting for the other one.
                if exitcode[0] is None and exitcode[1] is None:
                    self._dbg("SSHProcess._wait_intsh(): Enough lines were captured, stop looping")
                    break
                self._dbg("SSHProcess._wait_intsh(): Enough lines were captured, but waiting "
                          "for the second marker")

            if exitcode[0] is not None and exitcode[1] is not None:
                self.exitcode = exitcode[0]

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
            else:
                if exitcode[streamid] is not None:
                    raise Error(f"The marker for and interactive shell process{self.hostmsg} "
                                f"stream {streamid} was already observed, but new data were "
                                f"received, the data:\n{data}")

                # The indication that the process has exited are 2 markers, one in stdout (stream 0)
                # and the other in stderr (stream 1).The goal is to watch for this marker, hide it
                # from the user, because it does not belong to the output of the process. The marker
                # always starts at the beginning of line.
                #
                # Both markers must be observed before concluding that the command has finished.
                # Observing the marker only in one stream is not enough to guarantee that the output
                # from the other stream was fully consumed.
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

    def _read_pid(self):
        """
        Read the process ID (PID) of the executed command and store it in 'self.pid'.

        Notes:
            - The reason this method exists is that paramiko does not have a mechanism to get PID.
              So this is a workaround.
        """

        self._dbg("SSHProcess._read_pid(): Reading PID for the following command: %s", self.cmd)

        stdout, stderr, _ = self.wait(timeout=60, lines=(1, -1), join=False)

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
                 password: str = "",
                 privkeypath: str | Path | None = None,
                 timeout: int | float | None = None):
        """
        Initialize a class instance and establish SSH connection to a remote host.

        Args:
            hostname: The name of the host to connect to.
            ipaddr: IP address of the host. If provided, it is used instead of 'hostname' for
                    connecting, and 'hostname' is used for logging purposes.
            port: The port number to connect to. Defaults to 22.
            username: Username for authentication. Defaults to the current system user.
            password: Password for the specified username. Defaults to an empty string.
            privkeypath: Optional path to the private key for authentication. If no private key path
                         is provided, the method attempts to locate one using SSH configuration
                         files.
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
            _username = os.getenv("USER")
            if _username:
                username = _username
            else:
                username = Trivial.get_username()
        self.username = username

        self.password = password
        if privkeypath:
            self.privkeypath: str | None = str(privkeypath)
        else:
            self.privkeypath = None

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
            name = self._cfg_lookup("hostname", hostname, self.username)
            if isinstance(name, str) and name:
                connhost = name
                self._vhostname = f"{hostname} ({connhost})"
            else:
                self._vhostname = connhost = hostname

        if not self.privkeypath:
            try:
                self.privkeypath = self._lookup_privkey(hostname, self.username)
            except Exception as err: # pylint: disable=broad-except
                msg = Error(str(err)).indent(2)
                _LOG.debug(f"Private key lookup failed:\n{msg}")

        if self.privkeypath:
            # Private SSH key sanity checks.
            try:
                mode = os.stat(self.privkeypath).st_mode
            except OSError as err:
                msg = Error(str(err)).indent(2)
                raise Error(f"'stat()' failed for private SSH key at '{self.privkeypath}':\n"
                            f"{msg}") from None

            if not stat.S_ISREG(mode):
                raise Error(f"Private SSH key at '{self.privkeypath}' is not a regular file")

            if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                raise Error(f"Private SSH key at '{self.privkeypath}' permissions are too wide: "
                            f"Make sure 'others' cannot read/write/execute it")

        _LOG.debug("Establishing SSH connection to %s, port %d, username '%s', timeout '%s', "
                   "password '%s', priv. key '%s', SSH pman object ID: %s",
                   self._vhostname, port, self.username, self.connection_timeout, self.password,
                   self.privkeypath, id(self))

        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # We expect to be authenticated either with the key or an empty password.
            self.ssh.connect(username=self.username, hostname=connhost, port=port,
                             key_filename=self.privkeypath, timeout=self.connection_timeout,
                             password=self.password, allow_agent=True, look_for_keys=True)
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

    def _cfg_lookup(self,
                    optname: str,
                    hostname: str,
                    username: str,
                    cfgfiles: list[str] | None = None) -> str | list[str] | None:
        """
        Search for an SSH configuration option for a given host and user in SSH config files.

        Args:
            optname: The name of the SSH configuration option to search for.
            hostname: The hostname for which the configuration option is being queried.
            username: The username to for possible SSH tokens expansion (%u in SSH options is
                      expanded with the user name)
            cfgfiles: A list of SSH configuration file paths to search. Use standard paths by
                      default.

        Returns:
            The value of the SSH configuration option if found, otherwise None.
        """

        old_username = None
        try:
            old_username = os.getenv("USER")
            os.environ["USER"] = username

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

                cfg = config.lookup(hostname)
                if optname in cfg and cfg.get("user", None) == username:
                    return cfg[optname]

                if "include" in cfg:
                    # The include directive may contain wildcards. Expand them. Sort the resulting
                    # list to have a deterministic order.
                    include_cfgfiles = sorted(glob.glob(cfg["include"]))
                    optval = self._cfg_lookup(optname, hostname, username,
                                              cfgfiles=include_cfgfiles)
                    if optval:
                        return optval
        finally:
            if old_username:
                os.environ["USER"] = old_username
            else:
                # Remove the USER environment variable if it was not set before.
                os.environ.pop("USER", None)

        return None

    def _lookup_privkey(self,
                        hostname: str,
                        username: str,
                        cfgfiles: list[str] | None = None) -> str | None:
        """
        Look up the private SSH authentication key for a given host and user.

        Args:
            hostname: The hostname of the target SSH server.
            username: The username for the SSH connection.
            cfgfiles: List of configuration files to search for the key. Use standard files by
                      default.

        Returns:
            The path to the private key if found, or None if no key is found.
        """

        privkeypath = self._cfg_lookup("identityfile", hostname, username, cfgfiles=cfgfiles)
        if isinstance(privkeypath, list):
            privkeypath = privkeypath[0]

        return privkeypath

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
            string that prints the PID before executing the original command.
        """

        prefix = ""
        if env:
            for key, value in env.items():
                prefix += f'export {key}="{value}"; '
        prefix += r'printf "%s\n" "$$";'
        if cwd:
            prefix += f""" cd "{cwd}" &&"""
        return prefix + " exec " + cmd

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
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot create a new SSH session for running the following "
                        f"command{self.hostmsg}:\n  {cmd}\nThe error is:\n{msg}") from err

        try:
            chan.exec_command(cmd)
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Cannot execute the following command in a new SSH session"
                        f"{self.hostmsg}:\n  {cmd}\nThe error is:\n{msg}") from err

        try:
            stdin = chan.makefile("wb")
        except BaseException as err: # pylint: disable=broad-except
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to create the stdin file-like object for the following "
                        f"command{self.hostmsg}:\n  {cmd}\nThe Error is:\n{msg}") from err

        if mix_output:
            try:
                chan.set_combine_stderr(True)
            except BaseException as err: # pylint: disable=broad-except
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
                  cwd: str | Path | None = None,
                  intsh: bool = False,
                  env: dict[str, str] | None = None,
                  mix_output: bool = False) -> SSHProcess:
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

        Returns:
            A 'SSHProcess' object representing the executed remote asynchronous process.
        """

        command = str(command)
        if not intsh:
            return self._run_in_new_session(command, cwd=cwd, env=env, mix_output=mix_output)

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

    def run_async(self,
                  cmd: str | Path,
                  cwd: str | Path | None = None,
                  intsh: bool = False,
                  stdin: IO | None = None,
                  stdout: IO | None = None,
                  stderr: IO | None = None,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False) -> SSHProcess:
        """Refer to 'ProcessManagerBase.run_async()'."""

        # The 'newgrp' argument is ignored, because it makes no sense in a remote host case.
        # The 'stdin', 'stdout', and 'stderr' arguments are not supported.

        # pylint: disable=unused-argument
        for arg, val in (("stdin", None), ("stdout", None), ("stderr", None)):
            if locals()[arg] != val:
                raise Error(f"'SSHProcessManager.run_async()' doesn't support the '{arg}' argument")

        cmd = str(cmd)

        if cwd:
            cwd_msg = f"\nWorking directory: {cwd}"
        else:
            cwd_msg = ""

        _LOG.debug("Running the following command asynchronously%s (intsh %s):\n%s%s",
                   self.hostmsg, str(intsh), cmd, cwd_msg)

        return self._run_async(cmd, cwd=cwd, intsh=intsh, env=env)

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = None,
            capture_output: bool = True,
            mix_output: bool = False,
            join: bool = True,
            output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
            cwd: str | Path | None = None,
            intsh: bool = True,
            env: dict[str, str] | None = None,
            newgrp: bool = False) -> ProcWaitResultType:
        """Refer to 'ProcessManagerBase.run()'."""

        # pylint: disable=unused-argument

        msg = f"Running the following command{self.hostmsg} (intsh {intsh}):\n{cmd}"
        if cwd:
            msg += f"\nWorking directory: {cwd}"
        _LOG.debug(msg)

        # Execute the command on the remote host.
        with self._run_async(cmd, cwd=cwd, intsh=intsh, env=env, mix_output=mix_output) as proc:
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
                   cwd: str | Path | None = None,
                   intsh: bool = True,
                   env: dict[str, str] | None = None,
                   newgrp: bool = False) -> tuple[str | list[str], str | list[str]]:
        """Refer to 'ProcessManagerBase.run_verify()'."""

        # pylint: disable=unused-argument

        result = self.run(cmd, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs, cwd=cwd,
                          intsh=intsh, env=env)
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
              src: str | Path,
              dst: str | Path,
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
                src = f"{self.hostname}:{src}"
            else:
                src = str(src)
            if remotedst:
                dst = f"{self.hostname}:{dst}"
            else:
                dst = str(dst)

            cmd = f"rsync {opts} -e 'ssh {self.get_ssh_opts()}' -- '{src}' '{dst}'"
            result = LocalProcessManager.LocalProcessManager().run(cmd)
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
            raise Error(f"Failed to copy files '{src}' to '{dst}':\n{err.indent(2)}") from err

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

    def open(self, path: str | Path, mode: str) -> IO:
        """Refer to 'ProcessManagerBase.open()'."""

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
                except BaseException as err: # pylint: disable=broad-except
                    msg = Error(str(err)).indent(2)
                    errmsg = get_err_prefix(fobj, "write")
                    raise Error(f"{errmsg}:\nFailed to encode data before writing:\n"
                                f"{msg}") from None

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
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
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
        if "b" in mode:
            return cast(IO[bytes], wfobj)
        return cast(IO[str], wfobj)

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""

        cmd = "date +%s"
        stdout, _ = self.run_verify(cmd)
        tt = cast(str, stdout).strip()
        what = f"current time on {self.hostname} acquired via SSH using {cmd}"
        return Trivial.str_to_float(tt, what=what)

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

    def lsdir(self, path: str | Path) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase.lsdir()'."""

        path = Path(path)

        # A small python program to get the list of directories with some metadata.
        python_path = self.get_python_path()
        cmd = f"""{python_path} -c 'import os
import sys
path = "{path}"
try:
    entries = os.listdir(path)
except FileNotFoundError as err:
    raise SystemExit(2)
except OSError as err:
    print(str(err), file=sys.stderr)
    raise SystemExit(1)
for ent in entries:
    try:
        stinfo = os.lstat(os.path.join(path, ent))
    except OSError as err:
        print(str(err), file=sys.stderr)
        raise SystemExit(1)
    print(ent, stinfo.st_mode, stinfo.st_ctime)'"""

        stdout, stderr, exitcode = self.run(cmd)

        if exitcode == 2:
            raise ErrorNotFound(f"Directory '{path}' does not exists{self.hostmsg}") from None
        if exitcode != 0:
            raise Error(self.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

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
            stdout, _ = self.run_verify(cmd)
        except Error as err:
            if "FileNotFoundError" in str(err):
                raise ErrorNotFound(f"'{path}' does not exist{self.hostmsg}") from None
            raise

        mtime = cast(str, stdout).strip()
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
        stdout, _ = self.run_verify(cmd)

        rpath = cast(str, stdout).strip()

        if not self.exists(rpath):
            raise ErrorNotFound(f"Path '{rpath}' does not exist")

        return Path(rpath)

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """Refer to 'ProcessManagerBase.mkdtemp()'."""

        cmd = f"mktemp -d -t '{prefix}XXXXXX'"
        if basedir:
            cmd += f" -p '{basedir}'"

        stdout, _ = self.run_verify(cmd)
        path = cast(str, stdout).strip()
        if not path:
            raise Error(f"Cannot create a temporary directory{self.hostmsg}, the following command "
                        f"returned an empty string:\n{cmd}")

        _LOG.debug("Created a temporary directory '%s'%s", path, self.hostmsg)
        return Path(path)

    def get_envar(self, envar: str) -> str | None:
        """Refer to 'ProcessManagerBase.get_envar()'."""

        try:
            stdout, _ = self.run_verify(f"echo ${envar}")
        except ErrorNotFound:
            # See commentaries in '_shell_test()', this is a similar case.
            stdout, _ = self.run_verify(f"sh -c -l \"echo ${envar}\"")


        result = cast(str, stdout).strip()
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
                stdout, stderr, exitcode = self.run(cmd, join=False)
            except ErrorNotFound:
                if which_cmd != which_cmds[-1]:
                    # We have more commands to try.
                    continue
                raise

            self._which_cmd = which_cmd
            break

        if not exitcode:
            # Which could return several paths. They may contain aliases.
            for line in cast(list[str], stdout):
                line = line.strip()
                if not line.startswith("alias"):
                    return Path(line)
            return raise_or_return()

        # The 'which' tool exits with status 1 when the program is not found. Any other error code
        # is an real failure.
        if exitcode != 1:
            raise Error(self.get_cmd_failure_msg(cmd, stdout, stderr, exitcode))

        return raise_or_return()
