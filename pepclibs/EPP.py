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

import contextlib
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import Trivial, ClassHelpers
from pepclibs import _EPBase

# The minimum and maximum EPP values.
_EPP_MIN, _EPP_MAX = 0, 0xFF

class EPP(_EPBase.EPBase):
    """
    This module provides a capability of reading and changing EPP (Energy Performance Preference) on
    Intel CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get/set EPP: 'get_epp()', 'set_epp()'.
    2. Single CPU.
        * Get/set EPP: 'get_cpu_epp()', 'set_cpu_epp()'.
    """

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

    def _validate_value(self, val, policy_ok=False):
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
                raise ErrorNotSupported(f"no EPP policies supported{self._pman.hostmsg}, please "
                                        f"use instead an integer within [{_EPP_MIN},{_EPP_MAX}]")

            if val not in policies:
                policies = ", ".join(policies)
                raise ErrorNotSupported(f"EPP value must be one of the following EPP policies: "
                                        f"{policies}, or integer within [{_EPP_MIN},{_EPP_MAX}]")

    def _read_from_msr(self, cpu):
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

    def _write_to_msr(self, val, cpu):
        """Write EPP 'epp' for CPU 'cpu' to MSR."""

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control("epp", cpu)

        try:
            hwpreq.write_cpu_feature("epp", val, cpu)
        except Error as err:
            raise type(err)(f"failed to set EPP HW{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _read_from_sysfs(self, cpu):
        """Read EPP for CPU 'cpu' from sysfs."""

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get("epp", cpu, "sysfs")

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r") as fobj:
                epp = fobj.read().strip()
        except ErrorNotFound:
            epp = None

        return self._pcache.add("epp", cpu, epp, "sysfs")

    def _write_to_sysfs(self, val, cpu):
        """Write EPP 'epp' for CPU 'cpu' to sysfs."""

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r+") as fobj:
                try:
                    fobj.write(val)
                except Error:
                    # This is a workaround for a kernel bug, which has been fixed in v6.5:
                    #   03f44ffb3d5be cpufreq: intel_pstate: Fix energy_performance_preference for
                    #                 passive
                    # The bug is that write fails is the new value is the same as the current value.
                    fobj.seek(0)
                    val1 = fobj.read().strip()
                    if val != val1:
                        raise

                    self._aliases[val] = val1
                else:
                    # Setting some options will not read back the same value. E.g. "default" EPP
                    # might be "balance_performance", "0" might be "powersave".
                    try:
                        val1 = self._aliases[val]
                    except KeyError:
                        fobj.seek(0)
                        self._aliases[val] = fobj.read().strip()
                        val1 = self._aliases[val]
        except Error as err:
            if isinstance(err, ErrorNotFound):
                err = ErrorNotSupported(err)
            raise type(err)(f"failed to set EPP{self._pman.hostmsg}:\n{err.indent(2)}") from err

        return self._pcache.add("epp", cpu, val1, "sysfs")

    def get_epp(self, cpus="all", mnames=None):
        """
        Read EPP for CPUs 'cpus' using the 'mname' mechanism and yield (CPU number, EPP value)
        pairs. The arguments are as follows.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for getting EPP (see '_PropsClassBase.MECHANISMS').
                     The mechanisms will be tried in the order specified in 'mnames'. By default,
                     all supported mechanisms will be tried.
        """

        return self._get_epp_or_epb(cpus=cpus, mnames=mnames)

    def get_cpu_epp(self, cpu, mnames=None):
        """Similar to 'get_epp()', but for a single CPU 'cpu'."""

        _, epp = next(self.get_epp(cpus=(cpu,), mnames=mnames))
        return epp

    def set_epp(self, epp, cpus="all", mnames=None):
        """
        Set EPP for CPU in 'cpus' using the 'mname' mechanism. The arguments are as follows.
          * epp - the EPP value to set. Can be an integer, a string representing an integer. If
                  'mname' is "sysfs", 'epp' can also be EPP policy name (e.g., "performance").
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for setting EPP (see '_PropsClassBase.MECHANISMS').
                     The mechanisms will be tried in the order specified in 'mnames'. By default,
                     all supported mechanisms will be tried.

        Raise 'ErrorNotSupported' if the platform does not support EPP.
        """

        return self._set_epb_or_epb(epp, cpus=cpus, mnames=mnames)

    def set_cpu_epp(self, epp, cpu, mnames=None):
        """Similar to 'set_epp()', but for a single CPU 'cpu'."""

        self.set_epp(epp, cpus=(cpu,), mnames=mnames)

    def __init__(self, pman=None, cpuinfo=None, msr=None, hwpreq=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * hwpreq - an 'HWPRequest.HWPRequest()' object.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__("EPP", pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._hwpreq = hwpreq

        self._close_hwpreq = hwpreq is None

        self._hwpreq_pkg = None
        self._aliases = {}

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        # List of available EPP policies according to sysfs.
        self._epp_policies = None

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_hwpreq", "_hwpreq_pkg", "_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
