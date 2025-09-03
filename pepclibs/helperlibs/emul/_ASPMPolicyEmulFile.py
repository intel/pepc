# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide 'ASPMPolicyEmulFile' class to emulate the global PCI ASPM policy file
('/sys/module/pcie_aspm/parameters/policy').
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import types
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.emul import _EmulFileBase

if typing.TYPE_CHECKING:
    from typing import IO, Callable

def _aspm_policy_emul_file_write(self: IO[str], data: str) -> int:
    """
    Write data to the emulated global ASPM policy sysfs file.

    Args:
        self: The file object of the global PCI ASPM policy sysfs file to write to.
        data: The policy name to write to the sysfs file.

    Returns:
        The number of characters written to the file.
    """

    # Mimic the sysfs ASPM policy file behavior, which provides the current policy name in brackets.
    # Example:
    #     - Initial policy file contents:
    #         [default] performance powersave powersupersave
    #     - File contents after writing 'performance':
    #         default [performance] powersave powersupersave

    self.seek(0)

    policies: str = self.read()
    policies = policies.replace("[", "").replace("]", "")

    data = data.rstrip("\n")
    if data not in policies.rstrip("\n").split():
        raise Error(f"Invalid ASPM policy: '{data}'")

    policies = policies.replace(data, f"[{data}]")

    self.truncate(len(policies))
    self.seek(0)

    orig_write: Callable[[str], int] = getattr(self, "__orig_write")
    return orig_write(policies)

class ASPMPolicyEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate the global PCI ASPM policy file ('/sys/module/pcie_aspm/parameters/policy').
    """

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated global PCI ASPM polity file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated file object with a patched `write()` method.
        """

        fobj = super().open(mode)

        # Save the original 'write()' method and set up the new 'write()' method by monkey-patching
        # the file object.
        setattr(fobj, "__orig_write", fobj.write)
        setattr(fobj, "write", types.MethodType(_aspm_policy_emul_file_write, fobj))

        return fobj
