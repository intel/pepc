# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide API for reading and writing sysfs files. Implement caching.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import time
import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorBadFormat
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorVerifyFailed

if typing.TYPE_CHECKING:
    from typing import TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _TransactionItemTypedDict(TypedDict, total=False):
        """
        A typed dictionary for a single item in the transaction buffer.

        Attributes:
            val: The value to write.
            what: A description of the write operation.
            verify: Whether to verify the write operation after execution.
            retries: Number of verification retries.
            sleep: Sleep duration between retries.
        """

        val: str
        what: str
        verify: bool
        retries: int
        sleep: int | float

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class SysfsIO(ClassHelpers.SimpleCloseContext):
    """
    Provide API for reading and writing sysfs files. Implement caching.

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

    def __init__(self, pman: ProcessManagerType | None = None, enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. Use a local process
                  manager if not provided.
            enable_cache: Enable caching if True, disable if False.
        """

        self._enable_cache = enable_cache
        self._close_pman = pman is None

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        # The write-through data cache, indexed by the file path.
        self._cache: dict[Path, str] = {}
        # Stores new MSR values to be written when 'commit_transaction()' is called.
        self._transaction_buffer: dict[Path, _TransactionItemTypedDict] = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pman",)
        ClassHelpers.close(self, close_attrs=close_attrs)

    def cache_get(self, path: Path) -> str:
        """
        Retrieve the cached value for a given sysfs file path.

        Args:
            path: Path to the sysfs file whose cached value should be retrieved.

        Returns:
            The cached value as a string.

        Raises:
            ErrorNotFound: If caching is disabled or if there is no cached value for the specified
                           path.
        """

        if not self._enable_cache:
            raise ErrorNotFound("Caching is disabled")

        try:
            return self._cache[path]
        except KeyError:
            raise ErrorNotFound(f"sysfs file '{path}' is not cached") from None

    def cache_add(self, path: Path, val: str) -> str:
        """
        Add a value to the cache for a given sysfs file path.

        Args:
            path: Path of the sysfs file to cache.
            val: Value to cache.

        Returns:
            The cached value.
        """

        if not self._enable_cache:
            return val

        self._cache[path] = val
        return val

    def cache_remove(self, path: Path):
        """
        Remove the cached value for the specified sysfs file path. Do nothing if caching is disabled
        or if there is no cached value for the specified path.

        Args:
            path: Path of the sysfs file whose cached value should be removed.
        """

        if not self._enable_cache:
            return

        if path in self._cache:
            del self._cache[path]

    def _add_for_transaction(self,
                             path: Path,
                             val: str,
                             what: str,
                             verify: bool = True,
                             retries: int = 0,
                             sleep: int | float = 0):
        """
        Add a write operation to the transaction buffer for later execution.

        Args:
            path: The file path to write to.
            val: The value to write.
            what: A description of the write operation.
            verify: Whether to verify the write operation after execution.
            retries: Number of verification retries.
            sleep: Sleep duration between retries.
        """

        if not self._enable_cache:
            raise Error("Transactions support requires caching to be enabled")

        if path not in self._transaction_buffer:
            self._transaction_buffer[path] = {}

        _LOG.debug("Adding for transaction: path='%s', val='%s', what='%s', verify='%s', "
                   "retries='%d', sleep='%s'", path, str(val), what, verify, retries, sleep)
        tinfo = self._transaction_buffer[path]
        if "what" in tinfo and tinfo["what"] != what:
            raise Error(f"BUG: Inconsistent description for file '{path}':\n"
                        f"  old: {tinfo['what']}, new: {what}.")
        if "verify" in tinfo and tinfo["verify"] != verify:
            raise Error(f"BUG: Inconsistent verification flag value for file '{path}':\n"
                        f"  old: {tinfo['verify']}, new: {verify}.")
        if "retries" in tinfo and tinfo["retries"] != retries:
            raise Error(f"BUG: Inconsistent verification re-tries count for file '{path}':\n"
                        f"  old: {tinfo['retries']}, new: {retries}.")
        if "sleep" in tinfo and tinfo["sleep"] != sleep:
            raise Error(f"BUG: Inconsistent verification sleep value for file '{path}':\n"
                        f"  old: {tinfo['sleep']}, new: {sleep}.")

        tinfo["val"] = val
        tinfo["what"] = what
        tinfo["verify"] = verify
        tinfo["retries"] = retries
        tinfo["sleep"] = sleep

    def start_transaction(self):
        """
        Begin a new transaction for sysfs file writes.

        When a transaction is active, all writes to sysfs files are cached and only written to the
        filesystem upon calling 'commit_transaction()' or 'flush_transaction()'. This reduces I/O
        operations by buffering writes and merging multiple writes to the same file into a single
        operation.
        """

        if not self._enable_cache:
            _LOG.debug("Transactions support requires caching to be enabled")
            return

        if self._in_transaction:
            raise Error("Cannot start a transaction, it has already started")

        self._in_transaction = True

    def _write(self, path: Path, val: str, what: str):
        """
        Write a value to a sysfs file at the specified path.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional description of what is being written, used for logging and error
                  messages.

        Raises:
            ErrorNotSupported: If the file is not found.
        """

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if what:
                what = f" {what}"
            _LOG.debug("Writing value '%s' to%s sysfs file '%s'%s",
                       val, what, path, self._pman.hostmsg)

        try:
            with self._pman.open(path, "r+") as fobj:
                try:
                    fobj.write(val)
                except Error as err:
                    what = "" if what is None else f" {what}"
                    val = str(val)
                    if len(val) > 24:
                        val = f"{val[:23]}...snip..."
                    raise Error(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                                f"{self._pman.hostmsg}:\n{err.indent(2)}") from err
        except ErrorNotFound as err:
            if what:
                what = f" {what}"
            val = str(val)
            if len(val) > 24:
                val = f"{val[:23]}...snip..."
            # TODO: Why ErrorNotSupported here, not ErrorNotFound?
            raise ErrorNotSupported(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _verify(self,
                path: Path,
                val: str,
                what: str = "",
                retries: int = 0,
                sleep: int | float = 0):
        """
        Verify that the specified sysfs file contains the expected value.

        If the value does not match, retry the verification up to 'retries' times, sleeping for
        'sleep' seconds between attempts. Remove any cached value before each read.

        Args:
            path: Path to the sysfs file to verify.
            val: Expected value to verify in the file.
            what: Optional description of what is being verified (used in error messages).
            retries: Number of times to retry verification if the value does not match.
            sleep: Number of seconds to sleep between retries.

        Returns:
            The value read from the sysfs file if verification succeeds.

        Raises:
            ErrorVerifyFailed: If the value in the file does not match 'val' after all retries.
        """

        while True:
            # Read CPU frequency back and verify that it was set correctly.
            self.cache_remove(path)
            new_val = self.read(path, what=what)
            _LOG.debug("Verifying %s value '%s' in sysfs file '%s'%s: read back '%s'",
                       what, val, path, self._pman.hostmsg, new_val)
            if val == new_val:
                return new_val

            retries -= 1
            if retries < 0:
                break

            time.sleep(sleep)

        if what:
            what = f" {what}"
        val_str = str(val)
        if len(val_str) > 24:
            val_str = f"{val[:23]}...snip..."
        raise ErrorVerifyFailed(f"Failed to write value '{val_str}' to{what} sysfs file '{path}'"
                                f"{self._pman.hostmsg}:\n  wrote '{val}', but read '{new_val}' "
                                f"back", expected=val, actual=new_val, path=path)

    def flush_transaction(self):
        """
        Flush the transaction buffer and write all buffered data to sysfs files.
        """

        if not self._enable_cache:
            return
        if not self._in_transaction:
            return

        if self._transaction_buffer:
            _LOG.debug("Flushing SysfsIO transaction buffer")

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
        Commit the current transaction by writing all buffered data to the sysfs files.

        This operation does not provide atomicity. It is intended as an optimization to reduce the
        number of sysfs I/O operations.
        """

        if not self._in_transaction:
            raise Error("Cannot commit a transaction, it did not start")

        self.flush_transaction()
        self._in_transaction = False
        _LOG.debug("Transaction in SysfsIO has been committed")

    def read(self, path: Path, what: str = "") -> str:
        """
        Read the contents of a sysfs file at the specified path.

        Args:
            path: Path to the sysfs file to read.
            what: Optional short description of what is being read, included in exception messages.

        Returns:
            The contents of the file as a string.

        Raises:
            ErrorNotSupported: If the file does not exist.
        """

        with contextlib.suppress(ErrorNotFound):
            return self.cache_get(path)

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    val = fobj.read().strip()
                except Error as err:
                    if what:
                        what = f" {what}"
                    raise Error(f"Failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err
        except ErrorNotFound as err:
            if what:
                what = f" {what}"
            # TODO: Why ErrorNotSupported here, not ErrorNotFound?
            raise ErrorNotSupported(f"Failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}") from err

        return self.cache_add(path, val)

    def read_int(self, path: Path, what: str = "") -> int:
        """
        Read a sysfs file and return its contents as an integer.

        Args:
            path: Path to the sysfs file to read.
            what: Optional short description of what is being read, included in exception messages.

        Returns:
            The integer value read from the file.

        Raises:
            ErrorNotSupported: If the file does not exist.
            ErrorBadFormat: If the file contents cannot be parsed as an integer.
        """

        val = self.read(path, what=what)

        try:
            return Trivial.str_to_int(val, what=what)
        except Error as err:
            if what:
                what = f" {what}"
            raise ErrorBadFormat(f"Bad contents of{what} sysfs file '{path}'{self._pman.hostmsg}\n"
                                 f"{err.indent(2)}") from err

    def write(self, path: Path, val: str, what: str = ""):
        """
        Write a value to a sysfs file and update the cache.

        If a transaction is in progress, the write operation is queued for the transaction,
        otherwise, the value is written immediately. The cache is updated after the write operation.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional short description of what is being written, included in exception
                  messages.

        Raises:
            ErrorNotSupported: If the file does not exist.
        """

        self.cache_remove(path)
        if self._in_transaction:
            self._add_for_transaction(path, val, what)
        else:
            self._write(path, val, what=what)
        self.cache_add(path, val)

    def write_int(self, path: Path, val: str | int, what: str = ""):
        """
        Write an integer value to a sysfs file.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional short description of what is being written, included in exception
                  messages.

        Raises:
            ErrorNotSupported: If the file does not exist.
        """

        int_val = Trivial.str_to_int(val, what=what)
        self.write(path, str(int_val), what=what)

    def write_verify(self,
                     path: Path,
                     val: str,
                     what: str = "",
                     retries: int = 0,
                     sleep: int | float = 0):
        """
        Write a value to a sysfs file and verify that the kernel accepted it.

        Write the specified value to the sysfs file, then read the it back to ensure it matches what
        was written.If the verification fails, it retry the operation.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional short description of what is being written, included in exception
                  messages.
            retries: Number of times to retry verification if it fails.
            sleep: Number of seconds to sleep between verification retries.

        Raises:
            ErrorNotSupported: If the file does not exist.
            ErrorVerifyFailed: If the value read from the file does not match the value written.
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

    def write_verify_int(self,
                         path: Path,
                         val: str | int,
                         what: str = "",
                         retries: int = 0,
                         sleep: int | float = 0):
        """Same as 'write_verify()', but write an integer value 'val'."""

        intval = Trivial.str_to_int(val, what=what)
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
                if hasattr(err, "actual") and Trivial.is_int(str(err.actual)):
                    err.actual = int(str(err.actual))
                raise err

        self.cache_add(path, val)
