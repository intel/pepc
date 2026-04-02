# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Provide API for loading and unloading Linux kernel modules (drivers)."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Logging, LocalProcessManager, Dmesg, ClassHelpers

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class KernelModule(ClassHelpers.SimpleCloseContext):
    """Represent a Linux kernel module."""

    def __init__(self,
                 name: str,
                 pman: ProcessManagerType | None = None,
                 dmesg: Dmesg.Dmesg | bool | None = None):
        """
        Initialize a class instance.

        Args:
            name: Kernel module name.
            pman: The process manager object that defines the target host.
            dmesg: 'True' to enable 'dmesg' output checks (default), 'False' to disable them.
                   Can also be a 'Dmesg' object.

        Notes:
            - By default, objects of this class capture 'dmesg' output on the host defined by
              'pman'. The first 'dmesg' snapshot is taken before loading/unloading the driver.
              The second snapshot is taken only if an error happens. This allows to extract new
              'dmesg' lines, which are potentially related to the kernel module. These lines are
              then included to the error message, which is very helpful for diagnosing the error.
            - If you already have a 'Dmesg' object with the first snapshot captured, you can pass
              it via the 'dmesg' argument, in which case the 'dmesg' tool will be invoked one less
              time, which is more optimal.
        """

        if not name:
            raise Error("BUG: No driver name provided")

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        self.name = name
        self._dmesg_obj: Dmesg.Dmesg | None

        self._close_pman = pman is None
        self._close_dmesg_obj = dmesg is None

        if self._pman.is_emulated:
            # Emulated environment is used for testing, and it doesn't support 'dmesg'.
            dmesg = False

        if dmesg is False:
            self._dmesg_obj = None
        elif isinstance(dmesg, Dmesg.Dmesg):
            self._dmesg_obj = dmesg
        else:
            # dmesg is None or True - create a new Dmesg object
            self._dmesg_obj = Dmesg.Dmesg(pman=self._pman)

    def close(self):
        """Uninitialize the class instance."""
        ClassHelpers.close(self, close_attrs=("_dmesg_obj", "_pman",))

    def _get_usage_count(self) -> int | None:
        """
        Return 'None' if module is not loaded, otherwise return the module usage count.

        Returns:
            The module usage count, or 'None' if the module is not loaded.
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

    def _get_new_dmesg(self) -> str:
        """
        Return new dmesg messages if available.

        Returns:
            New dmesg messages, or an empty string if none are available.
        """

        if not self._dmesg_obj:
            return ""
        new_msgs = self._dmesg_obj.get_new_messages(join=True)
        if new_msgs:
            return f"New kernel messages{self._pman.hostmsg}:\n{new_msgs}"
        return ""

    def _run_mod_cmd(self, cmd: str):
        """
        Run module load/unload command.

        Args:
            cmd: The command to run.
        """

        if self._dmesg_obj:
            if not self._dmesg_obj.captured:
                self._dmesg_obj.run(capture=True)

            try:
                self._pman.run_verify(cmd)
            except Error as err:
                raise type(err)(f"{err}\n{self._get_new_dmesg()}") from err

            if _LOG.getEffectiveLevel() == Logging.DEBUG:
                _LOG.debug("The following command finished: %s\n%s", cmd, self._get_new_dmesg())
        else:
            self._pman.run_verify(cmd)

    def is_loaded(self) -> bool:
        """
        Check if the module is loaded.

        Returns:
            'True' if the module is loaded, 'False' otherwise.
        """

        if self._pman.is_emulated:
            # Assume any module is loaded in the emulated environment.
            return True

        return self._get_usage_count() is not None

    def _unload(self):
        """Unload the module if it is loaded."""

        if self.is_loaded():
            self._run_mod_cmd(f"rmmod {self.name}")

    def unload(self):
        """Unload the module if it is loaded."""

        if self._pman.is_emulated:
            return

        self._unload()

    def load(self, opts: str | None = None, unload: bool = False):
        """
        Load the module.

        Args:
            opts: Options to pass to 'modprobe'.
            unload: If 'True', unload the module first before loading.
        """

        if self._pman.is_emulated:
            return

        if unload:
            self._unload()
        elif self.is_loaded():
            return

        cmd = f"modprobe {self.name}"
        if opts:
            cmd += f" {opts}"
        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            cmd += " dyndbg=+pf"
        self._run_mod_cmd(cmd)
