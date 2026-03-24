#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the '--force-color' option."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import sys
import typing
from io import StringIO

import pytest

from pepclibs.helperlibs import Logging
from pepctools import _Pepc
from tests import common

if typing.TYPE_CHECKING:
    from typing import Generator
    from tests.common import CommonTestParamsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Yield a dictionary with testing parameters.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman:
        params = common.build_params(pman)
        yield params

def _run_pepc_capture_output(args: str, pman: ProcessManagerType) -> str:
    """
    Run pepc command and capture combined stdout and stderr output.

    Args:
        args: The command-line arguments, e.g., '-d topology info --cpus 0'.
        pman: The process manager object that specifies the host to run the command on.

    Returns:
        The captured combined output (stdout + stderr) as a string.
    """

    stdout_buf = StringIO()
    stderr_buf = StringIO()
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    saved_argv = sys.argv.copy()

    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        sys.argv = [_Pepc.__file__] + args.split()

        # Reconfigure the logger to pick up the new sys.argv, stdout, and stderr.
        # This is necessary because the logger is configured at module import time.
        log = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc")
        log.configure(prefix=_Pepc.TOOLNAME, info_stream=stdout_buf, error_stream=stderr_buf)

        _Pepc.do_main(pman=pman)
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
        sys.argv = saved_argv

        # Restore the logger configuration with the original streams.
        log = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc")
        log.configure(prefix=_Pepc.TOOLNAME, info_stream=saved_stdout, error_stream=saved_stderr)

    # Return combined output (info messages from stdout + debug/error from stderr).
    return stdout_buf.getvalue() + stderr_buf.getvalue()

def test_force_color(params: CommonTestParamsTypedDict):
    """
    Test that '--force-color' option enables ANSI color codes in non-TTY output.

    Notes:
        - INFO level messages are never colored, so we test with debug (`-d`) mode.
    """

    pman = params["pman"]

    # ANSI color code pattern (e.g., \x1b[32m, \x1b[1;33m, \x1b[0m for reset).
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')

    # Test 1: Run without --force-color in debug mode, output to StringIO (non-TTY).
    # Should NOT contain color codes.
    output_no_color = _run_pepc_capture_output("-d topology info --cpus 0", pman)
    has_color_codes = bool(ansi_pattern.search(output_no_color))

    assert not has_color_codes, \
        "Output to non-TTY should not contain ANSI color codes without --force-color"

    # Test 2: Run with --force-color in debug mode, output to StringIO (non-TTY).
    # Should contain color codes.
    output_with_color = _run_pepc_capture_output("--force-color -d topology info --cpus 0", pman)
    has_color_codes = bool(ansi_pattern.search(output_with_color))

    assert has_color_codes, \
        "Output to non-TTY with --force-color should contain ANSI color codes"
