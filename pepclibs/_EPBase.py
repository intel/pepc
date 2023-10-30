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
This is the base class for 'EPP' and 'EPB' modules which includes common functionality.
"""

from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial, Human
from pepclibs import CPUInfo, _PropsCache
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

# Supported mechanism names
_MNAMES = ("sysfs", "msr")

def _bug_method_not_defined(method_name):
    """Raise an error if the child class did not define the 'method_name' mandatory method."""

    raise Error(f"BUG: '{method_name}()' was not defined by the child class")

class EPBase(ClassHelpers.SimpleCloseContext):
    """
    This is the base class for 'EPP' and 'EPB' modules which includes common functionality.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    @staticmethod
    def _normalize_mnames(mnames):
        """Validate and normalize mechanism names in 'mnames'."""

        if mnames is None:
            return list(_MNAMES)

        for mname in mnames:
            if mname in _MNAMES:
                continue
            mnames = ", ".join(_MNAMES)
            raise Error(f"BUG: bad mechanism name '{mname}', supported mechanisms are: {_MNAMES}")

        return Trivial.list_dedup(mnames)

    def _raise_getset_exception(self, cpus, mnames, action, errors):
        """
        Rase an exception from the "get" or "set" method in a situation when EPP/EPB could not be
        set or set using mechanisms in 'mname'.
        """

        if len(mnames) > 1:
            mnames_str = f"using {','.join(mnames)} methods"
        else:
            mnames_str = f"using the {mnames[0]} method"

        cpus_range = Human.rangify(cpus)
        sub_errmsgs = "\n".join([err.indent(2) for err in errors])

        raise ErrorNotSupported(f"cannot {action} {self._what} '{mnames_str}' for the following "
                                f"CPUs: {cpus_range}\n{sub_errmsgs}")

    def _validate_value(self, val, policy_ok=False):
        """
        Validate EPP or EPB value. When 'policy_ok=True' will not raise exception if not a numeric
        value.
        """

        # pylint: disable=unused-argument
        return _bug_method_not_defined("_EPBase._validate_value")

    def _read_from_msr(self, cpu):
        """Read EPP or EPB from msr for CPU 'cpu'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("_EPBase._read_from_msr")

    def _read_from_sysfs(self, cpu):
        """Read EPP or EPB from sysfs for CPU 'cpu'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("_EPBase._read_from_sysfs")

    def _write_to_msr(self, val, cpu):
        """write EPP or EPB from msr for CPU 'cpu'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("_EPBase._write_to_msr")

    def _write_to_sysfs(self, val, cpu):
        """write EPP or EPB from sysfs for CPU 'cpu'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("_EPBase._write_to_sysfs")

    def _get_epp_or_epb(self, cpus="all", mnames=None):
        """Get EPB or EPP. Refer to 'EPP.get_epp()' or 'EPB.get_epb()' docstring."""

        mnames = self._normalize_mnames(mnames)
        cpus = self._cpuinfo.normalize_cpus(cpus)
        errors = []

        for mname in mnames:
            if mname == "sysfs":
                func = self._read_from_sysfs
            else:
                func = self._read_from_msr

            try:
                for cpu in cpus:
                    yield (cpu, func(cpu))
            except ErrorNotSupported as err:
                if cpu == cpus[0]:
                    errors.append(err)
                    continue
                raise

            return

        # None of the methods worked.
        self._raise_getset_exception(cpus, mnames, "get", errors)

    def _set_epb_or_epb(self, epb, cpus="all", mnames=None):
        """
        Set EPB for CPU in 'cpus' using the 'mname' mechanism. The arguments are as follows.
          * epb - the EPB value to set. Can be an integer, a string representing an integer. If
                  'mname' is "sysfs", 'epb' can also be EPB policy name (e.g., "performance").
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for setting EPB (see '_PropsClassBase.MECHANISMS').
                     The mechanisms will be tried in the order specified in 'mnames'. By default,
                     all supported mechanisms will be tried.

        Raise 'ErrorNotSupported' if the platform does not support EPB.
        """

        mnames = self._normalize_mnames(mnames)
        cpus = self._cpuinfo.normalize_cpus(cpus)
        errors = []

        for mname in mnames:
            if mname == "sysfs":
                func = self._write_to_sysfs
                policy_ok = True
            else:
                func = self._write_to_msr
                policy_ok = False

            cpu = 0
            try:
                self._validate_value(epb, policy_ok=policy_ok)
                for cpu in cpus:
                    func(str(epb), cpu)
            except ErrorNotSupported as err:
                if cpu == cpus[0]:
                    errors.append(err)
                    continue
                raise

            return

        # None of the methods worked.
        self._raise_getset_exception(cpus, mnames, "set", errors)

    def __init__(self, what, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * what - should be "EPP" or "EPB".
          * pman - the process manager object that defines the host to manage EPB/EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        self._what = what
        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._enable_cache = enable_cache

        # EPP/EPB scope name.
        self.sname = "CPU"

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # The per-CPU cache for read-only data, such as policies list. MSR implements its own
        # caching.
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
