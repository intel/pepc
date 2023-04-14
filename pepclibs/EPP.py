# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides a capability of reading and changing EPP (Energy Performance Preference) on
Intel CPUs.
"""

from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs import CPUInfo, _PropsCache

# The minimum and maximum EPP values.
_EPP_MIN, _EPP_MAX = 0, 0xFF

class EPP(ClassHelpers.SimpleCloseContext):
    """
    This module provides a capability of reading and changing EPP (Energy Performance Preference) on
    Intel CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPP through MSR: 'get_epp_hw()', 'set_epp_hw()'.
        * Get/set EPP through sysfs: 'get_epp()', 'set_epp()'.
    2. Single CPU.
        * Get/set EPP through MSR: 'get_cpu_epp_hw()', 'set_cpu_epp_hw()'.
        * Get/set EPP through sysfs: 'get_cpu_epp()', 'set_cpu_epp()'.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    def _get_hwpreq(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            from pepclibs.msr import HWPRequest # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            from pepclibs.msr import HWPRequestPkg # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_available_policies(self, cpu):
        """Returns list of available EPP policies read from sysfs."""

        if not self._epp_policies:
            try:
                with self._pman.open(self._sysfs_epp_policies_path % cpu, "r") as fobj:
                    line = fobj.read().strip()

                self._epp_policies = Trivial.split_csv_line(line, sep=" ")
            except Error:
                self._epp_policies = None

        return self._epp_policies

    def _validate_epp_value(self, val, policy_ok=False):
        """
        Validate EPP value. When 'policy_ok=True' will not raise exception if not a numeric value.
        """

        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPP_MIN, _EPP_MAX, what="EPP value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPP value must be an integer within [{_EPP_MIN},{_EPP_MAX}]")
        else:
            policies = self._get_available_policies(0)
            if not policies:
                raise ErrorNotSupported(f"No EPP policies supported{self._pman.hostmsg}, please "
                                        f"use instead an integer within [{_EPP_MIN},{_EPP_MAX}]")

            if val not in policies:
                policies = ", ".join(policies)
                raise ErrorNotSupported(f"EPP value must be one of the following EPP policies: "
                                        f"{policies}, or integer within [{_EPP_MIN},{_EPP_MAX}]")

# ------------------------------------------------------------------------------------------------ #
# Get EPP through MSR.
# ------------------------------------------------------------------------------------------------ #

    def _read_cpu_epp_hw(self, cpu):
        """Read EPP for CPU 'cpu' from MSR."""

        # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
        try:
            hwpreq = self._get_hwpreq()
        except ErrorNotSupported:
            return None

        if hwpreq.is_cpu_feature_pkg_controlled("epp", cpu):
            hwpreq = self._get_hwpreq_pkg()

        try:
            return hwpreq.read_cpu_feature("epp", cpu)
        except ErrorNotSupported:
            return None

    def get_epp_hw(self, cpus="all"):
        """
        Yield (CPU number, EPP value) pairs for CPUs in 'cpus'. The EPP value is read via MSR.
        The arguments are as follows.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._read_cpu_epp_hw(cpu))

    def get_cpu_epp_hw(self, cpu):
        """Similar to 'get_epp_hw()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._read_cpu_epp_hw(cpu)

# ------------------------------------------------------------------------------------------------ #
# Set EPP through MSR.
# ------------------------------------------------------------------------------------------------ #

    def _write_cpu_epp_hw(self, epp, cpu):
        """Write EPP 'epp' for CPU 'cpu' to MSR."""

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control("epp", cpu)

        try:
            hwpreq.write_cpu_feature("epp", epp, cpu)
        except Error as err:
            raise type(err)(f"failed to set EPP HW{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def set_epp_hw(self, epp, cpus="all"):
        """
        Set EPP for CPUs in 'cpus'. The EPP value is set via MSR. The arguments are as follows.
          * epp - the EPP value to set. Can be an integer or string representing an integer.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
        """

        self._validate_epp_value(epp)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._write_cpu_epp_hw(epp, cpu)

    def set_cpu_epp_hw(self, epp, cpu):
        """Similar to 'set_epp_hw()', but for a single CPU 'cpu'."""

        self._validate_epp_value(epp)

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._write_cpu_epp_hw(epp, cpu)

# ------------------------------------------------------------------------------------------------ #
# Get EPP through sysfs.
# ------------------------------------------------------------------------------------------------ #

    def _read_cpu_epp(self, cpu):
        """Read EPP for CPU 'cpu' from sysfs."""

        if self._pcache.is_cached("epp", cpu):
            return self._pcache.get("epp", cpu)

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r") as fobj:
                epp = fobj.read().strip()
        except ErrorNotFound:
            epp = None

        return self._pcache.add("epp", cpu, epp)

    def get_epp(self, cpus="all"):
        """
        Yield (CPU number, EPP value) pairs for CPUs in 'cpus'. The EPP value is read via sysfs.
        The arguments are as follows.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._read_cpu_epp(cpu))

    def get_cpu_epp(self, cpu):
        """Similar to 'get_epp()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._read_cpu_epp(cpu)

# ------------------------------------------------------------------------------------------------ #
# Set EPP through sysfs.
# ------------------------------------------------------------------------------------------------ #

    def _write_cpu_epp(self, epp, cpu):
        """Write EPP 'epp' for CPU 'cpu' to sysfs."""

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r+") as fobj:
                fobj.write(epp)
        except Error as err:
            raise type(err)(f"failed to set EPP{self._pman.hostmsg}:\n{err.indent(2)}") from err

        # Setting some options will not read back the same value. E.g. "default" EPP might be
        # "balance_performance", "0" might be "powersave".
        try:
            val = self._aliases[epp]
        except KeyError:
            with self._pman.open(self._sysfs_epp_path % cpu, "r") as fobj:
                self._aliases[epp] = fobj.read().strip()
            val = self._aliases[epp]

        return self._pcache.add("epp", cpu, val)

    def set_epp(self, epp, cpus="all"):
        """
        Set EPP for CPU in 'cpus'. The EPP value is written via sysfs. The arguments are as follows.
          * epp - the EPP value to set. Can be an integer, a string representing an integer, or one
                  of the EPP policy names.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
        """

        self._validate_epp_value(epp, policy_ok=True)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._write_cpu_epp(str(epp), cpu)

    def set_cpu_epp(self, epp, cpu):
        """Similar to 'set_epp()', but for a single CPU 'cpu'."""

        self._validate_epp_value(epp, policy_ok=True)

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._write_cpu_epp(str(epp), cpu)

# ------------------------------------------------------------------------------------------------ #

    def __init__(self, pman=None, cpuinfo=None, msr=None, hwpreq=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * hwpreq - an 'HWPRequest.HWPRequest()' object.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._hwpreq = hwpreq
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_hwpreq = hwpreq is None

        self._hwpreq_pkg = None

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # The per-CPU cache for read-only data, such as policies list. MSR implements its own
        # caching.
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)
        self._aliases = {}
        # List of available EPP policies according to sysfs.
        self._epp_policies = None

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_hwpreq", "_hwpreq_pkg", "_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
