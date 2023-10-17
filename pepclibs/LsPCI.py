# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@intel.com>

"""This module can be used to get information about PCI devices in system."""

import re
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers

class LsPCI(ClassHelpers.SimpleCloseContext):
    """This is a wrapper class for 'lspci' tool."""

    @staticmethod
    def _parse_dev_info(lines):
        """
        Parse 'lspci' output lines in 'lines'. The lines should belong to a single device and should
        not be stripped. Returns the resulting dictionary.
        """

        line = lines[0].strip().split()
        info = {"pciaddr" : line[0]}

        line = line[2].split(':')
        info["vendorid"] = line[0]
        info["devid"] = line[1]

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            # Many lines are like "key: val", but not all of them. E.g.:
            #   DeviceName: Intel i210
            #   Memory at b2000000 (32-bit, prefetchable) [size=16M]
            # Split and strip the former, skip the latter.
            line = [text.strip() for text in line.split(":", maxsplit=1)]
            if len(line) != 2:
                continue

            key, val = line

            # Keep only device name for now, but this can be extended later.
            if key == "DeviceName":
                info["name"] = val
            if key == "LnkCtl":
                info["aspm_enabled"] = "Enabled" in val

        # 'Lspci' does not necessarily resolves all the names.
        if "name" not in info:
            info["name"] = "unknown"

        return info

    def get_info(self, devaddr):
        """
        Return dictionary of PCI device information. Argument 'devaddr' is in format of:
        [[[[<domain>]:]<bus>]:][<slot>][.[<func>]].
        """

        cmd = f"{self._lspci_path} -D -n -vv -s {devaddr}"
        stdout, _ = self._pman.run_verify(cmd, join=False)
        if not stdout:
            raise Error(f"failed to get information for PCI slot: {devaddr}")

        return self._parse_dev_info(stdout)

    def get_devices(self):
        """Generator yields device info as dictionary for each device. """

        cmd = f"{self._lspci_path} -D -n -v"
        stdout, _ = self._pman.run_verify(cmd, join=False)

        # The output structure is as follows:
        #
        # 0000:02:00.0 0300: 102b:0522 (rev 05) (prog-if 00 [VGA controller])
        #    DeviceName: ServerEngines Pilot III
        #    ....
        # 0000:04:00.0 0200: 8086:1533 (rev 03)
        #    DeviceName: Intel i210
        #    ....
        #
        # So every line without a space at the beginning is a marker of a new device. Use this
        # property to split the output on per-device chunks.
        lines = []
        for line in stdout:
            if not line.strip():
                continue

            if re.match(r'\s', line):
                lines.append(line)
            else:
                if lines:
                    yield self._parse_dev_info(lines)
                lines = [line]

    def __init__(self, pman=None):
        """Class constructor."""

        self._pman = pman
        self._lspci_path = "lspci"

        self._close_pman = pman is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
