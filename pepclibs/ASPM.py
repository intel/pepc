# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@intel.com>

"""Provide an API to control PCI Active State Power Management (ASPM)."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers, KernelVersion
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class ASPM(ClassHelpers.SimpleCloseContext):
    """Provide an API to control PCI ASPM."""

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize an instance to control PCI ASPM.

        Args:
            pman: The process manager object that defines the target host.
        """

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        self._close_pman = pman is None
        self._policy_path = Path("/sys/module/pcie_aspm/parameters/policy")
        self._sysfs_base = Path("/sys/bus/pci/devices")

        self._kver: str = ""

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))

    def _get_policies(self, strip: bool = True) -> list[str]:
        """
        Return a list of available ASPM policies on the system.

        Args:
            strip: If 'True', remove square brackets from the currently active policy name.

        Returns:
            List of available ASPM policy names.
        """

        try:
            with self._pman.open(self._policy_path, "r") as fobj:
                policies_str = fobj.read().strip()
        except Error as err:
            raise Error(f"Failed to read ASPM policy from file '{self._policy_path}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        policies = Trivial.split_csv_line(policies_str, sep=" ")
        if strip:
            policies = [policy.strip("[]") for policy in policies]

        return policies

    def set_policy(self, policy: str):
        """
        Set the global ASPM policy.

        Args:
            policy: ASPM policy name to set.

        Raises:
            ErrorPermissionDenied: Failed to set the policy due to insufficient permissions.
        """

        policies = self._get_policies()

        if policy not in policies:
            policies_str = ", ".join(policies)
            raise Error(f"ASPM policy '{policy}' not available{self._pman.hostmsg}.\n"
                        f"  Use one of the following: {policies_str}")

        errmsg = f"Failed to set ASPM policy to '{policy}'{self._pman.hostmsg}:"
        try:
            with self._pman.open(self._policy_path, "r+") as fobj:
                fobj.write(policy)
        except ErrorPermissionDenied as err:
            raise ErrorPermissionDenied(f"{errmsg}\n{err.indent(2)}\n  Sometimes booting with "
                                        f"'pcie_aspm=force' command line option helps") from err
        except Error as err:
            raise Error(f"{errmsg}\n{err.indent(2)}") from err

    def get_policy(self) -> str:
        """
        Return the current global ASPM policy.

        Returns:
            The current global ASPM policy name.
        """

        policies = self._get_policies(strip=False)
        active = [policy for policy in policies if policy.startswith("[") and policy.endswith("]")]

        if not active:
            raise Error(f"No active ASPM policy found{self._pman.hostmsg}\nFound the following "
                        f"policies in the '{self._policy_path}' file:\n  {','.join(policies)}")

        return active[0].strip("[]")

    def get_policies(self) -> Generator[str, None, None]:
        """
        Yield the available global ASPM policy names.

        Yields:
            Available ASPM policy names.
        """

        for policy in self._get_policies():
            yield policy

    def _l1_file_not_found(self, addr: str, err: Error):
        """
        Raise an exception with a helpful error message when the per-device L1 ASPM sysfs file does
        not exist.

        Args:
            addr: The PCI device address in the extended BDF notation.
            err: The exception that was raised when the file was not found.

        Raises:
            ErrorNotSupported: The device does not support L1 ASPM or the kernel is too old.
        """

        path = self._sysfs_base / addr
        msg = f"The '{addr}' PCI device was not found{self._pman.hostmsg}:\n{err.indent(2)}"
        if not self._pman.exists(path):
            raise Error(msg)

        if not self._kver:
            # Check if kernel version is new enough.
            try:
                self._kver = KernelVersion.get_kver(pman=self._pman)
            except Error as err1:
                _LOG.warn_once("Failed to detect kernel version%s:\n%s",
                               self._pman.hostmsg, err1.indent(2))

        if self._kver:
            if KernelVersion.kver_lt(self._kver, "5.5"):
                raise ErrorNotSupported(f"{msg}\nKernel version{self._pman.hostmsg} is "
                                        f"{self._kver} and it is not new enough: PCI L1 ASPM "
                                        f"support was added in kernel version 5.5.")

        raise ErrorNotSupported(f"{msg}.\nPossible reasons:\n"
                                f"  1. The '{addr}' PCI device doesn't support L1 ASPM.\n"
                                f"  2. The PCI controller{self._pman.hostmsg} does not support "
                                f"L1 ASPM.\n"
                                f"  3. The Linux kernel is older than version 5.5, so it doesn't "
                                f"support the per-device L1 ASPM sysfs files.\n"
                                f"  4. The 'CONFIG_PCIEASPM' kernel configuration option is "
                                f"disabled.")

    def is_l1_enabled(self, addr: str) -> bool:
        """
        Return 'True' if L1 ASPM is enabled for a PCI device and 'False' otherwise.

        Args:
            addr: The PCI device address in the extended BDF notation
                  ([<domain>:<bus>:<slot>.<func>] format).

        Returns:
            'True' if L1 ASPM is enabled for the device, 'False' otherwise.

        Raises:
            ErrorNotSupported: The device does not support L1 ASPM.
        """

        path = self._sysfs_base / addr / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "r") as fobj:
                val = fobj.read()
        except ErrorNotFound as err:
            return self._l1_file_not_found(addr, err)
        except Error as err:
            raise Error(f"Sysfs file read operation failed{self._pman.hostmsg}:\n"
                        f"{err.indent(2)}") from err

        return bool(Trivial.str_to_int(val, what="L1 ASPM state value from '{path}"))

    def toggle_l1_state(self, addr: str, enable: bool):
        """
        Enable or disable L1 ASPM for a PCI device.

        Args:
            addr: The PCI device address in the extended BDF notation
                  ([<domain>:<bus>:<slot>.<func>] format).
            enable: Enable L1 ASPM if 'True', otherwise disable.

        Raises:
            ErrorNotSupported: The device does not support L1 ASPM.
        """

        val = "1" if enable else "0"
        path = self._sysfs_base / addr / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "w") as fobj:
                fobj.write(val)
        except ErrorNotFound as err:
            self._l1_file_not_found(addr, err)
        except Error as err:
            raise Error(f"Sysfs file write operation failed{self._pman.hostmsg}:\n"
                        f"{err.indent(2)}") from err
