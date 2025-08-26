# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide 'TPMIEmulFile' class to emulate TPMI debugfs 'mem_write' files.
"""

import re
import types
from typing import IO, Callable
from pathlib import Path
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.emul import _EmulFileBase

def _mem_write_emul_file_write(self: IO[str], data: str) -> int:
    """
    Write data to an emulated TPMI 'mem_write' debugfs file.

    Args:
        self: The file object of the TPMI 'mem_write' debugfs file to write to.
        data: The string to write to the TPMI 'mem_write' debugfs file.

    Returns:
        The number of characters written to the file.
    """

    split = data.split(",")
    if len(split) != 3:
        raise Error(f"Invalid TPMI 'mem_write' file data format '{data}'")

    instance_str, offset_str, value_str = split

    instance = Trivial.str_to_int(instance_str, what="TPMI instance")
    offset = Trivial.str_to_int(offset_str, what=f"TPMI instance {instance_str} offset")
    value = Trivial.str_to_int(value_str,
                               what=f"TPMI instance {instance_str}, offset {offset_str} value",
                               base=16)

    # The value has to be a 32-bit value.
    if value < 0 or value > 0xffffffff:
        raise Error(f"Bad value for TPMI 'mem_write' file in '{data}': must be a 32-bit integer")

    # Format a string for the 'mem_dump' file. The value has to be in hex format, without the 0x
    # prefix, and include exactly 8 digits.
    value_str = f"{value:08x}"

    md_fullpath: Path = getattr(self, "__md_fullpath")
    mdmap: dict[int, dict[int, int]] = getattr(self, "__mdmap")

    try:
        with open(md_fullpath, "r+", encoding="utf-8") as fobj:
            fobj.seek(mdmap[instance][offset])
            print(f"{data}, writing {value_str}")
            fobj.write(value_str)
    except Error as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to update the 'mem_dump' file at {md_fullpath}:\n{errmsg}") from err

    self.truncate(len(data))
    self.seek(0)

    orig_write: Callable[[str], int] = getattr(self, "__orig_write")
    return orig_write(data)

class TPMIEmulFile(_EmulFileBase.EmulFileBase):
    """
    Emulate TPMI 'mem_write' debugfs files.

    Writes to TPMI 'mem_write' files follow the format: <instance>,<offset>,<value>. In case of real
    hardware, the writes are consumed by the hardware. Writes update the TPMI memory buffer, and
    become visible via the corresponding 'mem_dump' debugfs file. The 'mem_dump' file contains a
    structured hexdump representing TPMI data for all instances.

    The goal of this class is to update the 'mem_dump' file a 'mem_write' file is written to.

    Example file path handled by this class:
        /sys/kernel/debug/tpmi-0000:00:03.1/tpmi-id-02/mem_write
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
            data: The initial data to populate the emulated file with. Create an empty file if "",
                  do not create an empty file if None.
        """

        super().__init__(path, basepath, readonly=readonly, data=data)

        self._md_fullpath = self.fullpath.parent / "mem_dump"

        # The 'mem_dump' file map (mdmap) is a dictionary that maps TPMI instance and offset values
        # to corresponding offsets within the 'mem_dump' file. Writing "<instance>,<offset>,<value>"
        # to a TPMI 'mem_write' file updates 'mem_dump' file position mdmap[<instance>][<offset>]
        # with <value>.
        self._mdmap: dict[int, dict[int, int]] = {}

    def _do_build_mdmap(self, fobj: IO[str]):
        """
        Build the 'mem_dump' file map (mdmap) from the contents of the provided file object.

        Args:
            fobj: A file object to read memory dump data from.
        """

        mdmap: dict[int, dict[int, int]] = {}
        pos = 0

        for line in fobj:
            line = line.rstrip()
            line_pos = 0

            # Sample line to match: "TPMI Instance:1 offset:0x40005000".
            match = re.match(r"TPMI Instance:(\d+) offset:(0x[0-9a-f]+)", line)
            if match:
                instance = Trivial.str_to_int(match.group(1), what="instance number")
                mdmap[instance] = {}
            else:
                # Matches two different line formats:
                #   " 00000020: 013afd40 00004000 2244aacc deadbeef" and
                #   "[00000020] 013afd40 00004000 2244aacc deadbeef".
                # Some older kernels have the second format in place.
                match = re.match(r"^( |\[)([0-9a-f]+)(:|\]) (.*)$", line)
                if match:
                    offs = Trivial.str_to_int(match.group(2), base=16, what="TPMI offset")
                    regvals = Trivial.split_csv_line(match.group(4), sep=" ")
                    line_pos += 3 + len(match.group(2))
                    for regval in regvals:
                        # Sanity-check register values and drop them.
                        Trivial.str_to_int(regval, base=16, what="TPMI value")
                        mdmap[instance][offs] = pos + line_pos
                        line_pos += 9
                        offs += 4
                else:
                    raise Error(f"Unexpected line in TPMI file '{self._md_fullpath}:\n{line}")

            pos += len(line) + 1

        self._mdmap = mdmap

    def _build_mdmap(self):
        """
        Build the 'mem_dump' file map (mdmap) from the 'mem_dump' file contents.
        """

        try:
            with open(self._md_fullpath, "r", encoding="utf-8") as fobj:
                self._do_build_mdmap(fobj)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to build 'mem_dump' file map from '{self._md_fullpath}':\n"
                        f"{errmsg}") from err

    def open(self, mode: str) -> IO[str]:
        """
        Open the emulated TPMI 'mem_write' file.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.

        Returns:
            An emulated file object with a patched `write()` method.
        """

        fobj = super().open(mode)

        if not self._md_fullpath.exists():
            raise Error(f"No 'mem_dump' TPMI file found at '{self._md_fullpath}'")

        if not self._mdmap:
            self._build_mdmap()

        setattr(fobj, "__md_fullpath", self._md_fullpath)
        setattr(fobj, "__mdmap", self._mdmap)
        setattr(fobj, "__orig_write", fobj.write)
        # Monkey-patch the 'write()' method of the file object.
        setattr(fobj, "write", types.MethodType(_mem_write_emul_file_write, fobj))

        return fobj
