# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide the 'GeneralRWSysfsEmulFile' class for emulating general sysfs read-write files.

The specific feature of these files is that writes always start at offset 0, as opposed to starting
from the current file offset.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import types
from pepclibs.helperlibs.emul import _EmulFileBase

if typing.TYPE_CHECKING:
    from typing import IO, Callable

def _generic_sysfs_emul_file_write(self: IO[str], data: str) -> int:
    """
    Write data to the emulated sysfs file.

    Args:
        self: The file object of the sysfs file to write to.
        data: The policy name to write to the sysfs file.

    Returns:
        The number of characters written to the file.
    """

    self.truncate(len(data))
    self.seek(0)

    orig_write: Callable[[str], int] = getattr(self, "__orig_write")
    return orig_write(data)

class GeneralRWSysfsEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate a general sysfs read-write file.
    """

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated sysfs file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated file object with a patched 'write()' method.
        """

        fobj = super().open(mode)

        # Save the original 'write()' method and set up the new 'write()' method by monkey-patching
        # the file object.
        setattr(fobj, "__orig_write", fobj.write)
        setattr(fobj, "write", types.MethodType(_generic_sysfs_emul_file_write, fobj))

        return fobj
