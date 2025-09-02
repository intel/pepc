# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide 'DevMSREmulFile' class, which emulates '/dev/cpu/*/msr' character device files for reading
and writing CPU Model Specific Registers (MSRs).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import types
from typing import IO, Callable
from pathlib import Path
from pepclibs.helperlibs.emul import _EmulFileBase
from pepclibs.helperlibs.Exceptions import Error

def _dev_msr_emul_file_seek(self: IO[bytes], addr: int, whence: int = 0) -> int:
    """
    Seek to an MSR offset in the emulated MSR file, mimicking '/dev/msr/*' seek behavior.

    Args:
        addr: The MSR address to seek to.
        whence: Defines the reference point for the offset. Same as in the standard file 'seek()'
                method.

    Returns:
        The new absolute position of the file pointer.
    """

    orig_seek: Callable[[int, int], int] = getattr(self, "__orig_seek")
    return orig_seek(addr * 8, whence)

class DevMSREmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate '/dev/cpu/*/msr' character device files for reading and writing CPU Model Specific
    Registers (MSRs).
    """

    def __init__(self,
                 path: Path,
                 basepath: Path,
                 readonly: bool = False,
                 data: dict[int, bytes] | None = None):
        """
        Initialize a class instance.

        Args:
            path: Path to the file to emulate.
            basepath: Path to the base directory (where the emulated files are stored).
            readonly: Whether the emulated file is read-only.
            data: The initial data to populate the emulated file with. Create an empty file if "",
                  do not create an empty file if None.
        """

        super().__init__(path, basepath, readonly=readonly, data=None)

        assert data is not None
        self._populate_sparse_file(data)

    def _populate_sparse_file(self, data: dict[int, bytes]):
        """
        Create a sparse file representing the MSR device node and populate it with data.

        Args:
            data: A dictionary mapping MSR addresses to their values.
        """

        try:
            if not self.fullpath.parent.exists():
                self.fullpath.parent.mkdir(parents=True)

            with open(self.fullpath, "wb") as fobj:
                for addr, value in data.items():
                    fobj.seek(addr * 8)
                    fobj.write(value)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to prepare MSR file '{self.fullpath}':\n{errmsg}") from err

    def open(self, mode: str) -> IO[bytes]:
        """
        Open the emulated MSR device file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated file object with a patched `seek()` method.
        """

        fobj = super().open(mode)

        # Save the original 'seek()' method and set up the new 'seek()' method by monkey-patching
        # the file object.
        setattr(fobj, "__orig_seek", fobj.seek)
        setattr(fobj, "seek", types.MethodType(_dev_msr_emul_file_seek, fobj))

        return fobj
