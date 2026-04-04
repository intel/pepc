# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Provide API for Linux PCI devices control and discovery."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ProcessManager, LocalProcessManager, ClassHelpers, Trivial

if typing.TYPE_CHECKING:
    from typing import Generator, TypedDict, Literal
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType, LsdirTypedDict

    class PCIInfoTypedDict(TypedDict, total=False):
        """
        Represent PCI device basic information.

        Attributes:
            addr: PCI device address in extended BDF notation ([<domain>:<bus>:<slot>.<func>]).
            vendorid: PCI device vendor ID.
            devid: PCI device ID.
        """

        addr: str
        vendorid: int
        devid: int

def get_basic_info(addr: str, pman: ProcessManagerType | None = None) -> PCIInfoTypedDict:
    """
    Get basic information about a PCI device.

    Args:
        addr: PCI device address in the [<domain>:<bus>:<slot>.<func>] format.
        pman: Process manager object that defines the target host (local host by default).

    Returns:
        Dictionary with PCI device information:
            * addr: PCI device address in extended BDF notation
                    ([<domain>:<bus>:<slot>.<func>] format).
            * vendorid: PCI device vendor ID.
            * devid: PCI device ID.
    """

    info: PCIInfoTypedDict = {}
    info["addr"] = addr
    basepath = Path("/sys/bus/pci/devices") / addr

    _keys: tuple[Literal["vendorid", "devid"], ...] = ("vendorid", "devid")

    with ProcessManager.pman_or_local(pman) as wpman:
        for key, descr, fname in ((_keys[0], "Vendor ID", "vendor"),
                                  (_keys[1], "Device ID", "device")):
            path = basepath / fname
            try:
                with wpman.open(path, "r") as fobj:
                    val = fobj.read()
            except Error as err:
                raise type(err)(f"Sysfs file read operation failed{wpman.hostmsg}:\n"
                                f"{err.indent(2)}") from err

            what = f"{descr} for PCI device {addr}"
            info[key] = Trivial.str_to_int(val, base=16, what=what)

    return info

class LsPCI(ClassHelpers.SimpleCloseContext):
    """List PCI devices."""

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: Process manager object that defines the target host.
        """

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        self._sysfs_base = Path("/sys/bus/pci/devices")
        self._close_pman = pman is None

    def close(self):
        """Uninitialize the class instance."""
        ClassHelpers.close(self, close_attrs=("_pman",))

    def lspci(self) -> Generator[PCIInfoTypedDict, None, None]:
        """
        Yield basic information for every PCI device on the target host.

        Yields:
            Dictionary with PCI device information. Refer to 'get_basic_info()' for the dictionary
            format.
        """

        for entry in self._pman.lsdir(self._sysfs_base):
            if typing.TYPE_CHECKING:
                entry = typing.cast(LsdirTypedDict, entry)
            yield get_basic_info(entry["name"], pman=self._pman)
