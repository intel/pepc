# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#                Antti Laakso <antti.laakso@intel.com>

"""Helper functions for running tools in tests."""

from __future__ import annotations

import sys
import typing
from io import StringIO

from pepclibs.helperlibs import Logging

if typing.TYPE_CHECKING:
    from types import ModuleType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _run_tool(tool: ModuleType,
              toolname: str,
              arguments: str,
              pman: ProcessManagerType | None,
              exp_exc: type[Exception] | None,
              ignore: dict[type[Exception], str]):
    """
    Run the tool and handle exceptions.

    Args:
        Arguments are the same as in 'run_tool()'.
    """

    try:
        tool.do_main(pman=pman)
    except Exception as err: # pylint: disable=broad-except
        err_type = type(err)
        msg = f"Command '{toolname} {arguments}' raised the following exception:\n" \
              f"- {type(err).__name__}({err})"
        if err_type in ignore and (not ignore[err_type] or ignore[err_type] in arguments):
            _LOG.debug(msg)
            return

        if exp_exc is None:
            assert False, msg

        if isinstance(err, exp_exc):
            return

        assert False, f"Command '{toolname} {arguments}' raised the following exception:\n" \
                      f"- {type(err).__name__}({err})\nbut it was expected to raise the following" \
                      f"exception:\n- {exp_exc.__name__}"

    if exp_exc is not None:
        assert False, f"Command '{toolname} {arguments}' did not raise the following " \
                      f"exception type:\n- {exp_exc.__name__}"

def run_tool(tool: ModuleType,
             toolname: str,
             arguments: str,
             pman: ProcessManagerType | None = None,
             exp_exc: type[Exception] | None = None,
             ignore: dict[type[Exception], str] | None = None,
             capture_output: bool = False) -> tuple[str, str]:
    """
    Run a tool with specified arguments and verify the outcome.

    Args:
        tool: The main Python module of the tool to run.
        toolname: The tool name used in error messages.
        arguments: Command-line arguments to pass to the tool (e.g., 'pstate info --cpus 0-43').
        pman: Process manager object specifying the host to run the tool on. Uses local host if not
              provided.
        exp_exc: Expected exception type. If provided, the test fails if the tool does not raise
                 this exception. If not provided, any exception is considered a test failure.
        ignore: Dictionary mapping exception types to command argument substrings. Exceptions
                matching both the type and substring are ignored.
        capture_output: Whether to capture and return stdout and stderr.

    Returns:
        Tuple of (stdout, stderr) strings. Returns empty strings when 'capture_output' is False.

    Notes:
        - When 'capture_output' is True, stdout and stderr are redirected to 'StringIO' buffers.
          'StringIO.isatty()' returns 'False', so the logger treats output as non-TTY and
          suppresses ANSI color codes unless '--force-color' is specified.
    """

    if not ignore:
        ignore = {}

    cmd = f"{tool.__file__} {arguments}"
    _LOG.debug("Running: %s", cmd)

    argv = cmd.split()
    saved_argv = sys.argv.copy()
    sys.argv = argv

    stdout_buf = None
    stderr_buf = None
    log = None
    saved_handlers = None
    saved_level = None

    try:
        if capture_output:
            stdout_buf = StringIO()
            stderr_buf = StringIO()
            log = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc")
            # Save existing handlers and log level to restore later (for test isolation).
            saved_handlers = log.handlers.copy()
            saved_level = log.level
            # Reconfigure logger to detect command-line flags in 'argv' (e.g., '--force-color').
            log.configure(prefix=toolname, argv=argv)
            log.add_info_stream(stdout_buf)
            log.add_error_stream(stderr_buf)

        _run_tool(tool, toolname, arguments, pman, exp_exc, ignore)
    finally:
        sys.argv = saved_argv
        if capture_output and log and stdout_buf and stderr_buf:
            log.remove_info_stream(stdout_buf)
            log.remove_error_stream(stderr_buf)
            # Restore the original handlers and log level to maintain test isolation.
            if saved_handlers is not None:
                log.handlers = saved_handlers
            if saved_level is not None:
                log.setLevel(saved_level)

    if capture_output and stdout_buf and stderr_buf:
        return (stdout_buf.getvalue(), stderr_buf.getvalue())
    return ("", "")
