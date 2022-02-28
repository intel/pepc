# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a capability of reading and changing EPP (Energy Performance Preference) on
Intel CPUs.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import Procs, Trivial, FSHelpers
from pepclibs import CPUInfo
from pepclibs.msr import MSR, HWPRequest, HWPRequestPkg

_LOG = logging.getLogger()

# The fall-back EPP policy to EPP value map.
#
# Note, we do not expose the values to the user because they are platform-specific (even though in
# current implementation they are not, but we can improve this later).
_EPP_POLICIES = {"performance": 0,
                 "balance_performance": 0x80,
                 "balance_power": 0xC0,
                 "power": 0xFF}

# The minimum and maximum EPP values.
_EPP_MIN, _EPP_MAX = 0, 0xFF

class EPP:
    """
    This module provides a capability of reading and changing EPP (Energy Performance Preference) on
    Intel CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPP: 'get_epp()', 'set_epp()'.
        * Get EPP policy name: 'get_epp_policy()'.
    2. Single CPU.
        * Get/set EPP: 'get_cpu_epp()', 'set_cpu_epp()'.
        * Check if the CPU supports EPP: 'is_epp_supported()'
        * Get EPP policy name: 'get_cpu_epp_policy()'.
        * Get the list of available EPP policies: 'get_cpu_epp_policies()'.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._proc, cpuinfo=self._cpuinfo)
        return self._msr

    def _get_hwpreq(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(proc=self._proc, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(proc=self._proc, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_cpu_epp_policies(self, cpu):
        """Implements 'get_cpu_epp_policies()'."""

        if cpu in self._policies:
            return self._policies[cpu]

        # Prefer using the names from the Linux kernel.
        path = self._sysfs_epp_policies_path % cpu
        line = FSHelpers.read(path, default=None, proc=self._proc)
        if line is None:
            self._policies[cpu] = None
        else:
            self._policies[cpu] = Trivial.split_csv_line(line, sep=" ")

        return self._policies[cpu]

    def get_cpu_epp_policies(self, cpu):
        """Return a list of all EPP policy names for CPU 'cpu."""

        cpu = self._cpuinfo.normalize_cpu(cpu)

        policies = self._get_cpu_epp_policies(cpu)
        if policies is None:
            return list(_EPP_POLICIES)
        return policies

    def is_epp_supported(self, cpu):
        """Returns 'True' if EPP is supported, on CPU 'cpu', otherwise returns 'False'."""

        return self._get_hwpreq().is_cpu_feature_supported("epp", cpu)

    def _get_cpu_epp_policy(self, cpu, unknown_ok):
        """Returns EPP policy for CPU 'cpu'."""

        path = self._sysfs_epp_policy_path % cpu

        try:
            policy = FSHelpers.read(path, proc=self._proc)
            return policy.strip()
        except ErrorNotFound:
            pass

        # The kernel does not support the EPP policies. Try to figure the policy out.
        epp = self._get_cpu_epp(cpu)
        if epp in self._epp_rmap:
            return self._epp_rmap[epp]

        if unknown_ok:
            return f"unknown (EPP {epp})"

        raise Error(f"unknown policy name for EPP value {epp} on CPU {cpu}{self._proc.hostmsg}")

    def get_epp_policy(self, cpus="all", unknown_ok=True):
        """
        Yield (CPU number, EPP policy name) pairs for CPUs in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
          * unknown_ok - if the EPP value does not match any policy name, this method returns the
                         "unknown (EPP <value>)" string by default. However, if 'unknown_ok' is
                         'False', an exception is raised instead.
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._get_cpu_epp_policy(cpu, unknown_ok))

    def get_cpu_epp_policy(self, cpu, unknown_ok=True):
        """Similar to 'get_epp_policy()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epp_policy(cpu, unknown_ok)

    def _get_cpu_epp(self, cpu):
        """Implements 'get_cpu_epp()'."""

        # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
        hwpreq = self._get_hwpreq()
        pkg_control = hwpreq.is_cpu_feature_enabled("pkg_control", cpu)
        epp_valid = hwpreq.is_cpu_feature_enabled("epp_valid", cpu)
        if pkg_control and not epp_valid:
            hwpreq = self._get_hwpreq_pkg()

        return hwpreq.read_cpu_feature("epp", cpu)

    def get_epp(self, cpus="all"):
        """
        Yield (CPU number, EPP) pairs for CPUs in 'cpus'. The 'cpus' argument is the same as in
        'set_epp()'.
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._get_cpu_epp(cpu))

    def get_cpu_epp(self, cpu):
        """Similar to 'get_epp()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epp(cpu)

    def _set_cpu_epp(self, epp, cpu):
        """Implements 'set_cpu_epp()'."""

        policies = self._get_cpu_epp_policies(cpu)

        if Trivial.is_int(epp):
            Trivial.validate_int_range(epp, _EPP_MIN, _EPP_MAX, what="EPP")

            if policies:
                path = self._sysfs_epp_policy_path % cpu
                _LOG.warning("overriding Linux CPU %d EPP policy%s by a direct MSR write.\n"
                             "The recommended way of changing EPP%s is is via the '%s' file.",
                             cpu, self._proc.hostmsg, self._proc.hostmsg, path)

            hwpreq = self._get_hwpreq()
            if hwpreq.is_cpu_feature_enabled("pkg_control", cpu):
                # Override package control by setting the "EPP valid" bit.
                hwpreq.write_cpu_feature("epp_valid", "on", cpu)
            hwpreq.write_cpu_feature("epp", epp, cpu)
            return

        policy = epp.lower()

        if not policies:
            policies = _EPP_POLICIES
        else:
            policies = set(policies)

        if policy not in policies:
            policy_names = ", ".join(self.get_cpu_epp_policies(cpu))
            raise Error(f"EPP policy '{epp}' is not supported{self._proc.hostmsg}, please "
                        f"provide one of the following EPP policy names: {policy_names}")

        FSHelpers.write(self._sysfs_epp_policy_path % cpu, policy, proc=self._proc)

    def set_epp(self, epp, cpus="all"):
        """
        Set EPP for CPUs in 'cpus'. The arguments are as follows.
          * epp - the EPP value to set. Can be an integer, a string representing an integer, or one
                  of the EPP policy names.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._set_cpu_epp(epp, cpu)

    def set_cpu_epp(self, epp, cpu):
        """Similar to 'set_epp()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._set_cpu_epp(epp, cpu)

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to manage EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._hwpreq = None
        self._hwpreq_pkg = None
        self._policies = {}
        self._epp_rmap = {code:name for name, code in _EPP_POLICIES.items()}

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_policy_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        if not self._proc:
            self._proc = Procs.Proc()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported vendor {cpuinfo.info['vendor']}{proc.hostmsg}. "
                                    f"Only Intel CPUs are supported.")

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_hwpreq", "_hwpreq_pkg", "_msr", "_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if hasattr(self, f"_close{attr}"):
                    if getattr(self, f"_close{attr}"):
                        getattr(obj, "close")()
                else:
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
