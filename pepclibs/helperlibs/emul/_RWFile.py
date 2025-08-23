# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Emulate read-write sysfs, procfs, and debugfs files."""

import types
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.emul import _EmulFileBase

class RWSysinfoFile(_EmulFileBase.EmulFileBase):
    """Emulate read-write sysfs files."""

    def __init__(self,
                 path: Path,
                 basepath: Path,
                 data: str):
        """
        Initialize a class instance.

        Args:
            path: Path to the file to emulate.
            basepath: Path to the base directory (where the emulated files are stored).
            readonly: Whether the emulated file is read-only.
            data: The initial data to populate the emulated file with.
        """

        super().__init__(path, basepath, data=data)

    def _set_write_method(self, fobj, path, mode):
        """
        Some files needs special handling when written to. Replace the 'write()' method of 'fobj'
        with a custom method in order to properly emulate the behavior of the file in 'path'.
        """

        def _epb_write(self, data):
            """
            Mimic the sysfs 'energy_perf_bias' file behavior. In addition to supporting numbers, it
            also supports policies.
            """

            policies = {"performance": 0, "balance-performance": 4, "normal": 6,
                        "balance-power": 8, "power": 15}

            key = data.strip()
            if key in policies:
                data = f"{policies[key]}\n"
            self.truncate(len(data))
            self.seek(0)
            self._orig_write(data)

        def _aspm_write(self, data):
            """
            Mimic the sysfs ASPM policy file behavior.

            For example, writing "powersave" to the file results in the following file contents:
            "default performance [powersave] powersupersave".
            """

            line = fobj._policies.replace(data, f"[{data}]") # pylint: disable=protected-access
            self.truncate(len(data))
            self.seek(0)
            self._orig_write(line)

        def _truncate_write(self, data):
            """
            Mimic behavior of most sysfs files: writing does not continue from the current file
            offset, but instead, starts from file offset 0. For example, writing "performance" to
            the 'scaling_governor' results in the file containing only "performance", regardless of
            what the file contained before the write operation.
            """

            self.truncate(len(data))
            self.seek(0)
            self._orig_write(data)

        if "w" in mode:
            raise Error("BUG: use 'r+' mode when opening sysfs virtual files")

        if mode != "r+":
            return

        # pylint: disable=pepc-unused-variable,protected-access
        fobj._orig_write = fobj.write

        path_str = str(path)
        if path_str.endswith("pcie_aspm/parameters/policy"):
            policies = fobj.read().strip()
            fobj._policies = policies.replace("[", "").replace("]", "")
            setattr(fobj, "write", types.MethodType(_aspm_write, fobj))
        elif path_str.endswith("/energy_perf_bias"):
            setattr(fobj, "write", types.MethodType(_epb_write, fobj))
        else:
            setattr(fobj, "write", types.MethodType(_truncate_write, fobj))
        # pylint: enable=pepc-unused-variable,protected-access

    def open(self, mode):
        """Create a file in the temporary directory and return the file object with 'mode'."""

        fobj = super().open(mode)
        self._set_write_method(fobj, self.path, mode)
        return fobj
