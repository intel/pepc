# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide 'EPBEmulFile' class to emulate EPB sysfs files, for example
'/sys/devices/system/cpu/cpu10/power/energy_perf_bias'.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import types
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.emul import _EmulFileBase

if typing.TYPE_CHECKING:
    from typing import IO, Final, Callable

# Dictionary mapping EPB policy names to their corresponding EPB values.
_EPB_POLICIES: Final[dict[str, int]] = {"performance": 0, "balance-performance": 4, "normal": 6,
                                        "balance-power": 8, "power": 15}

def _epb_emul_file_write(self: IO[str], data: str) -> int:
    """
    Write data to an emulated EPB sysfs file, supporting both integer EPB values and EPB policy
    names.

    Args:
        self: The file object of the EPB sysfs file to write to.
        data: The string to write to the EPB sysfs file. Can be an integer value or a
              policy name.

    Returns:
        The number of characters written to the file.
    """

    value = data.strip()
    if value in _EPB_POLICIES:
        data = f"{_EPB_POLICIES[value]}\n"
    elif not Trivial.is_int(data):
        raise Error(f"Invalid EPB value: {data}")

    self.truncate(len(data))
    self.seek(0)

    orig_write: Callable[[str], int] = getattr(self, "__orig_write")
    return orig_write(data)

class EPBEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate EPB sysfs files, for example '/sys/devices/system/cpu/cpu10/power/energy_perf_bias'.
    """

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated EPB sysfs file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated read-only file object with a patched 'write()' method.
        """

        fobj = super().open(mode)

        # Save the original 'write()' method and set up the new 'write()' method by monkey-patching
        # the file object.
        setattr(fobj, "__orig_write", fobj.write)
        setattr(fobj, "write", types.MethodType(_epb_emul_file_write, fobj))

        return fobj
