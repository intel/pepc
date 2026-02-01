# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide 'CPUOnlineEmulFile' class to emulate CPU online state files ('/proc/cpuinfo' and
'/sys/devices/system/cpu/online').
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import types
from pathlib import Path

from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import ErrorBadFormat
from pepclibs.helperlibs.emul import _EmulFileBase

if typing.TYPE_CHECKING:
    from typing import IO, cast

def _get_online_cpus(basepath: Path) -> list[int]:
    """
    Scan per-CPU online files under the base directory and return a list of online CPU numbers.

    Args:
        basepath: The base directory where per-CPU online files are located.

    Returns:
        A list of online CPU numbers.
    """

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

    return online_cpus

def _proc_cpuinfo_emul_file_read(self: IO[str]) -> str:
    """
    Implement the 'read()' method of a file object representing the '/proc/cpuinfo' file.

    Scan per-CPU online files under the base directory and format the resulting
    string as the contents of the '/proc/cpuinfo' file, including only online CPUs.

    Args:
        self: The file object of the '/proc/cpuinfo' file in the base directory.
    Returns:
        The contents of the '/proc/cpuinfo' file.
    """

    online_cpus = _get_online_cpus(Path(getattr(self, "__emul_basepath")))
    proc_cpuinfo_blocks: dict[int, str] = getattr(self, "__proc_cpuinfo_blocks")
    contents = ""

    for cpu in online_cpus:
        if contents:
            contents += "\n\n"
        contents += proc_cpuinfo_blocks[cpu]

    return contents

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

    online_cpus = _get_online_cpus(basepath)
    return Trivial.rangify(online_cpus)

class CPUOnlineEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate files containing per-CPU information, such as '/proc/cpuinfo' and
    '/sys/devices/system/cpu/online' file. The problem with these files is that when a CPU goes
    online or offline, the contents of these files change.
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

        super().__init__(path, basepath, readonly=readonly, data=data)


        # The '/proc/cpuinfo' consists of blocks of text, one block per CPU. Store these blocks in a
        # dictionary keyed by CPU number in order to quickly generate the contents of the emulated
        # '/proc/cpuinfo' file based on which CPUs are online.
        self._proc_cpuinfo_blocks: dict[int, str] = {}

        if path == Path("/proc/cpuinfo"):
            if typing.TYPE_CHECKING:
                _data = cast(str, data)
            else:
                _data = data
            self._init_proc_cpuinfo_blocks(_data)

    def _init_proc_cpuinfo_blocks(self, data: str) -> None:
        """
        Parse the contents of the '/proc/cpuinfo' file and store the blocks for online and offline
        CPUs. The end goal is to be able to quickly generate the contents of the emulated
        '/proc/cpuinfo' file based on which CPUs are online.

        This method assumes that initially all CPUs are online.
        """

        for block in data.strip().split("\n\n"):
            for line in block.split("\n"):
                if not line.startswith("processor"):
                    continue
                cpu = Trivial.str_to_int(line.split(":", 1)[1].strip())
                self._proc_cpuinfo_blocks[cpu] = block
                break

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated global CPU online file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated read-only file object with a patched 'read()' method.
        """

        fobj = super().open(mode)

        # Save the base directory path in the file object.
        setattr(fobj, "__emul_basepath", self.basepath)

        # Monkey-patch the 'read()' method of the file object.
        if self.path == Path("/proc/cpuinfo"):
            # Save the 'proc_cpuinfo_blocks' in the file object.
            setattr(fobj, "__proc_cpuinfo_blocks", self._proc_cpuinfo_blocks)
            setattr(fobj, "read", types.MethodType(_proc_cpuinfo_emul_file_read, fobj))
        else:
            setattr(fobj, "read", types.MethodType(_cpu_online_emul_file_read, fobj))

        return fobj
