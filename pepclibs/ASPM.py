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
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied

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
            raise Error(f"ASPM policy '{policy}' not available{self._pman.hostmsg}. Use one of the "
                        f"following: {policies_str}")

        errmsg = f"failed to set ASPM policy to '{policy}'{self._pman.hostmsg}:"
        try:
            with self._pman.open(self._policy_path, "r+") as fobj:
                fobj.write(policy)
        except ErrorPermissionDenied as err:
            raise ErrorPermissionDenied(f"{errmsg}\n{err}\nSometimes booting with " \
                                        f"'pcie_aspm=force' command line option helps.") from err
        except Error as err:
            raise Error(f"{errmsg}\n{err}") from err

    def get_policy(self):
        """Return currently active ASPM policy."""

        policies = self._get_policies(strip=False)
        active = [policy for policy in policies if policy.startswith("[") and policy.endswith("]")]

        return active[0].strip("[]")

    def get_policies(self):
        """Yield all available policies on target system."""

        for policy in self._get_policies():
            yield policy

    def __init__(self, pman=None):
        """The class constructor."""

        self._pman = pman

        self._close_pman = pman is None
        self._policy_path = Path("/sys/module/pcie_aspm/parameters/policy")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))