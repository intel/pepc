# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#
# Parts of the code was contributed by Len Brown <len.brown@intel.com>.

"""
This module provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
CPUs.
"""

import contextlib
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs import CPUInfo, _PropsCache

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
        * Get/set EPB: 'get_epb()', 'set_epb()'.
    2. Single CPU.
        * Get/set EPB: 'get_cpu_epb()', 'set_cpu_epb()'.
    """

    def _get_msrobj(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    def _get_epbobj(self):
        """Returns an 'EnergyPerfBias.EnergyPerfBias()' object."""

        if not self._epb_msr:
            from pepclibs.msr import EnergyPerfBias # pylint: disable=import-outside-toplevel

            msr = self._get_msrobj()
            self._epb_msr = EnergyPerfBias.EnergyPerfBias(pman=self._pman, cpuinfo=self._cpuinfo,
                                                          msr=msr)
        return self._epb_msr

    @staticmethod
    def _validate_mname(mname):
        """Validate mechanism name 'mname'."""

        mnames = {"sysfs", "msr"}
        if mname not in mnames:
            mnames = ", ".join(mnames)
            raise Error(f"BUG: bad mechanism name '{mname}', supported mechanisms are: {mnames}")

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
            raise ErrorNotSupported(f"EPB value must be one of the following EPB policies: "
                                    f"{policies}, or integer within [{_EPB_MIN},{_EPB_MAX}]")

    def _read_cpu_epb_msr(self, cpu):
        """Read EPB for CPU 'cpu' from MSR."""

        try:
            return self._get_epbobj().read_cpu_feature("epb", cpu)
        except ErrorNotSupported:
            return None

    def _write_cpu_epb_msr(self, epb, cpu):
        """Write EPB 'epb' for CPU 'cpu' to MSR."""

        _epb = self._get_epbobj()

        try:
            _epb.write_cpu_feature("epb", epb, cpu)
        except Error as err:
            raise type(err)(f"failed to set EPB HW{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _read_cpu_epb_sysfs(self, cpu):
        """Read EPB for CPU 'cpu' from sysfs."""

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get("epb", cpu, "sysfs")

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r") as fobj:
                val = int(fobj.read().strip())
        except ErrorNotFound:
            val = None

        return self._pcache.add("epb", cpu, val, "sysfs")

    def _write_cpu_epb_sysfs(self, epb, cpu):
        """Write EPB 'epb' for CPU 'cpu' to sysfs."""

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r+") as fobj:
                fobj.write(epb)
        except Error as err:
            if isinstance(err, ErrorNotFound):
                err = ErrorNotSupported(err)
            raise type(err)(f"failed to set EPB{self._pman.hostmsg}:\n{err.indent(2)}") from err

        # Setting EPB to policy name will not read back the name, rather the numeric value.
        # E.g. "performance" EPB might be "0".
        if not Trivial.is_int(epb):
            if not self._epb_policies[epb]:
                self._epb_policies[epb] = int(self._read_cpu_epb_sysfs(cpu))

            self._pcache.add("epb", cpu, self._epb_policies[epb], "sysfs")
        else:
            self._pcache.add("epb", cpu, int(epb), "sysfs")

    def get_epb(self, cpus="all", mname="sysfs"):
        """
        Get EPB for CPUs 'cpus' using the 'mname' mechanism and yield (CPU number, EPB value) pairs.
        The arguments are as follows.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mname - name of the mechanism to use (see '_PropsClassBase.MECHANISMS').
        """

        self._validate_mname(mname)

        if mname == "sysfs":
            func = self._read_cpu_epb_sysfs
        else:
            func = self._read_cpu_epb_msr

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, func(cpu))

    def get_cpu_epb(self, cpu, mname="sysfs"):
        """Similar to 'get_epb()', but for a single CPU 'cpu'."""

        _, epb = next(self.get_epb(cpus=(cpu,), mname=mname))
        return epb

    def set_epb(self, epb, cpus="all", mname="sysfs"):
        """
        Set EPB for CPU in 'cpus' using the 'mname' mechanism. The arguments are as follows.
          * epb - the EPB value to set. Can be an integer, a string representing an integer. If
                  'mname' is "sysfs", 'epb' can also be EPB policy name (e.g., "performance").
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mname - name of the mechanism to use (see '_PropsClassBase.MECHANISMS').

        Raise 'ErrorNotSupported' if the platform does not support EPB.
        """

        self._validate_mname(mname)

        if mname == "sysfs":
            func = self._write_cpu_epb_sysfs
            policy_ok = True
        else:
            func = self._write_cpu_epb_msr
            policy_ok = False

        self._validate_epb_value(epb, policy_ok=policy_ok)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            func(str(epb), cpu)

    def set_cpu_epb(self, epb, cpu, mname="sysfs"):
        """Similar to 'set_epb()', but for a single CPU 'cpu'."""
        self.set_epb(epb, cpus=(cpu,), mname=mname)

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

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_epb_msr", "_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
