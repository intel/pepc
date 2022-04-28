# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides convenient API for running Linux 'dmesg' tool.
"""

# pylint: disable=redefined-outer-name

import itertools
import difflib
import logging
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers

_LOG = logging.getLogger()

class Dmesg:
    """This class provides convenient API to the 'dmesg' tool."""

    def run(self, join=True, strip=False, capture=False):
        """
        Execute the 'dmesg' program and return the output. The arguments are as follows.
          * join - if 'True', return the output as a single string, otherwise return it as a list of
                   lines.
          * strip - whether the output should be stripped from the trailing newlines.
          * capture - save the output in the 'captured' attribute in order to use it for generating
                      diffs (see 'get_new_messages()').
        """

        output = self._pman.run_verify("dmesg", join=False)[0]

        if capture:
            self.captured = output

        if join:
            output = "".join(output)
            if strip:
                return output.strip()
            return output

        if strip:
            return [line.strip() for line in output]

        return output

    def get_new_messages(self, join=True, strip=False):
        """
        Run the 'dmesg' program, compare the output to the previously captured 'dmesg' output, and
        return the new lines (those present in the most recent 'dmesg' output but absent from the
        previously captured 'dmesg' output). The arguments are the same as in 'run()'.
        """

        new_output = self.run(join=False, strip=False, capture=False)

        new_lines = []
        diff = difflib.unified_diff(self.captured, new_output, n=0,
                                    fromfile=f"{self._pman.hostname}-dmesg-before",
                                    tofile=f"{self._pman.hostname}-dmesg-after")

        for line in itertools.islice(diff, 2, None):
            if line[0] == "+":
                new_lines.append(line[1:])

        if join:
            new_lines = "".join(new_lines)
            if strip:
                return new_lines.strip()
            return new_lines

        if strip:
            return [line.strip() for line in new_lines]
        return new_lines

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to run 'dmesg' on.
        """

        self._pman = pman
        self._close_pman = pman is None

        self.captured = []

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Stop the measurements."""
        ClassHelpers.close(self, close_attrs=("_pman",))

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the run-time context."""
        self.close()
