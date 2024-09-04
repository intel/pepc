# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""API to Linux PCI devices control and discovery."""

from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ProcessManager, LocalProcessManager, ClassHelpers, Trivial

def get_basic_info(devaddr, pman=None):
    """
    Get basic information about a PCI device. The arguments are as follows.
      * devaddr - the PCI device address in the [<domain>:<bus>:<slot>.<func> format].
      * pman - the process manager object that defines the target host (local host by default).

    The basic PCI device information dictionary includes the following keys.
      * pciaddr - the PCI device address in the [<domain>:<bus>:<slot>.<func> format] (string).
      * vendorid - rhe PCI device vendor ID (integer).
      * devid - the PCI device ID (integer)
    """

    info = {"pciaddr" : devaddr}
    basepath = Path("/sys/bus/pci/devices") / devaddr

    with ProcessManager.pman_or_local(pman) as wpman:
        for key, descr, fname in (("vendorid", "Vendor DI", "vendor"),
                                  ("devid", "Device ID", "device")):
            path = basepath / fname
            try:
                with wpman.open(path, "r") as fobj:
                    val = fobj.read()
            except Error as err:
                raise type(err)(f"sysfs file read operation failed{wpman.hostmsg}:\n"
                                f"{err.indent(2)}") from err

            what = f"{descr} for PCI device {devaddr}"
            info[key] = Trivial.str_to_int(val, base=16, what=what)

    return info

class LsPCI(ClassHelpers.SimpleCloseContext):
    """List PCI devices."""

    def get_devices(self):
        """Yield device info as dictionary for every PCI device on the system."""

        for devaddr, _, _ in self._pman.lsdir(self._sysfs_base):
            yield get_basic_info(devaddr, pman=self._pman)

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        self._pman = pman
        self._sysfs_base = Path("/sys/bus/pci/devices")

        self._close_pman = pman is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
