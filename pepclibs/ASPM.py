# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@intel.com>

"""This module provides an API to control PCI Active State Power Management (ASPM)."""

from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers, KernelVersion
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

_LOG = Logging.getLogger(f"pepc.{__name__}")

class ASPM(ClassHelpers.SimpleCloseContext):
    """This class provides an API to control PCI ASPM."""

    def _get_policies(self, strip=True):
        """
        Return list of available ASPM profiles on system. If strip is False, square brackets are
        not removed from currently active policy.
        """

        try:
            with self._pman.open(self._policy_path, "r") as fobj:
                policies = fobj.read().strip()
        except Error as err:
            raise Error(f"failed to read ASPM policy from file '{self._policy_path}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        policies = Trivial.split_csv_line(policies, sep=" ")
        if strip:
            policies = [policy.strip("[]") for policy in policies]

        return policies

    def set_policy(self, policy):
        """
        Set global ASPM policy. The arguments are as follows.
          * policy - ASPM policy name to set.
        """

        policies = self._get_policies()

        if policy not in policies:
            policies_str = ", ".join(policies)
            raise Error(f"ASPM policy '{policy}' not available{self._pman.hostmsg}.\n"
                        f"  Use one of the following: {policies_str}")

        errmsg = f"failed to set ASPM policy to '{policy}'{self._pman.hostmsg}:"
        try:
            with self._pman.open(self._policy_path, "r+") as fobj:
                fobj.write(policy)
        except ErrorPermissionDenied as err:
            raise ErrorPermissionDenied(f"{errmsg}\n{err.indent(2)}\n  Sometimes booting with "
                                        f"'pcie_aspm=force' command line option helps") from err
        except Error as err:
            raise Error(f"{errmsg}\n{err.indent(2)}") from err

    def get_policy(self):
        """Return current global ASPM policy."""

        policies = self._get_policies(strip=False)
        active = [policy for policy in policies if policy.startswith("[") and policy.endswith("]")]

        return active[0].strip("[]")

    def get_policies(self):
        """Yield the available global ASPM policy names."""

        for policy in self._get_policies():
            yield policy

    def _l1_file_not_found(self, addr, err):
        """
        Raise an exception with a helpful error message when the per-device L1 ASPM sysfs file does
        not exist.
        """

        path = self._sysfs_base / addr
        msg = f"the '{addr}' PCI device was not found{self._pman.hostmsg}:\n{err.indent(2)}"
        if not self._pman.exists(path):
            raise Error(msg)

        if not self._kver:
            # Check if kernel version is new enough.
            try:
                self._kver = KernelVersion.get_kver(pman=self._pman)
            except Error as err1:
                _LOG.warn_once("failed to detect kernel version%s:\n%s",
                               self._pman.hostmsg, err1.indent(2))

        if self._kver:
            if KernelVersion.kver_lt(self._kver, "5.5"):
                raise ErrorNotSupported(f"{msg}\nKernel version{self._pman.hostmsg} is "
                                        f"{self._kver} and it is not new enough - PCI L1 ASPM "
                                        f"support was added in kernel version 5.5.")

        raise ErrorNotSupported(f"{msg}.\nPossible reasons:\n"
                                f"  1. The '{addr}' PCI device doesn't support L1 ASPM.\n"
                                f"  2. The PCI controller{self._pman.hostmsg} does not support "
                                f"L1 ASPM.\n"
                                f"  3. The Linux kernel is older than version 5.5, so it doesn't "
                                f"support the per-device L1 ASPM sysfs files.\n"
                                f"  4. The 'CONFIG_PCIEASPM' kernel configuration option is "
                                f"disabled.")

    def is_l1_enabled(self, addr):
        """
        Return 'True' if L1 ASPM is enabled for a PCI device 'addr' and 'False' otherwise. The
        arguments are as follows.
          * addr - the PCI device address in the extended BDF notation
                   ([<domain>:<bus>:<slot>.<func> format]).

        Raise 'ErrorNotSupported' if the device does not support L1 ASPM.
        """

        path = self._sysfs_base / addr / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "r") as fobj:
                val = fobj.read()
        except ErrorNotFound as err:
            return self._l1_file_not_found(addr, err)
        except Error as err:
            raise Error(f"sysfs file read operation failed{self._pman.hostmsg}:\n"
                        f"{err.indent(2)}") from err

        return bool(Trivial.str_to_int(val, what="L1 ASPM state value from '{path}"))

    def toggle_l1_state(self, addr, enable):
        """
        Enable or disable a L1 ASPM for a PCI device. The arguments are as follows.
          * addr - the PCI device address in the extended BDF notation
                   ([<domain>:<bus>:<slot>.<func> format]).
          * enable - enable L1 ASPM if 'True', otherwise disable.

        Raise 'ErrorNotSupported' if the device does not support L1 ASPM.
        """

        val = "1" if enable else "0"
        path = self._sysfs_base / addr / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "w") as fobj:
                fobj.write(val)
        except ErrorNotFound as err:
            self._l1_file_not_found(addr, err)
        except Error as err:
            raise Error(f"sysfs file write operation failed{self._pman.hostmsg}:\n"
                        f"{err.indent(2)}") from err

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        self._pman = pman

        self._close_pman = pman is None
        self._policy_path = Path("/sys/module/pcie_aspm/parameters/policy")
        self._sysfs_base = Path("/sys/bus/pci/devices")

        self._kver = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
