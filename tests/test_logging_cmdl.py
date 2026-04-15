#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test logging-related command-line options such as '-q', '-d', and '--debug-modules'."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
from pathlib import Path
from tests import _Common
from pepclibs.helperlibs import TestRunner
from pepclibs.helperlibs.Exceptions import Error
from pepctools import _Pepc

# Path to the TPMI debugfs dump test data directory.
_TPMI_DEBUGFS_DUMP: Path = _Common.get_test_data_base() / "test_tpmi_nohost" / "debugfs-dump"

# Debug messages use the default prefix: [timestamp] [time] [module,lineno].
# Example: "[1745987654.12] [12:34:56] [TPMI,226] ..."
# 're.MULTILINE' makes '^' match at the start of each line, not just the start of the string.
_DEBUG_LINE_REGEX = re.compile(r"^\[[\d.]+\] \[[\d:]+\] \[(\w+),\d+\]", re.MULTILINE)

# ANSI color escape sequence pattern (e.g., '\x1b[32m', '\x1b[1;33m', '\x1b[0m').
_ANSI_COLOR_REGEX = re.compile(r"\x1b\[[0-9;]*m")

def _run(options: str = "",
         exp_exc: type[Exception] | None = None,
         capture_output: bool = False) -> tuple[str, str]:
    """
    Run 'pepc tpmi ls --base <dump> <options>' and return (stdout, stderr).

    Args:
        options: Options to append to the command, e.g. '-d' or '-q -d'.
        exp_exc: Expected exception type. If set, the call must raise this exception.
        capture_output: Whether to capture and return stdout/stderr.

    Returns:
        A tuple of (stdout, stderr) strings.

    Notes:
        - 'tpmi ls --base' is used as the test vehicle because it does not require root access,
          a real host, or emulation. It reads from a local debugfs dump directory.
    """

    cmd = f"tpmi ls --base {_TPMI_DEBUGFS_DUMP}"
    arguments = f"{cmd} {options}" if options else cmd
    return TestRunner.run_tool(_Pepc, _Pepc.TOOLNAME, arguments, pman=None, exp_exc=exp_exc,
                               capture_output=capture_output)

def test_quiet():
    """
    Test that '-q' suppresses all output.
    """

    stdout, stderr = _run("-q", capture_output=True)

    assert not stdout, "Expected no stdout output with '-q'"
    assert not stderr, "Expected no stderr output with '-q'"

def _get_debug_modules(text: str) -> set[str]:
    """
    Return the set of module names that appear in debug log lines in 'text'.

    Args:
        text: Log output text to scan for debug messages.

    Returns:
        A set of module name strings extracted from debug message prefixes.
    """

    return set(_DEBUG_LINE_REGEX.findall(text))

def test_debug():
    """
    Test that '-d' produces debug messages in stderr.
    """

    _, stderr = _run("-d", capture_output=True)

    assert _get_debug_modules(stderr), "Expected debug messages in stderr with '-d'"

def test_debug_modules():
    """
    Test that '--debug-modules' limits debug output to the specified module.

    Run 'tpmi ls' with full debug output and then with '--debug-modules TPMI'. The filtered
    output must contain only 'TPMI' debug messages, while the unfiltered output must contain
    debug messages from more than one module.
    """

    _, stderr_all = _run("-d", capture_output=True)
    _, stderr_filtered = _run("-d --debug-modules TPMI", capture_output=True)

    modules_all = _get_debug_modules(stderr_all)
    modules_filtered = _get_debug_modules(stderr_filtered)

    assert len(modules_all) > 1, \
           "Expected debug messages from multiple modules with '-d' and no '--debug-modules'"
    assert modules_filtered == {"TPMI"}, \
           f"Expected only 'TPMI' debug messages with '--debug-modules TPMI', but got: " \
           f"{modules_filtered}"

def test_quiet_debug_conflict():
    """
    Test that combining '-q' and '-d' raises an error.
    """

    _run("-q -d", exp_exc=Error)

def test_debug_modules_requires_debug():
    """
    Test that '--debug-modules' without '-d' raises an error.
    """

    _run("--debug-modules TPMI", exp_exc=Error)

def test_no_color():
    """
    Test that output to a non-TTY does not contain ANSI color codes by default.

    Notes:
        - 'capture_output=True' redirects output to 'StringIO' buffers. 'StringIO.isatty()'
          returns 'False', making the logger treat the output as non-TTY automatically.
        - Debug mode ('-d') is used to generate enough output to check for color codes.
    """

    stdout, stderr = _run("-d", capture_output=True)

    assert not _ANSI_COLOR_REGEX.search(stdout + stderr), \
        "Expected no ANSI color codes in non-TTY output without '--force-color'"

def test_force_color():
    """
    Test that '--force-color' enables ANSI color codes in non-TTY output.

    Notes:
        - INFO level messages are never colored, so debug mode ('-d') is used to ensure colored
          output is produced when '--force-color' is active.
    """

    stdout, stderr = _run("--force-color -d", capture_output=True)

    assert _ANSI_COLOR_REGEX.search(stdout + stderr), \
        "Expected ANSI color codes in non-TTY output with '--force-color'"
