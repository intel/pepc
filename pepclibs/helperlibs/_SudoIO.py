# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide 'SudoFile' - a file-like object implementing file I/O via sudo shell commands.

The current implementation is primitive and inefficient. Each read or write operation spawns a
separate sudo shell command ('cat' or 'printf'), which involves significant overhead. A more
efficient implementation would run an agent process on the SUT, which could receive commands such as
open, read, and write via stdin and return results via stdout and errors via stderr, avoiding the
per-operation process creation cost.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import shlex
import typing
from collections import deque
from pathlib import Path
from pepclibs.helperlibs import ClassHelpers, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied

if typing.TYPE_CHECKING:
    from typing import cast
    from pepclibs.helperlibs._ProcessManagerTypes import ProcessManagerProtocol

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class SudoFile(ClassHelpers.SimpleCloseContext):
    """
    A file-like object providing read, write, and seek operations via sudo shell commands.

    Instead of opening the file directly, each I/O operation runs a shell command with sudo
    privileges via the process manager.

    Notes:
        - Binary mode ('b' in 'mode') is supported only for UTF-8 encoded text files. Arbitrary
          binary data (e.g., executables) is not supported, because all I/O goes through a shell,
          which operates on text.
    """

    def __init__(self, pman: ProcessManagerProtocol, path: str | Path, mode: str):
        """
        Initialize 'SudoFile'.

        Args:
            pman: The process manager to use for running sudo commands.
            path: The path to the file to access.
            mode: The file mode (e.g., "r", "r+", "rb"). Determines whether the file is accessed
                  in text or binary mode.
        """

        self._offset = 0
        self._pman = pman
        self._path = path
        self._mode = mode

        self.name = Path(path).name
        self._lines: deque[str] | deque[bytes] = deque()

        _LOG.debug(f"Opening file '{path}' with mode '{mode}' via sudo{self._pman.hostmsg}")

        if "w" in mode:
            # The "w" mode always assumes truncation.
            pman.run_verify(f"true > {shlex.quote(str(path))}", su=True)

    def close(self):
        """Free allocated resources."""

        ClassHelpers.close(self, unref_attrs=("_pman",))

    def read(self, size: int | None = None) -> bytes | str:
        """
        Read data from the file via sudo.

        Read the entire file via 'cat', then return the portion starting at the current file
        position, optionally limited to 'size' bytes or characters.

        Args:
            size: Maximum number of bytes or characters to read. If None, read until the end of the
                  file.

        Returns:
            The data read from the file. Return bytes in binary mode, or a string in text mode.
        """

        path = str(self._path)

        _LOG.debug(f"Reading from file '{path}' with size {size} and mode '{self._mode}' via sudo"
                   f"{self._pman.hostmsg}")

        stdout, _ = self._pman.run_verify_join(f"cat {shlex.quote(path)}", su=True)
        data = stdout[self._offset:]
        if size is not None:
            data = data[:size]
        self._offset += len(data)

        if "b" in self._mode:
            try:
                return data.encode("utf-8")
            except UnicodeEncodeError as err:
                raise Error(f"Failed to encode data read from '{path}' as UTF-8") from err

        return data

    def write(self, data: str | bytes) -> int:
        """
        Write data to the file via sudo.

        Args:
            data: The data to write. Must be a string in text mode or bytes in binary mode.

        Returns:
            The number of characters or bytes written.
        """

        path = str(self._path)

        _LOG.debug(f"Writing to file '{path}' with mode '{self._mode}' via sudo"
                   f"{self._pman.hostmsg}. Data length: {len(data)}")

        path_quoted = shlex.quote(path)

        if isinstance(data, bytes):
            try:
                str_data = data.decode("utf-8")
            except UnicodeDecodeError as err:
                raise Error(f"Failed to decode data to write to '{path}' as UTF-8") from err
        else:
            str_data = data

        write_len = len(str_data)

        if "a" in self._mode:
            # Append mode: always write after the end of the file.
            cmd = f"printf '%s' {shlex.quote(str_data)} >> {path_quoted}"
        elif path.startswith("/sys"):
            # Sysfs files are not seekable and always expect writes from the beginning.
            cmd = f"printf '%s' {shlex.quote(str_data)} > {path_quoted}"
        else:
            # All other modes: write at the current offset.
            #
            # Read the current content, insert the new data at the current offset, and write the
            # full modified content back.
            stdout, _ = self._pman.run_verify_join(f"cat {path_quoted}", su=True)
            end = self._offset + write_len
            file_content = stdout[:self._offset] + str_data + stdout[end:]
            cmd = f"printf '%s' {shlex.quote(file_content)} > {path_quoted}"

        try:
            self._pman.run_verify(cmd, su=True)
        except Error as err:
            errmsg = str(err).lower()
            if "permission denied" in errmsg or "operation not permitted" in errmsg:
                raise ErrorPermissionDenied(str(err)) from err
            raise

        self._offset += write_len
        return len(data)

    def truncate(self, size: int | None = None) -> int:
        """
        Truncate the file to at most 'size' characters or bytes via sudo.

        Read the full file content and write back only the first 'size' characters. If 'size' is
        None, truncate at the current file position. The file position is not changed.

        Args:
            size: The new file length. If None, use the current file position.

        Returns:
            The new file size.

        Notes:
            - Extending the file size is not supported.
        """

        if size is None:
            size = self._offset

        path = str(self._path)

        _LOG.debug(f"Truncating file '{path}' to size {size} with mode '{self._mode}' via sudo"
                   f"{self._pman.hostmsg}")

        path_quoted = shlex.quote(path)

        if path.startswith("/sys"):
            raise Error(f"Truncating sysfs files is not supported, file '{path}'"
                        f"{self._pman.hostmsg}")

        stdout, _ = self._pman.run_verify_join(f"cat {path_quoted}", su=True)

        if size > len(stdout):
            raise Error(f"Extending file size is not supported: Requested size {size}, current "
                        f"file size {len(stdout)}, file '{path}'{self._pman.hostmsg}")

        if size == len(stdout):
            return size

        new_content = stdout[:size]
        self._pman.run_verify(f"printf '%s' {shlex.quote(new_content)} > {path_quoted}", su=True)

        return size

    def seek(self, offset: int, whence: int = 0) -> int:
        """
        Move the file position to the given offset.

        Args:
            offset: The new file position, interpreted according to 'whence'.
            whence: How to interpret 'offset': 0 for absolute positioning (SEEK_SET), 1 for
                    relative to the current position (SEEK_CUR). SEEK_END (2) is not supported.

        Returns:
            The new file position.
        """

        if whence == 0:
            self._offset = offset
        elif whence == 1:
            self._offset += offset
        else:
            raise NotImplementedError(f"'whence={whence}' is not supported")

        _LOG.debug(f"Seeking to offset {self._offset} in file '{self._path}' with mode "
                   f"'{self._mode}' via sudo{self._pman.hostmsg}")

        return self._offset

    def readlines(self) -> list[str] | list[bytes]:
        """
        Read and return all lines from the current file position as a list.

        Returns:
            A list of lines. Return a list of 'bytes' objects in binary mode, or a list of strings
            in text mode.
        """

        data = self.read()
        return data.splitlines(keepends=True)

    def __iter__(self) -> SudoFile:
        """Return the iterator object (self)."""

        lines = self.readlines()
        if typing.TYPE_CHECKING:
            self._lines = deque(cast(list, lines))
        else:
            self._lines = deque(lines)
        return self

    def __next__(self) -> str | bytes:
        """Return the next line, raising 'StopIteration' when exhausted."""

        if not self._lines:
            raise StopIteration
        return self._lines.popleft()
