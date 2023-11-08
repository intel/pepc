# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@intel.com>

"""This module provides an API to control PCI Active State Power Management (ASPM)."""

from pathlib import Path
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorPermissionDenied

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
        """Set ASPM policy. Raise an error if requested policy doesn't exist on target system."""

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
        """Return currently active ASPM policy."""

        policies = self._get_policies(strip=False)
        active = [policy for policy in policies if policy.startswith("[") and policy.endswith("]")]

        return active[0].strip("[]")

    def get_policies(self):
        """Yield all available policies on target system."""

        for policy in self._get_policies():
            yield policy

    def _sysfs_file_not_found(self, pci_address, err):
        """Print error message in case L1 ASPM file operation fails."""

        path = self._sysfs_base / pci_address
        if self._pman.exists(path):
            kopts = "CONFIG_PCIEASPM and CONFIG_PCIEASPM_DEFAULT"
            raise Error(f"device '{pci_address}' doesn't support L1 ASPM{self._pman.hostmsg}:\n"
                        f"{err.indent(2)}\n"
                        f"Possible reasons for L1 ASPM not being supported on '{pci_address}' "
                        f"device:\n"
                        f"1. this device's hardware doesn't support L1 ASPM.\n"
                        f"2. this platform's hardware doesn't support ASPM. To get more "
                        f"information please run 'journalctl -b | grep ASPM'.\n"
                        f"3. the kernel is old and doesn't have PCIe ASPM support. The support was "
                        f"introduced in kernel 5.5.\n"
                        f"4. the kernel was built without {kopts}. Try to compile the kernel with "
                        f"{kopts} set to 'y'.")
        raise Error(f"device '{pci_address}' was not found{self._pman.hostmsg}:\n{err.indent(2)}")

    def read_l1_aspm_state(self, pci_address): # pylint: disable=inconsistent-return-statements
        """
        Returns the state of L1 ASPM for a specified PCI device. The arguments are as follows.
         * pci_address - PCI address in extended BDF notation format that contains the domain.

        If the specified device is present and has L1 ASPM support the return value can be either
        True or False. Otherwise an error is raised.
        """

        path = self._sysfs_base / pci_address / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "r") as fobj:
                return Trivial.str_to_int(fobj.read(), what="L1 ASPM state")
        except ErrorNotFound as err:
            self._sysfs_file_not_found(pci_address, err)
        except Error as err:
            raise Error(f"read failed{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def write_l1_aspm_state(self, pci_address, value):
        """
        Enable or disable a L1 ASPM on a specified PCI device. The arguments are as follows.
         * pci_address - PCI address in extended BDF notation format that contains the domain.
         * value - case-insensitive string indicating if L1 ASPM should be enabled or disabled.
                   Valid values are 'false', 'true', 'off', 'on', 'disable','enable'

        If the passed address points to a valid PCI device that supports L1 ASPM, either '0' or '1'
        is written into sysfs which changes the devices state.
        """

        if value.lower() not in ["false", "true", "off", "on", "disable", "enable"]:
            raise Error(f"bad value {value.lower()} for modifying L1 ASPM state.\n"
                        f"Valid values are 'false', 'true', 'off', 'on', 'disable', 'enable'")

        if value.lower() in ["false", "off", "disable"]:
            pci_value = "0"
        else:
            pci_value = "1"

        path = self._sysfs_base / pci_address / Path("link/l1_aspm")

        try:
            with self._pman.open(path, "w") as fobj:
                fobj.write(pci_value)
        except (ErrorNotFound, ErrorPermissionDenied) as err:
            self._sysfs_file_not_found(pci_address, err)
        except Error as err:
            raise Error(f"write failed{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def __init__(self, pman=None):
        """The class constructor."""

        self._pman = pman

        self._close_pman = pman is None
        self._policy_path = Path("/sys/module/pcie_aspm/parameters/policy")
        self._sysfs_base = Path("/sys/bus/pci/devices/")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
