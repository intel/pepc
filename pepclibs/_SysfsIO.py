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
import logging
import contextlib
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorVerifyFailed

_LOG = logging.getLogger()

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
    3. Transactions support.
        * 'start_transaction()' - start a transaction.
        * 'flush_transaction()' - flush the transaction buffer.
        * 'commit_transaction()' - commit the transaction.

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

    def _add_for_transaction(self, path, val, what, verify=True, retries=0, sleep=0):
        """Add a write operation to the transaction buffer."""

        if not self._enable_cache:
            raise Error("transactions support requires caching to be enabled, see 'enable_cache' "
                        "argument of the constructor")

        if path not in self._transaction_buffer:
            self._transaction_buffer[path] = {}

        tinfo = self._transaction_buffer[path]
        if "what" in tinfo and tinfo["what"] != what:
            raise Error(f"BUG: inconsistent description for file '{path}':\n"
                        f"  old: {tinfo['what']}, new: {what}.")
        if "verify" in tinfo and tinfo["verify"] != verify:
            raise Error(f"BUG: inconsistent verification flag value for file '{path}':\n"
                        f"  old: {tinfo['verify']}, new: {verify}.")
        if "retries" in tinfo and tinfo["retries"] != retries:
            raise Error(f"BUG: inconsistent verification re-tries count for file '{path}':\n"
                        f"  old: {tinfo['retries']}, new: {retries}.")
        if "sleep" in tinfo and tinfo["sleep"] != sleep:
            raise Error(f"BUG: inconsistent verification sleep value for file '{path}':\n"
                        f"  old: {tinfo['sleep']}, new: {sleep}.")

        tinfo["val"] = val
        tinfo["what"] = what
        tinfo["verify"] = verify
        tinfo["retries"] = retries
        tinfo["sleep"] = sleep

    def start_transaction(self):
        """
        Start transaction. All writes to sysfs files will be cached, and will only be written to the
        actual file-system on 'commit_transaction()' or 'flush_transaction()'.

        The purpose of a transaction is to reduce the amount of I/O. There is no atomicity and
        roll-back functionality, it is only about buffering the I/O and merging multiple writes to
        the same files into a single write operation.
        """

        if not self._enable_cache:
            _LOG.debug("transactions support requires caching to be enabled")
            return

        if self._in_transaction:
            raise Error("cannot start a transaction, it has already started")

        self._in_transaction = True

    def _write(self, path, val, what):
        """Write value 'val' to file at path 'path'."""

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

    def _verify(self, path, val, what=None, retries=0, sleep=0):
        """Verify that file 'path' has value 'what'."""

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

    def flush_transaction(self):
        """
        Flush the transaction buffer. Write all the buffered data to the sysfs files. If there
        multiple writes to the same file, they will be merged into a single write operation.
        The transaction does not stop after flushing.
        """

        if not self._enable_cache:
            return

        if not self._in_transaction:
            raise Error("cannot commit a transaction, it did not start")

        if self._transaction_buffer:
            _LOG.debug("flushing SysfsIO transaction buffer")

        for path, val_info in self._transaction_buffer.items():
            val = val_info["val"]
            what = val_info["what"]
            verify = val_info["verify"]

            self.cache_remove(path)

            self._write(path, val, what)
            if verify:
                retries = val_info["retries"]
                sleep = val_info["sleep"]
                self._verify(path, val, what, retries=retries, sleep=sleep)

            self.cache_add(path, val)

        self._transaction_buffer.clear()

    def commit_transaction(self):
        """
        Commit the transaction. Write all the buffered data to the sysfs files and close the
        transaction. Note, there is no atomicity guarantee, this is not like a database transaction,
        this is just an optimization to reduce the amount of sysfs I/O.
        """

        self.flush_transaction()
        self._in_transaction = False
        _LOG.debug("transaction in SysfsIO has been committed")

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
        if self._in_transaction:
            self._add_for_transaction(path, val, what)
        else:
            self._write(path, val, what=what)
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

        self.cache_remove(path)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if self._in_transaction:
            self._add_for_transaction(path, val, what, verify=True, retries=retries, sleep=sleep)
        else:
            self._write(path, val, what=what)
            self._verify(path, val, what, retries, sleep)

        self.cache_add(path, val)

    def write_verify_int(self, path, val, what=None, retries=0, sleep=0):
        """
        Same as 'write_verify()', but write an integer value 'val'. The arguments are as follows.
          * path - path of the sysfs file to write to.
          * val - the integer value to write.
          * what - short description of the file at 'path.
          * retries - how many times to re-try the verification.
          * sleep - sleep for 'sleep' amount of seconds before repeating the verification.

        Raise 'ErrorVerifyFailed' if the value read was not the same as value written.
        """

        intval = int(val)
        val = str(intval)

        self.cache_remove(path)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if self._in_transaction:
            self._add_for_transaction(path, val, what, verify=True, retries=retries, sleep=sleep)
        else:
            self._write(path, val, what=what)
            try:
                self._verify(path, val, what, retries, sleep)
            except ErrorVerifyFailed as err:
                # Make sure the expected and actual values are of an integer time.
                setattr(err, "expected", intval)
                if hasattr(err, "actual") and Trivial.is_int(err.actual):
                    err.actual = int(err.actual)
                raise err

        self.cache_add(path, val)

    def __init__(self, pman=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to read/write sysfs files on.
          * enable_cache - enable caching if 'True', otherwise disable it.
        """

        self._pman = pman
        self._enable_cache = enable_cache

        self._close_pman = pman is None

        # The write-through data cache, indexed by the file path.
        self._cache = {}
        # Stores new MSR values to be written when 'commit_transaction()' is called.
        self._transaction_buffer = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pman",)
        ClassHelpers.close(self, close_attrs=close_attrs)
