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
import queue
import errno
import codecs
import logging
import threading
import subprocess
from pepclibs.helperlibs import _Procs, WrapExceptions, Trivial
from pepclibs.helperlibs._Procs import ProcResult # pylint: disable=unused-import
from pepclibs.helperlibs.Exceptions import Error, ErrorTimeOut, ErrorPermissionDenied, ErrorNotFound

_LOG = logging.getLogger()

# This attribute helps making the API of this module similar to the API of the 'SSH' module.
hostname = "localhost"

# The exceptions to handle when dealing with file I/O.
_EXCEPTIONS = (OSError, IOError, BrokenPipeError)

def _stream_fetcher(streamid, task):
    """
    This function runs in a separate thread. All it does is it fetches one of the output streams
    of the executed program (either stdout or stderr) and puts the result into the queue.
    """

    tobj = task.tobj
    pd = tobj._pd_
    stream = pd.streams[streamid]
    try:
        decoder = codecs.getincrementaldecoder('utf8')(errors="surrogateescape")
        while not task.threads_exit:
            if not stream:
                task._dbg("stream %d: stream is closed", streamid)
                break

            data = None
            try:
                data = stream.read(4096)
            except Error as err:
                if err.errno == errno.EAGAIN:
                    continue
                raise

            if not data:
                task._dbg("stream %d: no more data", streamid)
                break

            data = decoder.decode(data)
            if not data:
                task._dbg("stream %d: read more data", streamid)
                continue

            task._dbg("stream %d: read data:\n%s", streamid, data)
            pd.queue.put((streamid, data))
    except BaseException as err: # pylint: disable=broad-except
        _LOG.error(err)

    pd.queue.put((streamid, None))
    task._dbg("stream %d: thread exists", streamid)

def _have_enough_lines(output, lines=(None, None)):
    """Returns 'True' if there are enough lines in the output buffer."""

    for streamid in (0, 1):
        if lines[streamid] and len(output[streamid]) >= lines[streamid]:
            return True
    return False

def _get_err_prefix(fobj, method):
    """Return the error message prefix."""
    return "method '%s()' failed for %s" % (method, fobj.name)

class _ProcessPrivateData:
    """
    We need to attach additional data to the Popen object. This class represents that data.
    """

    def __init__(self):
        """The constructor."""

        # The 2 output streams of the command's process (stdout, stderr).
        self.streams = []
        # The queue which is used for passing commands output from stream fetcher threads.
        self.queue = None
        # The threads fetching data from the output streams and placing them to the queue.
        self.threads = [None, None]
        # Exit code of the command ('None' if it is still running).
        self.exitcode = None
        # The output for the command that was read from 'queue', but not yet sent to the user
        # (separate for 'stdout' and 'stderr').
        self.output = [[], []]
        # This tuple contains the last partial lines of the # 'stdout' and 'stderr' output of the
        # command.
        self.partial = ["", ""]
        # Whether the command was executed via the shell.
        self.shell = None

        # Real command (user command and all the prefixes/suffixes).
        self.real_cmd = None

def _add_custom_fields(tobj, cmd, real_cmd, shell):
    """Add a couple of custom fields to the process object returned by 'subprocess.Popen()'."""

    for name in ("stdin", "stdout", "stderr"):
        if getattr(tobj, name):
            wrapped_fobj = WrapExceptions.WrapExceptions(getattr(tobj, name),
                                                         exceptions=_EXCEPTIONS,
                                                         get_err_prefix=_get_err_prefix)
            setattr(tobj, name, wrapped_fobj)

    pd = tobj._pd_ = _ProcessPrivateData()

    pd.real_cmd = real_cmd
    pd.shell = shell
    pd.streams = [tobj.stdout, tobj.stderr]

    # The below attributes are added to the Popen object look similar to the channel object which
    # the 'SSH' module uses.
    tobj.cmd = cmd
    tobj.timeout = _Procs.TIMEOUT
    return tobj

class Task(_Procs.TaskBase):
    """
    This class represents a local tobj (process) that was executed by a 'Proc' object.
    """

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

    def _do_wait_for_cmd(self, timeout=None, capture_output=True, output_fobjs=(None, None),
                         lines=(None, None)):
        """Implements '_wait_for_cmd()'."""

        tobj = self.tobj
        pd = tobj._pd_
        output = pd.output
        partial = pd.partial
        start_time = time.time()

        self._dbg("_do_wait_for_cmd: starting with partial: %s, output:\n%s", partial, str(output))

        while not _have_enough_lines(output, lines=lines):
            if pd.exitcode is not None:
                self._dbg("_do_wait_for_cmd: process exited with status %d", pd.exitcode)
                break

            streamid, data = _Procs.get_next_queue_item(pd.queue, timeout)
            if streamid == -1:
                self._dbg("_do_wait_for_cmd: nothing in the queue for %d seconds", timeout)
                break
            if data is not None:
                _Procs.capture_data(self, streamid, data, capture_output=capture_output,
                                    output_fobjs=output_fobjs)
            else:
                self._dbg("_do_wait_for_cmd: stream %d closed", streamid)
                # One of the output streams closed.
                pd.threads[streamid].join()
                pd.threads[streamid] = pd.streams[streamid] = None

                if not pd.streams[0] and not pd.streams[1]:
                    self._dbg("_do_wait_for_cmd: both streams closed")
                    pd.exitcode = self._wait_timeout(timeout)
                    break

            if not timeout:
                self._dbg(f"_do_wait_for_cmd: timeout is {timeout}, exit immediately")
                break
            if time.time() - start_time >= timeout:
                self._dbg("_do_wait_for_cmd: stop waiting for the command - timeout")
                break

        return _Procs.get_lines_to_return(self, lines=lines)

    def _wait_for_cmd(self, timeout=None, capture_output=True, output_fobjs=(None, None),
                      lines=(None, None), join=True):
        """
        This function waits for a command executed with the run_async()' function to finish or print
        something to stdout or stderr.

        The optional 'timeout' argument specifies the longest time in seconds this function will
        wait for the command to finish. If the command does not finish, this function exits and
        returns 'None' as the exit code of the command. The timeout must be a positive floating
        point number. By default it is 1 hour. If 'timeout' is '0', then this function will just
        check process status, grab its output, if any, and return immediately.

        Note, this function saves the used timeout in 'tobj.timeout' attribute upon exit.

        The 'capture_output' parameter controls whether the output of the command should be
        collected or not. If it is not 'True', the output will simply be discarded and this function
        will return empty strings instead of command's stdout and stderr.

        The 'output_fobjs' parameter is a tuple with two file-like objects where the stdout and
        stderr of the command will be echoed, in addition to being captured and returned. If not
        specified, then the the command output will not be echoed anywhere.

        The 'lines' argument provides a capability to wait for the command to output certain amount
        of lines. By default, there is no limit, and this function will wait either for timeout or
        until the command exits. The 'line' argument is a tuple, the first element of the tuple is
        the 'stdout' limit, the second is the 'stderr' limit. For example, 'lines=(1, 5)' would mean
        to wait for one full line in 'stdout' or five full lines in 'stderr'. And 'lines=(1, None)'
        would mean to wait for one line in 'stdout' and any amount of lines in 'stderr'.

        The 'join' argument controls whether the captured output lines should be joined and returned
        as a single string, or no joining is needed and the output should be returned as a list of
        strings.

        This function returns a named tuple similar to what the 'run()' function returns.
        """

        if timeout is None:
            timeout = _Procs.TIMEOUT
        if timeout < 0:
            raise Error(f"bad timeout value {timeout}, must be > 0")

        for streamid in (0, 1):
            if not lines[streamid]:
                continue
            if not Trivial.is_int(lines[streamid]):
                raise Error("the 'lines' argument can only include integers and 'None'")
            if lines[streamid] < 0:
                raise Error("the 'lines' argument cannot include negative values")

        if lines[0] == 0 and lines[1] == 0:
            raise Error("the 'lines' argument cannot be (0, 0)")

        tobj = self.tobj
        pd = tobj._pd_
        tobj.timeout = timeout

        self._dbg("_wait_for_cmd: timeout %s, capture_output %s, lines: %s, join: %s, command: %s\n"
                  "real command: %s", timeout, capture_output, str(lines), join, tobj.cmd,
                  pd.real_cmd)

        if self.threads_exit:
            raise Error("this process has 'threads_exit' flag set and it cannot be used")

        if _Procs.all_output_consumed(self):
            # This command has already exited.
            return ProcResult(stdout="", stderr="", exitcode=pd.exitcode)

        if not tobj.stdout and not tobj.stderr:
            pd.exitcode = self._wait_timeout(timeout)
            return ProcResult(stdout="", stderr="", exitcode=pd.exitcode)

        if not pd.queue:
            pd.queue = queue.Queue()
            for streamid in (0, 1):
                if pd.streams[streamid]:
                    assert pd.threads[streamid] is None
                    pd.threads[streamid] = threading.Thread(target=_stream_fetcher,
                                                            name='Procs-stream-fetcher',
                                                            args=(streamid, self), daemon=True)
                    pd.threads[streamid].start()
        else:
            self._dbg("_wait_for_cmd: queue is empty: %s", pd.queue.empty())

        output = self._do_wait_for_cmd(timeout=timeout, capture_output=capture_output,
                                       output_fobjs=output_fobjs, lines=lines)

        stdout = stderr = ""
        if output[0]:
            stdout = output[0]
            if join:
                stdout = "".join(stdout)
        if output[1]:
            stderr = output[1]
            if join:
                stderr = "".join(stderr)

        if _Procs.all_output_consumed(self):
            exitcode = pd.exitcode
        else:
            exitcode = None

        if self.debug:
            sout = "".join(output[0])
            serr = "".join(output[1])
            self._dbg("_wait_for_cmd: returning, exitcode %s, stdout:\n%s\nstderr:\n%s",
                      exitcode, sout.rstrip(), serr.rstrip())

        return ProcResult(stdout=stdout, stderr=stderr, exitcode=exitcode)

    def _cmd_failed_msg(self, stdout, stderr, exitcode, startmsg=None, timeout=None):
        """
        A wrapper over '_Procs.cmd_failed_msg()'. The optional 'timeout' argument specifies the
        timeout that was used for the command.
        """

        tobj = self.tobj
        if timeout is None:
            timeout = tobj.timeout

        cmd = tobj.cmd
        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if tobj.cmd != tobj._pd_.real_cmd:
                cmd = f"{cmd}\nReal command: {tobj._pd_.real_cmd}"

        return _Procs.cmd_failed_msg(cmd, stdout, stderr, exitcode, hostname=self.hostname,
                                     startmsg=startmsg, timeout=timeout)

    def _dbg(self, fmt, *args):
        """Print a debugging message related to process 'tobj'."""

        tobj = self.tobj
        if self.debug:
            pfx = ""
            if self.debug_id:
                pfx += f"{self.debug_id}: "
            if hasattr(tobj, "pid"):
                pfx += f"PID {tobj.pid}: "

            _LOG.debug(pfx + fmt, *args)

    def _close(self):
        """Task's 'close()' method that will signal the threads to exit."""

        self._dbg("_close()")
        super().close()

    def __del__(self):
        """Task object destructor which makes all threads to exit."""

        self._dbg("__del__()")
        super().__del__()

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
            if shell:
                real_cmd = cmd = _Procs.format_command_for_pid(command, cwd=cwd)
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

        _add_custom_fields(tobj, command, real_cmd, shell)
        task = Task(self, tobj)

        if shell:
            # The first line of the output should contain the PID - extract it.
            tobj.pid = _Procs.read_pid(task)

        return task

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
        result = task._wait_for_cmd(capture_output=capture_output, output_fobjs=output_fobjs,
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
