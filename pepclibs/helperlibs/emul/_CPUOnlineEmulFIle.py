# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide 'CPUOnlineEmulFile' class to emulate the global '/sys/devices/system/cpu/online' file.
"""

import types
from pathlib import Path
from typing import IO
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import ErrorBadFormat
from pepclibs.helperlibs.emul import _EmulFileBase

def _cpu_online_emul_file_read(self: IO[str]) -> str:
    """
    Implement the 'read()' method of a file object representing the global CPU online file
    ('/sys/devices/system/cpu/online').

    Scan per-CPU online files under the base directory and format the resulting
    string as a range of online CPU numbers.

    For example, if there are 4 CPUs and CPU2 is offline, read the following files:
      - '/sys/devices/system/cpu/cpu0/online': "1"
      - '/sys/devices/system/cpu/cpu1/online': "1"
      - '/sys/devices/system/cpu/cpu2/online': "0"
      - '/sys/devices/system/cpu/cpu3/online': "1"

    Return the result as "0-1,3".

    Args:
        self: The file object of the global CPU online file in the base directory.

    Returns:
        The contents of the global CPU online file.
    """

    basepath = Path(getattr(self, "__emul_basepath"))
    cpuonline_dir = basepath / "sys" / "devices" / "system" / "cpu"

    online_cpus: list[int] = []
    for dirname in cpuonline_dir.iterdir():
        # Only process directories matching the "cpu\d+" pattern.
        if not dirname.name.startswith("cpu"):
            continue
        try:
            cpu = Trivial.str_to_int(dirname.name[3:])
        except ErrorBadFormat:
            continue

        try:
            with open(dirname / "online", "r", encoding="utf-8") as fobj:
                data = fobj.read().strip()
        except FileNotFoundError:
            if cpu == 0:
                # CPU 0 does not have a "online" file, because Linux does not support offlining
                # CPU0. So assume it is online.
                online_cpus.append(cpu)
                continue
            raise

        if data == "1":
            online_cpus.append(cpu)

    return Trivial.rangify(online_cpus)

class CPUOnlineEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate the global '/sys/devices/system/cpu/online' file. This file containts CPU numbers of
    all online CPUs in the system.

    For example, if there are 4 CPUs in total, and CPU 2 is offline, the file will contain "0-1,3".
    """

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated global CPU online file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated read-only file object with a patched `read()` method.
        """

        fobj = super().open(mode)

        # Save the base directory path in the file object.
        setattr(fobj, "__emul_basepath", self.basepath)
        # Monkey-patch the 'read()' method of the file object.
        setattr(fobj, "read", types.MethodType(_cpu_online_emul_file_read, fobj))

        return fobj
