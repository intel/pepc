# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@intel.com>

"""This module provides an API to control PCI Active State Power Management (ASPM)."""

from pathlib import Path
from pepclibs.helperlibs import Procs, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied

class ASPM:
    """This class provides an API to control PCI ASPM."""

    def _get_policies(self, strip=True):
        """
        Return list of available ASPM profiles on system. If strip is False, square brackets are
        not removed from currently active policy.
        """

        try:
            with self._proc.open(self._policy_path, "r") as fobj:
                policies = fobj.read().strip()
        except Error as err:
            raise Error(f"failed to read ASPM policy from file '{self._policy_path}'"
                        f"{self._proc.hostmsg}:\n{err}") from err

        policies = Trivial.split_csv_line(policies, sep=" ")
        if strip:
            policies = [policy.strip("[]") for policy in policies]

        return policies

    def set_policy(self, policy):
        """Set ASPM policy. Raise an error if requested policy doesn't exist on target system."""

        policies = self._get_policies()

        if policy not in policies:
            policies_str = ", ".join(policies)
            raise Error(f"ASPM policy '{policy}' not available{self._proc.hostmsg}. Use one of the "
                        f"following: {policies_str}")

        errmsg = f"failed to set ASPM policy to '{policy}'{self._proc.hostmsg}:"
        try:
            with self._proc.open(self._policy_path, "w") as fobj:
                fobj.write(policy)
        except ErrorPermissionDenied as err:
            raise Error(f"{errmsg}\n{err}\nsometimes booting with 'pcie_aspm=force' command line "
                        f"option helps.") from err
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

    def __init__(self, proc=None):
        """The class constructor."""

        self._proc = proc

        self._close_proc = proc is None
        self._policy_path = Path("/sys/module/pcie_aspm/parameters/policy")

        if not self._proc:
            self._proc = Procs.Proc()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_proc", None):
            if self._close_proc:
                self._proc.close()
            self._proc = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
