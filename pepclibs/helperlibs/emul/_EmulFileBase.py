# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Base class for emulated file objects.

Emulated file classes provide a single public method: open(). This method returns a file-like object
for the emulated file, allowing users to perform standard I/O operations.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import types
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import IO

class EmulFileBase:
    """
    Base class for emulated file classes. Represents a regular read-only or read-write file in the
    base directory.
    """

    def __init__(self,
                 path: Path,
                 basepath: Path,
                 readonly: bool = False,
                 data: str | bytes | None = None):
        """
        Initialize a class instance.

        Args:
            path: Path to the file to emulate.
            basepath: Path to the base directory (where the emulated files are stored).
            readonly: Whether the emulated file is read-only.
            data: The initial data to populate the emulated file with. Create an empty file if empty
                  string, do not create an empty file if None.
        """

        self.path = path
        self.basepath = basepath
        self.readonly = readonly

        # Note about lstrip(): 'self.path' is usually an absolute path starting with '/', and
        # joining it directly with 'self.basepath' would ignore the base path. For example,
        # Path("/tmp") / "/sys" results in "/sys" instead of "/tmp/sys". Removing the leading '/'
        # ensures the file is placed under the base path.
        self.fullpath = self.basepath / str(self.path).lstrip("/")

        if data is not None:
            try:
                if not self.fullpath.parent.exists():
                    self.fullpath.parent.mkdir(parents=True)
                with self._open("w") as fobj:
                    fobj.write(data)
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to prepare '{self.fullpath}':\n{errmsg}") from err

    def _open(self, mode: str) -> IO:
        """
        Open the emulated file. The file resides in the temporary directory the base directory.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated read-only file object.
        """

        encoding: str | None

        # Allow for disabling buffering only in binary mode.
        if "b" in mode:
            buffering = 0
            encoding = None
        else:
            buffering = -1
            encoding = "utf-8"

        errmsg_prefix = f"Cannot open file '{self.fullpath}' with mode '{mode}': "
        try:
            # pylint: disable-next=consider-using-with
            fobj = open(self.fullpath, mode, buffering=buffering, encoding=encoding)
        except PermissionError as err:
            errmsg = Error(str(err)).indent(2)
            raise ErrorPermissionDenied(f"{errmsg_prefix}\n{errmsg}") from None
        except FileNotFoundError as err:
            errmsg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg_prefix}\n{errmsg}") from None
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"{errmsg_prefix}\n{errmsg}") from None

        return fobj

    def open(self, mode: str) -> IO:
        """
        Open the emulated file with read-only enforcement if configured.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            File object with 'write()' method patched if the file is read-only.
        """

        def _readonly_fobj_write(self: IO, _):
            """
            The 'write()' method for read-only file objects. Just raise an exception.

            Args:
                _: Ignored.

            Raises:
                ErrorPermissionDenied: If a write operation is attempted on a read-only file.
            """

            fullpath: str = getattr(self, "__emul_fullpath", "")
            raise ErrorPermissionDenied(f"Cannot write to a read-only file '{fullpath}'")

        fobj = self._open(mode)

        if self.readonly:
            # Monkey-patch the 'write()' method to ensure writes fail.
            setattr(fobj, "__emul_fullpath", self.fullpath)
            setattr(fobj, "write", types.MethodType(_readonly_fobj_write, fobj))

        return fobj
