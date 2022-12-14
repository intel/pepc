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

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs import CPUInfo, _PropsCache
from pepclibs.msr import MSR, EnergyPerfBias

# EPB policy names, from the following Linux kernel file: arch/x86/kernel/cpu/intel_epb.c
_EPB_POLICIES = ("performance", "balance-performance", "normal", "balance-power", "power")

# The minimum and maximum EPB values.
_EPB_MIN, _EPB_MAX = 0, 15

class EPB(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
    CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPB through sysfs: 'get_epb()', 'set_epb()'.
        * Get/set EPB through MSR: 'get_epb_hw()', 'set_epb_hw()'.
    2. Single CPU.
        * Get/set EPB through sysfs: 'get_cpu_epb()', 'set_cpu_epb()'.
        * Get/set EPB through MSR: 'get_cpu_epb_hw()', 'set_cpu_epb_hw()'.
    """

    def _get_msrobj(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    def _get_epbobj(self):
        """Returns an 'EnergyPerfBias.EnergyPerfBias()' object."""

        if not self._epb_msr:
            msr = self._get_msrobj()
            self._epb_msr = EnergyPerfBias.EnergyPerfBias(pman=self._pman, cpuinfo=self._cpuinfo,
                                                          msr=msr)
        return self._epb_msr

    @staticmethod
    def _validate_epb_value(val, policy_ok=False):
        """
        Validate EPB value and raise appropriate exception. When 'policy_ok=True' also validate
        against accepted EPB policies.
        """

        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPB_MIN, _EPB_MAX, what="EPB value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPB value must be an integer within [{_EPB_MIN},{_EPB_MAX}]")
        elif val not in _EPB_POLICIES:
            policies = ", ".join(_EPB_POLICIES)
            raise ErrorNotSupported(f"EPB value must be one of the following EPB policies: " \
                                    f"{policies}, or integer within [{_EPB_MIN},{_EPB_MAX}]")

# ------------------------------------------------------------------------------------------------ #
# Get EPB through MSR.
# ------------------------------------------------------------------------------------------------ #

    def _get_cpu_epb_from_msr(self, cpu):
        """Get EPB for CPU 'cpu' from MSR."""

        _epb = self._get_epbobj()

        try:
            return _epb.read_cpu_feature("epb", cpu)
        except ErrorNotSupported:
            return None

    def get_epb_hw(self, cpus="all"):
        """
        Yield (CPU number, EPB value) pairs for CPUs in 'cpus'. The EPB value is read via MSR.
        The arguments are as follows.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._get_cpu_epb_from_msr(cpu))

    def get_cpu_epb_hw(self, cpu):
        """Similar to 'get_epb_hw()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epb_from_msr(cpu)

# ------------------------------------------------------------------------------------------------ #
# Set EPB through MSR.
# ------------------------------------------------------------------------------------------------ #

    def _set_cpu_epb_in_msr(self, epb, cpu):
        """Set EPB for CPU 'cpu' in MSR."""

        _epb = self._get_epbobj()

        try:
            _epb.write_cpu_feature("epb", epb, cpu)
        except Error as err:
            raise type(err)(f"failed to set EPB HW{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def set_epb_hw(self, epb, cpus="all"):
        """
        Set EPB for CPUs in 'cpus'. The EPB value is set via MSR. The arguments are as follows.
          * epb - the EPB value to set. Can be an integer or string representing an integer.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        self._validate_epb_value(epb)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._set_cpu_epb_in_msr(epb, cpu)

    def set_cpu_epb_hw(self, epb, cpu):
        """Similar to 'set_epb_hw()', but for a single CPU 'cpu'."""

        self._validate_epb_value(epb)

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._set_cpu_epb_in_msr(epb, cpu)

# ------------------------------------------------------------------------------------------------ #
# Get EPB through sysfs.
# ------------------------------------------------------------------------------------------------ #

    def _read_cpu_epb_from_sysfs(self, cpu):
        """Reads EPB for CPU 'cpu' from sysfs."""

        if self._pcache.is_cached("epb", cpu):
            return self._pcache.get("epb", cpu)

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r") as fobj:
                val = fobj.read().strip()
        except ErrorNotFound:
            val = None

        return self._pcache.add("epb", cpu, int(val))

    def get_epb(self, cpus="all"):
        """
        Yield (CPU number, EPB value) pairs for CPUs in 'cpus'. The EPB value is read via sysfs.
        The arguments are as follows.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._read_cpu_epb_from_sysfs(cpu))

    def get_cpu_epb(self, cpu):
        """Similar to 'get_epb()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._read_cpu_epb_from_sysfs(cpu)

# ------------------------------------------------------------------------------------------------ #
# Set EPB through sysfs.
# ------------------------------------------------------------------------------------------------ #

    def _write_cpu_epb_to_sysfs(self, epb, cpu):
        """Write EPB for CPU 'cpu' to sysfs."""

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r+") as fobj:
                fobj.write(epb)
        except Error as err:
            raise type(err)(f"failed to set EPB{self._pman.hostmsg}:\n{err.indent(2)}") from err

        # Setting EPB to policy name will not read back the name, rather the numeric value.
        # E.g. "performance" EPB might be "0".
        if not Trivial.is_int(epb):
            if not self._epb_policies[epb]:
                self._epb_policies[epb] = int(self._read_cpu_epb_from_sysfs(cpu))

            self._pcache.add("epb", cpu, self._epb_policies[epb])
        else:
            self._pcache.add("epb", cpu, int(epb))

    def set_epb(self, epb, cpus="all"):
        """
        Set EPB for CPU in 'cpus'. The EPB value is written via sysfs. The arguments are as follows.
          * epb - the EPB value to set. Can be an integer, a string representing an integer, or a
                  EPB policy name.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        self._validate_epb_value(epb, policy_ok=True)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._write_cpu_epb_to_sysfs(str(epb), cpu)

    def set_cpu_epb(self, epb, cpu):
        """Similar to 'set_epb()', but for a single CPU 'cpu'."""

        self._validate_epb_value(epb, policy_ok=True)

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._write_cpu_epb_to_sysfs(str(epb), cpu)

# ------------------------------------------------------------------------------------------------ #

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPB for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._epb_msr = None
        # EPB policy to EPB value dictionary.
        self._epb_policies = {name : None for name in _EPB_POLICIES}
        self._sysfs_epb_path = "/sys/devices/system/cpu/cpu%d/power/energy_perf_bias"

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # The per-CPU cache for sysfs data. MSR implements its own caching.
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported vendor {cpuinfo.info['vendor']}{pman.hostmsg}. "
                                    f"Only Intel CPUs are supported.")

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_epb_msr", "_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
