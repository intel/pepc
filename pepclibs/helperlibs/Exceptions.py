# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Exception types used in this project.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path
from typing import Any, Match
import re

class Error(Exception):
    """The base class for all exceptions raised by this project."""

    def __init__(self, msg: str, *args: Any, **kwargs: Any):
        """
        Initialize the exception object..

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            **kwargs: Additional keyword arguments.
        """

        msg = str(msg)
        super().__init__(msg)

        for key, val in kwargs.items():
            setattr(self, key, val)

        if args:
            self.msg = msg % tuple(args)
        else:
            self.msg = msg

    def indent(self, indent: int | str, capitalize: bool = True) -> str:
        """
        Indent/prefix each line in the error message.

        Args:
            indent: Can be an integer or a string. If an integer, each line of the error message is
                    prefixed with the specified number of white spaces. If a string, each line is
                    prefixed with the specified string.
            capitalize: If True, ensures the message starts with a capital letter.

        Returns:
            str: The modified error message.
        """

        def capitalize_mobj(mobj: Match[str]):
            """
            Capitalize the intended/prefixed message.

            Args:
                mobj: The match object from a regex search.

            Returns:
                str: The capitalized version of the message.
            """

            return mobj.group(1) + mobj.group(2).capitalize()

        if isinstance(indent, int):
            pfx = " " * indent
        else:
            pfx = indent

        msg = pfx + self.msg.replace("\n", f"\n{pfx}")
        if capitalize:
            msg = re.sub(r"^(\s*)(\S)", capitalize_mobj, msg)

        return msg

    def __str__(self):
        """The string representation of the exception."""
        return self.msg

class ErrorTimeOut(Error):
    """Something timed out."""

class ErrorExists(Error):
    """Something already exists."""

class ErrorNotFound(Error):
    """Something was not found."""

class ErrorNotSupported(Error):
    """Feature/option/etc is not supported."""

class ErrorPermissionDenied(Error):
    """Something was not found."""

class ErrorBadFormat(Error):
    """Bad format of something, e.g., file contents."""

class ErrorVerifyFailed(Error):
    """Verification failed."""

    def __init__(self,
                 msg: str,
                 *args: Any,
                 cpu: int | None = None,
                 expected: Any | None = None,
                 actual: Any | None = None,
                 path: Path | None = None,
                 **kwargs: Any):
        """
        Initialize the exception object..

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            cpu: CPU number associated with the operation that failed the
                  verification.
            expected: The expected value or result of an operation.
            actual: The actual value or result of the operation, which was expected to be the same
                    as 'expected', but is different.
            path: A path associated with the operation that failed the verification.
            **kwargs: Additional keyword arguments.
        """

        self.cpu = cpu
        self.expected = expected
        self.actual = actual
        self.path = path

        super().__init__(msg, *args, **kwargs)

class ErrorConnect(Error):
    """Failed to connect to a remote host."""

    def __init__(self, msg: str, *args: Any, host: str | None = None, **kwargs: Any):
        """
        Initialize the exception object..

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            **kwargs: Additional keyword arguments.
            host: The host the connection failed to.
            **kwargs: Additional keyword arguments.
        """

        if host:
            msg = f"Cannot connect to host '{host}'\n{msg}"

        super().__init__(msg, *args, **kwargs)
