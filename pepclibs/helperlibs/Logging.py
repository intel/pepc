# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains helper functions related to logging.
"""

import sys
import types
import logging
import traceback
try:
    # It is OK if 'colorama' is not available, we only lose message coloring.
    import colorama
except ImportError:
    colorama = None
from pepclibs.helperlibs.Exceptions import Error # pylint: disable=unused-import

# Unlike all other log levels, 'INFO' does not add any prefix.
INFO = logging.INFO
# Same as 'INFO', but adds a "notice:" prefix.
NOTICE = logging.INFO + 1
DEBUG = logging.DEBUG
WARNING = logging.WARNING
ERROR = logging.ERROR
# Add the "ERRINFO" log lovel which is the same as "ERROR", but not prefixed.
ERRINFO = logging.ERROR + 1
CRITICAL = logging.CRITICAL

def _error_traceback(logger, msgformat, *args):
    """Print an error message occurred along with the traceback."""

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
        if colorama:
            dim = colorama.Style.RESET_ALL + colorama.Style.DIM
            undim = colorama.Style.RESET_ALL
        else:
            dim = undim = ""
        logger.log(ERRINFO, "--- Debug trace starts here ---")
        tb = "\n".join(tback)
        logger.log(ERRINFO, "%sAn error occurred, here is the traceback:\n%s%s", dim, tb, undim)
        logger.log(ERRINFO, "--- Debug trace ends here ---\n")

    if args:
        errmsg = msgformat % args
    else:
        errmsg = str(msgformat)
    logger.error(errmsg)

def _error_out(logger, msgformat, *args, print_tb=False):
    """
    Print an error message and terminate program execution. The optional 'print_tb' agument
    controls whether the stack trace should also be printed. Note, however, if debugging is enabled,
    the stack trace is printed out regardless of 'print_tb' value.
    """

    if print_tb or logger.getEffectiveLevel() == DEBUG:
        _error_traceback(logger, str(msgformat) + "\n", *args)
    else:
        if args:
            errmsg = msgformat % args
        else:
            errmsg = str(msgformat)
        logger.error(errmsg)

    raise SystemExit(1)

def _notice(logger, fmt, *args):
    """Just a convenient 'notice()' method for the logger."""
    logger.log(NOTICE, fmt, *args)

class _MyFormatter(logging.Formatter):
    """
    A custom formatter for logging messages. The reason we have it is to provide different message
    format for different log levels.
    """

    # pylint: disable=protected-access
    def __init__(self, prefix=None, colors=None):
        """
        The constructor. The arguments are as follows.
          * prefix' - the prefix for all non-info and non-debug messages. Default is no prefix. Info
                      messages come without any formating, debug messages have a prefix including
                      the time-stamp, module name, and line number.
          * colors - a dictionary containing colorama color codes for message time-staps and
                     prefixes.
        """

        def _start(level):
            """Return color code for log level 'level'."""
            return str(colors.get(level, ""))

        def _end(level):
            """Return the code for stopping coloring for log level 'level'."""
            if level in colors:
                return str(colorama.Style.RESET_ALL)
            return ""

        logging.Formatter.__init__(self, "%(levelname)s: %(message)s", "%H:%M:%S")

        if not prefix:
            prefix = ""
        self._prefix = prefix
        self._orig_fmt = self._style._fmt

        if not colors or not colorama:
            colors = {}

        self.myfmt = {}

        for lvl, pfx in ((WARNING, "warning"), (ERROR, "error"), (CRITICAL, "critical error"),
                         (NOTICE, "notice")):
            if not self._prefix:
                pfx = pfx.title()
            self.myfmt[lvl] = _start(lvl) + self._prefix + pfx + _end(lvl) + ": %(message)s"
        # Prefix debug messages with a green-colored time-stamp, module name and line number.
        lvl = DEBUG
        self.myfmt[lvl] = "[" + _start(lvl) + "%(asctime)s" + _end(lvl) + \
                          "] [%(module)s,%(lineno)d] " + self._style._fmt
        # Leave the info messages without any formatting.
        self.myfmt[ERRINFO] = self.myfmt[INFO] = "%(message)s"

    def format(self, record):
        """
        The formatter which which simply prefixes all debugging messages with a time-stamp and makes
        sure the info messages stay intact.
        """

        self._style._fmt = self.myfmt[record.levelno]
        return logging.Formatter.format(self, record)

class _MyFilter(logging.Filter):
    """A custom filter which allows only certain log levels to go through."""

    def __init__(self, let_go):
        """The constructor."""

        logging.Filter.__init__(self)
        self._let_go = let_go

    def filter(self, record):
        """Filter out all log levels except the ones user specified."""

        if record.levelno in self._let_go:
            return True
        return False

def setup_logger(prefix=None, loglevel=None, colored=None, info_stream=sys.stdout,
                 error_stream=sys.stderr, info_logfile=None, error_logfile=None):
    """
    Setup and return a logger.
      * prefix - usually the program name, but can be any prefix that will be used for "WARNING",
                 "ERROR" and "CRITICAL" log level messages. No prefix is used by default.
      * loglevel - the default log level. If not provided, this function initializes it depending on
                   the '-d' and '-q' command line options.
      * colored - whether the output should be colored or not. By default this function
                  automatically figures out the coloring by checking if the output file descriptors
                  are TTYs and whether the '--force-color" command line option is used.
      * info_stream - stream where messages with "INFO" level will be directed to. Default is
                      'sys.stdout'.
      * error_stream - same as 'info_stream', but will be used for all other logging levels. Default
                       is 'sys.stderr'.
      * info_logfile - path to the fiile where messages with "INFO" level will be directed to. If
                       both 'info_stream' and 'info_logfile' are provided, messages will go the
                       both.
      * error_logfile - same as 'info_logfile", but  will be used for all other logging levels.
    """

    if prefix:
        prefix = f"{prefix}: "

    if not loglevel:
        # Change log level names.
        if "-q" in sys.argv:
            loglevel = WARNING
        elif "-d" in sys.argv:
            loglevel = DEBUG
        else:
            loglevel = INFO

    if not colorama:
        colored = False

    if colored is None:
        if "--force-color" in sys.argv:
            colored = True
        else:
            colored = info_stream.isatty() and error_stream.isatty()

    logger = logging.getLogger()
    logger.colored = colored
    logger.setLevel(loglevel)

    colors = {}
    if colored:
        colors[DEBUG] = colorama.Fore.GREEN
        colors[WARNING] = colorama.Fore.YELLOW + colorama.Style.BRIGHT
        colors[NOTICE] = colorama.Fore.CYAN + colorama.Style.BRIGHT
        colors[ERROR] = colors[CRITICAL] = colorama.Fore.RED + colorama.Style.BRIGHT

    formatter = _MyFormatter(prefix=prefix, colors=colors)
    if colored:
        nocolor_formatter = _MyFormatter(prefix=prefix, colors={})
    else:
        nocolor_formatter = formatter

    # Remove existing handlers.
    logger.handlers = []

    where = logging.StreamHandler(error_stream)
    where.setFormatter(formatter)
    where.addFilter(_MyFilter([DEBUG, WARNING, NOTICE, ERROR, ERRINFO, CRITICAL]))
    logger.addHandler(where)

    where = logging.StreamHandler(info_stream)
    where.setFormatter(formatter)
    where.addFilter(_MyFilter([INFO]))
    logger.addHandler(where)

    if error_logfile:
        where = logging.FileHandler(error_logfile)
        where.setFormatter(nocolor_formatter)
        where.addFilter(_MyFilter([DEBUG, WARNING, NOTICE, ERROR, ERRINFO, CRITICAL]))
        logger.addHandler(where)

    if info_logfile:
        where = logging.FileHandler(info_logfile)
        where.setFormatter(nocolor_formatter)
        where.addFilter(_MyFilter([INFO]))
        logger.addHandler(where)

    logger.notice = types.MethodType(_notice, logger)
    logger.error_out = types.MethodType(_error_out, logger)

    return logger
