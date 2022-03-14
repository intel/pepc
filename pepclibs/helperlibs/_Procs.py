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

import re
import queue
import logging
import contextlib
from collections import namedtuple
from pepclibs.helperlibs import Human, ToolChecker
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

# The default command timeout in seconds
TIMEOUT = 4 * 60 * 60

# Results of a the process execution.
ProcResult = namedtuple("proc_result", ["stdout", "stderr", "exitcode"])

class ProcBase:
    """
    The base class for local or remote process management classes.
    """

    Error = Error

    def _get_tchk(self):
        """Returns an instance of the 'ToolChecker' class."""

        if not self._tchk:
            with contextlib.suppress(Error):
                self._tchk = ToolChecker.ToolChecker(proc=self)
        return self._tchk

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
        self._tchk = None

    def close(self):
        """Free allocated resources."""

        for attr in ("_tchk",):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()

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

def capture_data(task, streamid, data, capture_output=True, output_fobjs=(None, None),
                  by_line=True):
    """
    A helper for 'Procs' and 'SSH' that captures data 'data' from the 'streamid' stream fetcher
    thread. The keyword arguments are the same as in '_do_wait_for_cmd()'.
    """

    def _save_output(data, streamid):
        """Save a piece of 'pd.output' data 'data' from the 'streamid' stream fetcher."""

        if data:
            if capture_output:
                pd.output[streamid].append(data)
            if output_fobjs[streamid]:
                output_fobjs[streamid].write(data)

    if not data:
        return

    # pylint: disable=protected-access
    pd = task._pd_
    task._dbg_("capture_data: got data from stream %d:\n%s", streamid, data)

    if by_line:
        data, pd.partial[streamid] = extract_full_lines(pd.partial[streamid] + data)
        if data and pd.partial[streamid]:
            task._dbg_("capture_data: stream %d: full lines:\n%s",
                       streamid, "".join(data))
            task._dbg_("capture_data: stream %d: pd.partial line: %s",
                       streamid, pd.partial[streamid])
        for line in data:
            _save_output(line, streamid)
    else:
        if pd.partial[streamid]:
            data = pd.partial[streamid] + data
            pd.partial[streamid] = ""
        _save_output(data, streamid)

def get_lines_to_return(task, lines=(None, None)):
    """
    A helper for 'Procs' and 'SSH' that figures out what part of the captured command output should
    be returned to the user, and what part should stay in 'task._pd_.output', depending on the lines
    limit 'lines'. The keyword arguments are the same as in '_do_wait_for_cmd()'.
    """

    # pylint: disable=protected-access
    pd = task._pd_
    task._dbg_("get_lines_to_return: starting with lines %s, pd.partial: %s, pd.output:\n%s",
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

    task._dbg_("get_lines_to_return: starting with  pd.partial: %s, pd.output:\n%s\nreturning:\n%s",
               pd.partial, pd.output, output)
    return output

def all_output_consumed(task):
    """
    Returns 'True' if all the output of the process in 'task' was returned to the user and the
    process exited. Returns 'False' if there is some output still in the queue or "cached" in
    'task._pd_.output' or if the process did not exit yet.
    """

    # pylint: disable=protected-access
    pd = task._pd_
    return pd.exitcode is not None and \
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
