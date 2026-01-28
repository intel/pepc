# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API to the Linux 'dmesg' tool.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import itertools
import difflib
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class Dmesg(ClassHelpers.SimpleCloseContext):
    """Provide API to the Linux 'dmesg' tool."""

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. Use a local process
                  manager if not provided.
        """

        self._close_pman = pman is None

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        self.captured: list[str] = []

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_pman",))

    def run(self, join: bool = True, strip: bool = False, capture: bool = False) -> str | list[str]:
        """
        Run the 'dmesg' command and return its output.

        Args:
            join: If True, return the output as a single string, otherwise, return as a list of
                  lines.
            strip: If True, remove trailing newlines from the output.
            capture: If True, save the output in the 'captured' attribute for later use (e.g.,
                     generating diffs).

        Returns:
            The output of the 'dmesg' command, either as a single string or a list of lines,
            depending on 'join'.
        """

        output, _ = self._pman.run_verify_nojoin("dmesg")

        if capture:
            self.captured = output

        if join:
            joined_output = "".join(output)
            if strip:
                return joined_output.strip()
            return joined_output

        if strip:
            return [line.strip() for line in output]
        return output

    def get_new_messages(self, join: bool = True, strip: bool = False) -> str | list[str]:
        """
        Run the 'dmesg' command and return new log messages since the last capture.

        Compare the current output of 'dmesg' to the previously captured output, and extract lines
        that are present in the latest output but absent from the previous one. This helps identify
        new kernel messages.

        Args:
            join: If True, join the new lines into a single string. If False, return a list of
                  lines.
            strip: If True, strip leading and trailing whitespace from each line or the joined
                   string.

        Returns:
            New 'dmesg' messages as a single string (if join is True) or as a list of lines.
        """

        new_output = cast(list[str], self.run(join=False, strip=False, capture=False))

        new_lines: list[str] = []
        diff = difflib.unified_diff(self.captured, new_output, n=0,
                                    fromfile=f"{self._pman.hostname}-dmesg-before",
                                    tofile=f"{self._pman.hostname}-dmesg-after")

        for line in itertools.islice(diff, 2, None):
            if line[0] == "+":
                new_lines.append(line[1:])

        if join:
            joined_new_lines = "".join(new_lines)
            if strip:
                return joined_new_lines.strip()
            return joined_new_lines

        if strip:
            return [line.strip() for line in new_lines]
        return new_lines
