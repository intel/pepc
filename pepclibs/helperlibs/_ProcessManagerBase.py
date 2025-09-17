# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Base classes for process managers. Process managers provide an interface for executing commands and
managing files and processes. The idea is to have the same API for doing these regardless on whether
the command is executed on the local or remote system.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import queue
import codecs
import typing
import threading
import contextlib
from pathlib import Path
from typing import NamedTuple
from pepclibs.helperlibs import Logging, Human, Trivial, ClassHelpers, ToolChecker
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import IO, Any, cast, Generator, TypedDict

    class LsdirTypedDict(TypedDict):
        """
        A directory entry information dictionary.

        Attributes:
            name: The name of the directory entry (a file, a directory, etc).
            path: The full path to the directory entry.
            mode: The mode (permissions) of the directory entry.
            ctime: The creation time of the directory entry in seconds since the epoch.
        """

        name: str
        path: Path
        mode: int
        ctime: float

class ProcWaitResultType(NamedTuple):
    """
    The result of the 'wait()' method for a process.

    Attributes:
        stdout: The standard output of the process. Can be a single string or a list of strings
                lines. The tailing newline is not stripped.
        stderr: The standard error of the process. Can be a single string or a list of strings
                lines. The tailing newline is not stripped.
        exitcode: The exit code of the process. Can be an integer or None if the process is still
                  running.
    """

    stdout: str | list[str]
    stderr: str | list[str]
    exitcode: int | None

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# The default process timeout in seconds.
TIMEOUT = 24 * 60 * 60

def get_err_prefix(fobj: IO, method_name: str) -> str:
    """
    Generate an exception message prefix for a file-like object that will be wrapped by
    'ClassHelpers.WrapExceptions'.

    Args:
        fobj: The file-like object to generate the prefix for.
        method_name: The name of the method that raised the exception.

    Returns:
        The the exception message prefix string.
    """

    return f"Method '{method_name}()' failed for '{fobj.name}'"

def extract_full_lines(text: str) -> tuple[list[str], str]:
    """
    Extract full lines and the last partial line from a piece of output of a process.

    Args:
        text: The input string to process.

    Returns:
        A tuple containing:
        - A list of full lines extracted from the input string.
        - A string representing the last partial line, or an empty string if there is no partial
          line.
    """

    full: list[str] = []
    partial = ""

    for line_match in re.finditer("(.*[\n\r])|(.+$)", text):
        if line_match.group(2):
            partial = line_match.group(2)
            break
        full.append(line_match.group(1))

    return (full, partial)

def have_enough_lines(output: list[list[str]], lines: tuple[int, int] = (0, 0)) -> bool:
    """
    Check if there are enough lines in the output buffer.

    Args:
        output: A tuple containing two lists of strings, representing the stdout and stderr output.
        lines: A tuple of two integers specifying the minimum number of lines required in each
               stream's output buffer. A value of 0 means no requirement for that stream.

    Returns:
        True if at least one stream has the required number of lines, False otherwise.
    """

    any_amount = [False, False]
    result = [False, False]

    for streamid in (0, 1):
        if lines[streamid] <= 0:
            any_amount[streamid] = True
        if len(output[streamid]) >= lines[streamid]:
            result[streamid] = True

    if all(any_amount):
        # Both streams do not have a limit set, so no amount of lines in "enough", return False.
        return False

    return all(result)

class ProcessBase(ClassHelpers.SimpleCloseContext):
    """
    The base class for representing a processes created and managed by a process manager.
    """

    def __init__(self,
                 pman: ProcessManagerBase,
                 pobj: Any,
                 cmd: str,
                 real_cmd: str,
                 streams: tuple[Any, Any, Any]):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object responsible for managing this process.
            pobj: Low-level object representing the local or remote process corresponding to this
                  instance (e.g., a 'subprocess.Popen' object in case of a local process).
            cmd: The command that was executed to start the process.
            real_cmd: Actual (full) command that was executed, which may differ slightly from the
                      original command (e.g., prefixed with a PID print statement).
            streams: A Tuple containing objects that can be used for writing to process' stdin and
                     reading from process' stdout, and stderr. Value 'None' means that the stream is
                     not available.
        """

        self.pman = pman
        self.pobj = pobj
        self.cmd = cmd
        self.real_cmd = real_cmd
        self.stdin = streams[0]

        self.timeout: int | float = TIMEOUT
        self.hostname = pman.hostname
        self.hostmsg = pman.hostmsg

        # ID of the running process. Should be set by the child class. In some cases may be set to
        # 'None', which should be interpreted as "unknown".
        self.pid: int | None = None
        # Exit code of the process ('None' if it is still running).
        self.exitcode: int | None = None
        # The stdout and stderr streams.
        self._streams = [streams[1], streams[2]]
        # Count of lines the process printed to stdout and stderr.
        self._lines_cnt = [0, 0]

        # Print debugging messages if 'True'.
        self.debug = False
        # Prefix debugging messages with this string. Can be useful to distinguish between debugging
        # message related to different processes.
        self.debug_id = ""

        # The stream fetcher threads have to exit if the '_threads_exit' flag becomes 'True'.
        self._threads_exit = False
        # The output for the process that was read from 'self._queue', but not yet sent to the user
        # (separate for 'stdout' and 'stderr').
        self._output: list[list[str]] = [[], []]
        # The last partial lines of the stdout and stderr streams of the process.
        self._partial = ["", ""]
        # The threads fetching data from the stdout/stderr streams of the process.
        self._threads: list[threading.Thread | None] = [None, None]
        # The queue for passing process output from stream fetcher threads.
        self._queue: queue.Queue | None = None

        if self.stdin:
            if not getattr(self.stdin, "name", None):
                setattr(self.stdin, "name", "stdin")
            wrapped = ClassHelpers.WrapExceptions(self.stdin, get_err_prefix=get_err_prefix)
            if typing.TYPE_CHECKING:
                self.stdin = cast(IO[bytes], wrapped)
            else:
                self.stdin = wrapped

    def _reinit(self, cmd: str, real_cmd: str):
        """
        Reinitialize the process object for a new command execution.

        Reset the internal state of the process object to allow reusing it for running new command.

        Args:
            cmd: The new command that was executed to start the process.
            real_cmd: Actual (full) new command that was executed, which may differ slightly from
                      the original command (e.g., prefixed with a PID print statement).
        """

        self.cmd = cmd
        self.real_cmd = real_cmd

        self.pid = None
        self.exitcode = None

        self._threads_exit = False
        self._output = [[], []]
        self._partial = ["", ""]

    def __del__(self):
        """Class destructor."""

        with contextlib.suppress(BaseException):
            self._dbg("ProcessBase: __del__()")

        if hasattr(self, "_threads_exit"):
            # Increase chances of threads exiting if something went wrong (resilience).
            self._threads_exit = True

    def close(self):
        """Free allocated resources."""

        self._dbg("ProcessBase.close()")

        if hasattr(self, "_threads_exit"):
            # Make sure the threads exit.
            self._threads_exit = True

        unref_attrs = ("pman", "pobj", "_streams", "stdin", "_threads")
        ClassHelpers.close(self, unref_attrs=unref_attrs)

    def _fetch_stream_data(self, streamid: int, size: int) -> bytes:
        """
        Fetch up to the specified number of bytes from the given stream.

        Args:
            streamid: Identifier of the stream to fetch data from.
            size: Maximum number of bytes to retrieve.

        Returns:
            The retrieved data as bytes (empty bytes object no data are available).
        """

        raise NotImplementedError("ProcessBase._fetch_stream_data()")

    def _stream_fetcher(self, streamid: int):
        """
        Fetch data from a stream in a separate thread.

        Continuously read data from one of the output streams (stdout or stderr) of the executed
        program and place the data into a queue. Stop when the stream is closed, no more data are
        available, an error occurs, or the thread is signaled to exit via 'self._threads_exit'.

        Args:
            streamid: Identifier of the stream to fetch data from (0 for stdout, 1 for stderr).
        """

        assert self._queue is not None

        try:
            decoder = codecs.getincrementaldecoder('utf8')(errors="surrogateescape")
            while not self._threads_exit:
                if not self._streams[streamid]:
                    self._dbg("ProcessBase._stream_fetcher(): streamid %d: Stream is closed",
                              streamid)
                    break

                bytes_data = bytes()
                try:
                    bytes_data = self._fetch_stream_data(streamid, 4096)
                except Error as err:
                    _LOG.error("Failed to read from streamid %d of PID %s: %s\n"
                               "The command of the process: %s",
                               streamid, str(self.pid), err, self.cmd)
                    break

                if not bytes_data:
                    self._dbg("ProcessBase._stream_fetcher(): streamid %d: No more data", streamid)
                    break

                data = decoder.decode(bytes_data)
                if not data:
                    self._dbg("ProcessBase._stream_fetcher(): streamid %d: Will read more data",
                              streamid)
                    continue

                self._dbg("ProcessBase._stream_fetcher(): streamid %d: Read data:\n%s",
                          streamid, repr(data))
                self._queue.put((streamid, data))
        except BaseException as err: # pylint: disable=broad-except
            errmsg = Error(str(err)).indent(2)
            _LOG.error("Exception in stream fetcher for PID %s, streamid %d:\n%s",
                       str(self.pid), streamid, errmsg)

        # Place the end of stream indicator to the queue.
        self._queue.put((streamid, None))
        self._dbg("ProcessBase._stream_fetcher(): streamid %d: Thread exists", streamid)

    def _get_next_queue_item(self, timeout: int | float = 0) -> tuple[int, str | None]:
        """
        Retrieve a data item from the stream fetcher queue.

        Args:
            timeout: Maximum amount of seconds to wait for an item. If 0, wait indefinitely.

        Returns:
            The data item as a tuple in the format (streamid, data):
              - streamid: 0 for stdout, 1 for stderr.
              - data: Stream data, which may be a partial line.
            Return '(-1, None)' if the operation times out.
        """

        assert self._queue is not None

        try:
            if timeout:
                return self._queue.get(timeout=timeout)
            return self._queue.get(block=False)
        except queue.Empty:
            return (-1, None)

    def _handle_queue_item(self,
                           streamid: int,
                           data: str,
                           capture_output: bool = True,
                           output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None)):
        """
        Handle a queue item returned by '_get_next_queue_item()'.

        Exctract full lines from a stream output data (taking into account the partial line from the
        previous invocation) and write them to the given file-like objects. Update the internal
        state (partial line, line counters, etc).

        Args:
            streamid: The stream ID the data belongs to.
            data: The stream output data to handle.
            capture_output: Whether to store the processed lines in the internal output buffer.
            output_fobjs: Tuple of file-like objects for writing the full lines, one for each stream
                          (do not write if 'None').
        """

        self._dbg("ProcessBase._handle_queue_item(): got data from stream %d:\n%s",
                  streamid, repr(data))

        lines, self._partial[streamid] = extract_full_lines(self._partial[streamid] + data)
        if lines and self._partial[streamid]:
            self._dbg("ProcessBase._handle_queue_item(): stream %d: full lines:\n%s\n"
                      "partial line: %s", streamid, repr(lines), repr(self._partial[streamid]))

        self._lines_cnt[streamid] += len(lines)

        if capture_output:
            for line in lines:
                self._output[streamid].append(line)

        fobj = output_fobjs[streamid]
        if fobj is not None:
            for line in lines:
                fobj.write(line)
            fobj.flush()

    def _get_lines_to_return(self, lines: tuple[int, int]) -> list[list[str]]:
        """
        Fetch the portion of captured output to return to the user, and which portion should stay in
        'self._output'. The decision is based on the user-provided 'lines' argument, which specifies
        the desired number of lines for each output stream (stdout and stderr).

        Args:
            lines: A tuple where each element specifies the maximum number of lines to return for
                   the corresponding output stream. The first element corresponds to stdout, and the
                   second element corresponds to stderr. Zero means that all available lines should
                   be returned.

        Returns:
            A list of two lists, where each inner list contains the lines to be returned for the
            corresponding output stream (stdout and stderr).
        """

        self._dbg("ProcessBase._get_lines_to_return(): Requested lines:\n%s", str(lines))

        output: list[list[str]] = [[], []]

        for streamid in (0, 1):
            limit = lines[streamid]
            if limit == -1:
                continue

            if not limit or len(self._output[streamid]) <= limit:
                output[streamid] = self._output[streamid]
                self._output[streamid] = []
            else:
                output[streamid] = self._output[streamid][:limit]
                self._output[streamid] = self._output[streamid][limit:]

        self._dbg("ProcessBase._get_lines_to_return(): Returning the following lines:\nstdout:\n%s"
                  "\nstderr:\n%s", repr(output[0]), repr(output[1]))
        return output

    def _process_is_done(self) -> bool:
        """
        Check if the process has finished and all the process output has been consumed.

        Returns:
            True if the process has exited and all the process output lines have been consumed.
            False otherwise.
        """

        return self.exitcode is not None and \
               not self._output[0] and \
               not self._output[1] and \
               (not self._queue or self._queue.empty())

    def poll(self) -> int | None:
        """
        Check if the process is still running.

        Returns:
            None: If the process is still running.
            int: The exit status of the process if it has terminated.
        """

        raise NotImplementedError("ProcessBase.poll()")

    def _wait(self,
              timeout: int | float = 0,
              capture_output: bool = True,
              output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
              lines: tuple[int, int] = (0, 0)) -> list[list[str]]:
        """
        Wait for the process to complete and optionally capture its output.

        Implement the 'wait()' method, the matching arguments are similar.

        Args:
            timeout: Maximum time to wait for the process to complete. If 0, wait indefinitely.
            capture_output: If True, capture and return process's stdout and stderr.
            output_fobjs: A tuple of file-like objects to write stdout and stderr to, respectively.
                          Not affected by 'capture_output'.
            lines: A tuple specifying the maximum number of lines to capture from stdout and stderr.

        Returns:
            A list containing two lists: the captured stdout lines and stderr lines.
        """

        raise NotImplementedError("ProcessBase._wait()")

    def wait(self,
             timeout: int | float | None = None,
             capture_output: bool = True,
             output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
             lines: tuple[int, int] = (0, 0),
             join: bool = True) -> ProcWaitResultType:
        """
        Wait for the process to exit or produce output on stdout or stderr.

        Args:
            timeout: The maximum time in seconds to wait for the process to exit. If the process
                     does not exit within the timeout, return 'None' as the exit code. Must be a
                     positive floating-point number. Defaults to 'TIMEOUT'. If 0, check the process
                     status, possibly grab the available output, and return immediately. Save the
                     used timeout in 'self.timeout'.
            capture_output: Determine whether to capture the process output. If False, discard the
                            output and return empty strings for stdout and stderr.
            output_fobjs: A tuple of two file-like objects to echo the process's stdout and stderr
                          output to. If not specified, do not echo the output. This argument is
                          independent of 'capture_output'.
            lines: The number of lines from stdout and stderr to wait for. A tuple where the first
                   element is the stdout line limit and the second is the stderr line limit. For
                   example, 'lines=(1, 5)' will wait for one full line in stdout or five full lines
                   in stderr (or wait until timeout, whatever happens first). Value 0 means
                   "whatever is available". For example 'lines=(1, 0)' will wait for one line in
                   stdout any number of lines in stderr. Value -1 means "nothing". For example,
                   'lines=(-1, 2)' will wait for 2 lines in stderr and will collect all the
                   available stdout lines, but won't return them. They will be returned if/when they
                   are requested by a next 'wait()' call. The default value is (0, 0), which means
                   wait for 'timeout' amount of seconds or until the process exits, whichever
                   happens first, and return all the available lines.
            join: Whether to join captured output lines into a single string or return them as a
                  list of strings (trailing newlines are preserved in this case).

        Returns:
            A 'ProcWaitResultType' named tuple containing:
                - stdout: Captured stdout output as a string or list of strings (depending on
                  'join'). Empty list of string inf 'capture_output' is 'False'.
                - stderr: Captured stderr output as a string or list of strings (depending on
                  'join'). Empty list of string inf 'capture_output' is 'False'.
                - exitcode: Exit code of the process, or 'None' if the process did not exit.
        """

        if timeout is None:
            timeout = TIMEOUT

        if timeout < 0:
            raise Error(f"Bad timeout value {timeout}, must be greater than or equal to 0")

        for streamid in (0, 1):
            if not Trivial.is_int(lines[streamid]):
                raise Error("The 'lines' argument can only include integers")
            if lines[streamid] < 0 and lines[streamid] != -1:
                raise Error("The 'lines' argument cannot include negative values, except for -1")

        self.timeout = timeout

        self._dbg("ProcessBase.wait(): timeout %s, capture_output %s, lines: %s, join: %s, "
                  "real command:\n  %s", str(timeout), str(capture_output), str(lines), str(join),
                  self.real_cmd)

        if self._threads_exit:
            raise Error(f"The process (PID {str(self.pid)}) has 'threads_exit' flag set and cannot "
                        f"be used")

        stdout: str | list[str]
        stderr: str | list[str]
        if join:
            stdout = stderr = ""
        else:
            stdout = stderr = []

        if self._process_is_done():
            return ProcWaitResultType(stdout=stdout, stderr=stderr, exitcode=self.exitcode)

        if not self._queue:
            self._queue = queue.Queue()
            for streamid in (0, 1):
                if self._streams[streamid]:
                    assert self._threads[streamid] is None
                    try:
                        thread = threading.Thread(target=self._stream_fetcher,
                                                  name='stream-fetcher',
                                                  args=(streamid,), daemon=True)
                        thread.start()
                    except BaseException as err:
                        errmsg = Error(str(err)).indent(2)
                        raise Error(f"Failed to start the stream fetcher thread:\n{errmsg}\n"
                                    f"PID: {str(self.pid)}\nCommand: {self.cmd}") from err
                    self._threads[streamid] = thread
        else:
            self._dbg("ProcessBase.wait(): Queue is empty: %s", self._queue.empty())

        output = self._wait(timeout=timeout, capture_output=capture_output,
                            output_fobjs=output_fobjs, lines=lines)

        if self.exitcode == 127 and self._lines_cnt[0] == 0 and self._lines_cnt[1] == 1:
            # Exit code 127 is a typical shell exit code for the "command not found" case. We expect
            # a single output line in stderr in this case.
            if len(output[1]) > 0:
                errmsg = "".join(output[1]).strip()
            else:
                errmsg = ""
            # pylint: disable=protected-access
            raise self.pman._command_not_found(self.cmd, errmsg=errmsg)

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
            self._dbg("ProcessBase.wait(): returning: exitcode %s, stdout:\n%s\nstderr:\n%s",
                      str(exitcode), repr(sout), repr(serr))

        return ProcWaitResultType(stdout=stdout, stderr=stderr, exitcode=exitcode)

    def get_cmd_failure_msg(self,
                            stdout: str | list[str],
                            stderr: str | list[str],
                            exitcode: int | None,
                            timeout: int | float | None = None,
                            startmsg: str = "",
                            failed: bool = True):
        """
        Return a formatted message describing that the command has exited or failed.

        Args:
            stdout: Standard output of the command.
            stderr: Standard error of the command.
            exitcode: Exit code of the command.
            timeout: Timeout value for the command execution. Defaults to the timeout value used
                     in 'wait()', or 'TIMEOUT' if 'wait()' was never called.
            startmsg: Optional starting message to include in the resulting message.
            failed: Whether the command failed or just exited.

        Returns:
            A string containing the formatted exit/failure message.
        """

        if timeout is None:
            timeout = self.timeout
            if timeout is None:
                timeout = TIMEOUT

        cmd = self.cmd
        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if self.cmd != self.real_cmd:
                cmd += f"\nReal (full) command:\n  {self.real_cmd}"

        return self.pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode, timeout=timeout,
                                             startmsg=startmsg, failed=failed)

    def _dbg(self, fmt: str, *args: Any):
        """Print a debugging message."""

        if self.debug:
            pfx = ""
            if self.debug_id:
                pfx += f"{self.debug_id}: "
            if self.pid is not None:
                pfx += f"PID {self.pid}: "
            _LOG.debug(pfx + fmt, *args)

    def _dbg_log_buffered_output(self, pfx: str):
        """
        Log buffered output contents for debugging purposes.

        Args:
            pfx: A prefix string to include in the log message.

        Returns:
            None
        """

        if not self.debug:
            return

        if self._partial[0]:
            partial_stdout = "Partial stdout line: " + repr(self._partial[0])
        else:
            partial_stdout = "No partial stdout line"

        if self._partial[1]:
            partial_stderr = "Partial stderr line: " + repr(self._partial[1])
        else:
            partial_stderr = "No partial stderr line"

        if self._output[0]:
            stdout = self._output[0][0]
            if len(self._output[0]) > 1:
                stdout += " ... strip ...\n"
                stdout += self._output[0][-1]
            stdout = "First and last lines of stdout:\n" + repr(stdout)
        else:
            stdout = "No buffered stdout"

        if self._output[1]:
            stderr = repr(self._output[1][0])
            if len(self._output[1]) > 1:
                stderr += " ... strip ...\n"
                stderr += repr(self._output[1][-1])
            stderr = "First and last lines of stderr:\n" + repr(stderr)
        else:
            stderr = "No buffered stderr"

        self._dbg("%s: Buffered output:\n%s\n%s\n%s\n%s",
                  pfx, partial_stdout, partial_stderr, stdout, stderr)

class ProcessManagerBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for process managers.

    Process managers provide an interface for executing commands and managing files and processes.
    The idea is to have the same API for doing these regardless on whether the command is executed
    on the local or remote system.
    """

    def __init__(self):
        """Initialize the class instance."""

        # Whether the process manager is managing a remote host.
        self.is_remote = False
        # The hostname of the host.
        self.hostname = "localhost"
        # The message referring to the host to add to error messages.
        self.hostmsg = ""

        # Path to python interpreter.
        self._python_path: Path | None = None

    def run_async(self,
                  cmd: str | Path,
                  cwd: str | Path | None = None,
                  intsh: bool = False,
                  stdin: IO | None = None,
                  stdout: IO | None = None,
                  stderr: IO | None = None,
                  env: dict[str, str] | None = None,
                  newgrp: bool = False) -> ProcessBase:
        """
        Execute a command asynchronously without waiting for it to complete.

        Args:
            cmd: The command to execute. Can be a string or a 'pathlib.Path' pointing to the file to
                 execute.
            cwd: The working directory for the process.
            intsh: If True, use an existing interactive shell or create a new one. Only one
                   asynchronous process can run in an interactive shell at a time. It takes less
                   time to start a new process in an existing interactive shell, because it does not
                   require creating a new shell.
            stdin: Standard input stream for the process (file-like object).
            stdout: Standard output stream for the process (file-like object).
            stderr: Standard error stream for the process (file-like object).
            env: Environment variables for the process.
            newgrp: Create a new group for the process, as opposed to using the parent process
                    group.

        Returns:
            A process object (subclass of 'ProcessBase') representing the asynchronous process.
        """

        raise NotImplementedError("ProcessManagerBase.run_async()")

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
        """
        Execute a command and wait for it to finish.

        Args:
            cmd: The command to execute. Can be a string or a 'pathlib.Path' pointing to the file to
                 execute.
            timeout: Maximum amount of seconds to wait for the command to complete. Raises
                     'ErrorTimeOut' if the command exceeds this time. Defaults to 'TIMEOUT'.
            capture_output: If True, capture and return process's stdout and stderr.
            mix_output: If True, combine standard output and error streams into stdout.
            join: Return captured output as a single string if True, or as a list of lines if False.
                  Trailing newlines are preserved.
            output_fobjs: A tuple of two file-like objects to echo stdout and stderr. If
                         'mix_output' is True, the second object is ignored, and all output is
                         echoed to the first. Not affected by 'capture_output'.
            cwd: The working directory for the process.
            intsh: Use an existing interactive shell if True, or a new shell if False. The former
                   requires less time to start a new process, as it does not require creating a new
                   shell.
            env: Environment variables for the process.
            newgrp: Create a new group for the process, as opposed to using the parent process
                    group.

        Returns:
            A 'ProcWaitResultType' named tuple with the following elements:
                - exitcode: The exit code of the executed command.
                - stdout: The standard output of the executed command (either a string or a list of
                          line, depending on 'join').
                - stderr: The standard error of the executed command (either a string or a list of
                          line, depending on 'join').

        Notes:
            - If 'mix_output' is True, the 'stderr' part of the returned tuple will be an empty
              string or list.
            - If 'capture_output' is False, both 'stdout' and 'stderr' in the returned tuple will be
              empty strings or lists.
        """

        raise NotImplementedError("ProcessManagerBase.run()")

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
        """
        Execute a command and wait for it to finish and verify its success. Similar to 'run()', but
        it with a verification step. Refer to the 'run()' method for a more verbose argument
        descriptions.

        Args:
            cmd: The command to execute. Can be a string or a 'pathlib.Path' pointing to the file to
                 execute.
            timeout: The maximum time to wait for the command to complete.
            capture_output: Whether to capture the command's output.
            mix_output: Whether to merge stdout and stderr into a single stream.
            join: Whether to join the output streams.
            output_fobjs: File-like objects to write the command's stdout and stderr.
            cwd: The working directory to execute the command in.
            intsh: Use an existing interactive shell if True, or a new shell if False. The former
                   requires less time to start a new process, as it does not require creating a new
                   shell.
            env: Environment variables for the process.
            newgrp: Create a new group for the process, as opposed to using the parent process
                    group.

        Returns
            A tuple of:
                - stdout: The standard output of the executed command (either a string or a list of
                          line, depending on 'join').
                - stderr: The standard error of the executed command (either a string or a list of
                          line, depending on 'join').
        """

        raise NotImplementedError("ProcessManagerBase.run_verify()")

    def run_verify_join(self,
                        cmd: str | Path,
                        timeout: int | float | None = None,
                        capture_output: bool = True,
                        mix_output: bool = False,
                        output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                        cwd: str | Path | None = None,
                        intsh: bool = True,
                        env: dict[str, str] | None = None,
                        newgrp: bool = False) -> tuple[str, str]:
        """
        Same as 'run_verify(join=True)', provided for convenience and more deterministic return
        type.
        """

        ret = self.run_verify(cmd, timeout=timeout, capture_output=capture_output,
                              mix_output=mix_output, join=True, output_fobjs=output_fobjs,
                              cwd=cwd, intsh=intsh, env=env, newgrp=newgrp)
        if typing.TYPE_CHECKING:
            return cast(tuple[str, str], ret)
        return ret

    def run_verify_nojoin(self,
                          cmd: str | Path,
                          timeout: int | float | None = None,
                          capture_output: bool = True,
                          mix_output: bool = False,
                          output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                          cwd: str | Path | None = None,
                          intsh: bool = True,
                          env: dict[str, str] | None = None,
                          newgrp: bool = False) -> tuple[list[str], list[str]]:
        """
        Same as 'run_verify(join=False)', provided for convenience and more deterministic return
        type.
        """

        ret = self.run_verify(cmd, timeout=timeout, capture_output=capture_output,
                              mix_output=mix_output, join=False, output_fobjs=output_fobjs,
                              cwd=cwd, intsh=intsh, env=env, newgrp=newgrp)
        if typing.TYPE_CHECKING:
            return cast(tuple[list[str], list[str]], ret)
        return ret

    @staticmethod
    def _rsync_add_debug_opts(opts: str) -> str:
        """
        Add the '-v' option to the rsync options if debug-level logging is enabled.

        Args:
            opts: A string containing the current rsync options.

        Returns:
            A string with the updated rsync options, including the '-v' option if debug-level
            logging is enabled.
        """

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if opts:
                opts = f"{opts} -v"
            else:
                opts = "-v"

        return opts

    @staticmethod
    def _rsync_debug_log(stdout: str | list[str]):
        """
        Log the 'stdout' output of the 'rsync' command if debug-level logging is enabled.

        Args:
            stdout: The standard output of the 'rsync' command to be logged.
        """

        if stdout and _LOG.getEffectiveLevel() != Logging.DEBUG:
            return

        if isinstance(stdout, list):
            stdout = "".join(stdout)
        _LOG.debug("rsync output:\n%s", stdout)

    def rsync(self,
              src: str | Path,
              dst: str | Path,
              opts: str = "-rlD",
              remotesrc: bool = False,
              remotedst: bool = False):
        """
        Copy data from the source path to the destination path using the 'rsync' tool.

        Args:
            src: Source path.
            dst: Destination path.
            opts: Options for the 'rsync' tool. Defaults to "-rlD".
            remotesrc: Set to True if the source path is on the remote host.
            remotedst: Set to True if the destination path is on the remote host.

        Notes:
            - Refer to the 'rsync' tool documentation for a detailed description of the options.
            - Pay attention to the trailing slash at the end of paths, as it affects behavior. If
              there is a trailing slash in the end of the source path, the contents of the source
              directory will be copied to the destination directory. If there is no trailing slash,
              the source directory itself will be copied to the destination directory.
            - Default options:
                * r: Recursive copy.
                * l: Copy symlinks as symlinks.
                * D: Preserve device nodes and other special files.
        """

        raise NotImplementedError("ProcessManagerBase.rsync()")

    def get(self, src: str | Path, dst: str | Path):
        """
        Copy a file or directory from the source path to the destination path.

        Args:
            src: The source path of the file or directory to copy.
            dst: The destination path where the file or directory will be copied.
        """

        raise NotImplementedError("ProcessManagerBase.get()")

    def put(self, src: str | Path, dst: str | Path):
        """
        Copy a file or directory from the source path to the destination path.

        Args:
            src: The source path of the file or directory to copy.
            dst: The destination path where the file or directory will be copied.
        """

        raise NotImplementedError("ProcessManagerBase.put()")

    def _command_not_found(self, cmd: str, errmsg: str = "", toolname: str = "") -> ErrorNotFound:
        """
        Handle the case when a command cannot be executed because the executable file was not found.

        Format a helpful error message and return an exception object. Attempt to resolve the tool
        name to its corresponding OS package name for a more informative suggestion.

        Args
            cmd: The command that could not be executed.
            errmsg: An optional error message describing the failure.
            toolname: An optional name of the tool for which the command was not found. If not
                      provided, it will be extracted from the command.

        Returns
            An ErrorNotFound exception object with a detailed error message.
        """

        pkgname: str = ""
        if not toolname:
            # Get the tool (program) name.
            toolname = cmd.split()[0].split("/")[-1]

        try:
            # Try to resolve tool name to the OS package name.
            with ToolChecker.ToolChecker(self) as tchk:
                pkgname = tchk.tool_to_pkg(toolname)
        except Exception as err: # pylint: disable=broad-except
            _LOG.debug("Failed to format the command package suggestion: %s", err)

        if pkgname:
            what = f"'{pkgname}' OS package"
        else:
            what = f"'{toolname}' program"

        msg = f"Cannot execute the following command{self.hostmsg}:\n  {cmd}\n"
        if errmsg:
            msg += f"The error is:\n{Error(errmsg).indent(2)}\n"
        else:
            msg += "Command not found\n"
        msg += f"Try to install the {what}{self.hostmsg}"

        return ErrorNotFound(msg)

    def get_cmd_failure_msg(self,
                            cmd: str | Path,
                            stdout: str | list[str],
                            stderr: str | list[str],
                            exitcode: int | None,
                            timeout: int | float | None = None,
                            startmsg: str = "",
                            failed: bool = True):
        """
        Return a formatted message describing that the command has exited or failed.

        Args:
            cmd: The command that exited or failed. Can be a string or a 'pathlib.Path' pointing to
                 the file to execute.
            stdout: Standard output of the command.
            stderr: Standard error of the command.
            exitcode: Exit code of the command.
            timeout: Timeout value for the command execution. Defaults to 'TIMEOUT'.
            startmsg: Optional starting message to include in the resulting message.
            failed: Whether the command failed or just exited.

        Returns:
            A string containing the formatted exit/failure message.
        """

        if timeout is None:
            timeout = TIMEOUT

        if exitcode is None:
            human_tout = Human.duration(timeout)
            exitcode_msg = f"did not finish within {timeout} seconds ({human_tout})"
        else:
            if failed:
                verb = "failed"
            else:
                verb = "finished"
            exitcode_msg = f"{verb} with exit code {exitcode}"

        msg = ""
        for stream in (stdout, stderr):
            if not stream:
                continue
            if isinstance(stream, list):
                stream = "".join(stream)
            msg += f"{stream.strip()}\n"

        if startmsg:
            startmsg += "\n"

        if self.is_remote:
            startmsg += f"Ran the following command on host '{self.hostname}', but it " \
                        f"{exitcode_msg}:"
        else:
            startmsg += f"The following command {exitcode_msg}:"

        cmd = str(cmd)
        result = f"{startmsg}\n  {cmd}"
        if msg:
            result += f"\n\n{msg.strip()}"

        return result

    def open(self, path: str | Path, mode: str) -> IO:
        """
        Open a file at the specified path and return the file-like object.

        Args:
            path: The path to the file to open.
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            A file-like object corresponding to the opened file.

        Notes:
            If "b" is not in the mode, the file is opened in text mode with the "utf-8" encoding.
        """

        raise NotImplementedError("ProcessManagerBase.open()")

    def read_file(self, path: Path | str) -> str:
        """
        Read a file.

        Args:
            path: The path to the file to read.

        Returns:
            The contents of the file as a string

        Raises:
            ErrorNotFound: If the file does not exist.
        """

        try:
            with self.open(path, "r") as fobj:
                val = fobj.read()
        except ErrorNotFound as err:
            raise ErrorNotFound(f"File '{path}' does not exist{self.hostmsg}") from err

        return val

    def get_python_path(self) -> Path:
        """
        Locate and return the path to the Python interpreter.

        Returns:
            Path: The path to the Python interpreter.

        Raises:
            ErrorNotFound: If no valid Python interpreter is found in the predefined paths.
        """

        if self._python_path:
            return self._python_path

        # The paths to try.
        paths = ("python3", "/usr/bin/python3", "/usr/local/bin/python3",
                 "python", "/usr/bin/python", "/usr/local/bin/python")
        for path in paths:
            try:
                self.run_verify(f"{path} --version")
            except Error:
                continue

            if not path.startswith("/"):
                path = self.which(path, must_find=True)

            self._python_path = Path(path)
            return self._python_path

        paths_descr = "\n * " + "\n * ".join(paths)
        raise ErrorNotFound(f"Failed to find python interpreter{self.hostmsg}.\n"
                            f"Checked the following paths:{paths_descr}")

    def time_time(self) -> float:
        """
        Get the current time in seconds since the epoch as a floating-point number (similar to the
        standard Python `time.time()` function).

        Returns:
            The current time in seconds since the epoch as a floating-point number.
        """

        raise NotImplementedError("ProcessManagerBase.time_time()")

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """
        Create a directory.

        Args:
            dirpath: The path where the directory should be created.
            parents: Create parent directories as needed if True. Otherwise, raise an exception if
                     a parent directory does not exist.
            exist_ok: Do not raise an exception if the directory already exists when True.
        """

        raise NotImplementedError("ProcessManagerBase.mkdir()")

    def mksocket(self, path: str | Path, exist_ok: bool = False):
        """
        Create a Unix socket file.

        Args:
            path: The path where the Unix socket file should be created.
            exist_ok: Do not raise an exception if the unix socket file already exists when True.
        """

        raise NotImplementedError("ProcessManagerBase.mksocket()")

    def mkfifo(self, path: str | Path, exist_ok: bool = False):
        """
        Create a named pipe.

        Args:
            path: The path where the named pipe should be created.
            exist_ok: Do not raise an exception if the named pipe already exists when True.
        """

        raise NotImplementedError("ProcessManagerBase.mkfifo()")

    def lsdir(self, path: str | Path) -> Generator[LsdirTypedDict, None, None]:
        """
        Yield directory entries in the specified path as 'LsdirTypedDict' dictionaries.

        Entries are yielded in creation time (ctime) order.

        Args:
            path: The directory path to list entries from.

        Raises:
            ErrorNotFound: If the specified path does not exist or is not a directory.
        """

        raise NotImplementedError("ProcessManagerBase.lsdir()")

    def exists(self, path: str | Path) -> bool:
        """
        Check if the specified path exists.

        Args:
            path: The path to check.

        Returns:
            True if the path exists, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.exists()")

    def is_file(self, path: str | Path) -> bool:
        """
        Check if the given path exists and is a regular file.

        Args:
            path: The path to check.

        Returns:
            True if the path exists and is a regular file, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.is_file()")

    def is_dir(self, path: str | Path) -> bool:
        """
        Check if the given path exists and is a directory.

        Args:
            path: The path to check.

        Returns:
            True if the path exists and is a directory, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.is_dir()")

    def is_exe(self, path: str | Path) -> bool:
        """
        Check if the given path exists and is an executable file.

        Args:
            path: The path to check.

        Returns:
            True if the path exists and is an executable file, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.is_exe()")

    def is_socket(self, path: str | Path) -> bool:
        """
        Check if the given path exists and is a Unix socket file.

        Args:
            path: The path to check.

        Returns:
            True if the path exists and is a Unix socket file, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.is_socket()")

    def is_fifo(self, path: str | Path) -> bool:
        """
        Check if the given path exists and is a named pipe.

        Args:
            path: The path to check.

        Returns:
            True if the path exists and is a named pipe, False otherwise.
        """

        raise NotImplementedError("ProcessManagerBase.is_fifo()")

    def get_mtime(self, path: str | Path) -> float:
        """
        Get the modification time of a file or directory.

        Args:
            path: The path to the file or directory.

        Returns:
            The modification time as a floating-point number representing seconds since the epoch.
        """

        raise NotImplementedError("ProcessManagerBase.get_mtime()")

    def unlink(self, path: str | Path):
        """
        Remove a file.

        Args:
            path: The path to the file to remove.
        """

        raise NotImplementedError("ProcessManagerBase.unlink()")

    def rmtree(self, path: str | Path):
        """
        Recursively remove a file or directory at the specified path. If the path is a symlink,
        remove only the symlink without affecting the target it points to.

        Args:
            path: The file or directory path to remove.
        """

        raise NotImplementedError("ProcessManagerBase.rmtree()")

    def abspath(self, path: str | Path) -> Path:
        """
        Resolve the given path to an absolute real path.

        Args:
            path: The path to resolve into an absolute real path.

        Raises:
            ErrorNotFound: If the path does not exist or is not a file or directory.
        """

        raise NotImplementedError("ProcessManagerBase.abspath()")

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """
        Create a temporary directory and return its path.

        Args:
            prefix: A prefix for the temporary directory name.
            basedir: The base directory where the temporary directory should be created.

        Returns:
            The path to the created temporary directory.
        """

        raise NotImplementedError("ProcessManagerBase.mkdtemp()")

    def get_envar(self, envar: str) -> str | None:
        """
        Get the value of an environment variable.

        Args:
            envar: The name of the environment variable to retrieve.

        Returns:
            The value of the environment variable as a string, or None if the variable is not set.
        """

        raise NotImplementedError("ProcessManagerBase.get_envar()")

    def which(self, program: str | Path, must_find: bool = True):
        """
        Locate the full path of a program by searching in PATH.

        Args:
            program: Name of the program to locate.
            must_find: If True, raise 'ErrorNotFound' if the program was not found. If False, return
                       None when the program was not found.
        """

        raise NotImplementedError("ProcessManagerBase.which()")
