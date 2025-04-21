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

# pylint: disable=protected-access

# TODO: finish adding type hints to this module.
from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import queue
import codecs
import threading
import contextlib
from typing import NamedTuple, IO, Any, cast
from pathlib import Path
from pepclibs.helperlibs import Logging, Human, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

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

def have_enough_lines(output: tuple[list[str], list[str]],
                      lines: tuple[int, int] = (0, 0)) -> bool:
    """
    Check if there are enough lines in the output buffer.

    Args:
        output: A tuple containing two lists of strings, representing the stdout and stderr output.
        lines: A tuple of two integers specifying the minimum number of lines required in each
               stream's output buffer. A value of 0 means no requirement for that stream.

    Returns:
        True if at least one stream has the required number of lines, False otherwise.
    """

    for streamid in (0, 1):
        if lines[streamid] and len(output[streamid]) >= lines[streamid]:
            return True
    return False

class ProcessBase(ClassHelpers.SimpleCloseContext):
    """
    The base class for representing a processes created and managed by a process manager.
    """

    def __init__(self,
                 pman: ProcessManagerBase,
                 pobj: Any,
                 cmd: str,
                 real_cmd: str,
                 shell: bool,
                 streams: tuple[IO[bytes], IO[bytes], IO[bytes]]):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object responsible for managing this process.
            pobj: Low-level object representing the local or remote process corresponding to this
                  instance (e.g., a 'subprocess.Popen' object in case of a local process).
            cmd: The command that was executed to start the process.
            real_cmd: Actual (full) command that was executed, which may differ slightly from the
                      original command (e.g., prefixed with a PID print statement).
            shell: Indicates whether the command was executed via a shell.
            streams: A Tuple containing the stdin, stdout, and stderr stream objects of the process.
        """

        self.pman = pman
        self.pobj = pobj
        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell
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
            self.stdin = cast(IO[bytes], wrapped)

    def _reinit(self, cmd: str, real_cmd: str, shell: bool):
        """
        Reinitialize the process object for a new command execution.

        Reset the internal state of the process object to allow reusing it for running new command.

        Args:
            cmd: The new command that was executed to start the process.
            real_cmd: Actual (full) new command that was executed, which may differ slightly from
                      the original command (e.g., prefixed with a PID print statement).
            shell: Indicates whether the new command was executed in a shell.
        """

        self.cmd = cmd
        self.real_cmd = real_cmd
        self.shell = shell

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

        self._dbg("ProcessBase: close()")

        if hasattr(self, "_threads_exit"):
            # Make sure the threads exit.
            self._threads_exit = True

        unref_attrs = ("pman", "pobj", "_streams", "stdin", "_threads", "_queue")
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
                          streamid, data)
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

        self._dbg("ProcessBase._handle_queue_item(): got data from stream %d:\n%s", streamid, data)

        lines, self._partial[streamid] = extract_full_lines(self._partial[streamid] + data)
        if lines and self._partial[streamid]:
            self._dbg("ProcessBase._handle_queue_item(): stream %d: full lines:\n%s\n"
                      "partial line: %s", streamid, "".join(lines), self._partial[streamid])

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

        self._dbg("ProcessBase._get_lines_to_return(): requested lines:\n%s", str(lines))

        output: list[list[str]] = [[], []]

        for streamid in (0, 1):
            limit = lines[streamid]
            if not limit or len(self._output[streamid]) <= limit:
                output[streamid] = self._output[streamid]
                self._output[streamid] = []
            else:
                output[streamid] = self._output[streamid][:limit]
                self._output[streamid] = self._output[streamid][limit:]

        self._dbg("ProcessBase._get_lines_to_return(): returning the following lines:\nstdout:\n%s"
                  "\nstderr:\n%s", "".join(output[0]), "".join(output[1]))
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
               (self._queue is None or self._queue.empty())

    def _wait(self,
              timeout: int | float = 0,
              capture_output: bool = True,
              output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
              lines: tuple[int, int] = (0, 0)) -> tuple[list[str], list[str]]:
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
            A tuple containing two lists: the captured stdout lines and stderr lines.
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
                   in stderr. 'lines=(1, 0)' will wait for one line in stdout any number of lines in
                   stderr (ignore stderr lines as a wait criterion). Defaults to no limit.
            join: Whether to join captured output lines into a single string or return them as a
                  list of strings.

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
            if lines[streamid] < 0:
                raise Error("The 'lines' argument cannot include negative values")

        self.timeout = timeout

        self._dbg("ProcessBase.wait(): timeout %s, capture_output %s, lines: %s, join: %s, "
                  "command:\n  %s\nreal command:\n  %s", str(timeout), str(capture_output),
                  str(lines), str(join), self.cmd, self.real_cmd)

        if self._threads_exit:
            raise Error(f"The process (PID {str(self.pid)}) has 'threads_exit' flag set and cannot "
                        f"be used")

        stdout: str | list[str]
        stderr: str | list[str]
        if capture_output:
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
                    except Exception as err:
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
            sout = "".join(output[0]).rstrip()
            serr = "".join(output[1]).rstrip()
            self._dbg("ProcessBase.wait(): returning: exitcode %s, stdout:\n%s\nstderr:\n%s",
                      str(exitcode), sout, serr)

        return ProcWaitResultType(stdout=stdout, stderr=stderr, exitcode=exitcode)

    def _dbg(self, fmt: str, *args: Any):
        """Print a debugging message."""

        if self.debug:
            pfx = ""
            if self.debug_id:
                pfx += f"{self.debug_id}: "
            if self.pid is not None:
                pfx += f"PID {self.pid}: "
            _LOG.debug(pfx + fmt, *args)

    def poll(self) -> int | None:
        """
        Check if the process is still running.

        Returns:
            None: If the process is still running.
            int: The exit status of the process if it has terminated.
        """

        raise NotImplementedError("ProcessBase.poll()")

    def get_cmd_failure_msg(self,
                            stdout: str | list[str],
                            stderr: str | list[str],
                            exitcode: int | None,
                            timeout: int | float | None = None,
                            startmsg: str | None = None,
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
                  command: str,
                  cwd: str | None = None,
                  shell: bool = True,
                  intsh: bool = False,
                  stdin: IO | str | None = None,
                  stdout: IO | str | None = None,
                  stderr: IO | str | None = None) -> ProcessBase:
        """
        Execute a command asynchronously without waiting for it to complete.

        Args:
            command: The command to execute.
            cwd: The working directory for the process.
            shell: Whether to execute the command through a shell.
            intsh: If True, use an existing interactive shell or create a new one. Only one
                   asynchronous process can run in an interactive shell at a time. It takes less
                   time to start a new process in an existing interactive shell, because it does not
                   require creating a new shell.
            stdin: Standard input stream for the process. Can be a file-like object or a file path.
            stdout: Standard output stream for the process. Can be a file-like object or a file
                    path.
            stderr: Standard error stream for the process. Can be a file-like object or a file path.

        Returns:
            A process object (subclass of 'ProcessBase') representing the asynchronous process.
        """

        raise NotImplementedError("ProcessManagerBase.run_async()")

    def run(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
            output_fobjs=(None, None), cwd=None, shell=True, intsh=None) -> ProcWaitResultType:
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
                           the second element of the tuple will be ignored and all the output will
                           be echoed to the first element. By default the command output is not
                           echoed anywhere.
          * cwd - the working directory of the process.
          * shell - whether the command should be run via shell.
          * intsh - whether the command should run in an already running interactive shell or in a
                    new shell. The former should be more efficient.

        This function returns the 'ProcWaitResultType' named tuple of '(exitcode, stdout, stderr)'
        elements.
          * 'stdout' - stdout executed command.
          * 'stderr' - stdout executed command.
          * 'exitcode' - exit code of the executed command.

        If the 'mix_output' argument is 'True', the 'stderr' part of the returned tuple will be an
        empty string.  If the 'capture_output' argument is not 'True', the 'stdout' and 'stderr'
        parts of the returned tuple will be empty strings.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.run")

    def run_verify(self, command, timeout=None, capture_output=True, mix_output=False, join=True,
                   output_fobjs=(None, None), cwd=None, shell=True, intsh=None):
        """
        Similar as the "run()" method, but and raises the 'Error' exception if the command has
        failed.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.run_verify")

    @staticmethod
    def _rsync_add_debug_opts(opts):
        """Add the '-v' option to rsync options 'opts' if debug-level logging is enabled."""

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if opts:
                opts = f"{opts} -v"
            else:
                opts = "-v"

        return opts

    @staticmethod
    def _rsync_debug_log(stdout):
        """
        If debug-level logging is enabled, log the 'stdout' output of the 'rsync' command.
        """

        if stdout and _LOG.getEffectiveLevel() == Logging.DEBUG:
            _LOG.debug("rsync output:\n%s", stdout)

    def rsync(self, src, dst, opts="-rlD", remotesrc=False, remotedst=False):
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
          * D - preserve device nodes and others special files.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.rsync")

    def _command_not_found(self, cmd, errmsg=None, toolname=None):
        """
        This method is called when command 'cmd' could not be executed be it was not found. This
        method formats a helpful error message and returns an exception object.
        """
        from pepclibs.helperlibs import ToolChecker # pylint: disable=import-outside-toplevel

        pkgname = None
        if not toolname:
            # Get the tool (program) name.
            toolname = cmd.split()[0].split("/")[-1]

        try:
            # Try to resolve tool name to the OS package name.
            with ToolChecker.ToolChecker(self) as tchk:
                pkgname = tchk.tool_to_pkg(toolname)
        except BaseException as err: # pylint: disable=broad-except
            _LOG.debug("failed to format the command package suggestion: %s", err)

        if pkgname:
            what = f"'{pkgname}' OS package"
        else:
            what = f"'{toolname}' program"

        msg = f"cannot execute the following command{self.hostmsg}:\n  {cmd}\n"
        if errmsg:
            msg += f"The error is:\n{Error(errmsg).indent(2)}\n"
        else:
            msg += "Command not found\n"
        msg += f"Try to install the {what}{self.hostmsg}"

        return ErrorNotFound(msg)

    def get_cmd_failure_msg(self, cmd, stdout, stderr, exitcode, timeout=None, startmsg=None,
                            failed=True):
        """
        Format and return the command failure message. The arguments are as follows.
            * cmd - the failed command.
            * stdout - standard output of the failed command.
            * stderr - standard error of the failed command.
            * exitcode - exit code of the failed command.
            * timeout - command time out.
            * startmsg - the first line of the resulting message.
            * failed - if True, consider the command as failed, otherwise consider it as just
                       finished.
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

        if not startmsg:
            startmsg = ""
        else:
            startmsg += "\n"

        if self.is_remote:
            startmsg += f"Ran the following command on host '{self.hostname}', but it " \
                        f"{exitcode_msg}:"
        else:
            startmsg += f"The following command {exitcode_msg}:"

        result = f"{startmsg}\n  {cmd}"
        if msg:
            result += f"\n\n{msg.strip()}"
        return result

    def open(self, path, mode):
        """
        Open a file on the at 'path' and return a file-like object. The arguments are the same as in
        the builtin Python 'open()' function.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.open")

    def read(self, path, must_exist=True):
        """
        Read file at path 'path'. The arguments are as follows.
          * path - path to the file to read.
          * must_exist - if file 'path' does not exist, raise the 'ErrorNotFound' error if
                         'must_exist' is 'True'. Otherwise, return 'None' without raising an
                         exception.
        """

        try:
            with self.open(path, "r") as fobj:
                val = fobj.read()
        except ErrorNotFound as err:
            if must_exist:
                raise ErrorNotFound(f"file '{path}' does not exist{self.hostmsg}") from err
            return None

        return val

    def get_python_path(self):
        """
        Some FS operations have to execute python scripts. This method finds and returns python
        interpreter path.
        """

        if self._python_path:
            return self._python_path

        # The paths to try.
        paths = ("/usr/bin/python", "/usr/bin/python3", "python", "python3")
        for path in paths:
            try:
                self.run_verify(f"{path} --version")
            except Error:
                continue

            self._python_path = path
            return Path(path)

        paths_descr = "\n * " + "\n * ".join(paths)
        raise ErrorNotFound(f"python interpreter was not found{self.hostmsg}.\n"
                            f"Checked the following paths:{paths_descr}")

    def shell_test(self, path, opt):
        """
        Run the shell 'test' command against path 'path'. The 'opt' argument specifies the 'test'
        command options. For example, pass '-f' to run 'test -f' which returns 0 if 'path' exists
        and is a regular file and 1 otherwise.
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

    def mkdir(self, dirpath, parents=False, exist_ok=False):
        """
        Create a directory. The a arguments are as follows.
          * dirpath - path to the directory to create.
          * parents - if 'True', the parent directories are created as well.
          * exist_ok - if the directory already exists, this method raises an exception if
                       'exist_ok' is 'True', and it returns without an error if 'exist_ok' is
                       'False'.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.mkdir")

    def mkfifo(self, path, exist_ok=False):
        """
        Create a named pipe. The a arguments are as follows.
          * path - path to the named pipe to create.
          * exist_ok - if the named pipe already exists, this method raises an exception if
                       'exist_ok' is 'True', and it returns without an error if 'exist_ok' is
                       'False'.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.mkdir")

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

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.lsdir")

    def exists(self, path):
        """Returns 'True' if path 'path' exists."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.exists")

    def is_file(self, path):
        """Returns 'True' if path 'path' exists an it is a regular file."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.is_file")

    def is_dir(self, path):
        """Returns 'True' if path 'path' exists an it is a directory."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.is_dir")

    def is_exe(self, path):
        """Returns 'True' if path 'path' exists an it is an executable file."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.is_exe")

    def is_socket(self, path):
        """Returns 'True' if path 'path' exists an it is a Unix socket file."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.is_socket")

    def get_mtime(self, path):
        """Returns the modification time of a file or directory at path 'path'."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.get_mtime")

    def unlink(self, path):
        """Remove a file a path 'path'."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.rmtree")

    def rmtree(self, path):
        """
        Recursively remove a file or directory at path 'path'. If 'path' is a symlink, the link is
        removed, but the target of the link does not get removed.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.rmtree")

    def abspath(self, path, must_exist=True):
        """
        Returns absolute real path for 'path'. The arguments are as follows.
          * path - the path to resolve into the absolute real (no symlinks) path.
          * must_exist - if 'path' does not exist, raise and exception when 'must_exist' is 'True',
                         otherwise returns the 'path' value.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.abspath")

    def mkdtemp(self, prefix: str | None  = None, basedir: Path | None = None) -> Path:
        """
        Create a temporary directory and return its path. The arguments are as follows.
          * prefix - specifies the temporary directory name prefix.
          * basedir - path to the base directory where the temporary directory should be created.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.mkdtemp")

    def get_envar(self, envar):
        """Return the value of the environment variable 'envar'."""

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.get_envar")

    def which(self, program, must_find=True):
        """
        Find and return full path to a program 'program' by searching it in '$PATH'. The arguments
        are as follows.
          * program - name of the program to find the path to.
          * must_find - if 'True', raises the 'ErrorNotFound' exception if the program was not
                        found, otherwise returns 'None' without raising the exception.
        """

        # pylint: disable=unused-argument
        raise NotImplementedError("ProcessManagerBase.which")
