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

# TODO: Finish annotating and modernizing this module.
from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs import CPUInfo, _PropsCache
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from pepclibs._PropsClassBaseTypes import ScopeNameType

# Supported mechanism names.
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

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)
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
        Rase an exception for "get" or "set" method in a situation when EPP/EPB could not be
        read or set using mechanisms in 'mnames'.
        """

        if len(mnames) > 1:
            mnames_str = f"using {','.join(mnames)} methods"
        else:
            mnames_str = f"using the {mnames[0]} method"

        cpus_range = Trivial.rangify(cpus)
        if errors:
            sub_errmsgs = "\n" + "\n".join([err.indent(2) for err in errors])
        else:
            sub_errmsgs = ""

        raise ErrorNotSupported(f"cannot {action} {self._what} {mnames_str} for the following "
                                f"CPUs: {cpus_range}{sub_errmsgs}")

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

    def _get_epp_or_epb(self, cpus, mnames):
        """Yield EPB or EPP for CPUs in 'cpus'."""

        mnames = self._normalize_mnames(mnames)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        for mname in mnames:
            if mname == "sysfs":
                func = self._read_from_sysfs
            else:
                func = self._read_from_msr

            for cpu in cpus:
                val = func(cpu)
                if val is None:
                    break
                yield (cpu, val, mname)

            if val is None:
                continue

            return

        # None of the methods worked.
        self._raise_getset_exception(cpus, mnames, "get", [])

    def _set_epb_or_epb(self, val, cpus="all", mnames=None):
        """
        Set EPB or EPP for CPU in 'cpus' using the 'mname' mechanism. The arguments are as follows.
          * val - the EPB or EPP value to set. Can be an integer, a string representing an integer.
                  If 'mname' is "sysfs", 'val' can also be EPB or EPP policy name (e.g.,
                  "performance").
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for setting EPB or EPP. The mechanisms will be tried
            in the order specified in 'mnames'. By default, all supported mechanisms will be tried.

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
                self._validate_value(val, policy_ok=policy_ok)
                for cpu in cpus:
                    func(str(val), cpu)
            except ErrorNotSupported as err:
                if cpu == cpus[0]:
                    errors.append(err)
                    continue
                raise

            return mname

        # None of the methods worked.
        self._raise_getset_exception(cpus, mnames, "set", errors)

    def get_vals(self, cpus="all", mnames=None):
        """
        Read EPP or EPB for CPUs 'cpus' using mechanisms in 'mnames' and yield '(cpu, value, mname)'
        tuples for every CPU in 'cpus'. The arguments are as follows.
          * cpus - collection of integer CPU numbers to read EPP or EPB for. Special value 'all'
                   means "all CPUs".
          * mnames - list of mechanisms to use for reading EPP/EPP. The mechanisms will be tried in
                     the order specified in 'mnames'. By default, all supported mechanisms will be
                     tried.
        """

        yield from self._get_epp_or_epb(cpus, mnames)

    def get_cpu_val(self, cpu, mnames=None):
        """
        Read EPP or EPB for CPUs 'cpus' using mechanisms in 'mnames' and return the '(value, mname)'
        tuple. The arguments are as follows.
          * cpu - CPU number to read EPP or EPB for.
          * mnames - list of mechanisms to use for reading EPP/EPP. The mechanisms will be tried in
                     the order specified in 'mnames'. By default, all supported mechanisms will be
                     tried.
        """

        _, val, mname = next(self._get_epp_or_epb((cpu,), mnames))
        return val, mname

    def set_vals(self, val, cpus="all", mnames=None):
        """
        Set EPP or EPB for CPUs in 'cpus' using the 'mname' mechanism. The arguments are as follows.
          * val - the EPP/EPB value to set. Can be an integer or a string representing an integer.
                  If 'mname' is "sysfs", 'epp' can also be EPP/EPB policy name
                  (e.g., "performance").
          * cpus - collection of integer CPU numbers to set EPP or EPB for. Special value 'all'
                   means "all CPUs".
          * mnames - list of mechanisms to use for setting EPP/EPP. The mechanisms will be tried in
                     the order specified in 'mnames'. By default, all supported mechanisms will be
                     tried.

        Return name of the mechanism that was used for setting EPP or EPB. Raise 'ErrorNotSupported'
        if the platform does not support EPP/EPP.
        """

        return self._set_epb_or_epb(val, cpus=cpus, mnames=mnames)

    def set_cpu_val(self, val, cpu, mnames=None):
        """
        Set EPP or EPB for CPU cpu' using the 'mname' mechanism. The arguments are as follows.
          * val - the EPP/EPB value to set. Can be an integer or a string representing an integer.
                  If 'mname' is "sysfs", 'epp' can also be EPP/EPB policy name
                  (e.g., "performance").
          * cpu - CPU numbers to set EPP or EPB for.
          * mnames - list of mechanisms to use for setting EPP/EPP. The mechanisms will be tried in
                     the order specified in 'mnames'. By default, all supported mechanisms will be
                     tried.

        Return name of the mechanism that was used for setting EPP or EPB. Raise 'ErrorNotSupported'
        if the platform does not support EPP/EPP.
        """

        return self._set_epb_or_epb(val, cpus=(cpu,), mnames=mnames)

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
        self.sname: ScopeNameType = "CPU"

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # The per-CPU cache for read-only data, such as policies list. MSR implements its own
        # caching.
        # pylint: disable=pepc-unused-variable
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
