# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module implements a process manager for running and monitoring processes on a remote host over
SSH. In addition to this, the process manager provides many file I/O methods, such as 'open()' and
'exists()'. This allows for doing file I/O on a remote host as if it was a local host.

SECURITY NOTICE: this module and any part of it should only be used for debugging and development
purposes. No security audit had been done. Not for production use.

There are two ways run commands remotely over SSH: in a new paramiko SSH session, and in the
interactive shell. The latter way adds complexity, but the reason we have it is because it is much
faster to run a process this way, comparing to establishing a new session.

The first way of running commands is very straight-forward - we just open a new paramiko SSH session
and run the command. The session gets closed when the command finishes. The next command requires a
new session. Creating a new SSH session takes time, so if we need to run many commands, the overhead
becomes very noticeable.

The second way of running commands is via the interactive shell. We run the 'sh -s' process in a new
paramiko session, and then just run commands in this shell. One command can run at a time. But we do
not need to create a new SSH session between the commands. The complication with this method is to
detect when command has finished. We solve this problem my making each command print a unique random
hash to 'stdout' when it finishes.
"""

# pylint: disable=no-member
# pylint: disable=protected-access

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
import paramiko
from pepclibs.helperlibs import _ProcessManagerBase, ClassHelpers, Trivial
from pepclibs.helperlibs._ProcessManagerBase import ProcResult # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorTimeOut, ErrorConnect
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorExists

_LOG = logging.getLogger()

# Paramiko is a bit too noisy, lower its log level.
logging.getLogger("paramiko").setLevel(logging.WARNING)

class SSHProcess(_ProcessManagerBase.ProcessBase):
    """
    This class represents a remote process that was executed by 'SSHProcessManager'.
    """

    def _fetch_stream_data(self, streamid, size):
        """Fetch up to 'size' bytes from stdout or stderr of the process."""

        try:
            return self._streams[streamid](size)
        except BaseException as err:
            raise Error(str(err)) from err

    def _recv_exit_status_timeout(self, timeout):
        """
        This is a version of paramiko channel's 'recv_exit_status()' which supports a timeout.
        Returns the exit status or 'None' in case of 'timeout'.
        """

        chan = self.pobj
        self._dbg("_recv_exit_status_timeout: waiting for exit status, timeout %s sec", timeout)

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
            self._dbg("_recv_exit_status_timeout: exit status not ready for %s seconds", timeout)
            return None

        exitcode = chan.exit_status
        self._dbg("_recv_exit_status_timeout: exit status %d", exitcode)
        return exitcode

    def _process_is_done(self):
        """
        Returns 'True' if all output lines of the process have been returned to the user and the
        process has exited. Returns 'False' otherwise.
        """

        return not self._ll and super()._process_is_done()

    def _watch_for_marker(self, data):
        """
        When we run a command in the interactive shell (as opposed to running in a dedicated SSH
        session), the way we can detect that the command has ended is by watching for a special
        marker in 'stdout' of the interactive shell process.

        This is a helper for '_wait_intsh()' which takes a piece of 'stdout' data that came from the
        stream fetcher and checks for the marker in it. Returns a tuple of '(cdata, exitcode)',
        where 'cdata' is the stdout data that has to be captured, and exitcode is the exit code of
        the command.

        In other words, if no marker was not found, this function returns '(cdata, None)', and
        'cdata' may not be the same as 'data', because part of it may be saved in 'self._ll',
        because it looks like the beginning of the marker. I marker was found, this function returns
        '(cdata, exitcode)'. Again, 'cdata' does not have to be the same as 'data', because 'data'
        could contain the marker, which will not be present in 'cdata'. The 'exitcode' will contain
        an integer exit code of the command.
        """

        exitcode = None
        cdata = None

        self._dbg("_watch_for_marker: starting with self._check_ll %s, self._ll: %s, data:\n%s",
                  str(self._check_ll), str(self._ll), data)

        split = data.rsplit("\n", 1)
        if len(split) > 1:
            # We have got a new line. This is our new marker suspect. Keep it in 'self._ll', while
            # old 'self._ll' and the rest of 'data' can be returned up for capturing. Set
            # 'self._check_ll' to 'True' to indicate that 'self._ll' has to be checked for the
            # marker.
            cdata = self._ll + split[0] + "\n"
            self._check_ll = True
            self._ll = split[1]
        else:
            # We have got a continuation of the previous line. The 'check_ll' flag is 'True' when
            # 'self._ll' being a marker is a real possibility. If we already checked 'self._ll' and
            # it starts with data that is different to the marker, there is not reason to check it
            # again, and we can send it up for capturing.
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

        # OK, if 'self._ll' is still a real suspect, do a full check using the regex: full marker
        # line should contain not only the hash, but also the exit status.
        if self._check_ll and re.match(self._marker_regex, self._ll):
            # Extract the exit code from the 'self._ll' string that has the following form:
            # --- hash, <exitcode> ---
            split = self._ll.rsplit(", ", 1)
            assert len(split) == 2
            exitcode = split[1].rstrip(" ---")
            if not Trivial.is_int(exitcode):
                raise Error(f"the process was running{self.hostmsg} under the interactive "
                            f"shell and finished with a correct marker, but unexpected exit "
                            f"code '{exitcode}'.\nThe command was: {self.cmd}")

            self._ll = ""
            self._check_ll = False
            exitcode = int(exitcode)

        self._dbg("_watch_for_marker: ending with self._check_ll %s, self._ll %s, exitcode %s, "
                  "cdata:\n%s", str(self._check_ll), self._ll, str(exitcode), cdata)

        return (cdata, exitcode)

    def _wait_intsh(self, timeout=None, capture_output=True, output_fobjs=(None, None),
                    lines=(None, None)):
        """
        Implements 'wait()' for the optimized case when the command was executed in the interactive
        shell process. This case allows us to save time on creating a separate session for
        commands.
        """

        start_time = time.time()

        self._dbg("_wait_intsh: starting with self._check_ll %s, self._ll: %s, partial: %s, output:"
                  "\n%s", str(self._check_ll), str(self._ll), self._partial, str(self._output))

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None and self._queue.empty():
                self._dbg("_wait_intsh: process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                # Note, 'data' is going to be 'None' in this case.
                self._dbg("_wait_intsh: nothing in the queue for %d seconds", timeout)
            elif data is None:
                raise Error(f"the interactive shell process{self.hostmsg} closed stream {streamid} "
                            f"while running the following command:\n{self.cmd}")
            elif streamid == 0:
                # The indication that the process has exited is our marker in stdout (stream 0). Our
                # goal is to watch for this marker, hide it from the user, because it does not
                # belong to the output of the process. The marker always starts at the beginning of
                # line.
                data, self.exitcode = self._watch_for_marker(data)

            if data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)

            if not timeout:
                self._dbg(f"_wait_intsh: timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time > timeout:
                self._dbg("_wait_intsh: stop waiting for the process - timeout")
                break

        result = self._get_lines_to_return(lines)

        if self._process_is_done():
            # Mark the interactive shell process as vacant.
            acquired = self.pman._acquire_intsh_lock(self.cmd)
            if not acquired:
                _LOG.warning("failed to mark the interactive shell process as free")
            else:
                self.pman._intsh_busy = False
                self.pman._intsh_lock.release()

        return result

    def _wait_nointsh(self, timeout=None, capture_output=True, output_fobjs=(None, None),
                      lines=(None, None)):
        """
        Implements 'wait()' for the non-optimized case when the process was executed in its own
        separate SSH session.
        """

        start_time = time.time()

        self._dbg("_wait_nointsh: starting with partial: %s, output:\n%s",
                  self._partial, str(self._output))

        while not _ProcessManagerBase.have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("_wait_nointsh: process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            self._dbg("_get_next_queue_item(): returned: %d, %s", streamid, data)
            if streamid == -1:
                self._dbg("_wait_nointsh: nothing in the queue for %d seconds", timeout)
            elif data is not None:
                self._handle_queue_item(streamid, data, capture_output=capture_output,
                                        output_fobjs=output_fobjs)
            else:
                self._dbg("_wait_nointsh: stream %d closed", streamid)
                # One of the output streams closed.
                self._threads[streamid].join()
                self._threads[streamid] = self._streams[streamid] = None

                if not self._streams[0] and not self._streams[1]:
                    self._dbg("_wait_nointsh: both streams closed")
                    self.exitcode = self._recv_exit_status_timeout(timeout)
                    break

            if not timeout:
                self._dbg(f"_wait_nointsh: timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time > timeout:
                self._dbg("_wait_nointsh: stop waiting for the process - timeout")
                break

        return self._get_lines_to_return(lines)

    def _wait(self, timeout=None, capture_output=True, output_fobjs=(None, None),
              lines=(None, None)):
        """
        Implements 'wait()'. The arguments are the same as in 'wait()', but returns a tuple of two
        lists: '(stdout_lines, stderr_lines)' (lists of stdout/stderr lines).
        """

        if self.pman._intsh and self.pobj == self.pman._intsh.pobj:
            func = self._wait_intsh
        else:
            func = self._wait_nointsh

        return func(timeout=timeout, capture_output=capture_output, output_fobjs=output_fobjs,
                    lines=lines)

    def poll(self):
        """
        Check if the process is still running. If it is, return 'None', else return exit status.
        """

        chan = self.pobj
        if chan.exit_status_ready():
            return chan.recv_exit_status()
        return None

    def _read_pid(self):
        """Read 'PID' for the just executed process and store it in 'self.pid'."""

        self._dbg("_read_pid: reading PID for command: %s", self.cmd)
        assert self.shell

        stdout, stderr, _ = self.wait(timeout=60, lines=(1, 0), join=False)

        msg = f"\nThe command{self.hostmsg} was:\n{self.cmd}" \
              f"\nThe actual (real) command was:\n{self.real_cmd}"

        if len(stdout) != 1:
            raise Error(f"expected only one line with PID in stdout, got {len(stdout)} lines "
                        f"instead.{msg}")
        if stderr:
            raise Error(f"expected only one line with PID in stdout and no lines in stderr, got "
                        f"{len(stderr)} lines in stderr instead.{msg}")

        pid = stdout[0].strip()

        # The 'PID' line does not belong to the process, so decrement the lines counter.
        self._lines_cnt[0] -= 1

        if len(pid) > 128:
            raise Error(f"received too long and probably bogus PID: {pid}{msg}")
        if not Trivial.is_int(pid):
            raise Error(f"received a bogus non-integer PID: {pid}{msg}")

        self._dbg("_read_pid: PID is %s for command: %s", pid, self.cmd)
        self.pid = int(pid)

    def _reinit_marker(self):
        """
        Pick a new interactive shell command marker. The marker is used as an indication that the
        command executed in the interactive shell finished.
        """

        # Generate a random string which will be used as the marker, which indicates that the
        # interactive shell command has finished.
        randbits = random.getrandbits(256)
        self._marker = f"--- {randbits:064x}"
        self._marker_regex = re.compile(f"^{self._marker}, \\d+ ---$")

    def _reinit(self, cmd, real_cmd, shell):
        """
        Re-initialize the interactive shell process object when a new command is executed. The
        arguments are the same as in 'ProcessBase._reinit()'.
        """

        super()._reinit(cmd, real_cmd, shell)

        self._ll = ""
        self._check_ll = True
        self._lines_cnt = [0, 0]

        if shell:
            self._read_pid()

    def close(self):
        """Free allocated resources."""

        self._dbg("close()")
        ClassHelpers.close(self, close_attrs=("pobj",))
        super().close()

    def __init__(self, pman, pobj, cmd, real_cmd, shell, streams):
        """
        Initialize a class instance. The arguments are the same as in 'ProcessBase.__init__()'.
        """

        super().__init__(pman, pobj, cmd, real_cmd, shell, streams)

        #
        # The below attributes are used when the process runs in an interactive shell.
        #
        # The marker indicating that the command has finished.
        self._marker = None
        # The regular expression the last line of the command output should match.
        self._marker_regex = None
        # The last line printed by the command to stdout observed so far.
        self._ll = ""
        # Whether the last line ('ll') should be checked against the marker. Used as an optimization
        # in order to avoid matching the 'll' against the marker too often.
        self._check_ll = True

        if shell:
            self._read_pid()

class SSHProcessManager(_ProcessManagerBase.ProcessManagerBase):
    """
    This class implements a process manager for running and monitoring processes on a remote host
    over SSH.

    SECURITY NOTICE: this class and any part of it should only be used for debugging and development
    purposes. No security audit had been done. Not for production use.
    """

    @staticmethod
    def _format_cmd_for_pid(cmd, cwd=None):
        """
        When we run a process via the shell, we do not know it's PID. This function modifies the
        'cmd' command so that it prints the PID as the first line of its output to 'stdout'. This
        requires a shell.
        """

        # Prepend the command with a shell statement which prints the PID of the shell where the
        # command will be run. Then use 'exec' to make sure that the command inherits the PID.
        prefix = r'printf "%s\n" "$$";'
        if cwd:
            prefix += f""" cd "{cwd}" &&"""
        return prefix + " exec " + cmd

    def _run_in_new_session(self, command, cwd=None, shell=True):
        """Run command 'command' in a new session."""

        cmd = command
        if shell:
            cmd = self._format_cmd_for_pid(command, cwd=cwd)

        try:
            chan = self.ssh.get_transport().open_session(timeout=self.connection_timeout)
        except BaseException as err:
            msg = Error(err).indent(2)
            raise Error(f"cannot create a new SSH session for running the following "
                        f"command{self.hostmsg}:\n{cmd}\nThe error is:\n{msg}") from err

        try:
            chan.exec_command(cmd)
        except BaseException as err:
            msg = Error(err).indent(2)
            raise Error(f"cannot execute the following command in a new SSH session"
                        f"{self.hostmsg}:\n{cmd}\nThe error is:\n{msg}") from err

        try:
            stdin = chan.makefile("wb")
        except BaseException as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to create the stdin file-like object:\n{msg}") from err

        streams = (stdin, chan.recv, chan.recv_stderr)
        return SSHProcess(self, chan, command, cmd, shell, streams)

    def _run_in_intsh(self, command, cwd=None):
        """Run command 'command' in the interactive shell."""

        if not self._intsh:
            cmd = "sh -s"
            _LOG.debug("starting interactive shell%s: %s", self.hostmsg, cmd)
            self._intsh = self._run_in_new_session(cmd, shell=False)

        proc = self._intsh
        cmd = self._format_cmd_for_pid(command, cwd=cwd)

        # Pick a new marker for the new interactive shell command.
        proc._reinit_marker()
        # Run the command.
        cmd = "sh -c " + shlex.quote(cmd) + "\n" + f'printf "%s, %d ---" "{proc._marker}" "$?"\n'
        proc.pobj.send(cmd)
        # Re-initialize the interactive shell process object to match the new command.
        proc._reinit(command, cmd, True)

        return proc

    def _acquire_intsh_lock(self, command=None):
        """
        Acquire the interactive shell lock. It should be acquired only for short period of times.
        """

        timeout = 5
        acquired = self._intsh_lock.acquire(timeout=timeout) # pylint: disable=consider-using-with
        if not acquired:
            msg = "failed to acquire the interactive shell lock"
            if command:
                msg += f" for for the following command:\n{command}\n"
            else:
                msg += "."
            msg += f"Waited for {timeout} seconds."
            _LOG.warning(msg)
        return acquired

    def _run_async(self, command, cwd=None, shell=True, intsh=False):
        """Implements 'run_async()'."""

        if not shell and intsh:
            raise Error("'shell' argument must be 'True' when 'intsh' is 'True'")

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
            _LOG.warning("interactive shell is busy, running the following command in a new "
                         "SSH session:\n%s", command)
            return self._run_in_new_session(command, cwd=cwd, shell=shell)

        try:
            return self._run_in_intsh(command, cwd=cwd)
        except BaseException as err: # pylint: disable=broad-except
            _LOG.warning("failed to run the following command in an interactive shell: %s\n"
                         "The error was: %s", command, err)

            # Close the internal shell and try to run in a new session.
            with contextlib.suppress(BaseException):
                acquired = self._acquire_intsh_lock(command=command)

            if acquired:
                self._intsh_busy = False
                self._intsh_lock.release()
                if self._intsh:
                    with contextlib.suppress(BaseException):
                        self._intsh.pobj.send("exit\n")
                        self._intsh.close()
                    self._intsh = None
            else:
                _LOG.warning("failed to acquire the interactive shell process lock")

            return self._run_in_new_session(command, cwd=cwd, shell=shell)

    def run_async(self, command, cwd=None, shell=True, intsh=False, stdin=None, stdout=None,
                  stderr=None):
        """
        Run command 'command' on the remote host. Refer to 'ProcessManagerBase.run_async()' for more
        information.

        Notes.

        1. The 'stdin', 'stdout' and 'stderr' arguments are not supported.
        2. Standard Unix systems have some sort of shell, so it is safe to use 'shell=True'. But
           this is not always the case. E.g., Dell's iDRACs do not run a shell when you log into
           them.  Use 'shell=False' in such cases.
        """

        # pylint: disable=unused-argument
        for arg in ('stdin', 'stdout', 'stderr'):
            if locals()[arg] is not None:
                raise Error(f"'SSHProcessManager.run_async()' does not support the '{arg}' "
                            f"argument")

        # Allow for 'command' to be a 'pathlib.Path' object which Paramiko does not accept.
        command = str(command)

        if cwd:
            if not shell:
                raise Error(f"cannot set working directory to '{cwd}' - using shell is disallowed")
            cwd_msg = f"\nWorking directory: {cwd}"
        else:
            cwd_msg = ""
        _LOG.debug("running the following command asynchronously%s (shell %s, intsh %s):\n%s%s",
                   self.hostmsg, str(shell), str(intsh), command, cwd_msg)

        return self._run_async(str(command), cwd=cwd, shell=shell, intsh=intsh)

    def run(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
            output_fobjs=(None, None), cwd=None, shell=True, intsh=None):
        """
        Run command 'command' on the remote host and wait for it to finish. Refer to
        'ProcessManagerBase.run()' for more information.

        Notes.

        1. Standard Unix systems have some sort of shell, so it is safe to use 'shell=True'. But
           this is not always the case. E.g., Dell's iDRACs do not run a shell when you log into
           them. Use 'shell=False' in such cases.
        2. The 'intsh' argument indicates whether the command should run in an interactive shell or
           in a separate SSH session. The former is faster because creating a new SSH session takes
           time.  By default, 'intsh' is the same as 'shell' ('True' if using shell is allowed,
           'False' otherwise).
        """

        # pylint: disable=unused-argument
        msg = f"running the following command{self.hostmsg} (shell {shell}, intsh {intsh}):\n" \
              f"{command}"
        if cwd:
            msg += f"\nWorking directory: {cwd}"
        _LOG.debug(msg)

        if intsh is None:
            intsh = shell

        # Execute the command on the remote host.
        proc = self._run_async(command, cwd=cwd, shell=shell, intsh=intsh)
        chan = proc.pobj
        if mix_output:
            chan.set_combine_stderr(True)

        # Wait for the command to finish and handle the time-out situation.
        result = proc.wait(timeout=timeout, capture_output=capture_output,
                           output_fobjs=output_fobjs, join=join)

        if result.exitcode is None:
            msg = self.get_cmd_failure_msg(command, *tuple(result), timeout=timeout)
            raise ErrorTimeOut(msg)

        if output_fobjs[0]:
            output_fobjs[0].flush()
        if output_fobjs[1]:
            output_fobjs[1].flush()

        return result

    def run_verify(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
                   output_fobjs=(None, None), cwd=None, shell=True, intsh=None):
        """
        Same as the "run()" method, but also verifies the exit status and if the command failed,
        raises the "Error" exception.
        """

        result = self.run(command, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs, cwd=cwd,
                          shell=shell, intsh=intsh)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        msg = self.get_cmd_failure_msg(command, *tuple(result), timeout=timeout)
        raise Error(msg)

    def get_ssh_opts(self):
        """
        Returns 'ssh' command-line tool options that are necessary to establish an SSH connection
        similar to the current connection.
        """

        ssh_opts = f"-o \"Port={self.port}\" -o \"User={self.username}\""
        if self.privkeypath:
            ssh_opts += f" -o \"IdentityFile={self.privkeypath}\""
        return ssh_opts

    def rsync(self, src, dst, opts="-rlpD", remotesrc=False, remotedst=False):
        """
        Copy data from path 'src' to path 'dst' using the 'rsync' tool with options specified in
        'opts'. Refer to '_ProcessManagerBase.rsync() for more information.
        """

        opts = self._rsync_add_debug_opts(opts)
        cmd = f"rsync {opts}"

        if remotesrc and remotedst:
            pman = self
        else:
            from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

            pman = LocalProcessManager.LocalProcessManager()
            cmd += f" -e 'ssh {self.get_ssh_opts()}'"
            if remotesrc:
                src = f"{self.hostname}:{src}"
            if remotedst:
                dst = f"{self.hostname}:{dst}"

        command = f"{cmd} -- '{src}' '{dst}'"
        result = pman.run(command)
        if result.exitcode == 0:
            self._rsync_debug_log(result.stdout)
            return

        if not pman.is_remote and result.exitcode == 12 and "command not found" in result.stderr:
            # This is special case. We ran 'rsync' on the local system in order to copy files
            # to/from the remote system. The 'rsync' is available on the local system, but it is not
            # installed on the remote system.
            raise self._command_not_found(command, result.stderr, toolname="rsync")

        msg = self.get_cmd_failure_msg(command, *tuple(result))
        raise Error(msg)

    def _scp(self, src, dst):
        """
        Helper that copies 'src' to 'dst' using 'scp'. File names should be already quoted. The
        remote path should use double quoting, otherwise 'scp' fails if path contains symbols like
        ')'.
        """

        from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel
        pman = LocalProcessManager.LocalProcessManager()

        opts = f"-o \"Port={self.port}\" -o \"User={self.username}\""
        if self.privkeypath:
            opts += f" -o \"IdentityFile={self.privkeypath}\""
        cmd = f"scp -r {opts}"

        try:
            pman.run_verify(f"{cmd} -- {src} {dst}")
        except Error as err:
            raise Error(f"failed to copy files '{src}' to '{dst}':\n{err.indent(2)}") from err

    def get(self, remote_path, local_path):
        """
        Copy a file or directory 'remote_path' from the remote host to 'local_path' on the local
        machine.
        """

        self._scp(f"{self.hostname}:\"{remote_path}\"", f"\"{local_path}\"")

    def put(self, local_path, remote_path):
        """
        Copy local file or directory defined by 'local_path' to 'remote_path' on the remote host.
        """

        self._scp(f"\"{local_path}\"", f"{self.hostname}:\"{remote_path}\"")

    def _get_sftp(self):
        """Get an SFTP server object."""

        if self._sftp:
            return self._sftp

        try:
            self._sftp = self.ssh.open_sftp()
        except BaseException as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to establish SFTP session with {self.hostname}:\n{msg}") from err

        return self._sftp

    def open(self, path, mode):
        """
        Open a file. Refer to '_ProcessManagerBase.ProcessManagerBase().open()' for more
        information.
        """

        def _read_(fobj, size=None):
            """
            This wrapper improves exceptions message and adds text mode support (SFTP file objects
            support only binary mode).
            """

            data = fobj._orig_fread_(size=size)

            if "b" not in fobj._orig_fmode_:
                try:
                    data = data.decode("utf-8")
                except UnicodeError as err:
                    msg = Error(err).indent(2)
                    raise Error(f"failed to decode data read from '{fobj._orig_fpath_}':\n{msg}") \
                          from None

            return data

        def _write_(fobj, data):
            """
            This wrapper improves exceptions message and adds text mode support (SFTP file objects
            support only binary mode).
            """

            errmsg = f"failed to write to '{fobj._orig_fpath_}': "
            if "b" not in fobj._orig_fmode_:
                try:
                    data = data.encode("utf-8")
                except UnicodeError as err:
                    msg = Error(err).indent(2)
                    raise Error(f"{errmsg}: failed to encode data before writing:\n{msg}") from None
                except AttributeError as err:
                    msg = Error(err).indent(2)
                    raise Error(f"{errmsg}: the data to write must be a string:\n{msg}") from None

            return fobj._orig_fwrite_(data)

        def get_err_prefix(fobj, method):
            """Return the error message prefix."""
            return f"method '{method}()' failed for file '{fobj._orig_fpath_}'"

        path = str(path) # In case it is a pathlib.Path() object.
        sftp = self._get_sftp()

        errmsg = f"failed to open file '{path}' with mode '{mode}' on {self.hostname} via SFTP: "
        try:
            fobj = sftp.file(path, mode)
        except PermissionError as err:
            msg = Error(err).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(err).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
        except Exception as err:
            msg = Error(err).indent(2)
            raise Error(f"{errmsg}\n{msg}") from err

        # Save the path and the mode in the object.
        fobj._orig_fpath_ = path
        fobj._orig_fmode_ = mode

        fobj._orig_fread_ = fobj.read
        fobj._orig_fwrite_ = fobj.write

        fobj.read = types.MethodType(_read_, fobj)
        fobj.write = types.MethodType(_write_, fobj)

        # Make sure methods of 'fobj' always raise the 'Error' exception.
        return ClassHelpers.WrapExceptions(fobj, get_err_prefix=get_err_prefix)

    def time_time(self):
        """
        Return the time in seconds since the epoch as a floating point number (just as the standard
        python 'time.time()' function).
        """

        return float(self.run_verify("date +%s")[0].strip())

    def mkdir(self, dirpath, parents=False, exist_ok=False):
        """
        Create a directory. The a arguments are as follows.
          * dirpath - path to the directory to create.
          * parents - if 'True', the parent directories are created as well.
          * exist_ok - if the directory already exists, this method raises an exception if
                       'exist_ok' is 'True', and it returns without an error if 'exist_ok' is
                       'False'.
        """

        if self.shell_test(dirpath, "-e"):
            if exist_ok:
                return
            raise ErrorExists(f"path '{dirpath}' already exists{self.hostmsg}")

        cmd = "mkdir"
        if parents:
            cmd += " -p"
        cmd += f" -- '{dirpath}'"
        self.run_verify(cmd)

    def lsdir(self, path, must_exist=True):
        """
        For each directory entry in 'path', yield the ('name', 'path', 'mode') tuple, where 'name'
        is the direntry name, 'path' is full directory entry path, and 'mode' is the
        'os.lstat().st_mode' value for the directory entry.

        The directory entries are yielded in ctime (creation time) order.

        If 'path' does not exist, this function raises an exception. However, this behavior can be
        changed with the 'must_exist' argument. If 'must_exist' is 'False, this function just
        returns and does not yield anything.
        """

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

        entries = {}
        for line in stdout.splitlines():
            entry = Trivial.split_csv_line(line.strip(), sep=" ")
            if len(entry) != 3:
                raise Error(f"BUG: failed to list directory '{path}': received the following "
                            f"unexpected line:\n{line}\nExpected line format: 'entry mode ctime'")
            entries[entry[0]] = {"name": entry[0], "ctime": float(entry[2]), "mode": int(entry[1])}

        for einfo in sorted(entries.values(), key=itemgetter("ctime"), reverse=True):
            yield (einfo["name"], path / einfo["name"], einfo["mode"])

    def exists(self, path):
        """Returns 'True' if path 'path' exists."""
        return self.shell_test(path, "-e")

    def is_file(self, path):
        """Returns 'True' if path 'path' exists an it is a regular file."""
        return self.shell_test(path, "-f")

    def is_dir(self, path):
        """Returns 'True' if path 'path' exists an it is a directory."""
        return self.shell_test(path, "-d")

    def is_exe(self, path):
        """Returns 'True' if path 'path' exists an it is an executable file."""
        return self.shell_test(path, "-x")

    def is_socket(self, path):
        """Returns 'True' if path 'path' exists an it is a Unix socket file."""
        return self.shell_test(path, "-S")

    def get_mtime(self, path):
        """Returns the modification time of a file or directory at path 'path'."""

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'import os; print(os.stat(\"{path}\").st_mtime)'"
        try:
            stdout, _ = self.run_verify(cmd)
        except Error as err:
            if "FileNotFoundError" in str(err):
                raise ErrorNotFound(f"'{path}' does not exist{self.hostmsg}") from None
            raise

        mtime = stdout.strip()
        if not Trivial.is_float(mtime):
            raise Error(f"got erroneous modification time of '{path}'{self.hostmsg}:\n{mtime}")
        return float(mtime)

    def rmtree(self, path):
        """
        Recursively remove a file or directory at path 'path'. If 'path' is a symlink, the link is
        removed, but the target of the link does not get removed.
        """

        self.run_verify(f"rm -rf -- '{path}'")

    def abspath(self, path, must_exist=True):
        """
        Returns absolute real path for 'path'. The arguments are as follows.
          * path - the path to resolve into the absolute real (no symlinks) path.
          * must_exist - if 'path' does not exist, raise and exception when 'must_exist' is 'True',
                         otherwise returns the 'path' value.
        """

        python_path = self.get_python_path()
        cmd = f"{python_path} -c 'from pathlib import Path; print(Path(\"{path}\").resolve())'"
        stdout, _ = self.run_verify(cmd)

        rpath = stdout.strip()

        if must_exist and not self.exists(rpath):
            raise ErrorNotFound(f"path '{rpath}' does not exist")

        return Path(rpath)

    def mkdtemp(self, prefix=None, basedir=None):
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

    def get_homedir(self):
        """Return return the home directory path for the logged in user."""

        try:
            return Path(self.run_verify("echo $HOME")[0].strip())
        except ErrorNotFound:
            # See commentaries in 'shell_test()', this is a similar case.
            return Path(self.run_verify("sh -c -l \"echo $HOME\"")[0].strip())

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
            else:
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

            config = paramiko.SSHConfig()
            for cfgfile in cfgfiles:
                with open(cfgfile, "r", encoding="utf-8") as fobj:
                    config.parse(fobj)

            cfg = config.lookup(hostname)
            if optname in cfg:
                return cfg[optname]
            if "include" in cfg:
                cfgfiles = glob.glob(cfg['include'])
                return self._cfg_lookup(optname, hostname, username, cfgfiles=cfgfiles)
            return None
        finally:
            os.environ["USER"] = old_username

    def _lookup_privkey(self, hostname, username, cfgfiles=None):
        """Lookup for private SSH authentication keys for host 'hostname'."""

        privkeypath = self._cfg_lookup("identityfile", hostname, username, cfgfiles=cfgfiles)
        if isinstance(privkeypath, list):
            privkeypath = privkeypath[0]
        return privkeypath

    def __init__(self, hostname=None, ipaddr=None, port=None, username=None, password="",
                 privkeypath=None, timeout=None):
        """
        Initialize a class instance and establish SSH connection to host 'hostname'. The arguments
        are as follows.
          o hostname - name of the host to connect to.
          o ipaddr - optional IP address of the host to connect to. If specified, then it is used
            instead of hostname, otherwise hostname is used.
          o port - optional port number to connect to, default is 22.
          o username - optional user name to use when connecting.
          o password - optional password to authenticate the 'username' user (not secure!).
          o privkeypath - optional public key path to use for authentication.
          o timeout - optional SSH connection timeout value in seconds.

        The 'hostname' argument being 'None' is a special case - this module falls-back to using the
        'LocalProcessManager' module and runs all all operations locally without actually involving
        SSH or networking. This is different to using 'localhost', which does involve SSH.

        SECURITY NOTICE: this class and any part of it should only be used for debugging and
        development purposes. No security audit had been done. Not for production use.
        """

        super().__init__()

        self.ssh = None
        self.is_remote = True
        self.hostname = hostname
        self.hostmsg = f" on host '{hostname}'"
        if not timeout:
            timeout = 60
        self.connection_timeout = float(timeout)
        if port is None:
            port = 22
        self.port = port
        look_for_keys = False
        self.username = username
        self.password = password
        self.privkeypath = privkeypath

        self._sftp = None
        # The interactive shell session.
        self._intsh = None
        # Whether we already run a process in the interactive shell.
        self._intsh_busy = False
        # A lock protecting 'self._intsh_busy' and 'self._intsh'. Basically this lock makes sure we
        # always run exactly one process in the interactive shell.
        self._intsh_lock = threading.Lock()
        # The "verbose" host name. The 'self.hostname', but with more details, like the IP address.
        self._vhostname = None

        if not self.username:
            self.username = os.getenv("USER")
            if not self.username:
                self.username = Trivial.get_username()

        if ipaddr:
            connhost = ipaddr
            self._vhostname = f"{hostname} ({ipaddr})"
        else:
            connhost = self._cfg_lookup("hostname", hostname, self.username)
            if connhost:
                self._vhostname = f"{hostname} ({connhost})"
            else:
                self._vhostname = connhost = hostname

        if not self.privkeypath:
            # Try finding the key filename from the SSH configuration files.
            look_for_keys = True
            with contextlib.suppress(BaseException):
                self.privkeypath = Path(self._lookup_privkey(hostname, self.username))

        key_filename = str(self.privkeypath) if self.privkeypath else None

        if key_filename:
            # Private SSH key sanity checks.
            try:
                mode = os.stat(key_filename).st_mode
            except OSError:
                raise Error(f"'stat()' failed for private SSH key at '{key_filename}'") from None

            if not stat.S_ISREG(mode):
                raise Error(f"private SSH key at '{key_filename}' is not a regular file")

            if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                raise Error(f"private SSH key at '{key_filename}' permissions are too wide: make "
                            f" sure 'others' cannot read/write/execute it")

        _LOG.debug("establishing SSH connection to %s, port %d, username '%s', timeout '%s', "
                   "priv. key '%s', SSH pman object ID: %s", self._vhostname, port, self.username,
                   timeout, self.privkeypath, id(self))

        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # We expect to be authenticated either with the key or an empty password.
            self.ssh.connect(username=self.username, hostname=connhost, port=port,
                             key_filename=key_filename, timeout=self.connection_timeout,
                             password=self.password, allow_agent=False, look_for_keys=look_for_keys)
        except paramiko.AuthenticationException as err:
            msg = Error(err).indent(2)
            raise ErrorConnect(f"SSH authentication failed when connecting to {self._vhostname} as "
                               f"'{self.username}':\n{msg}") from err
        except BaseException as err:
            msg = Error(err).indent(2)
            raise ErrorConnect(f"cannot establish TCP connection to {self._vhostname} with "
                               f"{timeout} secs time-out:\n{msg}") from err

    def close(self):
        """Close the SSH connection."""

        _LOG.debug("closing SSH connection to %s (port %d, username '%s', priv. key '%s', SSH pman "
                   "object ID: %s", self._vhostname, self.port, self.username, self.privkeypath,
                   id(self))

        if getattr(self, "_intsh", None):
            with contextlib.suppress(BaseException):
                self._intsh.pobj.send("exit\n")

        ClassHelpers.close(self, close_attrs=("_sftp", "_intsh", "ssh",))

        super().close()
