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
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import LocalProcessManager, ToolChecker

_LOG = logging.getLogger()

# A unique object used as the default value for the 'default' key in some functions.
_RAISE = object()

class Dmesg:
    """This class provides convenient API to the 'dmesg' tool."""

    def run(self, join=True, strip=False, capture=False, default=_RAISE):
        """
        Execute the 'dmesg' program and return the output. The arguments are as follows.
          * join - if 'True', return the output as a single string, otherwise return it as a list of
                   lines.
          * strip - whether the output should be stripped from the trailing newlines.
          * capture - save the output in the 'captured' attribute in order to use it for generating
                      diffs (see 'get_new_messages()').
          * default - the value to return in case of error (by default an exception is raised).
        """

        try:
            output = self._proc.run_verify("dmesg", join=False)[0]
        except Error as err:
            if default is _RAISE:
                raise
            _LOG.debug(err)
            return default

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

    def get_new_messages(self, join=True, strip=False, default=_RAISE):
        """
        Runs 'dmesg', compares the output to the last captured dmesg output, and returns the new
        lines (those ptresent in the most recent dmesg output but absent in the captured dmesg
        output). The arguments are the same as in 'run()'.
        """

        new_output = self.run(join=False, strip=False, capture=False, default=default)
        if new_output is default:
            return default

        new_lines = []

        diff = difflib.unified_diff(self.captured, new_output, n=0,
                                    fromfile=f"{self._proc.hostname}-dmesg-before",
                                    tofile=f"{self._proc.hostname}-dmesg-after")

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

    def __init__(self, proc=None, tchk=None):
        """
        The class constructor. The arguments are as follows.
          * proc - the process manager object that defines the host to run 'dmesg' on.
          * tchk - an optional 'ToolChecker.ToolChecker()' object which will be used for checking if
                   the required tools like 'dmesg' are present on the target host.
        """

        self._proc = proc
        self._tchk = tchk

        self._close_proc = proc is None
        self._close_tchk = tchk is None

        self.captured = []

        if not self._proc:
            self._proc = LocalProcessManager.LocalProcessManager()
        if not self._tchk:
            self._tchk = ToolChecker.ToolChecker(proc=self._proc)

        self._tchk.check_tool("dmesg")

    def close(self):
        """Stop the measurements."""

        for attr in ("_tchk", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the run-time context."""
        self.close()

def capture(proc):
    """
    This is a helper function for capturing the dmesg output and ignoring errors. The idea is that
    the caputred messaged then can be passed to 'get_new_messages()' in order to get new messages.

    This function returns the caputred dmesg messages that should be passed to 'get_new_messages()',
    and should not be used for anything else, as the messages format is implementation-specific. So
    treat the return value as an opaque object.

    The 'proc' argument is the process manager object that defines the host to run 'dmesg' on.
    """

    with Dmesg(proc) as dmesg:
        if dmesg.run(join=False, strip=False, capture=True, default=None) is None:
            return None
        return dmesg.captured

def get_new_messages(captured, proc, join=True, strip=False):
    """
    Return new dmesg messages since the previous 'capture()' invocation. The 'captured' argument is
    the object previously returned by 'capture()'.

    If an error occures and dmesg output cannot be captured, this function returns an empty string
    (or empty list if 'join' is 'False').

    The 'proc' argumens is the process manager object that defines the host to run 'dmesg' on. The
    'join' and 'strip' arguments are the same as in 'dmesg.run()'.
    """

    if captured is None:
        new_lines = None
    else:
        with Dmesg(proc) as dmesg:
            dmesg.captured = captured
            new_lines = dmesg.get_new_messages(join=join, strip=strip, default=None)

    if new_lines is None:
        return "" if join else []

    return new_lines
