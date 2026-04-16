# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide 'LoggerFile', a write-only file-like object that routes written data to the logger.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import io
import typing
from typing import IO
from pepclibs.helperlibs import Logging, _ProcessManagerBase

if typing.TYPE_CHECKING:
    from types import TracebackType
    from typing import Iterator

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class LoggerFile(IO[str]):
    """
    A write-only file-like object that routes data to the logger.

    The intended use case is to capture output of a command run via a process manager and route it
    through the logging system.

    Examples:
        - Route command stdout to the logger at INFO level and stderr at WARNING level:
            stdout_fobj = LoggerFile(Logging.INFO)
            stderr_fobj = LoggerFile(Logging.WARNING)
            pman.run_verify(cmd, output_fobjs=(stdout_fobj, stderr_fobj))
        - Add a prefix to distinguish the command output from other log messages:
            fobj = LoggerFile(Logging.DEBUG, prefix="[my command] ")
            pman.run_verify(cmd, output_fobjs=(fobj, None))
    """

    @property
    def mode(self) -> str:
        """The file mode."""
        return "w"

    @property
    def encoding(self) -> str:
        """The file encoding."""
        return "utf-8"

    @property
    def errors(self) -> str | None:
        """The file error mode."""
        return None

    @property
    def line_buffering(self) -> bool:
        """Whether line buffering is enabled."""
        return False

    @property
    def newlines(self) -> str | tuple[str, ...] | None:
        """The newlines used in the file."""
        return None

    @property
    def name(self) -> str | int:
        """The file name."""
        return "<LoggerFile>"

    @property
    def closed(self) -> bool:
        """Whether this file object has been closed."""
        return self._closed

    @property
    def buffer(self) -> IO[bytes]:
        """The underlying binary buffer."""
        raise io.UnsupportedOperation("buffer")

    def __init__(self,
                 level: int = Logging.INFO,
                 prefix: str = "",
                 logger: Logging.Logger | None = None):
        """
        Initialize a class instance.

        Args:
            level: The logging level for emitting complete lines. Defaults to 'Logging.INFO'.
            prefix: An optional string prepended to every logged line.
            logger: The logger to emit lines to. Defaults to the module-level logger.
        """

        self._level = level
        self._prefix = prefix
        self._buf = ""
        self._logger = logger if logger is not None else _LOG
        self._closed = False

    def write(self, data: str) -> int:
        """
        Log complete lines from the provided data, buffer the incomplete line, waiting for the next
        write to provide the rest of the line.

        Args:
            data: The string data to write.

        Returns:
            The number of characters in 'data'.
        """

        lines, self._buf = _ProcessManagerBase.extract_full_lines(self._buf + data, keepends=False)
        for line in lines:
            self._logger.log(self._level, self._prefix + line)
        return len(data)

    def writelines(self, lines: list[str]) -> None:  # type: ignore[override]
        """Write a list of lines by calling 'write()' for each one."""

        for line in lines:
            self.write(line)

    def flush(self) -> None:
        """
        Flush the logger's handlers.

        Note:
            Partial lines are held in the buffer to avoid the logger appending a premature newline
            if more data arrives later.
        """

        for handler in self._logger.handlers:
            handler.flush()

    def close(self) -> None:
        """Emit any remaining buffered data to the logger and flush the logger's handlers."""

        if self._buf:
            self._logger.log(self._level, self._prefix + self._buf)
            self._buf = ""

        self._closed = True
        self.flush()

    def __enter__(self) -> IO[str]:
        """Enter the runtime context."""
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> None:
        """Exit the runtime context."""
        self.close()

    def readable(self) -> bool:
        """Whether the file is readable."""
        return False

    def writable(self) -> bool:
        """Whether the file is writable."""
        return True

    def seekable(self) -> bool:
        """Whether the file supports seeking."""
        return False

    def isatty(self) -> bool:
        """Whether the file is interactive."""
        return False

    def read(self, n: int = -1) -> str:
        """Read and return up to 'n' characters from the file."""
        raise io.UnsupportedOperation("read")

    def readline(self, limit: int = -1) -> str:
        """Read and return one line from the file."""
        raise io.UnsupportedOperation("readline")

    def readlines(self, hint: int = -1) -> list[str]:
        """Read and return a list of lines from the file."""
        raise io.UnsupportedOperation("readlines")

    def seek(self, offset: int, whence: int = 0) -> int:
        """Change the file position to 'offset'."""
        raise io.UnsupportedOperation("seek")

    def tell(self) -> int:
        """Return the current file position."""
        raise io.UnsupportedOperation("tell")

    def truncate(self, size: int | None = None) -> int:
        """Truncate the file to at most 'size' bytes."""
        raise io.UnsupportedOperation("truncate")

    def fileno(self) -> int:
        """Return the underlying file descriptor."""
        raise io.UnsupportedOperation("fileno")

    def __iter__(self) -> Iterator[str]:
        """Return an iterator over the lines of the file."""
        raise io.UnsupportedOperation("__iter__")

    def __next__(self) -> str:
        """Return the next line from the stream."""
        raise io.UnsupportedOperation("__next__")
