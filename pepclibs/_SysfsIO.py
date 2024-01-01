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
Provide a capability of reading and writing sysfs files. Implement caching.
"""

import time
import contextlib
from pepclibs import CPUInfo
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorVerifyFailed

class SysfsIO(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and writing sysfs files. Implement caching.

    Public methods overview.

    1. Read / write to a file.
        * 'read()' - read a string.
        * 'read_int()' - read an integer.
        * 'write()' - write a string.
        * 'write_verify()' - write a string and verify.
    2. Cache operations.
        * cache_get() - get data from the cache.
        * cache_add() - add data to the cache.
        * cache_remove() - remove data from the cache.

    Note, the method of this class do not normalize the input path, and the user is supposed to do
    it for caching to work efficiently (the cache is indexed by file path).
    """

    def cache_get(self, path):
        """
        Get cached value a sysfs file 'path'. The argument are as follows.
          * path - path to the sysfs file to get the cached value for.

        Raise 'ErrorNotFound' if there is no cached value for path 'path'.
        """

        if not self._enable_cache:
            raise ErrorNotFound("caching is disabled")

        try:
            return self._cache[path]
        except KeyError:
            raise ErrorNotFound(f"sysfs file '{path}' is not cached") from None

    def cache_add(self, path, val):
        """
        Add value 'val' for path 'path' to the cache. The argument are as follows.
          * path - path of the sysfs file to cache.
          * val - the value to cache.

        Return 'val'.
        """

        if not self._enable_cache:
            return val

        self._cache[path] = val
        return val

    def cache_remove(self, path):
        """
        Remove possibly cached value for 'path'. The argument are as follows.
          * path - path of the sysfs file to remove the cached value for.
        """

        if not self._enable_cache:
            return

        with contextlib.suppress(KeyError):
            del self._cache[path]

    def read(self, path, what=None):
        """
        Read a sysfs file at 'path'. The arguments are as follows.
          * path - path of the sysfs file to read.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.

        Return the contents of the file at 'path'. Raise 'ErrorNotSupported' if the file does not
        exist.
        """

        with contextlib.suppress(ErrorNotFound):
            return self.cache_get(path)

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    val = fobj.read().strip()
                except Error as err:
                    what = "" if what is None else f" {what}"
                    raise Error(f"failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err
        except ErrorNotFound as err:
            what = "" if what is None else f" {what}"
            raise ErrorNotSupported(f"failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}") from err

        return self.cache_add(path, val)

    def read_int(self, path, what=None):
        """
        Read a sysfs file 'path' and return its contents as an interger value. The arguments are as
        follows.
          * path - path of the sysfs file to read.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.

        Validate the contents of the 'path', raise 'Error' if the contents is not an integer value.
        Otherwise, return the the value as an integer ('int' type). Return 'None' if the file does
        not exist.
        """

        val = self.read(path, what=what)

        try:
            return Trivial.str_to_int(val, what=what)
        except Error as err:
            what = "" if what is None else f" {what}"
            raise Error(f"bad contents of{what} sysfs file '{path}'{self._pman.hostmsg}\n"
                        f"{err.indent(2)}") from err

    def write(self, path, val, what=None):
        """
        Write value 'val' to a sysfs file at 'path'. The arguments are as follows.
          * path - path of the sysfs file to write to.
          * val - the value to write.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.
        """

        self.cache_remove(path)

        try:
            with self._pman.open(path, "r+") as fobj:
                try:
                    fobj.write(val)
                except Error as err:
                    what = "" if what is None else f" {what}"
                    val = str(val)
                    if len(val) > 24:
                        val = f"{val[:23]}...snip..."
                    raise Error(f"failed to write value '{val}' to{what} sysfs file '{path}'"
                                f"{self._pman.hostmsg}:\n{err.indent(2)}") from err
        except ErrorNotFound as err:
            what = "" if what is None else f" {what}"
            val = str(val)
            if len(val) > 24:
                val = f"{val[:23]}...snip..."
            raise ErrorNotSupported(f"failed to write value '{val}' to{what} sysfs file '{path}'"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        self.cache_add(path, val)

    def write_verify(self, path, val, what=None, retries=0, sleep=0):
        """
        Write value 'val' to a sysfs file at 'path' and verify that it was "accepted" by the kernel
        by reading it back and comparing to the written value. The arguments are as follows.
          * path - path of the sysfs file to write to.
          * val - the value to write.
          * what - short description of the file at 'path', will be included to the exception
                   message in case of a failure.
          * retries - how many times to re-try the verification.
          * sleep - sleep for 'sleep' amount of seconds before repeating the verification.

        Raise 'ErrorVerifyFailed' if the value read was not the same as value written.
        """

        self.write(path, val, what=what)

        while True:
            # Read CPU frequency back and verify that it was set correctly.
            self.cache_remove(path)
            new_val = self.read(path, what=what)
            if val == new_val:
                return new_val

            retries -= 1
            if retries < 0:
                break

            time.sleep(sleep)

        what = "" if what is None else f" {what}"
        val_str = str(val)
        if len(val_str) > 24:
            val_str = f"{val[:23]}...snip..."
        raise ErrorVerifyFailed(f"failed to write value '{val_str}' to{what} sysfs file '{path}'"
                                f"{self._pman.hostmsg}:\n  wrote '{val}', but read '{new_val}' "
                                "back", expected=val, actual=new_val, path=path)

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to read/write sysfs files on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - enable caching if 'True', otherwise disable it.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._cache = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
