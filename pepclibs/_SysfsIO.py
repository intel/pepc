# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of reading and writing sysfs files.
"""

from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

class SysfsIO(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and writing sysfs files.
    """

    def read(self, path, what=None):
        """
        Read a sysfs file at 'path'. The arguments are as follows.
          * path - path of the sysfs file to read.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.

        Return the contents of the file at 'path'. Return 'None' if the file does not exist.
        """

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    val = fobj.read().strip()
                except Error as err:
                    what = "" if what is None else f" {what}"
                    raise Error(f"failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err
        except ErrorNotFound:
            return None

        return val

    def read_int(self, path, what=None):
        """
        Read a sysfs file 'path' and return its contents as an interger value. The arguments are as
        follows.
          * path - path of the sysfs file to read.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.

        Validate the contents of the 'path', raise 'Error' if the contents is not an integer value.
        Otherwise, return the the value as an integer ('int' typei). Return 'None' if the file does
        not exist.
        """

        val = self.read(path, what=what)
        if val is None:
            return None

        try:
            return Trivial.str_to_int(val, what=what)
        except Error as err:
            what = "" if what is None else f" {what}"
            raise Error(f"bad contents of{what} syfs file '{path}'{self._pman.hostmsg}\n"
                        f"{err.indent(2)}") from err

    def write(self, path, val, what=None):
        """
        Write value 'val' to a sysfs file at 'path'. The arguments are as follows.
          * path - path of the sysfs file to write to.
          * val - the value to write.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.
        """

        try:
            with self._pman.open(path, "r+") as fobj:
                fobj.write(val)
        except Error as err:
            what = "" if what is None else f" {what}"
            val = str(val)
            if len(val) > 24:
                val = f"{val[:23]}...snip..."
            raise Error(f"failed to write value '{val}' to{what} sysfs file '{path}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def __init__(self, pman=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to read/write sysfs files on.
        """

        self._pman = pman

        self._close_pman = pman is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pman", )
        ClassHelpers.close(self, close_attrs=close_attrs)
