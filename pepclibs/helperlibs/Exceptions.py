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

class Error(Exception):
    """The base class for all exceptions raised by this project."""

    def __init__(self, msg, *args, errno=None):
        """The constructor."""

        super().__init__(msg)
        if errno is not None:
            self.errno = errno
        if args:
            self.msg = str(msg) % tuple(args)
        else:
            self.msg = str(msg)

    def indent(self, indent):
        """
        Prefix each line in the error message. The arguments are as follows.
          * indent - can be an integer or a string. In case of an integer, each line of the error
                     string is prefixed with the 'indent' count of white-spaces. In case of a
                     string, each line is prefixed with the 'indent' string.

        The intended usage is combining several multi-line error messages into a single message.
        """

        if isinstance(indent, int):
            pfx = " " * indent
        else:
            pfx = indent

        pfx += f"\n{pfx}"
        msg = pfx + self.msg.replace("\n", pfx)
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

class ErrorConnect(Error):
    """Failed to connect to a remote host."""

    def __init__(self, msg, *args, host=None, **kwargs):
        """Constructor."""

        if host:
            msg = "cannot connect to host '%s'\n" % host + msg
        super().__init__(msg, *args, **kwargs)
