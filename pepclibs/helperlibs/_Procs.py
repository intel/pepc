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
import logging
import contextlib
from collections import namedtuple
from pepclibs.helperlibs import Human, Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

# The default command timeout in seconds
TIMEOUT = 4 * 60 * 60

# Results of a the process execution.
ProcResult = namedtuple("proc_result", ["stdout", "stderr", "exitcode"])

class TaskBase:
    """
    The base class for local and remote tasks (processes).
    """

    def wait_for_cmd(self, timeout=None, capture_output=True, output_fobjs=(None, None),
                     lines=(None, None), join=True):
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

        # pylint: disable=no-self-use
        raise Error("'wait_for_cmd()' was not defined by the child class")

    def read_pid(self):
        """Read 'PID' for the just executed command and store it in 'self.pid'."""

        self._dbg("read_pid: reading PID for command: %s", self.cmd)
        assert self.shell

        stdout, stderr, _ = self.wait_for_cmd(timeout=10, lines=(1, 0), join=False)

        msg = f"\nThe command{self.hostmsg} was:\n{self.cmd}" \
              f"\nThe actual (real) command was:\n{self.real_cmd}"

        if len(stdout) != 1:
            raise Error(f"expected only one line with PID in stdout, got {len(stdout)} lines "
                        "instead.{msg}")
        if stderr:
            raise Error(f"expected only one line with PID in stdout and no lines in stderr, got "
                        f"{len(stderr)} lines in stderr instead.{msg}")

        pid = stdout[0].strip()

        if len(pid) > 128:
            raise Error(f"received too long and probably bogus PID: {pid}{msg}")
        if not Trivial.is_int(pid):
            raise Error(f"received a bogus non-integer PID: {pid}{msg}")

        self._dbg("read_pid: PID is %s for command: %s", pid, self.cmd)
        self.pid = int(pid)

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
        raise Error("'poll()' was not defined by the child class")

    def __init__(self, proc, tobj, cmd, real_cmd, shell):
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
        """

        self.proc = proc
        self.tobj = tobj
        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell

        self.hostname = proc.hostname
        self.hostmsg = proc.hostmsg

        # Process ID of the running task. In some cases may be set to 'None', which should be
        # interpreted as "not known".
        self.pid = None
        # Exit code of the command ('None' if it is still running).
        self.exitcode = None

        # The stream fetcher threads have to exit if the 'threads_exit' flag becomes 'True'.
        self.threads_exit = False
        # Print debugging messages if 'True'.
        self.debug = False
        # Prefix debugging messages with this string. Can be useful to distinguish between debugging
        # message related to different tasks.
        self.debug_id = None

        if self.shell:
            self.read_pid()

    def close(self):
        """Free allocated resources."""

        self._dbg("close()")

        if hasattr(self, "threads_exit"):
            self.threads_exit = True

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

class ProcBase:
    """
    The base class for local or remote process management classes.
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

def format_command_for_pid(command, cwd=None):
    """
    When we run a command via the shell, we do not know it's PID. This function modifies the
    original user 'command' command so that it prints the PID as the first line of its output to the
    'stdout' stream. This requires a shell.
    """

    # Prepend the command with a shell statement which prints the PID of the shell where the
    # command will be run. Then use 'exec' to make sure that the command inherits the PID.
    prefix = r'printf "%s\n" "$$";'
    if cwd:
        prefix += f""" cd "{cwd}" &&"""
    return prefix + " exec " + command

def get_next_queue_item(qobj, timeout):
    """
    This is a common function for 'Procs' and 'SSH'. It reads the next data item from the 'qobj'
    queue. Returns '(-1, None)' in case of time out.
    """

    try:
        if timeout:
            return qobj.get(timeout=timeout)
        return qobj.get(block=False)
    except queue.Empty:
        return (-1, None)

def capture_data(task, streamid, data, capture_output=True, output_fobjs=(None, None)):
    """
    A helper for 'Procs' and 'SSH' that captures data 'data' from the 'streamid' stream fetcher
    thread. The keyword arguments are the same as in 'Task()._wait_for_cmd()'.
    """

    if not data:
        return

    # pylint: disable=protected-access
    tobj = task.tobj
    pd = tobj._pd_
    task._dbg("capture_data: got data from stream %d:\n%s", streamid, data)

    data, pd.partial[streamid] = extract_full_lines(pd.partial[streamid] + data)
    if data and pd.partial[streamid]:
        task._dbg("capture_data: stream %d: full lines:\n%s",
                  streamid, "".join(data))
        task._dbg("capture_data: stream %d: pd.partial line: %s",
                  streamid, pd.partial[streamid])
    for line in data:
        if not line:
            continue

        if capture_output:
            pd.output[streamid].append(line)
        if output_fobjs[streamid]:
            output_fobjs[streamid].write(line)

def get_lines_to_return(task, lines=(None, None)):
    """
    A helper for 'Procs' and 'SSH' that figures out what part of the captured command output should
    be returned to the user, and what part should stay in 'task._pd_.output', depending on the lines
    limit 'lines'. The keyword arguments are the same as in 'Task()._wait_for_cmd()'.
    """

    # pylint: disable=protected-access
    tobj = task.tobj
    pd = tobj._pd_
    task._dbg("get_lines_to_return: starting with lines %s, pd.partial: %s, pd.output:\n%s",
              str(lines), pd.partial, pd.output)

    output = [[], []]

    for streamid in (0, 1):
        limit = lines[streamid]
        if limit is None or len(pd.output[streamid]) <= limit:
            output[streamid] = pd.output[streamid]
            pd.output[streamid] = []
        else:
            output[streamid] = pd.output[streamid][:limit]
            pd.output[streamid] = pd.output[streamid][limit:]

    task._dbg("get_lines_to_return: starting with  pd.partial: %s, pd.output:\n%s\nreturning:\n%s",
              pd.partial, pd.output, output)
    return output

def all_output_consumed(task):
    """
    Returns 'True' if all the output of the process in 'task' was returned to the user and the
    process exited. Returns 'False' if there is some output still in the queue or "cached" in
    'task._pd_.output' or if the process did not exit yet.
    """

    # pylint: disable=protected-access
    pd = task.tobj._pd_
    return task.exitcode is not None and \
           not pd.output[0] and \
           not pd.output[1] and \
           not getattr(pd, "ll", None) and \
           pd.queue.empty()

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
