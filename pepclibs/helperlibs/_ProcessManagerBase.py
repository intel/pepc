# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides the base class for process managers, as well as common bits and pieces shared
between diffrent process manager implementations.
"""

# pylint: disable=protected-access

import re
import queue
import codecs
import logging
import threading
import contextlib
from collections import namedtuple
from pepclibs.helperlibs import Human, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

# The default process timeout in seconds.
TIMEOUT = 4 * 60 * 60

# Results of a process finished its execution.
ProcResult = namedtuple("proc_result", ["stdout", "stderr", "exitcode"])

def _get_err_prefix(fobj, method):
    """Return the error message prefix for a wrapped file-like object 'fobj'."""
    return f"method '{method}()' failed for stream '{fobj.name}'"

def extract_full_lines(text):
    """
    Extract full lines from string 'text'. Return a tuple containing 2 elements - the full lines and
    the last partial line.
    """

    full, partial = [], ""
    for line_match in re.finditer("(.*\n)|(.+$)", text):
        if line_match.group(2):
            partial = line_match.group(2)
            break
        full.append(line_match.group(1))

    return (full, partial)

def have_enough_lines(output, lines=(None, None)):
    """Returns 'True' if there are enough lines in the output buffer."""

    for streamid in (0, 1):
        if lines[streamid] and len(output[streamid]) >= lines[streamid]:
            return True
    return False


def _bug_method_not_defined(method_name):
    """
    Raise an error if the child class did not define the 'method_name' mandatory method.
    """

    raise Error(f"BUG: '{method_name}()' was not defined by the child class")

class ProcessBase:
    """
    The base class for processes created using one of the process managers.
    """

    def _fetch_stream_data(self, streamid, size):
        """
        Fetch up to 'size' bytes of data from stream 'streamid'. Returns 'None' if there are no
        data.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessBase._fetch_stream_data")

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
                    _LOG.error("failed reading from stream %d: %s\nThe command of the process:\n%s",
                               streamid, err, self.cmd)
                    break

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

    def _handle_queue_item(self, streamid, data, capture_output=True, output_fobjs=(None, None)):
        """
        Hadle an item item returned by '_get_next_queue_item()'. The item is the '(streamic, data)'
        pair. The keyword arguments are the same as in 'wait()'.
        """

        self._dbg("_handle_queue_item: got data from stream %d:\n%s", streamid, data)

        data, self._partial[streamid] = extract_full_lines(self._partial[streamid] + data)
        if data and self._partial[streamid]:
            self._dbg("_handle_queue_item: stream %d: full lines:\n%s\npartial line: %s",
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
        Figure out what part of captured output should be returned to the user, and what part should
        stay in 'self._output'. This depends on the 'lines' argument. The keyword arguments are the
        same as in 'wait()'.
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

    def _process_is_done(self):
        """
        Returns 'True' if all output lines of the process have been returned to the user and the
        process has exited. Returns 'False' otherwise.
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

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessBase._wait")

    def wait(self, timeout=None, capture_output=True, output_fobjs=(None, None), lines=(None, None),
             join=True):
        """
        This method waits for the process to exit or print something to stdout or stderr. The
        arguments are as follows.
          * timeout - the maximum time in seconds to wait for the process to exit . If it does not
                      exit, this function returns 'None' as the exit code. The 'timeout' argument
                      must be a positive floating point number. By default it is 1 hour. If
                      'timeout' is '0', then this method will just check process status, grab its
                      output, if any, and return immediately. Note, this method saves the used
                      timeout in 'self.timeout'.
          * capture_output - whether the output of the process should be captured. If it is 'False',
                             the output will simply be discarded and this method will return empty
                             strings instead of process' stdout and stderr.
          * output_fobjs - a tuple with two file-like objects where stdout and stderr output of the
                           process will be echoed. If not specified, then the the output will not be
                           echoed anywhere. Note, this argument is independent of the
                           'capture_output' argument.
          * lines - provides a capability to wait for the process to output certain amount of lines.
                    By default, there is no limit, and this function will wait either for timeout or
                    until the process exits. The 'line' argument is a tuple, the first element of
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

        if self._process_is_done():
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

        if self._process_is_done():
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
        """
        Check if the process is still running. If it is, return 'None', else return exit status.
        """

        # pylint: disable=no-self-use
        return _bug_method_not_defined("ProcessBase.poll")

    def get_cmd_failure_msg(self, stdout, stderr, exitcode, timeout=None, startmsg=None):
        """
        Format and return the command failure message. The arguments are the same as in
        'ProcessManagerBase.get_cmd_failure_msg()'.
        """

        if timeout is None:
            timeout = self.timeout

        cmd = self.cmd
        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if self.cmd != self.real_cmd:
                cmd += f"\nReal command: {self.real_cmd}"

        return self.pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode, timeout=timeout,
                                             startmsg=startmsg)

    def _reinit(self, cmd, real_cmd, shell):
        """
        Re-initialize this object in case the process it is associated with is re-used for running a
        different command (using 'exec', for example).
        """

        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell

        self.pid = None
        self.exitcode = None

        self._threads_exit = False
        self._output = [[], []]
        self._partial = ["", ""]

    def __init__(self, pman, pobj, cmd, real_cmd, shell, streams):
        """
        Initialize a class instance. The arguments are as follows.
          * pman - the process management object that was used for creating this object.
          * pobj - the low-level object representing the local or remote process corresponding to
                   this object.
          * cmd - the executed command.
          * real_cmd - sometimes the original command gets slightly amended, e.g., it is sometimes
                       prefixed with a PID print command. This argument should provide the actual
                       executed command.
          * shell - whether the command was executed via shell.
          * streams - the stdin, stdout and stderr stream objects of the process (collection of 3
                      elements).

         Note about the stream objects in 'streams'. The stderr stream object must be a file-like
         object, and it will be exposed via 'self.stderr'. The stdout and stderr stream objects do
         not have to be file-like objects. They can be just some objects representing the streams
         (defined by sub-classes). The are not exposed to the user, and they are only accessed via
         the '_fetch_stream_data()' method, which is defined by the sub-class.
        """

        self.pman = pman
        self.pobj = pobj
        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell
        self.stdin = streams[0]

        self.timeout = TIMEOUT
        self.hostname = pman.hostname
        self.hostmsg = pman.hostmsg

        # ID of the running process. Should be set by the child class. In some cases may be set to
        # 'None', which should be interpreted as "not known".
        self.pid = None
        # Exit code of the process ('None' if it is still running).
        self.exitcode = None
        # The stdout and stderr streams.
        self._streams = [streams[1], streams[2]]

        # Print debugging messages if 'True'.
        self.debug = False
        # Prefix debugging messages with this string. Can be useful to distinguish between debugging
        # message related to different processs.
        self.debug_id = None

        # The stream fetcher threads have to exit if the '_threads_exit' flag becomes 'True'.
        self._threads_exit = False
        # The output for the process that was read from 'self._queue', but not yet sent to the user
        # (separate for 'stdout' and 'stderr').
        self._output = [[], []]
        # The last partial lines of the stdout and stderr streams of the process.
        self._partial = ["", ""]
        # The threads fetching data from the stdout/stderr streams of the process.
        self._threads = [None, None]
        # The queue for passing process output from stream fetcher threads.
        self._queue = None

        if self.stdin:
            self.stdin = ClassHelpers.WrapExceptions(self.stdin, exceptions=(Exception,),
                                                     get_err_prefix=_get_err_prefix)

    def close(self):
        """Free allocated resources."""

        self._dbg("close()")

        if hasattr(self, "_threads_exit"):
            self._threads_exit = True

        ClassHelpers.close(self, unref_attrs=("pman",))

    def __del__(self):
        """Class destructor."""

        with contextlib.suppress(Exception):
            self._dbg("__del__()")

        if hasattr(self, "_threads_exit"):
            self._threads_exit = True

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()

class ProcessManagerBase:
    """
    The base class for process managers, which can manage both local and remote processes.
    """

    Error = Error

    def run_async(self, command, cwd=None, shell=False, intsh=False, stdin=None, stdout=None,
                  stderr=None):
        """
        Run command 'command' without waiting for it to complete. The arguments are as follows.
          * command - the command to run.
          * cwd - the working directory of the process.
          * shell - whether the command should be run via shell.
          * intsh - whether the command should run in an already running interactive shell or in a
                    new shell. The former should be more effecient.
          * stdin - the standard input stream to use for the process. Can be one of:
            - a file-like object
            - file path
          * stdout - similar to 'stdin', but for sandard output. If a file path is provided and it
                     does not exist, it will be created.
          * stderr - similar to 'stdin', but for sandard error.

        Note, there is only one interactive shell process at the moment, so only one asynchronous
        process an run in an interactive shell at a time.

        Returns the process object.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessManagerBase.run_async")

    def run(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
            output_fobjs=(None, None), cwd=None, shell=True, intsh=None):
        """
        Run command 'command' wait for it to finish. The arguments are as follows.
          * command - the command to run.
          * timeout - the longest time for this method to block. If the command takes longer to
                      finish, this method will raise the 'ErrorTimeOut' exception. The default is
                      4h (see '_ProcessManagerBase.TIMEOUT').
          * capture_output - if 'True', this method will intercept the output of the executed
                             command, otherwise the output will be dropped (default) (or echoed to
                             to 'output_fobjs').
          * mix_output - if 'True', the standard output and error streams will be mixed together.
          * join - controls whether the captured output is returned as a single string or as a list
                   of lines (trailing newlines are not stripped).
          * output_fobjs - an optional tuple providing 2 file-like objects where stdout and stderr
                           of the executed command should be echoed to. If 'mix_output' is 'True',
                           the second element of the tupe will be ignored and all the output will be
                           echoed to the first element. By default the command output is not echoed
                           anywhere.
          * cwd - the working directory of the process.
          * shell - whether the command should be run via shell.
          * intsh - whether the command should run in an already running interactive shell or in a
                    new shell. The former should be more effecient.

        This function returns the 'ProcResult' named tuple of '(exitcode, stdout, stderr)' elements.
          * 'stdout' - stdout executed command.
          * 'stderr' - stdout executed command.
          * 'exitcode' - exit code of the executed command.

        If the 'mix_output' argument is 'True', the 'stderr' part of the returned tuple will be an
        empty string.  If the 'capture_output' argument is not 'True', the 'stdout' and 'stderr'
        parts of the returned tuple will be empty strings.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessManagerBase.run")

    def run_verify(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
                   output_fobjs=(None, None), cwd=None, shell=True, intsh=None):
        """
        Similar as the "run()" method, but and raises the 'Error' exception if the command has
        failed.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessManagerBase.run_verify")

    def rsync(self, src, dst, opts="rlpD", remotesrc=False, remotedst=False):
        """
        Copy data from path 'src' to path 'dst' using the 'rsync' tool with options specified in
        'opts'. The arguments are as follows.
          * src - the source path.
          * dst - the destination path.
          * opts - the rsync tool options to use.
          * remotesrc - if 'True' the 'src' path is a path on the remote host (the host associated
                         with this object - 'self.hostname'). Otherwise this is a path on the local
                         host.
          * remotedst - if 'True', the 'dst' path is a path on the remote host, otherwise on the
                        local host.

        Notes.
          1. Please, refer to the 'rsync' tool documentation for the options description.
          2. The backslash at the end of the paths matters, refer to 'rsync' documentation.

        The default options in 'opts' are the following.
          * r - recursive.
          * l - copy symlinks as symlinks.
          * p - preserve permission.
          * s - preseve device nodes and others special files.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("ProcessManagerBase.rsync")

    def get_cmd_failure_msg(self, cmd, stdout, stderr, exitcode, timeout=None, startmsg=None):
        """
        Format and return the command failure message. The arguments are as follows.
            * cmd - the failed command.
            * stdout - standard output of the failed command.
            * stderr - standard error of the failed command.
            * exitcode - exit code of the failed command.
            * timeout - command time out.
            * startmsg - a string to start the error message with.
        """

        if timeout is None:
            timeout = TIMEOUT

        if exitcode is None:
            human_tout = Human.duration(timeout)
            exitcode_msg = f"did not finish within {timeout} seconds ({human_tout})"
        else:
            exitcode_msg = f"failed with exit code {exitcode}"

        msg = ""
        for stream in (stdout, stderr):
            if not stream:
                continue
            if isinstance(stream, list):
                stream = "".join(stream)
            msg += "%s\n" % stream.strip()

        if not startmsg:
            startmsg = ""
        else:
            startmsg += ".\n"

        if self.is_remote:
            startmsg += f"ran the following command on host '{self.hostname}', but it " \
                        f"{exitcode_msg}:"
        else:
            startmsg += f"the following command {exitcode_msg}:"

        result = f"{startmsg}\n{cmd}"
        if msg:
            result += "\n\n%s" % msg.strip()
        return result

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
