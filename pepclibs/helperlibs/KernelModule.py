# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API for loading and unloading Linux kernel modules (drivers).
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import LocalProcessManager, Dmesg, ToolChecker, ClassHelpers

_LOG = logging.getLogger()

# The drivers supported by this module.
DRIVERS = {}

class KernelModule:
    """This class represents a Linux kernel module."""

    def _get_usage_count(self):
        """
        Returns 'None' if module is not loaded, otherwise returns the module usage count.
        """

        with self._pman.open("/proc/modules", "r") as fobj:
            for line in fobj:
                line = line.strip()
                if not line:
                    continue
                name, _, usecnt, _ = line.split(maxsplit=3)
                if name == self.name:
                    return int(usecnt)

        return None

    def _get_new_dmesg(self):
        """Return new dmesg messages if available."""

        if not self._dmesg_obj:
            return ""
        new_msgs = self._dmesg_obj.get_new_messages(join=True)
        if new_msgs:
            return f"New kernel messages{self._pman.hostmsg}:\n{new_msgs}"
        return ""

    def _run_mod_cmd(self, cmd):
        """This helper function runs module load/unload command 'cmd'."""

        if self._dmesg_obj:
            if not self._dmesg_obj.captured:
                self._dmesg_obj.run(capture=True)

            try:
                self._pman.run_verify(cmd)
            except Error as err:
                raise Error(f"{err}\n{self._get_new_dmesg()}") from err

            if _LOG.getEffectiveLevel() == logging.DEBUG:
                _LOG.debug("the following command finished: %s\n%s", cmd, self._get_new_dmesg())
        else:
            self._pman.run_verify(cmd)

    def is_loaded(self):
        """Check if the module is loaded."""

        return self._get_usage_count() is not None

    def _unload(self):
        """Unload the module if it is loaded."""

        if self.is_loaded():
            self._run_mod_cmd(f"rmmod {self.name}")

    def unload(self):
        """Unload the module if it is loaded."""

        self._unload()

    def load(self, opts=None, unload=False):
        """
        Load the module with 'opts' options to 'modprobe'. If 'unload' is 'True', then unload the
        module first.
        """

        if unload:
            self._unload()
        elif self.is_loaded():
            return

        if opts:
            opts = f"{opts}"
        else:
            opts = ""
        if _LOG.getEffectiveLevel() == logging.DEBUG:
            opts += " dyndbg=+pf"
        self._run_mod_cmd(f"modprobe {self.name} {opts}")

    def __init__(self, name, pman=None, dmesg=None, tchk=None):
        """
        The class constructor. The arguments are as follows.
          * name - kernel module name.
          * pman - the process manager object that defines the target host.
          * dmesg - 'True' to enable 'dmesg' output checks (default), 'False' to disable them. Can
                    also be a 'Dmesg' object.
          * tchk - an optional 'ToolChecker.ToolChecker()' object which will be used for checking if
                   the required tools like 'modprobe' are present on the target host.

        By default, objects of this class capture 'dmesg' output on the host defined by 'pman'. The
        first 'dmesg' snapshot is taken before loading/unloading the driver. The second snapsot is
        taken only if an error happens. This allows to extract new 'dmesg' lines, which are
        potentially related to the delayed event device driver. These lines are then included to the
        error message, which is very helpful for diagnosing the error.

        If you already have a 'Dmesg' object with the first snapshot capured, you can pass it via
        the 'dmesg' argument, in which case the 'dmesg' tool will be invoked one less time, which is
        more optimal.
        """

        if dmesg is None:
            dmesg = True

        self._pman = pman
        self.name = name
        self._dmesg_obj = None
        self._tchk = tchk

        self._close_pman = pman is None
        self._close_dmesg_obj = False
        self._close_tchk = tchk is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if isinstance(dmesg, Dmesg.Dmesg):
            self._dmesg_obj = dmesg
        elif dmesg:
            self._dmesg_obj = Dmesg.Dmesg(pman=self._pman)
            self._close_dmesg = True
        if not self._tchk:
            self._tchk = ToolChecker.ToolChecker(pman=self._pman)

        self._tchk.check_tool("modprobe")
        self._tchk.check_tool("rmmod")

    def close(self):
        """Stop the measurements."""
        ClassHelpers.close(self, close_attrs=("_tchk", "_dmesg_obj", "_pman",))

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the run-time context."""
        self.close()
