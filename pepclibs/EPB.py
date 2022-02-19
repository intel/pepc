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

from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Procs, Trivial
from pepclibs import CPUInfo
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

class EPB:
    """
    This class provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
    CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPB: 'get_epb()', 'set_epb()'.
        * Get EPB policy name: 'get_epb_policy()'.
    2. Single CPU.
        * Get/set EPB: 'get_cpu_epb()', 'set_cpu_epb()'.
        * Check if the CPU supports EPB: 'is_epb_supported()'
        * Get EPB policy name: 'get_cpu_epb_policy()'.
        * Get the list of available EPB policies: 'get_cpu_epb_policies()'.
    """

    @staticmethod
    def get_cpu_epb_policies(cpu): # pylint: disable=unused-argument
        """Return a tuple of all EPB policy names for CPU 'cpu."""

        # In theory, EPB policies may be different for different CPU.
        return tuple(_EPB_POLICIES)

    def is_epb_supported(self, cpu):
        """Returns 'True' if EPB is supported, on CPU 'cpu', otherwise returns 'False'."""

        return self._epb_msr.is_cpu_feature_supported("epb", cpu)


    def _cpu_epb_to_policy(self, cpu, epb, unknown_ok):
        """Return policy name for EPB value 'epb' on CPU 'cpu'."""

        if epb in self._epb_rmap:
            return self._epb_rmap[epb]
        if unknown_ok:
            return f"unknown (EPB {epb})"

        raise Error(f"unknown policy name for EPB value {epb} on CPU {cpu}{self._proc.hostmsg}")

    def get_epb_policy(self, cpus="all", unknown_ok=True):
        """
        Yield (CPU number, EPB policy name) pairs for CPUs in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
          * unknown_ok - if the EPB value does not match any policy name, this method returns the
                         "unknown (EPB <value>)" string by default. However, if 'unknown_ok' is
                         'False', an exception is raised instead.
        """

        for cpu, epb in self._epb_msr.read_feature("epb", cpus=cpus):
            yield cpu, self._cpu_epb_to_policy(cpu, epb, unknown_ok)

    def get_cpu_epb_policy(self, cpu, epb=None, unknown_ok=True):
        """
        Similar to 'get_epb_policy()', but for a single CPU 'cpu'. Return EPB policy name for CPU
        'cpu'. The arguments are as follows.
          * cpu - CPU number to get EPB policy for. Can be an integer or a string with an integer
                  number.
          * epb - by default, this method reads the EPB value for CPU 'cpu' from the MSR. But if the
                  'epb' argument is provided, this method skips the reading part and just translates
                  the EPB value in 'epb' to the policy name.
          * unknown_ok - same as in 'get_epb_policy()'.
        """

        if epb is None:
            epb = self.get_cpu_epb(cpu)
        else:
            self._epb_msr.check_cpu_feature_supported("epb", cpu)

        return self._cpu_epb_to_policy(cpu, epb, unknown_ok)

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
                raise Error(f"EPB policy '{epb}' is not supported{self._proc.hostmsg}, please "
                            f"provide one of the following EPB policy names: {policy_names}")
            epb = _EPB_POLICIES[epb_policy]

        self._epb_msr.write_feature("epb", int(epb), cpus=cpus)

    def set_cpu_epb(self, epb, cpu):
        """Similar to 'set_epb()', but for a single CPU 'cpu'."""

        self.set_epb(epb, cpus=(cpu,))

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to manage EPB for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._epb_msr = None
        self._epb_rmap = {code:name for name, code in _EPB_POLICIES.items()}

        if not self._proc:
            self._proc = Procs.Proc()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise Error(f"unsupported vendor {cpuinfo.info['vendor']}{proc.hostmsg}. Only Intel "
                        f"CPUs are supported.")

        if not self._msr:
            self._msr = MSR.MSR(self._proc, cpuinfo=self._cpuinfo)

        self._epb_msr = EnergyPerfBias.EnergyPerfBias(proc=self._proc, cpuinfo=self._cpuinfo,
                                                      msr=self._msr)

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_epb_msr", "_msr", "_cpuinfo", "_proc"):
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
