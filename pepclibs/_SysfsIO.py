# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API for reading and writing sysfs files. Implement transactions, caching and optimized I/O
operations for remote hosts.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import time
import typing
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, EmulProcessManager, ClassHelpers
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorBadFormat
from pepclibs.helperlibs.Exceptions import Error, ErrorPath, ErrorNotFound
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed, ErrorVerifyFailedPath

if typing.TYPE_CHECKING:
    from typing import TypedDict, Generator, Iterable
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

# A debug option to disable I/O optimizations.
DISABLE_IO_OPTIMIZATIONS: bool = False
# A debug option for self-verifying I/O optimizations.
VERIFY_IO_OPTIMIZATIONS: bool = False

# The maximum total length of file paths for the optimized I/O operations.
_MAX_PATHS_LEN = 16000

class SysfsIO(ClassHelpers.SimpleCloseContext):
    """
    Provide API for reading and writing sysfs files with transactions, caching, and optimized I/O.

    Public methods overview.

    1. Read / write a single file.
        - 'read()' - read a string.
        - 'read_int()' - read an integer.
        - 'write()' - write a string.
        - 'write_int()' - write an integer.
        - 'write_verify()' - write a string and verify.
        - 'write_verify_int()' - write an integer and verify.
    2. Read multiple files.
        - 'read_paths()' - read multiple files, return strings.
        - 'read_paths_int()' - read multiple files, return integers.
    3. Write multiple files.
        - 'write_paths()' - write a string to multiple files.
        - 'write_paths_int()' - write an integer to multiple files.
        - 'write_paths_verify()' - write a string to multiple files and verify.
        - 'write_paths_verify_int()' - write an integer to multiple files and verify.
    4. Cache operations.
        - 'cache_add()' - add data to the cache.
        - 'cache_remove()' - remove data from the cache.
        - 'cache_flush()' - flush the cache.
    5. Transactions support.
        - 'start_transaction()' - start a transaction.
        - 'flush_transaction()' - flush the transaction buffer.
        - 'commit_transaction()' - commit the transaction.

    Notes:
        - Methods do not normalize input paths. The caller should normalize paths for efficient
          caching (cache is indexed by file path).
    """

    def __init__(self, pman: ProcessManagerType | None = None, enable_cache: bool = True,
                 read_only: bool = False):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. Use a local process
                  manager if not provided.
            enable_cache: Enable caching if True, disable if False.
            read_only: If True, any write operation will raise an error. Read-only mode is mutually
                       exclusive with transactions.
        """

        self._enable_cache = enable_cache
        self._read_only = read_only
        self._close_pman = pman is None

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if DISABLE_IO_OPTIMIZATIONS and VERIFY_IO_OPTIMIZATIONS:
            _LOG.warning("I/O optimizations are disabled, but their verification is enabled")

        if isinstance(self._pman, EmulProcessManager.EmulProcessManager):
            self._optimize_io = False
        else:
            if DISABLE_IO_OPTIMIZATIONS:
                self._optimize_io = False
            elif VERIFY_IO_OPTIMIZATIONS:
                # Run optimized I/O even for local hosts when verification is enabled.
                self._optimize_io = True
            else:
                self._optimize_io = self._pman.is_remote

        # The write-through data cache, indexed by the file path.
        self._cache: dict[Path, str] = {}
        # Stores new values to be written when 'commit_transaction()' is called.
        self._transaction_buffer: dict[Path, _TransactionItemTypedDict] = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_pman",)
        ClassHelpers.close(self, close_attrs=close_attrs)

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

    def cache_flush(self):
        """
        Flush the entire cache, removing all cached values.
        """

        if not self._enable_cache:
            return

        if self._in_transaction:
            raise Error("Cannot flush cache while a transaction is in progress")

        self._cache.clear()

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

        if self._read_only:
            raise Error("Cannot start a transaction in read-only mode")

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

        _LOG.debug("Writing value '%s' to%s sysfs file '%s'%s",
                   val, "" if not what else f" {what}", path, self._pman.hostmsg)

        try:
            with self._pman.open(path, "r+") as fobj:
                try:
                    fobj.write(val)
                except Error as err:
                    what = "" if not what else f" {what}"
                    val = str(val)
                    if len(val) > 24:
                        val = f"{val[:23]}...snip..."
                    raise ErrorPath(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}", path=path) from err
        except ErrorNotFound as err:
            what = "" if not what else f" {what}"
            val = str(val)
            if len(val) > 24:
                val = f"{val[:23]}...snip..."
            raise ErrorNotSupported(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _verify(self,
                path: Path,
                val: str,
                what: str = "",
                retries: int = 0,
                sleep: int | float = 0) -> str:
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
            ErrorVerifyFailedPath: Specific subclass of ErrorVerifyFailed that includes the file
                                   path information (this is what's actually raised).
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

        what = "" if not what else f" {what}"
        val_str = str(val)
        if len(val_str) > 24:
            val_str = f"{val_str[:23]}...snip..."
        raise ErrorVerifyFailedPath(f"Failed to write value '{val_str}' to{what} sysfs file "
                                    f"'{path}'{self._pman.hostmsg}:\n  Wrote '{val}', but read "
                                    f"'{new_val}' back", expected=val, actual=new_val, path=path)

    def _write_paths_vals_optimized_helper(self,
                                            batch_info: dict[Path, _TransactionItemTypedDict],
                                            winfo: str):
        """
        Write multiple paths and values with I/O optimizations for remote hosts.

        Args:
            batch_info: The batch write information dictionary.
            winfo: The formatted string of write operations for the Python script.

        Raises:
            ErrorVerifyFailed: If verification of any write operation fails.
            ErrorVerifyFailedPath: Specific subclass of ErrorVerifyFailed that includes the file
                                   path information (this is what's actually raised).
        """

        python_path = self._pman.get_python_path()

        _LOG.debug("Remote: Write: %d sysfs files with verification%s",
                   len(batch_info), self._pman.hostmsg)

        cmd = f"""{python_path} -c '
import time
winfo = {{{winfo}}}
for path, (val, verify, retries, sleep) in winfo.items():
    try:
        with open(path, "w") as fobj:
            fobj.write(val)
    except Exception as err:
        print("ERROR: Write: '%s': '%s'" % (path, err))
        raise SystemExit(0)

    if not verify:
        continue

    while True:
        try:
            with open(path, "r") as fobj:
                new_val = fobj.read().strip()
        except Exception as err:
            print("ERROR: Read: '%s': '%s'" % (path, err))
            raise SystemExit(0)

        if val == new_val:
            break

        retries -= 1
        if retries < 0:
            print("ERROR: Verify: '%s': Expected '%s': Got '%s'" % (path, val, new_val))
            raise SystemExit(0)

        time.sleep(sleep)
'"""

        try:
            stdout, stderr = self._pman.run_verify_join(cmd)
        except Error as err:
            errmsg = err.indent(2)
            raise type(err)(f"Failed to write sysfs files{self._pman.hostmsg}:\n"
                            f"{errmsg}") from err

        if stderr:
            # Nothing is expected on stderr, if there is any output, treat it as an error.
            raise Error(f"Failed to write sysfs files{self._pman.hostmsg}:\n"
                        f"Unexpected output on stderr:\n{stderr}")

        if not stdout:
            # All files flushed and verified successfully.
            return

        generic_errmsg = f"Failed to write sysfs files{self._pman.hostmsg}:\n{stdout}"

        if not stdout.startswith("ERROR: "):
            raise Error(generic_errmsg)

        # Only one line of output is expected, if there are multiple lines, something is wrong with
        # the output format.
        stdout_lines = stdout.splitlines()
        if len(stdout_lines) != 1:
            raise Error(generic_errmsg)

        stdout = stdout_lines[0].strip()
        stdout_tokens = stdout.split()
        if len(stdout_tokens) < 4:
            raise Error(generic_errmsg)

        # The second line token is the error type, e.g. "Write", "Read", or "Verify".
        error_type = stdout_tokens[1]
        if not error_type.endswith(":"):
            raise Error(generic_errmsg)
        error_type = error_type[:-1]

        if error_type == "Write":
            regex = r"ERROR: Write: '(.+)': '(.+)'"
        elif error_type == "Read":
            regex = r"ERROR: Read: '(.+)': '(.+)'"
        elif error_type == "Verify":
            regex = r"ERROR: Verify: '(.+)': Expected '(.+)': Got '(.+)'"
        else:
            raise Error(generic_errmsg)

        mobj = re.match(regex, stdout)
        if not mobj:
            raise Error(generic_errmsg)

        _path = mobj.group(1)
        if _path not in batch_info:
            raise Error(f"Unexpected path '{_path}' in the error message:\n{stdout}")

        path = Path(_path)
        val_info = batch_info[path]
        val = val_info["val"]
        what = val_info["what"]
        what = "" if not what else f" {what}"

        if error_type == "Write":
            raise ErrorPath(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                            f"{self._pman.hostmsg}:\n{stdout}", path=path)
        if error_type == "Read":
            raise ErrorPath(f"Failed to read back value from{what} sysfs file '{path}'"
                            f"{self._pman.hostmsg}:\n{stdout}", path=path)
        if error_type == "Verify":
            expected_val = mobj.group(2)
            actual_val = mobj.group(3)
            raise ErrorVerifyFailedPath(f"Failed to write value '{val}' to{what} sysfs file "
                                        f"'{path}'{self._pman.hostmsg}:\n  Wrote '{expected_val}', "
                                        f"but read '{actual_val}' back",
                                        expected=expected_val, actual=actual_val, path=path)

    def _write_paths_vals_optimized(self, batch_info: dict[Path, _TransactionItemTypedDict]):
        """
        Write multiple paths and values with I/O optimizations for remote hosts.

        The input argument is the batch write information dictionary in the same format as the
        transaction buffer.

        Args:
            batch_info: The batch write information dictionary.

        Raises:
            ErrorVerifyFailed: If verification of any write operation fails.
            ErrorVerifyFailedPath: Specific subclass of ErrorVerifyFailed that includes the file
                                   path information (this is what's actually raised).
        """

        # Format a dictionary of write operations as a string for the Python script: winfo, which
        # stands for "write information".
        winfo = ""
        for path, val_info in batch_info.items():
            val = val_info["val"]
            verify = val_info["verify"]
            retries = val_info["retries"]
            sleep = val_info["sleep"]

            val_quoted = val.replace("'", "\'").replace('"', '\"')
            winfo_line = f"\"{str(path)}\": (\"{val_quoted}\", {verify}, {retries}, {sleep})"

            if len(winfo_line) > _MAX_PATHS_LEN:
                raise Error(f"Write line '{winfo_line}' is too long for optimized writing (length "
                            f"{len(winfo_line)}: It exceeds the limit of {_MAX_PATHS_LEN} "
                            f"characters)")

            if len(winfo) + len(winfo_line) < _MAX_PATHS_LEN:
                winfo += f"{winfo_line},\n"
                continue

            self._write_paths_vals_optimized_helper(batch_info, winfo)
            winfo = f"{winfo_line},\n"

        self._write_paths_vals_optimized_helper(batch_info, winfo)

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

        for path in self._transaction_buffer:
            self.cache_remove(path)

        if self._optimize_io:
            self._write_paths_vals_optimized(self._transaction_buffer)
        else:
            for path, val_info in self._transaction_buffer.items():
                val = val_info["val"]

                self._write(path, val, val_info["what"])

                if val_info["verify"]:
                    what = val_info["what"]
                    retries = val_info["retries"]
                    sleep = val_info["sleep"]
                    self._verify(path, val, what, retries=retries, sleep=sleep)

        for path, val_info in self._transaction_buffer.items():
            self.cache_add(path, val_info["val"])

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

    def read(self, path: Path, what: str = "", val_if_not_found: str | None = None) -> str:
        """
        Read the contents of a sysfs file at the specified path.

        Args:
            path: Path to the sysfs file to read.
            what: Optional short description of what is being read, included in exception messages.
            val_if_not_found: Value to return if the file is not found instead of raising an
                              exception.

        Returns:
            The contents of the file as a string.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorPath: An I/O error occurred while reading the file (includes path information).
        """

        if path in self._cache:
            _LOG.debug("Cached: Read: Sysfs file '%s'%s", path, self._pman.hostmsg)
            return self._cache[path]

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if isinstance(self._pman, LocalProcessManager.LocalProcessManager):
                msg_prefix = "Local"
            elif isinstance(self._pman, EmulProcessManager.EmulProcessManager):
                msg_prefix = "Emulation"
            else:
                msg_prefix = "Remote"
            _LOG.debug("%s: Read: Sysfs file '%s'%s", msg_prefix, path, self._pman.hostmsg)

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    val = fobj.read().strip()
                except Error as err:
                    what = "" if not what else f" {what}"
                    raise ErrorPath(f"Failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}", path=path) from err
        except ErrorNotFound as err:
            if val_if_not_found is not None:
                return val_if_not_found
            what = "" if not what else f" {what}"
            raise ErrorNotSupported(f"Failed to read{what} from '{path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}") from err

        return self.cache_add(path, val)

    def read_int(self, path: Path, what: str = "", val_if_not_found: str | None = None) -> int:
        """
        Read a sysfs file and return its contents as an integer.

        Args:
            path: Path to the sysfs file to read.
            what: Optional short description of what is being read, included in exception messages.
            val_if_not_found: Value to return if the file is not found instead of raising an
                              exception.

        Returns:
            The integer value read from the file.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorBadFormat: The file contents cannot be parsed as an integer.
            ErrorPath: An I/O error occurred while reading the file (includes path information).
        """

        val = self.read(path, what=what, val_if_not_found=val_if_not_found)

        try:
            return Trivial.str_to_int(val, what=what)
        except Error as err:
            what = "" if not what else f" {what}"
            raise ErrorBadFormat(f"Bad contents of{what} sysfs file '{path}'{self._pman.hostmsg}\n"
                                 f"{err.indent(2)}") from err

    def _read_paths_optimized_helper(self,
                                     paths: list[Path],
                                     what: str = "",
                                     val_if_not_found: str | None = None) -> \
                                                            Generator[tuple[Path, str], None, None]:
        """
        Read the specified list of paths in a single SSH command. The arguments are the same as for
        'read_paths()'.

        Yields:
            Tuples of (path, value) for each successfully read path.
        """

        _file_not_found_val = "pepc_file_not_found"
        python_path = self._pman.get_python_path()

        read_paths = [path for path in paths if path not in self._cache]

        if read_paths:
            if _LOG.getEffectiveLevel() == Logging.DEBUG:
                paths_range = Trivial.rangify(list(range(len(read_paths))))
                _LOG.debug("Remote: Read: %d sysfs files (indices %s)%s",
                           len(read_paths), paths_range, self._pman.hostmsg)

            paths_str = ",\n".join(f"\"{str(path)}\"" for path in read_paths)

            cmd = f"""{python_path} -c '
paths = [{paths_str}]
for path in paths:
    try:
        with open(path, "r") as fobj:
            val = fobj.read().strip()
    except FileNotFoundError:
        val = "{_file_not_found_val}"
    except Exception as err:
        print("ERROR: Failed to read file '%s': %s" % (path, err))
        raise SystemExit(1)
    print(val)
'"""

            try:
                stdout, stderr = self._pman.run_verify_nojoin(cmd)
            except Error as err:
                errmsg = err.indent(2)
                raise type(err)(f"Failed to read sysfs files{self._pman.hostmsg}:\n"
                                f"{errmsg}") from err

            if stderr:
                stderr_str = "".join(stderr)
                raise Error(f"Unexpected output on stderr while reading sysfs files"
                            f"{self._pman.hostmsg}:\n{stderr_str}")

            if len(read_paths) != len(stdout):
                raise Error(f"BUG: Unexpected number of lines from the optimized read command:\n"
                            f"- Expected: {len(read_paths)}\n"
                            f"- Actual: {len(stdout)}")

            read_results = {}
            for path, val in zip(read_paths, stdout):
                val = val.strip()
                if val == _file_not_found_val:
                    if val_if_not_found is not None:
                        read_results[path] = val_if_not_found
                    else:
                        what = "" if not what else f" {what}"
                        raise ErrorNotSupported(f"Failed to read{what} from '{path}'"
                                                f"{self._pman.hostmsg}")
                else:
                    if val.startswith("ERROR: Failed to read file "):
                        raise ErrorPath(f"Failed to read{what} from '{path}'{self._pman.hostmsg}:\n"
                                        f"  {val}", path=path)
                    self.cache_add(path, val)
                    read_results[path] = val
        else:
            read_results = {}

        # Yield all paths in order, from read_results or cache.
        for path in paths:
            if path in read_results:
                yield path, read_results[path]
            else:
                yield path, self._cache[path]

    def _read_paths_optimized(self,
                              paths: Iterable[Path],
                              what: str = "",
                              val_if_not_found: str | None = None) -> \
                                                            Generator[tuple[Path, str], None, None]:
        """
        Implement 'read_paths()' with I/O optimizations for remote hosts. The arguments are the same
        as for 'read_paths()'.

        In case of a remote host, reading each sysfs file involves a separate SSH command, which can
        be very slow. To optimize this, we read multiple files in a single SSH command by running a
        Python script on the remote host that reads all the specified files and prints their
        contents.

        Yields:
            Tuples of (path, value) for each successfully read path.
        """

        _LOG.debug("Reading multiple sysfs files with I/O optimizations")

        read_paths: list[Path] = []
        read_paths_len = 0

        for path in paths:
            if path in self._cache:
                read_paths.append(path)
                continue

            path_len = len(str(path))
            if path_len > _MAX_PATHS_LEN:
                raise Error(f"Path '{path}' is too long for optimized reading (length {path_len}: "
                            f"It exceeds the limit of {_MAX_PATHS_LEN} characters)")

            if read_paths_len + path_len < _MAX_PATHS_LEN:
                read_paths_len += path_len
                read_paths.append(path)
                continue

            yield from self._read_paths_optimized_helper(read_paths, what=what,
                                                         val_if_not_found=val_if_not_found)

            read_paths = [path]
            read_paths_len = path_len

        if read_paths:
            yield from self._read_paths_optimized_helper(read_paths, what=what,
                                                         val_if_not_found=val_if_not_found)

    def _read_paths(self,
                    paths: Iterable[Path],
                    what: str = "",
                    val_if_not_found: str | None = None) -> Generator[tuple[Path, str], None, None]:
        """
        Implement 'read_paths()' without I/O optimizations for remote hosts. The arguments are the
        same as for 'read_paths()'.

        Yields:
            Tuples of (path, value) for each successfully read path.
        """

        for path in paths:
            val = self.read(path, what=what, val_if_not_found=val_if_not_found)
            yield path, val

    def read_paths(self,
                   paths: Iterable[Path],
                   what: str = "",
                   val_if_not_found: str | None = None) -> Generator[tuple[Path, str], None, None]:
        """
        Read multiple sysfs files and yield their paths and contents.

        Args:
            paths: Paths to the sysfs files to read.
            what: Optional short description of what is being read, included in exception messages.
            val_if_not_found: Value to return for missing files instead of raising an exception.

        Yields:
            Tuples of (path, value) for each file read.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorPath: An I/O error occurred while reading files (includes path information).

        Notes:
            - The order of yielded results matches the order of input paths.
        """

        if self._optimize_io:
            if not VERIFY_IO_OPTIMIZATIONS:
                yield from self._read_paths_optimized(paths, what=what,
                                                      val_if_not_found=val_if_not_found)
            else:
                # Materialize paths list since we need to iterate it twice for verification.
                paths_list = list(paths)
                iterator1 = self._read_paths(paths_list, what=what,
                                             val_if_not_found=val_if_not_found)
                iterator2 = self._read_paths_optimized(paths_list, what=what,
                                                       val_if_not_found=val_if_not_found)

                for (path1, val1), (path2, val2) in zip(iterator1, iterator2):
                    if path1 != path2 or val1 != val2:
                        raise Error(f"BUG: I/O optimization verification failed!\n"
                                    f"- Unoptimized path: '{path1}'\n"
                                    f"- Unoptimized value: '{val1}'\n"
                                    f"- Optimized path: '{path2}'\n"
                                    f"- Optimized value: '{val2}'")
                    yield path1, val1
        else:
            yield from self._read_paths(paths, what=what, val_if_not_found=val_if_not_found)

    def read_paths_int(self,
                       paths: Iterable[Path],
                       what: str = "",
                       val_if_not_found: str | None = None) -> \
                                                        Generator[tuple[Path, int], None, None]:
        """
        Read multiple sysfs files and yield their paths and contents as integers.

        Args:
            paths: Paths to the sysfs files to read.
            what: Optional short description of what is being read, included in exception messages.
            val_if_not_found: Value to return for missing files instead of raising an exception.

        Yields:
            Tuples of (path, value) for each file read, where value is an integer.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorBadFormat: The file contents cannot be parsed as an integer.
            ErrorPath: An I/O error occurred while reading files (includes path information).

        Notes:
            - The order of yielded results matches the order of input paths.
        """

        for path, val in self.read_paths(paths, what=what, val_if_not_found=val_if_not_found):
            try:
                intval = Trivial.str_to_int(val, what=what)
            except Error as err:
                what = "" if not what else f" {what}"
                raise ErrorBadFormat(f"Bad contents of{what} sysfs file '{path}'"
                                     f"{self._pman.hostmsg}\n{err.indent(2)}") from err
            yield path, intval

    def write(self, path: Path, val: str, what: str = ""):
        """
        Write a value to a sysfs file and update the cache.

        If a transaction is in progress, the write operation is queued for the transaction,
        otherwise, the value is written immediately.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional short description of what is being written, included in exception
                  messages.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorPath: An I/O error occurred while writing to the file (includes path
                       information).
        """

        if self._read_only:
            raise Error("Cannot write in read-only mode")

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
            ErrorNotSupported: The file does not exist.
            ErrorPath: An I/O error occurred while writing to the file (includes path
                       information).
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

        Write the specified value to the sysfs file, then read it back to ensure it matches what
        was written. If the verification fails, retry the operation.

        Args:
            path: Path to the sysfs file to write to.
            val: Value to write to the file.
            what: Optional short description of what is being written, included in exception
                  messages.
            retries: Number of times to retry verification if it fails.
            sleep: Number of seconds to sleep between verification retries.

        Raises:
            ErrorNotSupported: The file does not exist.
            ErrorVerifyFailedPath: The value read from the file does not match the value written
                                   (includes path information).
            ErrorPath: An I/O error occurred while writing to the file (includes path
                       information).
        """

        if self._read_only:
            raise Error("Cannot write in read-only mode")

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
        """
        Same as 'write_verify()', but write an integer value 'val'.

        Args:
            path: Path to the sysfs file to write to.
            val: Integer value to write (can be provided as string or int).
            what: Optional description of what is being written (used in error messages).
            retries: Number of times to retry verification if the value does not match.
            sleep: Number of seconds to sleep between retries.

        Raises:
            ErrorNotSupported: The sysfs file does not support the requested value.
            ErrorVerifyFailedPath: Verification failed after all retries (includes path
                                   information).
            ErrorPath: An I/O error occurred while writing to the file (includes path
                       information).
        """

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
                # Make sure the expected and actual values are of an integer type.
                setattr(err, "expected", intval)
                if hasattr(err, "actual") and Trivial.is_int(str(err.actual)):
                    err.actual = int(str(err.actual))
                raise err

        self.cache_add(path, val)

    def _write_paths_optimized_helper(self,
                                      paths: list[Path],
                                      val: str,
                                      what: str = ""):
        """
        Write a value to multiple sysfs files with I/O optimizations for remote hosts.

        Args:
            paths: List of file paths to write to.
            val: The value to write to the files.
            what: Optional short description of what is being written, included in exception
                  messages.
        """

        python_path = self._pman.get_python_path()

        _LOG.debug("Remote: Write: Value '%s' to %d sysfs files%s",
                   val, len(paths), self._pman.hostmsg)

        paths_str = ",\n".join(f"\"{str(path)}\"" for path in paths)
        cmd = f"""{python_path} -c '
paths = [{paths_str}]
for path in paths:
    try:
        with open(path, "w") as fobj:
            fobj.write("{val}")
    except Exception as err:
        print("ERROR: Write: '%s': '%s'" % (path, err))
        break
'"""

        try:
            stdout, stderr = self._pman.run_verify_join(cmd)
        except Error as err:
            what = "" if not what else f" {what}"
            errmsg = err.indent(2)
            raise type(err)(f"Failed to write to{what} sysfs file(s){self._pman.hostmsg}:\n"
                            f"{errmsg}") from err

        if stderr:
            # Nothing is expected on stderr, if there is any output, treat it as an error.
            what = "" if not what else f" {what}"
            raise Error(f"Failed to write to{what} sysfs file(s){self._pman.hostmsg}:\nUnexpected "
                        f"output on stderr:\n{stderr}")

        if not stdout:
            # All files written successfully.
            return

        generic_errmsg = f"Failed to flush transaction for sysfs files{self._pman.hostmsg}:\n" \
                         f"{stdout}"

        if not stdout.startswith("ERROR: Write: "):
            raise Error(generic_errmsg)

        # Only one line of output is expected, if there are multiple lines, something is wrong with
        # the output format.
        stdout_lines = stdout.splitlines()
        if len(stdout_lines) != 1:
            raise Error(generic_errmsg)
        stdout = stdout_lines[0].strip()

        regex = r"ERROR: Write: '(.+)': '(.+)'"
        mobj = re.match(regex, stdout)
        if not mobj:
            raise Error(generic_errmsg)

        path = Path(mobj.group(1))
        if path not in paths:
            raise Error(f"Unexpected path '{path}' in the error message:\n{stdout}")

        what = "" if not what else f" {what}"
        raise ErrorPath(f"Failed to write value '{val}' to{what} sysfs file '{path}'"
                        f"{self._pman.hostmsg}:\n{stdout}", path=path)

    def _write_paths_optimized(self, paths: Iterable[Path], val: str, what: str = ""):
        """
        Implement 'write_paths()' with I/O optimizations for remote hosts. The arguments are the
        same as for 'write_paths()'.

        In case of a remote host, writing to each sysfs file involves a separate SSH command, which
        can be very slow. To optimize this, we write to multiple files in a single SSH command by
        running a Python script on the remote host.
        """

        _LOG.debug("Writing to multiple sysfs files with I/O optimizations")

        write_paths: list[Path] = []
        paths_len = 0

        for path in paths:
            path_len = len(str(path))
            if path_len > _MAX_PATHS_LEN:
                raise Error(f"Path '{path}' is too long for optimized writing (length {path_len}: "
                            f"It exceeds the limit of {_MAX_PATHS_LEN} characters)")

            if paths_len + path_len < _MAX_PATHS_LEN:
                write_paths.append(path)
                paths_len += path_len
                continue

            self._write_paths_optimized_helper(write_paths, val, what=what)
            write_paths = [path]
            paths_len = path_len

        self._write_paths_optimized_helper(write_paths, val, what=what)

    def write_paths(self, paths: Iterable[Path], val: str, what: str = ""):
        """
        Write a value to multiple sysfs files and update the cache.

        If a transaction is in progress, the write operations are queued for the transaction,
        otherwise, the value is written immediately.

        Args:
            paths: Paths to the sysfs files to write to.
            val: The value to write to the files.
            what: Optional short description of what is being written, included in exception
                  messages.

        Raises:
            ErrorNotSupported: Any file does not exist.
            ErrorPath: An I/O error occurred while writing to files (includes path information).
        """

        if self._read_only:
            raise Error("Cannot write in read-only mode")

        paths_list = list(paths)

        for path in paths_list:
            self.cache_remove(path)

        if self._in_transaction:
            for path in paths_list:
                self._add_for_transaction(path, val, what)
        elif self._optimize_io:
            if not VERIFY_IO_OPTIMIZATIONS:
                self._write_paths_optimized(paths_list, val, what=what)
            else:
                self._write_paths_optimized(paths_list, val, what=what)
                for path in paths_list:
                    self._verify(path, val, what=what)
        else:
            for path in paths_list:
                self._write(path, val, what=what)

        for path in paths_list:
            self.cache_add(path, val)

    def write_paths_int(self, paths: Iterable[Path], val: str | int, what: str = ""):
        """
        Write an integer value to multiple sysfs files.

        If a transaction is in progress, the write operations are queued for the transaction,
        otherwise, the value is written immediately.

        Args:
            paths: Paths to the sysfs files to write to.
            val: The integer value to write to the files.
            what: Optional short description of what is being written, included in exception
                  messages.

        Raises:
            ErrorNotSupported: Any file does not exist.
            ErrorPath: An I/O error occurred while writing to files (includes path information).
        """

        intval = Trivial.str_to_int(val, what=what)
        self.write_paths(paths, str(intval), what=what)

    def write_paths_verify(self,
                           paths: Iterable[Path],
                           val: str,
                           what: str = "",
                           retries: int = 0,
                           sleep: int | float = 0):
        """
        Write a value to multiple sysfs files and verify that the kernel accepted it.

        Write the specified value to the sysfs files, then read them back to ensure they match what
        was written. If the verification fails, retry the operation.

        If a transaction is in progress, the write operations are queued for the transaction,
        otherwise, the value is written immediately.

        Args:
            paths: Paths to the sysfs files to write to.
            val: The value to write to the files.
            what: Optional short description of what is being written, included in exception
                  messages.
            retries: Number of times to retry verification if it fails.
            sleep: Number of seconds to sleep between verification retries.

        Raises:
            ErrorVerifyFailedPath: Verification of a write operation failed (includes path
                                   information).
            ErrorPath: An I/O error occurred while writing to files (includes path information).
        """

        if self._read_only:
            raise Error("Cannot write in read-only mode")

        paths_list = list(paths)

        if self._in_transaction:
            for path in paths_list:
                self.cache_remove(path)
                self._add_for_transaction(path, val, what, verify=True, retries=retries,
                                          sleep=sleep)
                self.cache_add(path, val)
        else:
            for path in paths_list:
                self.cache_remove(path)

            if self._optimize_io:
                # Prepare the batch buffer.
                batch_info: dict[Path, _TransactionItemTypedDict] = {}
                for path in paths_list:
                    batch_info[path] = {
                        "val": val,
                        "what": what,
                        "verify": True,
                        "retries": retries,
                        "sleep": sleep
                    }
                self._write_paths_vals_optimized(batch_info)
            else:
                for path in paths_list:
                    self._write(path, val, what=what)
                    self._verify(path, val, what, retries, sleep)

            for path in paths_list:
                self.cache_add(path, val)

    def write_paths_verify_int(self,
                               paths: Iterable[Path],
                               val: str | int,
                               what: str = "",
                               retries: int = 0,
                               sleep: int | float = 0):
        """
        Write an integer value to multiple sysfs files and verify that the kernel accepted it.

        Write the specified integer value to the sysfs files, then read them back to ensure they
        match what was written. If the verification fails, retry the operation.

        If a transaction is in progress, the write operations are queued for the transaction,
        otherwise, the value is written immediately.

        Args:
            paths: Paths to the sysfs files to write to.
            val: The integer value to write to the files.
            what: Optional short description of what is being written, included in exception
                  messages.
            retries: Number of times to retry verification if it fails.
            sleep: Number of seconds to sleep between verification retries.

        Raises:
            ErrorVerifyFailedPath: Verification of a write operation failed (includes path
                                   information).
            ErrorPath: An I/O error occurred while writing to files (includes path information).
        """

        intval = Trivial.str_to_int(val, what=what)
        self.write_paths_verify(paths, str(intval), what=what, retries=retries, sleep=sleep)
