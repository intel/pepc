# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains common bits and pieces shared between the 'Procs' and 'SSH' modules.
"""

# pylint: disable=protected-access

import re
import queue
import codecs
import logging
import threading
import contextlib
from collections import namedtuple
from pepclibs.helperlibs import Human, Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

# The default command timeout in seconds
TIMEOUT = 4 * 60 * 60

# Results of a the process execution.
ProcResult = namedtuple("proc_result", ["stdout", "stderr", "exitcode"])

def extract_full_lines(text, join=False):
    """
    Extract full lines from string 'text'. Return a tuple containing 2 elements - the full lines and
    the last partial line. If 'join' is 'False', the full lines are returned as a list of lines,
    otherwise they are returned as a single string.
    """

    full, partial = [], ""
    for line_match in re.finditer("(.*\n)|(.+$)", text):
        if line_match.group(2):
            partial = line_match.group(2)
            break
        full.append(line_match.group(1))

    if join:
        full = "".join(full)
    return (full, partial)

class TaskBase:
    """
    The base class for local and remote tasks (processes).
    """

    @staticmethod
    def _bug_method_not_defined(method_name):
        """
        Raise an error if the child class did not define the 'method_name' mandatory method.
        """

        raise Error(f"BUG: '{method_name}()' was not defined by the child class")

    def _fetch_stream_data(self, streamid, size): # pylint: disable=unused-argument
        """
        Fetch up to 'size' bytes of data from stream 'streamid'. Returns 'None' if there are no
        data.
        """

        return self._bug_method_not_defined("_fetch_stream_data")

    def _stream_fetcher(self, streamid):
        """
        This method runs in a separate thread. All it does is it fetches one of the output streams
        of the executed program (either stdout or stderr) and puts the result into the queue.
        """

        try:
            decoder = codecs.getincrementaldecoder('utf8')(errors="surrogateescape")
            while not self._threads_exit:
                if not self._streams[streamid]:
                    self._dbg("stream %d: stream is closed", streamid)
                    break

                data = None
                try:
                    data = self._fetch_stream_data(streamid, 4096)
                except Error as err:
                    self._dbg("stream %d: %s", streamid, err)
                    continue

                if not data:
                    self._dbg("stream %d: no more data", streamid)
                    break

                data = decoder.decode(data)
                if not data:
                    self._dbg("stream %d: read more data", streamid)
                    continue

                self._dbg("stream %d: read data:\n%s", streamid, data)
                self._queue.put((streamid, data))
        except Exception as err: # pylint: disable=broad-except
            _LOG.error(err)

        # The end of stream indicator.
        self._queue.put((streamid, None))
        self._dbg("stream %d: thread exists", streamid)

    def _get_next_queue_item(self, timeout):
        """
        Read the next data item from the stream fetcher queue. The items in the queue have the
        following format: '(streamid, data)'.
           * streamid - 0 for stdout, 1 for stderr.
           * data - stream data (can be a partial line).

        Returns '(-1, None)' in case of time out.
        """

        try:
            if timeout:
                return self._queue.get(timeout=timeout)
            return self._queue.get(block=False)
        except queue.Empty:
            return (-1, None)

    def _process_queue_item(self, streamid, data, capture_output=True, output_fobjs=(None, None)):
        """
        Process the '(streamic, data)' item returned by '_get_next_queue_item()'. The keyword
        arguments are the same as in 'wait()'.
        """

        self._dbg("_process_queue_item: got data from stream %d:\n%s", streamid, data)

        data, self._partial[streamid] = extract_full_lines(self._partial[streamid] + data)
        if data and self._partial[streamid]:
            self._dbg("_process_queue_item: stream %d: full lines:\n%s\npartial line: %s",
                      streamid, "".join(data), self._partial[streamid])

        for line in data:
            if not line:
                continue
            if capture_output:
                self._output[streamid].append(line)
            if output_fobjs[streamid]:
                output_fobjs[streamid].write(line)

    def _get_lines_to_return(self, lines):
        """
        Figure out what part of captured task output should be returned to the user, and what part
        should stay in 'task._output'. This depends on the 'lines' argument. The keyword arguments
        are the same as in 'wait()'.
        """

        # pylint: disable=protected-access
        self._dbg("_get_lines_to_return: start: lines:\n%s\npartial lines:\n%s\noutput:\n%s",
                  str(lines), self._partial, self._output)

        output = [[], []]

        for streamid in (0, 1):
            limit = lines[streamid]
            if limit is None or len(self._output[streamid]) <= limit:
                output[streamid] = self._output[streamid]
                self._output[streamid] = []
            else:
                output[streamid] = self._output[streamid][:limit]
                self._output[streamid] = self._output[streamid][limit:]

        self._dbg("_get_lines_to_return: end: partial lines:\n%s\noutput:\n%s\nreturning:\n%s",
                  self._partial, self._output, output)
        return output

    def _task_is_done(self):
        """
        Returns 'True' if all output lines of the task have been returned to the user and the task
        has finished. Returns 'False' otherwise.
        """

        # pylint: disable=protected-access
        return self.exitcode is not None and \
               not self._output[0] and \
               not self._output[1] and \
               self._queue.empty()

    def _wait(self, timeout=None, capture_output=True, output_fobjs=(None, None),
              lines=(None, None)):
        """
        Implements 'wait()'. The arguments are the same as in 'wait()', but returns a tuple of two
        lists: '(stdout_lines, stderr_lines)' (lists of stdout/stderr lines).
        """

        # pylint: disable=unused-argument
        return self._bug_method_not_defined("_wait")

    def wait(self, timeout=None, capture_output=True, output_fobjs=(None, None), lines=(None, None),
             join=True):
        """
        This method waits for the task to finish or print something to stdout or stderr. The
        arguments are as follows.
          * timeout - the maximum time in seconds to wait for the task to finish. If it does not
                      finish, this function exits and returns 'None' as the exit code. The 'timeout'
                      argument must be a positive floating point number. By default it is 1 hour. If
                      'timeout' is '0', then this method will just check task status, grab its
                      output, if any, and return immediately. Note, this method saves the used
                      timeout in 'self.timeout'.
          * capture_output - whether the output of the task should be captured. If it is 'False',
                             the output will simply be discarded and this method will return empty
                             strings instead of command's stdout and stderr.
          * output_fobjs - a tuple with two file-like objects where stdout and stderr output of the
                             task will be echoed. If not specified, then the the command output will
                             not be echoed anywhere. Note, this argument is independent on the
                             'capture_output' argument.
          * lines - provides a capability to wait for the command to output certain amount of lines.
                    By default, there is no limit, and this function will wait either for timeout or
                    until the command exits. The 'line' argument is a tuple, the first element of
                    the tuple is the 'stdout' limit, the second is the 'stderr' limit. For example,
                    'lines=(1, 5)' would mean to wait for one full line in 'stdout' or five full
                    lines in 'stderr'. And 'lines=(1, None)' would mean to wait for one line in
                    'stdout' and any amount of lines in 'stderr'.
          * join - controls whether the captured output lines should be joined and returned as a
                   single string, or no joining is needed and the output should be returned as a
                   list of strings.

        This function returns the 'ProcResult' named tuple.
        """

        if timeout is None:
            timeout = TIMEOUT
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

        self.timeout = timeout

        self._dbg("wait: timeout %s, capture_output %s, lines: %s, join: %s, command: %s\n"
                  "real command: %s", timeout, capture_output, str(lines), join, self.cmd,
                  self.real_cmd)

        if self._threads_exit:
            raise Error("this process has 'threads_exit' flag set and it cannot be used")

        if self._task_is_done():
            return ProcResult(stdout="", stderr="", exitcode=self.exitcode)

        if not self._queue:
            self._queue = queue.Queue()
            for streamid in (0, 1):
                if self._streams[streamid]:
                    assert self._threads[streamid] is None
                    self._threads[streamid] = threading.Thread(target=self._stream_fetcher,
                                                               name='stream-fetcher',
                                                               args=(streamid,), daemon=True)
                    self._threads[streamid].start()
        else:
            self._dbg("wait: queue is empty: %s", self._queue.empty())

        output = self._wait(timeout=timeout, capture_output=capture_output,
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

        if self._task_is_done():
            exitcode = self.exitcode
        else:
            exitcode = None

        if self.debug:
            sout = "".join(output[0])
            serr = "".join(output[1])
            self._dbg("wait: returning, exitcode %s, stdout:\n%s\nstderr:\n%s",
                      exitcode, sout.rstrip(), serr.rstrip())

        return ProcResult(stdout=stdout, stderr=stderr, exitcode=exitcode)

    def _dbg(self, fmt, *args):
        """Print a debugging message."""

        if self.debug:
            pfx = ""
            if self.debug_id:
                pfx += f"{self.debug_id}: "
            if self.pid is not None:
                pfx += f"PID {self.pid}: "
            _LOG.debug(pfx + fmt, *args)

    def poll(self):
        """Check if the task is still running. If it is, return 'None', else return exit status."""

        # pylint: disable=no-self-use
        return self._bug_method_not_defined("poll")

    def _reinit(self, cmd, real_cmd, shell):
        """
        Re-initialize the task object in case its process is re-used for running a different
        command.
        """

        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell

        self.pid = None
        self.exitcode = None

        self._threads_exit = False
        self._output = [[], []]
        self._partial = ["", ""]

    def __init__(self, proc, tobj, cmd, real_cmd, shell, streams):
        """
        Initialize a class instance. The arguments are as follows.
          * proc - the process management object that was used for creating this task (e.g.,
                   'Procs.Proc()' or 'SSH.SSH()'.
          * tobj - the low-level object representing the local or remote process corresponding to
                   this task object. E.g., this is a 'Popen()' object in case of a local process.
          * cmd - the executed command.
          * real_cmd - sometimes the original command gets slightly amended, e.g., it is sometimes
                       prefixed with a PID print command. This argument should provide the actual
                       executed command.
          * shell - whether the command was executed via shell.
          * streams - the stderr and stdout stream objects of the task. These are not necessarily
                      file-like objects, just some objects representing the streams (defined by
                      sub-classes).
          * pid - process ID of the running task, if it is known.
        """

        self.proc = proc
        self.tobj = tobj
        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell
        self._streams = list(streams)

        self.timeout = TIMEOUT
        self.hostname = proc.hostname
        self.hostmsg = proc.hostmsg

        # Process ID of the running task. Should be set by the child class. In some cases may be set
        # to 'None', which should be interpreted as "not known".
        self.pid = None
        # Exit code of the command ('None' if it is still running).
        self.exitcode = None

        # Print debugging messages if 'True'.
        self.debug = False
        # Prefix debugging messages with this string. Can be useful to distinguish between debugging
        # message related to different tasks.
        self.debug_id = None

        # The stream fetcher threads have to exit if the '_threads_exit' flag becomes 'True'.
        self._threads_exit = False
        # The output for the task that was read from 'self._queue', but not yet sent to the user
        # (separate for 'stdout' and 'stderr').
        self._output = [[], []]
        # The last partial lines of the stdout and stderr streams of the task.
        self._partial = ["", ""]
        # The threads fetching data from the stdout/stderr streams of the task.
        self._threads = [None, None]
        # The queue for passing task output from stream fetcher threads.
        self._queue = None

    def close(self):
        """Free allocated resources."""

        self._dbg("close()")

        if hasattr(self, "_threads_exit"):
            self._threads_exit = True

        tobj = getattr(self, "tobj", None)
        if tobj:
            if hasattr(tobj, "close"):
                tobj.close()
            self.tobj = None

        if hasattr(self, "proc"):
            self.proc = None

    def __del__(self):
        """Class destructor."""

        with contextlib.suppress(Exception):
            self._dbg("__del__()")

        with contextlib.suppress(Exception):
            self.close()

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()

class ProcessManagerBase:
    """
    The base class for process local or remote process managers.
    """

    Error = Error

    def _cmd_start_failure(self, cmd, err, intsh=False):
        """
        Form and return the exception object for a situation when command 'cmd' has failed to start.
        """

        if self.is_remote:
            if intsh:
                session = " in an interactive shell over SSH"
            else:
                session = " in a new SSH session"
        else:
            session = ""

        return Error(f"cannot execute the following command{session}{self.hostmsg}:\n"
                     f"{cmd}\nReason: {err}")

    def __init__(self):
        """Initialize a class instance."""

        self.is_remote = None
        self.hostname = None
        self.hostmsg = None

    def close(self):
        """Free allocated resources."""

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()

def cmd_failed_msg(command, stdout, stderr, exitcode, hostname=None, startmsg=None, timeout=None):
    """
    This helper function formats an error message for a failed command 'command'. The 'stdout' and
    'stderr' arguments are what the command printed to the standard output and error streams, and
    'exitcode' is the exit status of the failed command. The 'hostname' parameter is ignored and it
    is here only for the sake of keeping the 'Procs' API look similar to the 'SSH' API. The
    'startmsg' parameter can be used to specify the start of the error message. The 'timeout'
    argument specifies the command timeout.
    """

    if not isinstance(command, str):
        # Sometimes commands are represented by a list of command components - join it.
        command = " ".join(command)

    if timeout is None:
        timeout = TIMEOUT
    elif timeout == -1:
        timeout = None

    if exitcode is not None:
        exitcode_msg = "failed with exit code %s" % exitcode
    elif timeout is not None:
        exitcode_msg = "did not finish within %s seconds (%s)" \
                       % (timeout, Human.duration(timeout))
    else:
        exitcode_msg = "failed, but no exit code is available, this is a bug!"

    msg = ""
    for stream in (stdout, stderr):
        if not stream:
            continue
        if isinstance(stream, list):
            stream = "".join(stream)
        msg += "%s\n" % stream.strip()

    if not startmsg:
        if hostname:
            startmsg = "ran the following command on host '%s', but it %s" \
                        % (hostname, exitcode_msg)
        else:
            startmsg = "the following command %s:" % exitcode_msg

    result = "%s\n%s" % (startmsg, command)
    if msg:
        result += "\n\n%s" % msg.strip()
    return result
