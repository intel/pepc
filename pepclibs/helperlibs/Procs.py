# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains helper function to run and manage operating system processes (tasks).
"""

# pylint: disable=no-member
# pylint: disable=protected-access

import time
import shlex
import errno
import logging
import subprocess
from pepclibs.helperlibs import _Procs, WrapExceptions
from pepclibs.helperlibs._Procs import ProcResult # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error, ErrorTimeOut, ErrorPermissionDenied, ErrorNotFound

_LOG = logging.getLogger()

# This attribute helps making the API of this module similar to the API of the 'SSH' module.
hostname = "localhost"

# The exceptions to handle when dealing with file I/O.
_EXCEPTIONS = (OSError, IOError, BrokenPipeError)

def _have_enough_lines(output, lines=(None, None)):
    """Returns 'True' if there are enough lines in the output buffer."""

    for streamid in (0, 1):
        if lines[streamid] and len(output[streamid]) >= lines[streamid]:
            return True
    return False

def _get_err_prefix(fobj, method):
    """Return the error message prefix."""
    return "method '%s()' failed for %s" % (method, fobj.name)

class Task(_Procs.TaskBase):
    """
    This class represents a local task (process) that was executed by a 'Proc' object.
    """

    def _fetch_stream_data(self, streamid, size):
        """Fetch up to 'size' butes from tasks stdout or stderr."""

        retries = 0
        max_retries = 16

        while retries < max_retries:
            retries += 1

            try:
                return self._streams[streamid].read(4096)
            except Error as err:
                if err.errno == errno.EAGAIN:
                    continue
                raise

        raise Error(f"received 'EAGAIN' error {retries} times")

    def _wait_timeout(self, timeout):
        """Wait for task to finish with a timeout."""

        tobj = self.tobj
        self._dbg("_wait_timeout: waiting for exit status, timeout %s sec", timeout)
        try:
            exitcode = tobj.wait(timeout=timeout)
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

        if not self.tobj.stdout and not self.tobj.stderr:
            self.exitcode = self._wait_timeout(timeout)
            return [[], []]

        start_time = time.time()

        self._dbg("_wait: starting with partial: %s, output:\n%s", self._partial, str(self._output))

        while not _have_enough_lines(self._output, lines=lines):
            if self.exitcode is not None:
                self._dbg("_wait: process exited with status %d", self.exitcode)
                break

            streamid, data = self._get_next_queue_item(timeout)
            if streamid == -1:
                self._dbg("_wait: nothing in the queue for %d seconds", timeout)
                break
            if data is not None:
                self._process_queue_item(streamid, data, capture_output=capture_output,
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
                self._dbg("_wait: stop waiting for the command - timeout")
                break

        return self._get_lines_to_return(lines)

    def _cmd_failed_msg(self, stdout, stderr, exitcode, startmsg=None, timeout=None):
        """
        A wrapper over '_Procs.cmd_failed_msg()'. The optional 'timeout' argument specifies the
        timeout that was used for the command.
        """

        if timeout is None:
            timeout = self.timeout

        cmd = self.cmd
        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if self.cmd != self.real_cmd:
                cmd += f"\nReal command: {self.real_cmd}"

        return _Procs.cmd_failed_msg(cmd, stdout, stderr, exitcode, hostname=self.hostname,
                                     startmsg=startmsg, timeout=timeout)

    def poll(self):
        """Check if the task is still running. If it is, return 'None', else return exit status."""
        return self.tobj.poll()

class Proc(_Procs.ProcBase):
    """This class provides API similar to the 'SSH' class API."""

    def _do_run_async(self, command, stdin=None, stdout=None, stderr=None, bufsize=0, cwd=None,
                      env=None, shell=False, newgrp=False):
        """Implements 'run_async()'."""

        # pylint: disable=consider-using-with
        try:
            if stdin and isinstance(stdin, str):
                fname = stdin
                stdin = open(fname, "r")

            if stdout and isinstance(stdout, str):
                fname = stdout
                stdout = open(fname, "w+")

            if stderr and isinstance(stderr, str):
                fname = stderr
                stderr = open(fname, "w+")
        except OSError as err:
            raise Error("cannot open file '%s': %s" % (fname, err)) from None

        if not stdin:
            stdin = subprocess.PIPE
        if not stdout:
            stdout = subprocess.PIPE
        if not stderr:
            stderr = subprocess.PIPE

        if shell:
            real_cmd = cmd = self._format_cmd_for_pid(command, cwd=cwd)
        elif isinstance(command, str):
            real_cmd = command
            cmd = shlex.split(command)
        else:
            cmd = command
            real_cmd = command = " ".join(command)

        try:
            tobj = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr, bufsize=bufsize,
                                    cwd=cwd, env=env, shell=shell, start_new_session=newgrp)
        except OSError as err:
            raise self._cmd_start_failure(cmd, err) from err

        # Wrap the standard I/O file objects to ensure they raise only the 'Error' exception.
        for name in ("stdin", "stdout", "stderr"):
            if getattr(tobj, name):
                wrapped_fobj = WrapExceptions.WrapExceptions(getattr(tobj, name),
                                                             exceptions=_EXCEPTIONS,
                                                             get_err_prefix=_get_err_prefix)
                setattr(tobj, name, wrapped_fobj)

        return Task(self, tobj, command, real_cmd, shell, (tobj.stdout, tobj.stderr))

    def run_async(self, command, stdin=None, stdout=None, stderr=None, bufsize=0, cwd=None,
                  env=None, shell=False, newgrp=False, intsh=False): # pylint: disable=unused-argument
        """
        A helper function to run an external command asynchronously. The 'command' argument should
        be a string containing the command to run. The 'stdin', 'stdout', and 'stderr' parameters
        can be one of:
            * an open file descriptor (a positive integer)
            * a file object
            * file path (in case of stdout and stderr the file will be created if it does not exist)

        The 'bufsize', 'cwd','env' and 'shell' arguments are the same as in 'Popen()'.

        If the 'newgrp' argument is 'True', then new process gets new session ID.

        The 'intsh' argument is not used. It is present only for API compatibility between 'Procs'
        and 'SSH'.

        Returns the 'Popen' object of the executed process.
        """

        if cwd:
            cwd_msg = "\nWorking directory: %s" % cwd
        else:
            cwd_msg = ""
        _LOG.debug("running the following local command asynchronously (shell %s, newgrp %s):\n"
                   "%s%s", str(shell), str(newgrp), command, cwd_msg)

        return self._do_run_async(command, stdin=stdin, stdout=stdout, stderr=stderr,
                                  bufsize=bufsize, cwd=cwd, env=env, shell=shell, newgrp=newgrp)

    def run(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
            output_fobjs=(None, None), bufsize=0, cwd=None, env=None, shell=False, newgrp=False,
            intsh=True): # pylint: disable=unused-argument
        """
        Run command 'command' on the remote host and block until it finishes. The 'command' argument
        should be a string.

        The 'timeout' parameter specifies the longest time for this method to block. If the command
        takes longer, this function will raise the 'ErrorTimeOut' exception. The default is 1h.

        If the 'capture_output' argument is 'True', this function intercept the output of the
        executed program, otherwise it doesn't and the output is dropped (default) or printed to
        'output_fobjs'.

        If the 'mix_output' argument is 'True', the standard output and error streams will be mixed
        together.

        The 'join' argument controls whether the captured output is returned as a single string or a
        list of lines (trailing newline is not stripped).

        The 'bufsize', 'cwd','env' and 'shell' arguments are the same as in 'Popen()'.

        If the 'newgrp' argument is 'True', then new process gets new session ID.

        The 'output_fobjs' is a tuple which may provide 2 file-like objects where the standard
        output and error streams of the executed program should be echoed to. If 'mix_output' is
        'True', the 'output_fobjs[1]' file-like object, which corresponds to the standard error
        stream, will be ignored and all the output will be echoed to 'output_fobjs[0]'. By default
        the command output is not echoed anywhere.

        Note, 'capture_output' and 'output_fobjs' arguments can be used at the same time. It is OK
        to echo the output to some files and capture it at the same time.

        This function returns an named tuple of (stdout, stderr, exitcode), where
          o 'stdout' is the output of the executed command to stdout
          o 'stderr' is the output of the executed command to stderr
          o 'exitcode' is the integer exit code of the executed command

        If the 'mix_output' argument is 'True', the 'stderr' part of the returned tuple will be an
        empty string.

        If the 'capture_output' argument is not 'True', the 'stdout' and 'stderr' parts of the
        returned tuple will be an empty string.

        The 'intsh' argument is not used. It is present only for API compatibility between 'Procs'
        and 'SSH'.
        """

        if cwd:
            cwd_msg = "\nWorking directory: %s" % cwd
        else:
            cwd_msg = ""
        _LOG.debug("running the following local command (shell %s, newgrp %s):\n%s%s",
                   str(shell), str(newgrp), command, cwd_msg)

        stdout = subprocess.PIPE
        if mix_output:
            stderr = subprocess.STDOUT
        else:
            stderr = subprocess.PIPE

        task = self._do_run_async(command, stdout=stdout, stderr=stderr, bufsize=bufsize, cwd=cwd,
                                  env=env, shell=shell, newgrp=newgrp)

        # Wait for the command to finish and handle the time-out situation.
        result = task.wait(capture_output=capture_output, output_fobjs=output_fobjs,
                           timeout=timeout, join=join)

        if result.exitcode is None:
            msg = _Procs.cmd_failed_msg(command, *tuple(result), timeout=timeout)
            raise ErrorTimeOut(msg)

        if output_fobjs[0]:
            output_fobjs[0].flush()
        if output_fobjs[1]:
            output_fobjs[1].flush()

        return result

    def run_verify(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
                   output_fobjs=(None, None), bufsize=0, cwd=None, env=None, shell=False,
                   newgrp=False, intsh=True):
        """
        Same as 'run()' but verifies the command's exit code and raises an exception if it is not 0.
        """

        result = self.run(command, timeout=timeout, capture_output=capture_output,
                          mix_output=mix_output, join=join, output_fobjs=output_fobjs,
                          bufsize=bufsize, cwd=cwd, env=env, shell=shell, newgrp=newgrp,
                          intsh=intsh)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        raise Error(_Procs.cmd_failed_msg(command, *tuple(result), timeout=timeout))

    def rsync(self, src, dst, opts="rlpD", remotesrc=False, remotedst=True):
        # pylint: disable=unused-argument
        """
        Copy data from path 'src' to path 'dst' using 'rsync' with options specified in 'opts'. The
        'remotesrc' and 'remotedst' arguments are ignored. They only exist for compatibility with
        'SSH.rsync()'. The default options are:
          * r - recursive
          * l - copy symlinks as symlinks
          * p - preserve permission
          * s - preseve device nodes and others special files
        """

        cmd = "rsync -%s -- '%s' '%s'" % (opts, src, dst)
        try:
            self.run_verify(cmd)
        except Error as err:
            raise Error("failed to copy files '%s' to '%s':\n%s" % (src, dst, err)) from err

    def cmd_failed_msg(self, command, stdout, stderr, exitcode, startmsg=None, timeout=None):
        """A simple wrapper around '_Procs.cmd_failed_msg()'."""

        return _Procs.cmd_failed_msg(command, stdout, stderr, exitcode, hostname=self.hostname,
                                     startmsg=startmsg, timeout=timeout)

    @staticmethod
    def open(path, mode):
        """
        Open a file at 'path' using mode 'mode' (the arguments are the same as in the builtin Python
        'open()' function).
        """

        errmsg = f"cannot open file '{path}' with mode '{mode}': "
        try:
            fobj = open(path, mode) # pylint: disable=consider-using-with
        except PermissionError as err:
            raise ErrorPermissionDenied(f"{errmsg}{err}") from None
        except FileNotFoundError as err:
            raise ErrorNotFound(f"{errmsg}{err}") from None
        except OSError as err:
            raise Error(f"{errmsg}{err}") from None

        # Make sure methods of 'fobj' always raise the 'Error' exceptions.
        return WrapExceptions.WrapExceptions(fobj, exceptions=_EXCEPTIONS,
                                             get_err_prefix=_get_err_prefix)

    def __init__(self):
        """Initialize a class instance."""

        super().__init__()

        self.is_remote = False
        self.hostname = "localhost"
        self.hostmsg = ""
