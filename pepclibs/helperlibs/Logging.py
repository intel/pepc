# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains helper functions related to logging.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import logging
import traceback
from typing import NoReturn, Any, IO, cast
from pathlib import Path
try:
    # It is OK if 'colorama' is not available, we only lose message coloring.
    import colorama
    colorama_imported = True
except ImportError:
    colorama_imported = False
from pepclibs.helperlibs.Exceptions import Error

# Log levels.
#   * INFO: No prefixes, just the message.
#   * NOTICE: An INFO message, but with a prefix.
#   * DEBUG, WARNING, ERROR, CRITICAL: Also have the prefix.
#   * ERRINFO: An ERROR message, but without a prefix.
INFO = logging.INFO
NOTICE = logging.INFO + 1
DEBUG = logging.DEBUG
WARNING = logging.WARNING
ERROR = logging.ERROR
ERRINFO = logging.ERROR + 1
CRITICAL = logging.CRITICAL

# Name of the main logger instance. Other project loggers are supposed to be children of this one.
MAIN_LOGGER_NAME = "main"

# The default prefix for debug messages.
_DEFAULT_DBG_PREFIX = "[%(created)f] [%(asctime)s] [%(module)s,%(lineno)d]"

class _MyFormatter(logging.Formatter):
    """
    A custom formatter for logging messages. Provides different message formats for different log
    levels.
    """

    def __init__(self,
                 prefix: str | None = None,
                 prefix_debug: str | None = None,
                 colors: dict[int, int] | None = None):
        """
        Initialize the custom logging formatter.

        Args:
            prefix: Prefix for non-info and non-debug messages. Info messages go without any
                    formatting. By default, the prefix is just the log level name.
            prefix_debug: Prefix for debug messages. The default value is '_DEFAULT_DBG_PREFIX'.
            colors: A dictionary containing colorama color codes to use for 'prefix' and
                    'prefix_debug'.
        """

        logging.Formatter.__init__(self, "%(levelname)s: %(message)s", "%H:%M:%S")

        self._prefix = ""
        self._prefix_debug = ""

        self._myfmt: dict[int, str] = {}

        if not colors or not colorama:
            colors = {}

        self._colors = colors

        self.set_prefix(prefix=prefix, prefix_debug=prefix_debug)

    def set_prefix(self, prefix: str | None = None, prefix_debug: str | None = None):
        """
        Set the prefix for messages.

        Args:
            prefix: Prefix for non-info and non-debug messages. Info messages go without any
                    formatting. By default, the prefix is just the log level name.
            prefix_debug: Prefix for debug messages. The default value is '_DEFAULT_DBG_PREFIX'.
        """

        def _start(level):
            """
            Return the "start color output" code for the given log level.

            Args:
                level: The log level for which to get the "start color" code.

            Returns:
                str: The "start color output" code as a string.
            """
            return str(self._colors.get(level, ""))

        def _end(level):
            """
            Return the "end color output" code for the given log level.

            Args:
                level: The log level for which to get the "end color" code.

            Returns:
                str: The "end color output" code as a string.
            """

            if level in self._colors:
                return str(colorama.Style.RESET_ALL)
            return ""

        if not prefix:
            prefix = ""
        if prefix:
            prefix += ": "

        self._prefix = prefix

        for lvl, pfx in ((WARNING, "warning"), (ERROR, "error"), (CRITICAL, "critical error"),
                         (NOTICE, "notice")):
            if not prefix:
                pfx = pfx.title()
            self._myfmt[lvl] = _start(lvl) + prefix + pfx + _end(lvl) + ": %(message)s"

        # Debug messages formatting.
        lvl = DEBUG
        if prefix_debug is None:
            prefix_debug = _DEFAULT_DBG_PREFIX
        if not prefix_debug:
            prefix_debug = ""
        else:
            prefix_debug += ": "

        self._prefix_debug = prefix_debug

        self._myfmt[lvl] = prefix_debug + "%(message)s"
        self._myfmt[lvl] = self._myfmt[lvl].replace("[", "[" + _start(lvl))
        self._myfmt[lvl] = self._myfmt[lvl].replace("]", _end(lvl) + "]")

        # Leave the info messages without any formatting.
        self._myfmt[ERRINFO] = self._myfmt[INFO] = "%(message)s"

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record. Prefix debugging messages with a timestamp and keep info messages
        unchanged.

        Args:
            record: The log record to format.

        Returns:
            str: The formatted log record.
        """

        # pylint: disable=protected-access
        self._style._fmt = self._myfmt[record.levelno]
        return logging.Formatter.format(self, record)

class _MyFilter(logging.Filter):
    """A custom filter which allows only certain log levels to go through."""

    def __init__(self, let_go):
        """
        Initialize the logging filter.

        Args:
            let_go: A list of logging levels to let go through the filter.
        """

        logging.Filter.__init__(self)
        self._let_go = let_go

    def filter(self, record):
        """
        Filter out all log levels except the ones specified by the user.

        Args:
            record: The log record to filter.

        Returns:
            bool: True if the log level of the record is in the allowed levels, False otherwise.
        """

        if record.levelno in self._let_go:
            return True
        return False

class Logger(logging.Logger):
    """
    A custom logger class that provides the following functionality on top of the standard logger:
      * Message coloring.
      * Different prefixes for different log levels.
      * Debug messages with timestamps and file line numbers.
      * Error messages with stack traces.
      * The NOTICE and ERRINFO log levels.
      * The 'warn_once()' method.
      * The 'error_out()' method.
      * The 'debug_print_stacktrace()' method.
    """

    def __init__(self, name: str | None = None):
        """
        Setup and return a configured logger.

        Args:
            name: The name of the logger (same as in 'logging.Logger()').
        """

        self.prefix = ""
        self.colored = True
        self.info_stream = sys.stdout
        self.error_stream = sys.stderr

        self._colors: dict[int, int] = {}
        self._seen_msgs: set = set()
        self._formatters: list[_MyFormatter] = []

        if not name:
            name = "default"

        super().__init__(name)

    def _init_colors(self):
        """
        """

        self._colors[DEBUG] = colorama.Fore.GREEN
        self._colors[WARNING] = colorama.Fore.YELLOW + colorama.Style.BRIGHT
        self._colors[NOTICE] = colorama.Fore.CYAN + colorama.Style.BRIGHT
        self._colors[ERROR] = self._colors[CRITICAL] = colorama.Fore.RED + colorama.Style.BRIGHT

    def configure(self,
                  prefix: str | None = None,
                  level: int | None = None,
                  colored: bool | None = None,
                  info_stream: IO[str] = sys.stdout,
                  error_stream: IO[str] = sys.stderr):
        """
        Configure the logger.

        Args:
            prefix: The prefix for log messages, used for all levels except 'INFO' and 'ERRINFO'.
            level: The default log level. If not provided, it is automatically detected based on the
                   presence of '-d' (debug) and '-q' (quiet) command line options.
            colored: Whether to use colored output. By default, colored output is used for TTYs and
                     uncolored output for non-TTYs, unless the '--force-color' command line option
                     is specified, in which case colored output is used for non-TTYs as well.
            info_stream: The stream for 'INFO' level messages. Default is 'sys.stdout'.
            error_stream: The stream for messages of all levels except 'INFO'. Default is
                          'sys.stderr'.

        Returns:
            Logger: The configured logger instance.
        """

        if not prefix:
            prefix = ""

        self.prefix = prefix

        if not level:
            # Change log level names.
            if "-q" in sys.argv:
                level = WARNING
            elif "-d" in sys.argv:
                level = DEBUG
            else:
                level = INFO

        self.setLevel(level)

        if not colorama:
            colored = False

        if colored is None:
            if "--force-color" in sys.argv:
                colored = True
            else:
                colored = info_stream.isatty() and error_stream.isatty()

        self.colored = colored

        if colored:
            self._init_colors()

        # Remove existing handlers.
        self.handlers = []
        self._formatters = []

        formatter = _MyFormatter(prefix=self.prefix, colors=self._colors)
        self._formatters.append(formatter)

        stream_handler = logging.StreamHandler(info_stream)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(_MyFilter([INFO]))
        self.addHandler(stream_handler)

        stream_handler = logging.StreamHandler(error_stream)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(_MyFilter([DEBUG, WARNING, NOTICE, ERROR, ERRINFO, CRITICAL]))
        self.addHandler(stream_handler)

        return self

    def configure_log_file(self, fpath: Path, contents: str | None = None):
        """
        Configure the logger to mirror all stdout and stderr messages to the specified log file.

        Args:
            fpath: The file path to mirror the output to.
            contents: The initial contents to write to the log file.
        """

        if contents:
            try:
                with fpath.open("w+", encoding="utf-8") as fobj:
                    fobj.write(contents)
            except OSError as err:
                msg = Error(str(err)).indent(2)
                raise Error(f"Failed to write to '{fpath}':\n{msg}") from None

        if self.colored:
            colors = self._colors
        else:
            colors = {}

        formatter = _MyFormatter(prefix=self.prefix, colors=colors)
        self._formatters.append(formatter)

        file_handler = logging.FileHandler(str(fpath))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_MyFilter([DEBUG, WARNING, NOTICE, ERROR, ERRINFO, CRITICAL]))
        self.addHandler(file_handler)

        file_handler = logging.FileHandler(str(fpath))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_MyFilter([INFO]))
        self.addHandler(file_handler)

        return fpath

    def set_prefix(self, prefix: str):
        """
        Set the prefix for log messages.

        Args:
            prefix: The prefix string to be added to log messages.
        """

        self.prefix = prefix

        for formatter in self._formatters:
            formatter.set_prefix(prefix=prefix)

    def _print_traceback(self, level: int = ERROR):
        """
        Print an exception or stack traceback.

        Args:
            level: The logging level at which to log the traceback. Defaults to ERROR.
        """

        tback = []

        if sys.exc_info()[0]:
            lines = traceback.format_exc().splitlines()
        else:
            lines = [line.strip() for line in traceback.format_stack()]

        idx = 0
        last_idx = len(lines) - 1
        while idx < len(lines):
            if lines[idx].startswith('  File "'):
                idx += 2
                last_idx = idx
            else:
                idx += 1

        tback = lines[0:last_idx]

        if tback:
            if colorama_imported:
                dim = colorama.Style.RESET_ALL + colorama.Style.DIM
                undim = colorama.Style.RESET_ALL
            else:
                dim = undim = ""
            self.log(level, "--- Debug trace starts here ---")
            tb = "\n".join(tback)
            self.log(level, "%sAn error occurred, here is the traceback:\n%s%s", dim, tb, undim)
            self.log(level, "--- Debug trace ends here ---\n")

    def error_out(self, fmt: str, *args: Any, print_tb: bool = False) -> NoReturn:
        """
        Print an error message and terminate program execution.

        Args:
            fmt: The error message format string.
            *args: The arguments to format the error message.
            print_tb: If True, print the stack trace. Defaults to False.

        Notes:
            If debugging is enabled, the stack trace is printed regardless of the 'print_tb' value.

        Raises:
            SystemExit: Terminates the program with exit code 1.
        """

        if args:
            errmsg = fmt % args
        else:
            errmsg = str(fmt)

        if print_tb or self.getEffectiveLevel() == DEBUG:
            self._print_traceback(level=ERRINFO)

        self.error(errmsg)

        raise SystemExit(1)

    def debug_print_stacktrace(self):
        """Print the stack trace if debugging is enabled."""

        if self.getEffectiveLevel() == DEBUG:
            self._print_traceback(level=DEBUG)

    def notice(self, fmt: str, *args: Any):
        """
        Log a message with level 'NOTICE'.

        Args:
            fmt: The format string for the log message.
            *args: The arguments to format the log message.
        """

        self.log(NOTICE, fmt, *args)

    def warn_once(self, fmt: str, *args: Any):
        """
        Logs a warning message, ensuring that the same message is not logged more than once.

        Args:
            fmt: The format string for the warning message.
            *args: The arguments to format the warning message.
        """

        import inspect # pylint: disable=import-outside-toplevel

        caller_frame = inspect.stack()[1][0]
        if caller_frame:
            caller_info = inspect.getframeinfo(caller_frame)
            msg_hash = f"{caller_info.filename}:{caller_info.lineno}"
        else:
            raise Error("python interpretor does not support 'inspect.stack()'")

        if msg_hash not in self._seen_msgs:
            self._seen_msgs.add(msg_hash)
            self.log(WARNING, fmt, *args)

logging.setLoggerClass(Logger)

def getLogger(name: str | None = None) -> Logger:
    """
    Get a logger by name (similar to 'logging.getLogger()').

    Args:
        name: The name of the logger.

    Returns:
        Logger: The logger instance.
    """

    # Note, because of 'setLoggerClass()', this will return a 'Logger' instance (except for the root
    # logger case).
    return cast(Logger, logging.getLogger(name=name))
