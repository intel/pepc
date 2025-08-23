# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Emulate read-only sysfs, procfs, and debugfs files."""

import types
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.emul import _EmulFileBase

class ROFile(_EmulFileBase.EmulFileBase):
    """Emulate read-only procfs and debugfs files."""

    def __init__(self, path, basepath, data):
        """
        Class constructor. Arguments are as follows:
         * basepath - The basepath is a
                          path to the directory where emulated files should be created.
        """

        super().__init__(path, basepath, readonly=True)

        if not self.fullpath.parent.exists():
            self.fullpath.parent.mkdir(parents=True)

        with open(self.fullpath, "w", encoding="utf-8") as fobj:
            fobj.write(data)

class ROSysfsFile(ROFile):
    """Emulate read-only sysfs files."""

    def _set_read_method(self, fobj):
        """
        Contents of some read-only sysfs files can change depending on other files. Replace the
        'read()' method of 'fobj' with a custom method in order to properly emulate the behavior of
        a read-only file in 'path'.
        """

        def _online_read(self):
            """
            Mimic the '/sys/devices/system/cpu/online' file. It's contents depends on the per-CPU
            online files. For example if the per-cpu files contain the following:

            '/sys/devices/system/cpu/cpu0/online' : "1"
            '/sys/devices/system/cpu/cpu1/online' : "1"
            '/sys/devices/system/cpu/cpu2/online' : "0"
            '/sys/devices/system/cpu/cpu3/online' : "1"

            The global file contains the following:
            '/sys/devices/system/cpu/online' : "0-1,3"
            """

            online = []
            for dirname in self._base_path.iterdir():
                if not dirname.name.startswith("cpu"):
                    continue

                cpu = dirname.name[3:]
                if not Trivial.is_int(cpu):
                    continue

                try:
                    with open(dirname / "online", "r", encoding="utf-8") as fobj:
                        data = fobj.read().strip()
                except FileNotFoundError:
                    # CPU 0 does not have a "online" file, but it is online. So, we assume the same
                    # for any other CPU that has a folder but no "online" file.
                    online.append(cpu)
                    continue

                if data == "1":
                    online.append(cpu)

            return Trivial.rangify(online)

        # pylint: disable=pepc-unused-variable,protected-access
        fobj._base_path = self.basepath / "sys" / "devices" / "system" / "cpu"
        fobj._orig_read = fobj.read
        # pylint: enable=pepc-unused-variable,protected-access
        setattr(fobj, "read", types.MethodType(_online_read, fobj))

    def open(self, mode):
        """
        Return an emulated read-only file object, opened with 'mode', representing the emulated
        read-only Sysfs file.
        """

        fobj = super().open(mode)
        self._set_read_method(fobj)
        return fobj
