# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#
# Parts of the code was contributed by Len Brown <len.brown@intel.com>.

"""
This module provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
CPUs.
"""

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs import CPUInfo
from pepclibs import _PropsCache
from pepclibs.msr import MSR, EnergyPerfBias

# EPB policy to EPB value map. The names are from the following Linux kernel header file:
#   arch/x86/include/asm/msr-index.h
#
# Note, we do not expose the values to the user because they are platform-specific (not in current
# implementation, but this may change in the future).
_EPB_POLICIES = {"performance": 0,
                 "balance_performance": 4,
                 "normal": 6,
                 "balance_powersave": 8,
                 "powersave": 15}

# The minimum and maximum EPB values.
_EPB_MIN, _EPB_MAX = 0, 15

class EPB(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
    CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPB: 'get_epb()', 'set_epb()'.
        * Get EPB policy name: 'get_epb_policy()'.
        * Get the list of available EPB policies: 'get_epb_policies()'.
    2. Single CPU.
        * Get/set EPB: 'get_cpu_epb()', 'set_cpu_epb()'.
        * Check if the CPU supports EPB: 'is_epb_supported()'
        * Get EPB policy name: 'get_cpu_epb_policy()'.
        * Get the list of available EPB policies: 'get_cpu_epb_policies()'.
    """

    def get_epb_policies(self, cpus="all"):
        """Yield (CPU number, List of supported EPB policy names) pairs for CPUs in 'cpus'."""

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, list(_EPB_POLICIES)

    @staticmethod
    def get_cpu_epb_policies(cpu): # pylint: disable=unused-argument
        """Return a tuple of all EPB policy names for CPU 'cpu."""

        # In theory, EPB policies may be different for different CPU.
        return list(_EPB_POLICIES)

    def is_epb_supported(self, cpu):
        """Returns 'True' if EPB is supported, on CPU 'cpu', otherwise returns 'False'."""

        if self._pcache.is_cached("supported", cpu):
            return self._pcache.get("supported", cpu)

        val = self._epb_msr.is_cpu_feature_supported("epb", cpu)
        self._pcache.add("supported", cpu, val)
        return val

    def _cpu_epb_to_policy(self, cpu, epb): # pylint: disable=unused-argument
        """Return policy name for EPB value 'epb' on CPU 'cpu'."""

        if epb in self._epb_rmap:
            return self._epb_rmap[epb]

        return f"unknown EPB={epb}"

    def get_epb_policy(self, cpus="all"):
        """
        Yield (CPU number, EPB policy name) pairs for CPUs in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu, epb in self._epb_msr.read_feature("epb", cpus=cpus):
            yield cpu, self._cpu_epb_to_policy(cpu, epb)

    def get_cpu_epb_policy(self, cpu, epb=None):
        """
        Similar to 'get_epb_policy()', but for a single CPU 'cpu'. Return EPB policy name for CPU
        'cpu'. The arguments are as follows.
          * cpu - CPU number to get EPB policy for. Can be an integer or a string with an integer
                  number.
          * epb - by default, this method reads the EPB value for CPU 'cpu' from the MSR. But if the
                  'epb' argument is provided, this method skips the reading part and just translates
                  the EPB value in 'epb' to the policy name.
        """

        if epb is None:
            epb = self.get_cpu_epb(cpu)
        else:
            self._epb_msr.check_cpu_feature_supported("epb", cpu)

        return self._cpu_epb_to_policy(cpu, epb)

    def get_epb(self, cpus="all"):
        """
        Yield (CPU number, EPB) pairs for CPUs in 'cpus'. The 'cpus' argument is the same as in
        'set_epb()'.
        """

        yield from self._epb_msr.read_feature("epb", cpus=cpus)

    def get_cpu_epb(self, cpu):
        """Similar to 'get_epb()', but for a single CPU 'cpu'."""

        epb = None
        for _, epb in self.get_epb(cpus=(cpu, )):
            pass
        return epb

    def set_epb(self, epb, cpus="all"):
        """
        Set EPB for CPUs in 'cpus'. The arguments are as follows.
          * epb - the EPB value to set. Can be an integer, a string representing an integer, or one
                  of the EPB policy names.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        if Trivial.is_int(epb):
            Trivial.validate_int_range(epb, _EPB_MIN, _EPB_MAX, what="EPB")
        else:
            epb_policy = epb.lower()
            if epb_policy not in _EPB_POLICIES:
                policy_names = ", ".join(_EPB_POLICIES)
                raise Error(f"EPB policy '{epb}' is not supported{self._pman.hostmsg}, please "
                            f"provide one of the following EPB policy names: {policy_names}")
            epb = _EPB_POLICIES[epb_policy]

        self._epb_msr.write_feature("epb", int(epb), cpus=cpus)

    def set_cpu_epb(self, epb, cpu):
        """Similar to 'set_epb()', but for a single CPU 'cpu'."""

        self.set_epb(epb, cpus=(cpu,))

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPB for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._epb_msr = None
        self._epb_rmap = {code:name for name, code in _EPB_POLICIES.items()}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported vendor {cpuinfo.info['vendor']}{pman.hostmsg}. "
                                    f"Only Intel CPUs are supported.")

        # The per-CPU cache for read-only data. MSR implements its own caching.
        self._pcache = _PropsCache._PropsCache(cpuinfo=self._cpuinfo, pman=self._pman)

        if not self._msr:
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo)

        self._epb_msr = EnergyPerfBias.EnergyPerfBias(pman=self._pman, cpuinfo=self._cpuinfo,
                                                      msr=self._msr)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_epb_msr", "_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
