# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Types related to process manager modules.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import NamedTuple, TypedDict
from pathlib import Path

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
