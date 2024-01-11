# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Exception types used by all the modules in this package.
"""

import re

class Error(Exception):
    """The base class for all exceptions raised by this project."""

    def __init__(self, msg, *args, **kwargs):
        """
        The exception class constructor.
        """

        msg = str(msg)
        super().__init__(msg)

        for key, val in kwargs.items():
            setattr(self, key, val)

        if args:
            self.msg = msg % tuple(args)
        else:
            self.msg = msg

    def indent(self, indent, capitalize=True):
        """
        Prefix each line in the error message. The arguments are as follows.
          * indent - can be an integer or a string. In case of an integer, each line of the error
                     string is prefixed with the 'indent' count of white-spaces. In case of a
                     string, each line is prefixed with the 'indent' string.
          * capitalize - if 'True', make sure the message starts with a capital letter.

        The intended usage is combining several multi-line error messages into a single message.
        """

        def capitalize_mobj(mobj):
            """Capitalize a message matched with 're.sub()' ('mobj' is the match object)."""

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

class ErrorVerifyFailed(Error):
    """Verification failed."""

    def __init__(self, msg, *args, cpu=None, expected=None, actual=None, path=None, **kwargs):
        """
        The exception class constructor. The arguments are as follows.
          * cpu - CPU number the associated with the operation that failed the verification
          * expected - the expected value or result of an operation
          * actual - the actual value or result of operation, which was expected to be the same as
                     'expected', but it is different
          * path - a file-system path associated with the operation that failed the verification
        """

        self.cpu = cpu
        self.expected = expected
        self.actual = actual
        self.path = path

        super().__init__(msg, *args, **kwargs)

class ErrorConnect(Error):
    """Failed to connect to a remote host."""

    def __init__(self, msg, *args, host=None, **kwargs):
        """The exception class constructor."""

        if host:
            msg = f"cannot connect to host '{host}'\n{msg}"
        super().__init__(msg, *args, **kwargs)
