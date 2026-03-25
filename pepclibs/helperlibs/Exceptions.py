# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Exception types used in this project.

Exception Hierarchy:
====================

Error (base)
  ├─ ErrorPath                              (has path attribute)
  │    └─ ErrorVerifyFailedPath             (has path + expected + actual)
  │
  ├─ ErrorPerCPU                            (has cpu attribute)
  │    └─ ErrorPerCPUPath                   (has cpu + path)
  │         └─ ErrorVerifyFailedPerCPUPath  (has cpu + path + expected + actual)
  │
  ├─ ErrorVerifyFailed                      (has expected + actual attributes)
  │    ├─ ErrorVerifyFailedPath             (also inherits from ErrorPath)
  │    └─ ErrorVerifyFailedPerCPUPath       (also inherits from ErrorPerCPUPath)
  │
  ├─ ErrorConnect         (connection failures)
  ├─ ErrorOutOfRange      (value out of valid range)
  ├─ ErrorBadOrder        (incorrect ordering)
  ├─ ErrorTimeOut         (timeout occurred)
  ├─ ErrorExists          (already exists)
  ├─ ErrorNotFound        (not found)
  └─ ErrorNotSupported    (feature not supported)

Key Patterns:
  - Use ErrorPath when file path is involved
  - Use ErrorPerCPU when CPU number is involved
  - Use ErrorPerCPUPath when both CPU and path are involved (multiple inheritance)
  - Use ErrorVerifyFailed* variants when write-verify operations fail
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from typing import Any, Match, Union

# Just a unique object to distinguish "no value provided".
_DEFAULT_VALUE = object()

class Error(Exception):
    """The base class for all exceptions raised by this project."""

    def __init__(self, msg: str, *args: Any, **kwargs: Any):
        """
        Initialize the exception object.

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

    def indent(self, indent: int | str, capitalize: bool = False) -> str:
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

class ErrorPath(Error):
    """Base class for errors associated with a file path."""

    def __init__(self, msg: str, *args: Any, path: Path | None = None, **kwargs: Any):
        """
        Initialize the exception object.

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            path: A path associated with the error.
            **kwargs: Additional keyword arguments.
        """

        assert path is not None
        self.path = path
        super().__init__(msg, *args, **kwargs)

class ErrorPerCPU(Error):
    """Base class for per-CPU errors."""

    def __init__(self, msg: str, *args: Any, cpu: int = -1, **kwargs: Any):
        """
        Initialize the exception object.

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            cpu: CPU number associated with the error.
            **kwargs: Additional keyword arguments.
        """

        assert cpu != -1
        self.cpu = cpu
        super().__init__(msg, *args, **kwargs)

class ErrorPerCPUPath(ErrorPath, ErrorPerCPU):
    """Base class for per-CPU errors associated with a file path."""

class ErrorVerifyFailed(Error):
    """Verification failed."""

    def __init__(self,
                 msg: str,
                 *args: Any,
                 expected: Any = _DEFAULT_VALUE,
                 actual: Any = _DEFAULT_VALUE,
                 **kwargs: Any):
        """
        Initialize the exception object.

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            expected: The expected value or result of an operation.
            actual: The actual value or result of the operation, which was expected to be the same
                    as 'expected', but is different.
            **kwargs: Additional keyword arguments.
        """

        assert expected is not _DEFAULT_VALUE
        assert actual is not _DEFAULT_VALUE

        self.expected = expected
        self.actual = actual

        super().__init__(msg, *args, **kwargs)

class ErrorVerifyFailedPath(ErrorVerifyFailed, ErrorPath):
    """Verification failed, with associated file path."""

class ErrorVerifyFailedPerCPUPath(ErrorVerifyFailed, ErrorPerCPUPath):
    """Verification failed for a specific CPU, with associated file path."""

class ErrorConnect(Error):
    """Failed to connect to a remote host."""

    def __init__(self, msg: str, *args: Any, host: str | None = None, **kwargs: Any):
        """
        Initialize the exception object.

        Args:
            msg: The exception message.
            *args: Positional arguments for the message.
            host: The host the connection failed to.
            **kwargs: Additional keyword arguments.
        """

        if host:
            msg = f"Cannot connect to host '{host}'\n{msg}"

        super().__init__(msg, *args, **kwargs)

class ErrorOutOfRange(Error):
    """Something is out of range."""

class ErrorBadOrder(Error):
    """Something is in the wrong order."""

class ErrorTimeOut(Error):
    """Something timed out."""

class ErrorExists(Error):
    """Something already exists."""

class ErrorNotFound(Error):
    """Something was not found."""

class ErrorNotSupported(Error):
    """Feature/option/etc is not supported."""

class ErrorPermissionDenied(Error):
    """Permission denied."""

class ErrorBadFormat(Error):
    """Bad format of something, e.g., file contents."""

if typing.TYPE_CHECKING:
    ExceptionTypeType = Union[type[Error], type[ErrorTimeOut], type[ErrorExists],
                              type[ErrorNotFound], type[ErrorNotSupported],
                              type[ErrorPermissionDenied], type[ErrorBadFormat],
                              type[ErrorPath], type[ErrorPerCPU], type[ErrorPerCPUPath],
                              type[ErrorVerifyFailed], type[ErrorVerifyFailedPath],
                              type[ErrorVerifyFailedPerCPUPath], type[ErrorConnect],
                              type[ErrorOutOfRange], type[ErrorBadOrder]]
