# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of retrieving and setting P-state related properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from typing import Generator, NoReturn, cast

import contextlib
import statistics

from pepclibs import _PropsClassBase
from pepclibs.helperlibs import Trivial, Human, ClassHelpers

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed
from pepclibs._PropsClassBase import ErrorTryAnotherMechanism
# Make the exception class be available for users.
# pylint: disable-next=unused-import
from pepclibs._PropsClassBase import ErrorUsePerCPU

if typing.TYPE_CHECKING:
    from pepclibs.msr import MSR, FSBFreq
    from pepclibs import _SysfsIO, EPP, EPB, _CPUFreq, _UncoreFreq
    from pepclibs.CPUInfo import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._PropsClassBaseTypes import NumsType, DieNumsType, MechanismNameType
    from pepclibs._PropsClassBaseTypes import PropertyTypedDict, PropertyValueType

class ErrorFreqOrder(Error):
    """
    Raise when modification of minimum or maximum frequency fails due to ordering constraints.
    """

class ErrorFreqRange(ErrorTryAnotherMechanism):
    """
    Raise when minimum or maximum frequency values are outside the permitted range.

    This exception suggests that the current mechanism cannot handle the requested frequency,
    but another mechanism may succeed.
    """

# Special values for writable CPU frequency properties.
_SPECIAL_FREQ_VALS = {"min", "max", "base", "hfm", "P1", "eff", "lfm", "Pn", "Pm"}
# Special values for writable uncore frequency properties.
_SPECIAL_UNCORE_FREQ_VALS = {"min", "max", "mdl"}

# This properties dictionary defines the CPU properties supported by this module.
#
# Although this dictionary is user-visible and may be accessed directly, it is not recommended
# because it is incomplete. Prefer using 'PStates.props' instead.
#
# Some properties have their scope name set to 'None' because the scope may vary depending on the
# platform. In such cases, the scope can be determined using 'PStates.get_sname()'.
PROPS: dict[str, PropertyTypedDict] = {
    "turbo": {
        "name": "Turbo",
        "type": "bool",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "min_freq": {
        "name": "Min. CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
        "special_vals": _SPECIAL_FREQ_VALS,
    },
    "max_freq": {
        "name": "Max. CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
        "special_vals": _SPECIAL_FREQ_VALS,
    },
    "min_freq_limit": {
        "name": "Min. supported CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "max_freq_limit": {
        "name": "Max. supported CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "base_freq": {
        "name": "Base CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr", "cppc"),
        "writable": False,
    },
    "bus_clock": {
        "name": "Bus clock speed",
        "unit": "Hz",
        "type": "int",
        "sname": None,
        "mnames": ("msr", "doc"),
        "writable": False,
    },
    "min_oper_freq": {
        "name": "Min. CPU operating frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("msr", "cppc"),
        "writable": False,
    },
    "max_eff_freq": {
        "name": "Max. CPU efficiency frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("msr",),
        "writable": False,
    },
    "max_turbo_freq": {
        "name": "Max. CPU turbo frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("msr", "cppc"),
        "writable": False,
    },
    "frequencies": {
        "name": "Acceptable CPU frequencies",
        "unit": "Hz",
        "type": "list[int]",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "min_uncore_freq": {
        "name": "Min. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "max_uncore_freq": {
        "name": "Max. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "min_uncore_freq_limit": {
        "name": "Min. supported uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "max_uncore_freq_limit": {
        "name": "Max. supported uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "hwp": {
        "name": "Hardware power management",
        "type": "bool",
        "sname": "global",
        "mnames": ("msr",),
        "writable": False,
    },
    "epp": {
        "name": "EPP",
        "type": "str",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
    },
    "epb": {
        "name": "EPB",
        "type": "int",
        "sname": None,
        "mnames": ("sysfs", "msr"),
        "writable": True,
    },
    "driver": {
        "name": "CPU frequency driver",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "intel_pstate_mode": {
        "name": "Mode of 'intel_pstate' driver",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "governor": {
        "name": "CPU frequency governor",
        "type": "str",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "governors": {
        "name": "Available CPU frequency governors",
        "type": "list[str]",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
}

class PStates(_PropsClassBase.PropsClassBase):
    """
    This class provides API for managing platform settings related to P-states. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()'). If not provided, one is
                     created.
            msr: The MSR access object ('MSR.MSR()'). If not provided, one is created.
            sysfs_io: The sysfs access object ('_SysfsIO.SysfsIO()'). If not provided, one is
                      created.
            enable_cache: Enable property caching if True, do not use caching if False.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._eppobj: EPP.EPP | None = None
        self._epbobj: EPB.EPB | None = None
        self._fsbfreq: FSBFreq.FSBFreq | None = None

        self._cpufreq_sysfs_obj: _CPUFreq.CPUFreqSysfs | None = None
        self._cpufreq_cppc_obj: _CPUFreq.CPUFreqCPPC | None = None
        self._cpufreq_msr_obj: _CPUFreq.CPUFreqMSR | None= None

        self._uncfreq_sysfs_obj: _UncoreFreq.UncoreFreqSysfs | None = None
        self._uncfreq_sysfs_err: str | None = None

        super()._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_eppobj", "_epbobj", "_fsbfreq", "_cpufreq_sysfs_obj", "_cpufreq_cppc_obj",
                       "_cpufreq_msr_obj", "_uncfreq_sysfs_obj")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()

    def _is_uncore_prop(self, pname: str) -> bool:
        """
        Check if the given property name refers to an uncore property.

        Args:
            pname: The property name to check.

        Returns:
            True if the property is an uncore property, otherwise False.
        """

        return pname in {"min_uncore_freq", "max_uncore_freq",
                         "min_uncore_freq_limit", "max_uncore_freq_limit"}

    def _get_fsbfreq(self) -> FSBFreq.FSBFreq:
        """
        Get an 'FSBFreq' object.

        Returns:
            An instance of 'FSBFreq.FSBFreq'.
        """

        if not self._fsbfreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import FSBFreq

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_eppobj(self) -> EPP.EPP:
        """
        Get an 'EPP' object.

        Returns:
            An instance of 'EPP.EPP'.
        """

        if not self._eppobj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import EPP

            msr = self._get_msr()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._eppobj

    def _get_epbobj(self) -> EPB.EPB:
        """
        Get an 'EPB' object.

        Returns:
            An instance of 'EPB.EPB'.
        """

        if not self._epbobj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import EPB

            msr = self._get_msr()
            self._epbobj = EPB.EPB(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._epbobj

    def _get_cpufreq_sysfs_obj(self) -> _CPUFreq.CPUFreqSysfs:
        """
        Get an 'CPUFreqSysfs' object.

        Returns:
            An instance of '_CPUFreq.CPUFreqSysfs'.
        """

        if not self._cpufreq_sysfs_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreq

            msr = self._get_msr()
            sysfs_io = self._get_sysfs_io()
            self._cpufreq_sysfs_obj = _CPUFreq.CPUFreqSysfs(cpuinfo=self._cpuinfo, pman=self._pman,
                                                            msr=msr, sysfs_io=sysfs_io,
                                                            enable_cache=self._enable_cache)
        return self._cpufreq_sysfs_obj

    def _get_cpufreq_cppc_obj(self) -> _CPUFreq.CPUFreqCPPC:
        """
        Get an 'CPUFreqCPPC' object.

        Returns:
            An instance of '_CPUFreq.CPUFreqCPPC'.
        """

        if not self._cpufreq_cppc_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreq

            sysfs_io = self._get_sysfs_io()
            self._cpufreq_cppc_obj = _CPUFreq.CPUFreqCPPC(cpuinfo=self._cpuinfo, pman=self._pman,
                                                          sysfs_io=sysfs_io,
                                                          enable_cache=self._enable_cache)
        return self._cpufreq_cppc_obj

    def _get_cpufreq_msr_obj(self) -> _CPUFreq.CPUFreqMSR:
        """
        Get an 'CPUFreqMSR' object.

        Returns:
            An instance of '_CPUFreq.CPUFreqMSR'.
        """

        if not self._cpufreq_msr_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreq

            msr = self._get_msr()
            self._cpufreq_msr_obj = _CPUFreq.CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman,
                                                        msr=msr, enable_cache=self._enable_cache)
        return self._cpufreq_msr_obj

    def _get_uncfreq_sysfs_obj(self) -> _UncoreFreq.UncoreFreqSysfs:
        """
        Get an 'UncoreFreqSysfs' object.

        Returns:
            An instance of '_UncoreFreq.UncoreFreqSysfs'.
        """

        if self._uncfreq_sysfs_err:
            raise ErrorNotSupported(self._uncfreq_sysfs_err)

        if not self._uncfreq_sysfs_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _UncoreFreq

            sysfs_io = self._get_sysfs_io()
            try:
                obj = _UncoreFreq.UncoreFreqSysfs(self._cpuinfo, pman=self._pman, sysfs_io=sysfs_io,
                                                  enable_cache=self._enable_cache)
                self._uncfreq_sysfs_obj = obj
            except ErrorNotSupported as err:
                self._uncfreq_sysfs_err = str(err)
                raise

        return self._uncfreq_sysfs_obj

    def _get_epp(self,
                 cpus: NumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield EPP values for the specified CPUs using the specified mechanism.

        Args:
            cpus: CPU numbers to retrieve EPP values for.
            mname: Mechanism name to use for retrieving EPP values.

        Yields:
            Tuple of (cpu, val), where 'cpu' is th CPU number and 'val' is its EPP value.

        Notes:
            - The reason why the yield EPP values are strings is because the corresponding sysfs
              file may contain a policy name, which is a string, or a numeric value, which is also
              yielded as a string for simplicity.
        """

        for cpu, val, _ in self._get_eppobj().get_vals(cpus=cpus, mnames=(mname,)):
            yield cpu, val

    def _get_epb(self,
                 cpus: NumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield EPB values for the specified CPUs using the specified mechanism.

        Args:
            cpus: CPU numbers to retrieve EPB values for.
            mname: Mechanism name to use for retrieving EPB values.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its EPB value.
        """

        for cpu, val, _ in self._get_epbobj().get_vals(cpus=cpus, mnames=(mname,)):
            yield cpu, val

    def _get_max_eff_freq(self, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum efficiency frequency for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve maximum efficiency frequency for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its maximum efficiency
            frequency.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()
        yield from cpufreq_obj.get_max_eff_freq(cpus=cpus)

    def _get_hwp(self, cpus: NumsType) -> Generator[tuple[int, bool], None, None]:
        """
        Retrieve and yield the hardware power management (HWP) status for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve HWP status for.

        Yields:
            Tuple of (cpu, status), where 'cpu' is the CPU number and 'status' is its HWP status.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()
        yield from cpufreq_obj.get_hwp(cpus=cpus)

    def _get_cppc_freq(self, pname: str, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield frequency values for the specified CPUs using the CPPC mechanism.

        Args:
            pname: Property name to retrieve (e.g., "base_freq").
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_cppc_obj()

        if pname == "base_freq":
            yield from cpufreq_obj.get_base_freq(cpus)
            return

        with contextlib.suppress(ErrorNotSupported):
            if pname == "max_turbo_freq":
                yield from cpufreq_obj.get_max_freq_limit(cpus)
            elif pname == "min_oper_freq":
                yield from cpufreq_obj.get_min_freq_limit(cpus)
            else:
                raise Error(f"BUG: Unexpected property {pname}")
            return

        # Sometimes the frequency CPPC sysfs files are not readable, but the "performance" files
        # are. The base frequency is required to turn performance values to Hz.

        base_freq_iter = self._get_prop_cpus_mnames("base_freq", cpus)
        nominal_perf_iter = cpufreq_obj.get_base_perf(cpus)

        if pname == "max_turbo_freq":
            perf_iter = cpufreq_obj.get_max_perf_limit(cpus)
        else:
            perf_iter = cpufreq_obj.get_min_perf_limit(cpus)

        iterator = zip(base_freq_iter, nominal_perf_iter, perf_iter)
        for (cpu, base_freq), (_, nominal_perf), (_, perf) in iterator:
            yield cpu, (base_freq * perf) // nominal_perf

    def _get_min_oper_freq(self,
                           cpus: NumsType,
                           mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum operating frequency for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve minimum operating frequency for.
            mname: Name of the mechanism to use ('msr' or 'cppc').

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its minimum operating
            frequency.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_min_oper_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("min_oper_freq", cpus)
            return

        raise Error(f"BUG: Unsupported mechanism '{mname}'")

    def _get_max_turbo_freq(self,
                            cpus: NumsType,
                            mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum turbo frequency for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve maximum turbo frequency for.
            mname: Name of the mechanism to use ('msr' or 'cppc').

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its maximum turbo
            frequency.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_max_turbo_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("max_turbo_freq", cpus)
            return

        raise Error(f"BUG: Unsupported mechanism '{mname}'")

    def _get_base_freq(self,
                       cpus: NumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for the specified CPUs using the given mechanism.

        Args:
            cpus: CPU numbers to retrieve base frequency for.
            mname: Name of the mechanism to use for retrieving the base frequency: are 'sysfs',
                   'msr', and 'cppc'.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its base frequency.
        """

        if mname == "sysfs":
            sysfs_cpufreq_obj = self._get_cpufreq_sysfs_obj()
            yield from sysfs_cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "msr":
            msr_cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from msr_cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("base_freq", cpus)
            return

        raise Error(f"BUG: Unsupported mechanism '{mname}'")

    def _get_freq_sysfs(self, pname: str, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency values for the specified CPUs using the sysfs mechanism.

        Depending on the 'pname' argument, yield either the minimum, maximum, minimum limit, or
        maximum limit CPU frequency for the given CPUs.

        Args:
            pname: Name of the property to retrieve. Supported values are "min_freq", "max_freq",
                   "min_freq_limit", and "max_freq_limit".
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        elif pname == "min_freq_limit":
            yield from cpufreq_obj.get_min_freq_limit(cpus)
        elif pname == "max_freq_limit":
            yield from cpufreq_obj.get_max_freq_limit(cpus)
        else:
            raise Error(f"BUG: unexpected CPU frequency property {pname}")

    def _get_freq_msr(self, pname: str, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum or maximum CPU frequency for the specified CPUs using the MSR
        mechanism.

        Args:
            pname: The property to retrieve. Must be either "min_freq" or "max_freq".
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        else:
            raise Error(f"BUG: Unexpected CPU frequency property {pname}")

    def _get_freq(self, pname, cpus, mname):
        """
        Retrieve and yield the minimum or maximum CPU frequency for the specified CPUs using the
        specified mechanism.

        Args:
            pname: Name of the property to retrieve. Supported values are "min_freq", "max_freq".
            cpus: CPU numbers to retrieve frequency values for.
            mname: Name of the mechanism to use for retrieving the frequency (e.g., "sysfs").

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        if mname == "sysfs":
            yield from self._get_freq_sysfs(pname, cpus)
            return

        if mname == "msr":
            yield from self._get_freq_msr(pname, cpus)
            return

        raise Error(f"BUG: Unsupported mechanism '{mname}'")

    def _get_freq_limit(self, pname: str, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency limits for the specified CPUs using the sysfs mechanism.

        Args:
            pname: Property name to retrieve ("min_freq_limit" or "max_freq_limit").
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency limit in
            Hz.
        """

        yield from self._get_freq_sysfs(pname, cpus)

    def _get_uncore_freq_cpus(self,
                              pname: str,
                              cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield uncore frequency values for the specified CPUs using the sysfs mechanism.

        Args:
            pname: Name of the uncore frequency property to retrieve. Supported values are
                   "min_uncore_freq", "max_uncore_freq", "min_uncore_freq_limit", and
                   "max_uncore_freq_limit".
            cpus: CPU numbers to retrieve uncore frequency values for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its uncore frequency in
            Hz.
        """

        uncfreq_obj = self._get_uncfreq_sysfs_obj()

        if pname == "min_uncore_freq":
            yield from uncfreq_obj.get_min_freq_cpus(cpus)
            return
        if pname == "max_uncore_freq":
            yield from uncfreq_obj.get_max_freq_cpus(cpus)
            return
        if pname == "min_uncore_freq_limit":
            yield from uncfreq_obj.get_min_freq_limit_cpus(cpus)
            return
        if pname == "max_uncore_freq_limit":
            yield from uncfreq_obj.get_max_freq_limit_cpus(cpus)
            return

        raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _get_bclks_cpus(self, cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield bus clock speed for the specified CPUs using the MSR mechanism.

        Args:
            cpus: CPU numbers to retrieve bus clock speed for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is the bus clock speed in
            Hz.
        """

        try:
            fsbfreq = self._get_fsbfreq()
        except ErrorNotSupported:
            if self._cpuinfo.info["vendor"] != "GenuineIntel":
                raise
            # Fall back to 100MHz bus clock speed.
            for cpu in cpus:
                yield cpu, 100000000
        else:
            for cpu, bclk in fsbfreq.read_feature("fsb", cpus=cpus):
                # Convert MHz to Hz.
                yield cpu, int(bclk * 1000000)

    def _get_bclks_dies(self, dies: DieNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield bus clock speed for the specified dies using the MSR mechanism.

        Args:
            dies: Dictionary mapping package numbers to collections of die numbers.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the bus clock speed in Hz for the specified die.
        """

        try:
            self._get_fsbfreq()
        except ErrorNotSupported:
            if self._cpuinfo.info["vendor"] != "GenuineIntel":
                raise
            # Fall back to 100MHz bus clock speed.
            for package, pkg_dies in dies.items():
                for die in pkg_dies:
                    yield package, die, 100000000
        else:
            # Only legacy platforms support 'MSR_FSB_FREQ', and they do not have uncore frequency
            # control, so this code should never be executed.
            raise Error("BUG: Not implemented, contact project maintainers")

    def _get_bclk(self, cpu: int) -> int:
        """
        Return the bus clock speed in Hz for the specified CPU.

        Args:
            cpu: CPU number.

        Returns:
            Bus clock speed in Hz.
        """

        _, val = next(self._get_bclks_cpus((cpu,)))
        return val

    def _get_frequencies_intel(self,
                               cpus: NumsType) -> Generator[tuple[int, list[int]], None, None]:
        """
        Retrieve and yield available CPU frequencies for the specified CPUs using the 'intel_pstate'
        driver.

        Args:
            cpus: CPU numbers to retrieve frequencies for.

        Yields:
            Tuple of (cpu, freqs), where 'cpu' is the CPU number and 'freqs' is a list of available
            frequencies in Hz for that CPU.

        Raises:
            ErrorNotSupported: If the CPU frequency driver is not 'intel_pstate'.
        """

        driver_iter = self._get_prop_cpus_mnames("driver", cpus)
        min_freq_iter = self._get_prop_cpus_mnames("min_freq", cpus)
        max_freq_iter = self._get_prop_cpus_mnames("max_freq", cpus)
        bclks_iter = self._get_bclks_cpus(cpus)

        iter_zip = zip(driver_iter, min_freq_iter, max_freq_iter, bclks_iter)
        iterator = cast(Generator[tuple[tuple[int, str], tuple[int, int], tuple[int, int],
                                  tuple[int, int]], None, None], iter_zip)

        for (cpu, driver), (_, min_freq), (_, max_freq), (_, bclk) in iterator:
            if driver != "intel_pstate":
                raise ErrorNotSupported("Only 'intel_pstate' was verified to accept any frequency "
                                        "value that is multiple of bus clock")

            freqs: list[int] = []
            freq = min_freq
            while freq <= max_freq:
                freqs.append(freq)
                freq += bclk

            yield cpu, freqs

    def _get_frequencies(self, cpus: NumsType) -> Generator[tuple[int, list[int]], None, None]:
        """
        Retrieve and yield available CPU frequencies for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve frequencies for.

        Yields:
            Tuples of (cpu, freqs), where 'cpu' is the CPU number and 'freqs' is a list of available
            frequencies in Hz for that CPU.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        yielded = False

        try:
            for cpu, freq in cpufreq_obj.get_available_frequencies(cpus):
                yielded = True
                yield cpu, freq
        except ErrorNotSupported:
            if yielded:
                raise
        else:
            return

        yield from self._get_frequencies_intel(cpus)

    def _get_bus_clock(self,
                       cpus: NumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the bus clock speed for the specified CPUs using the given mechanism.

        Args:
            cpus: CPU numbers to retrieve bus clock speed for.
            mname: Name of the mechanism to use for retrieving the bus clock speed.

        Yields:
            Tuples of (cpu, bus_clock_speed), where 'cpu' is the CPU identifier and
            'bus_clock_speed' is the bus clock speed in Hz.

        Raises:
            ErrorNotSupported: If the mechanism is not supported for the CPU model or vendor.
            ErrorTryAnotherMechanism: If the 'doc' mechanism is not available and 'msr' should be
                                      used.
        """

        if mname == "msr":
            for cpu, val in self._get_fsbfreq().read_feature("fsb", cpus=cpus):
                yield cpu, int(val * 1000000)
            return

        if mname == "doc":
            try:
                self._get_fsbfreq()
            except ErrorNotSupported:
                if self._cpuinfo.info["vendor"] != "GenuineIntel":
                    raise ErrorNotSupported(f"Unsupported CPU model '{self._cpuinfo.cpudescr}"
                                            f"{self._pman.hostmsg}") from None
                for cpu in cpus:
                    # Modern Intel platforms use 100MHz bus clock.
                    yield cpu, 100000000
                return
            raise ErrorTryAnotherMechanism(f"use 'msr' method for {self._cpuinfo.cpudescr}")

        raise Error(f"BUG: Unsupported mechanism '{mname}'")

    def _read_int(self, path: Path) -> int:
        """
        Read an integer value from the specified file path.

        Args:
            path: The file system path to read the integer value from.

        Returns:
            The integer value read from the file.
        """

        val = self._pman.read_file(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"Read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_turbo(self, cpus: NumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the turbo status (on/off) for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve turbo status for.

        Yields:
            Tuples of (cpu, status), where 'cpu' is the CPU number and 'status' is its turbo status
            ("on" or "off").
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_turbo(cpus)

    def _get_driver(self, cpus: NumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the Linux CPU frequency driver name for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve driver names for.

        Yields:
            Tuples of (cpu, driver), where 'cpu' is the CPU number and 'driver' is its driver name.
            The driver name is obtained from the sysfs interface.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_driver(cpus)

    def _get_intel_pstate_mode(self, cpus: NumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the 'intel_pstate' mode name for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve 'intel_pstate' mode names for.

        Yields:
            Tuples of (cpu, mode), where 'cpu' is the CPU number and 'mode' is its 'intel_pstate'
            mode name. The mode name is obtained from the sysfs interface.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_intel_pstate_mode(cpus)

    def _get_governor(self, cpus: NumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the current CPU frequency governor for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve governor names for.

        Yields:
            Tuples of (cpu, governor), where 'cpu' is the CPU number and 'governor' is its current
            CPU frequency governor. The governor name is obtained from the sysfs interface.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_governor(cpus)

    def _get_governors(self, cpus: NumsType) -> Generator[tuple[int, list[str]], None, None]:
        """
        Retrieve and yield available CPU frequency governors for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve available governors for.

        Yields:
            Tuples of (cpu, governors), where 'cpu' is the CPU number and 'governors' is a list of
            available governor names (strings).
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_available_governors(cpus)

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: NumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, typing.Any], None, None]:
        """
        Retrieve and yield property values for the specified CPUs using the given mechanism.

        Args:
            pname: Name of the property to retrieve (e.g., "epp", "epb", "max_eff_freq").
            cpus: CPU numbers to retrieve property values for.
            mname: Name of the mechanism to use for property retrieval.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU identifier and 'value' is the property
            value for that CPU.
        """

        if pname == "epp":
            yield from self._get_epp(cpus, mname)
        elif pname == "epb":
            yield from self._get_epb(cpus, mname)
        elif pname == "max_eff_freq":
            yield from self._get_max_eff_freq(cpus)
        elif pname == "hwp":
            yield from self._get_hwp(cpus)
        elif pname == "min_oper_freq":
            yield from self._get_min_oper_freq(cpus, mname)
        elif pname == "max_turbo_freq":
            yield from self._get_max_turbo_freq(cpus, mname)
        elif pname == "base_freq":
            yield from self._get_base_freq(cpus, mname)
        elif pname in {"min_freq", "max_freq"}:
            yield from self._get_freq(pname, cpus, mname)
        elif pname in {"min_freq_limit", "max_freq_limit"}:
            yield from self._get_freq_limit(pname, cpus)
        elif self._is_uncore_prop(pname):
            yield from self._get_uncore_freq_cpus(pname, cpus)
        elif pname == "frequencies":
            yield from self._get_frequencies(cpus)
        elif pname == "bus_clock":
            yield from self._get_bus_clock(cpus, mname)
        elif pname == "turbo":
            yield from self._get_turbo(cpus)
        elif pname == "driver":
            yield from self._get_driver(cpus)
        elif pname == "intel_pstate_mode":
            yield from self._get_intel_pstate_mode(cpus)
        elif pname == "governor":
            yield from self._get_governor(cpus)
        elif pname == "governors":
            yield from self._get_governors(cpus)
        else:
            raise Error(f"BUG: Unknown property '{pname}'")

    def _get_uncore_freq_dies(self,
                              pname: str,
                              dies: DieNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield uncore frequency values for the specified dies using the sysfs mechanism.

        Args:
            pname: Name of the uncore frequency property to retrieve (e.g., "min_uncore_freq").
            dies: Dictionary mapping package numbers to collections of die numbers.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the uncore frequency or limit.
        """

        uncfreq_obj = self._get_uncfreq_sysfs_obj()

        if pname == "min_uncore_freq":
            yield from uncfreq_obj.get_min_freq_dies(dies)
            return
        if pname == "max_uncore_freq":
            yield from uncfreq_obj.get_max_freq_dies(dies)
            return
        if pname == "min_uncore_freq_limit":
            yield from uncfreq_obj.get_min_freq_limit_dies(dies)
            return
        if pname == "max_uncore_freq_limit":
            yield from uncfreq_obj.get_max_freq_limit_dies(dies)
            return

        raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _get_prop_dies(self,
                       pname: str,
                       dies: DieNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield property values for the specified dies using the given mechanism.

        Args:
            pname: Name of the property to retrieve.
            dies: Mapping of package numbers to collections of die numbers.
            mname: Name of the mechanism to use for property retrieval.

        Yields:
            Tuples of (package, die, value), where 'package' is the package number, 'die' is the
            die number, and 'value' is the property value for that die.
        """

        if not self._is_uncore_prop(pname):
            # Use the default implementation for anything but uncore frequency.
            yield from super()._get_prop_dies(pname, dies, mname)
        else:
            # In case of uncore frequency, there may be I/O dies, which have no CPUs, so implement
            # per-die access.
            yield from self._get_uncore_freq_dies(pname, dies)

    def _set_turbo(self, enable: bool, cpus: NumsType) -> MechanismNameType:
        """
        Enable or disable turbo mode for the specified CPUs.

        Args:
            enable: Whether to enable (True) or disable (False) turbo mode.
            cpus: CPU numbers to set turbo mode for.

        Returns:
            Name of the mechanism used to set turbo mode (e.g., "sysfs").
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_turbo(enable, cpus=cpus)
        return "sysfs"

    def _set_intel_pstate_mode(self, mode: str, cpus: NumsType) -> MechanismNameType:
        """
        Set the 'intel_pstate' driver mode for the specified CPUs.

        Args:
            mode: Name of the mode to set (e.g., "powersave", "performance").
            cpus: CPU numbers to set the mode for.

        Returns:
            The name of the mechanism used to set the mode (e.g., 'sysfs').
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_intel_pstate_mode(mode, cpus=cpus)
        return "sysfs"

    def _set_governor(self, governor: str, cpus: NumsType) -> MechanismNameType:
        """
        Set the CPU frequency governor for the specified CPUs.

        Args:
            governor: Name of the governor to set (e.g., "performance", "powersave").
            cpus: CPUs to apply the governor setting to.

        Returns:
            The name of the mechanism used to set the governor (e.g., "sysfs").
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_governor(governor, cpus=cpus)
        return "sysfs"

    def _set_freq_prop_cpus_msr(self, pname: str, freq: int, cpus: NumsType):
        """
        Set the 'min_freq' or 'max_freq' CPU frequency property to the specified value for the given
        CPUs.

        Args:
            pname: Name of the property to set ('min_freq' or 'max_freq').
            freq: Frequency value to set, in Hz.
            cpus: CPU numbers to apply the frequency setting to.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            cpufreq_obj.set_min_freq(freq, cpus)
        elif pname == "max_freq":
            cpufreq_obj.set_max_freq(freq, cpus)
        else:
            raise Error(f"BUG: Unexpected CPU frequency property {pname}")

    def _handle_write_and_read_freq_mismatch(self, err: ErrorVerifyFailed) -> NoReturn:
        """
        Handle mismatches between written and read CPU frequency values in sysfs.

        Args:
            err: The exception object containing the error details.

        Raises:
            ErrorVerifyFailed: always raised to indicate the mismatch, includes a detailed message.
        """

        if err.expected is None:
            raise Error("BUG: Frequency is not set in the 'ErrorVerifyFailed' object")
        freq = cast(int, err.expected)

        if err.actual is None:
            raise Error("BUG: Read frequency is not set in the 'ErrorVerifyFailed' object")
        read_freq = cast(int, err.actual)

        if err.cpu is None:
            raise Error("BUG: CPU number is not set in the 'ErrorVerifyFailed' object")
        cpu = err.cpu

        msg = str(err)

        with contextlib.suppress(Error):
            frequencies = cast(list[int], self._get_cpu_prop_mnames("frequencies", cpu))
            frequencies_set = set(frequencies)
            if freq not in frequencies_set and read_freq in frequencies_set:
                fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                freq_human = Human.num2si(freq, unit="Hz", decp=4)
                msg += f".\n  Linux kernel CPU frequency driver does not support " \
                       f"{freq_human}, use one of the following values instead:\n  {fvals}"

        with contextlib.suppress(Error):
            if self._get_cpu_prop_mnames("turbo", cpu) == "off":
                base_freq = cast(int, self._get_cpu_prop_mnames("base_freq", cpu))
                if base_freq and freq > base_freq:
                    base_freq_str = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f".\n  Hint: turbo is disabled, base frequency is {base_freq_str}, " \
                           f"and this may be the limiting factor."

        err.msg = msg
        raise err

    def _set_freq_prop_cpus_sysfs(self, pname: str, freq: int, cpus: NumsType):
        """
        Set the minimum or maximum CPU frequency property for the specified CPUs.

        Args:
            pname: Name of the property to set ('min_freq' or 'max_freq').
            freq: Frequency value to set, in Hz.
            cpus: CPU numbers to apply the frequency setting to.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        try:
            if pname == "min_freq":
                cpufreq_obj.set_min_freq(freq, cpus)
            elif pname == "max_freq":
                cpufreq_obj.set_max_freq(freq, cpus)
            else:
                raise Error(f"BUG: Unexpected CPU frequency property {pname}")
        except ErrorVerifyFailed as err:
            self._handle_write_and_read_freq_mismatch(err)

    def _raise_freq_out_of_range(self,
                                 pname: str,
                                 val: int,
                                 min_limit: int,
                                 max_limit: int,
                                 what: str) -> NoReturn:
        """
        Raise an 'ErrorFreqRange' exception if the provided frequency value is out of the allowed
        range.

        Args:
            pname: The property name whose frequency is out of range.
            val: The out of range frequency value.
            min_limit: The minimum allowed frequency.
            max_limit: The maximum allowed frequency.
            what: A description of what the frequency value refers to (e.g., CPU or uncore).

        Raises:
            ErrorFreqRange: If the frequency value is outside the specified range.
        """

        name = Human.uncapitalize(self._props[pname]["name"])
        val_str = Human.num2si(val, unit="Hz", decp=4)
        min_limit_str = Human.num2si(min_limit, unit="Hz", decp=4)
        max_limit_str = Human.num2si(max_limit, unit="Hz", decp=4)
        raise ErrorFreqRange(f"{name} value of '{val_str}' for {what} is out of range"
                             f"{self._pman.hostmsg}, must be within [{min_limit_str}, "
                             f"{max_limit_str}]")

    def _raise_wrong_freq_order(self,
                                pname: str,
                                new_freq: int,
                                cur_freq: int,
                                is_min: bool,
                                what: str) -> NoReturn:
        """
        Raise an 'ErrorFreqOrder' exception when attempting to set a CPU or uncore frequency that
        violates ordering constraints.

        Args:
            pname: Property name for the frequency being set.
            new_freq: The new frequency value being requested.
            cur_freq: The current frequency value configured.
            is_min: If True, indicates the minimum frequency is being set; otherwise, the maximum.
            what: Description of the target (e.g., CPU or uncore) for which the frequency is being
                  set.

        Raises:
            ErrorFreqOrder: always raised, indicating that the new frequency violates ordering
                            constraints.
        """

        name = Human.uncapitalize(self._props[pname]["name"])
        new_freq_str = Human.num2si(new_freq, unit="Hz", decp=4)
        cur_freq_str = Human.num2si(cur_freq, unit="Hz", decp=4)
        if is_min:
            msg = f"larger than currently configured max. frequency of {cur_freq_str}"
        else:
            msg = f"lower than currently configured min. frequency of {cur_freq_str}"
        raise ErrorFreqOrder(f"Can't set {name} of {what} to {new_freq_str} - it is {msg}")

    def _get_numeric_cpu_freq(self,
                              freq: str | int,
                              cpus: NumsType) -> Generator[tuple[int, int], None, None]:
        """
        Convert the user-provided frequency value to a numeric frequency in Hz. If the user-provided
        value is a special string (e.g., "max", "min", "base"), resolve it to the corresponding
        numeric frequency.

        Args:
            freq: Frequency value or special string (e.g., "max", "min", "base").
            cpus: CPU numbers to resolve the frequency for.

        Yields:
            Tuple (cpu, val), where 'cpu' is the CPU number and 'val' is the resolved frequency in
            Hz.
        """

        if freq == "min":
            yield from cast(Generator[tuple[int, int], None, None],
                            self._get_prop_cpus_mnames("min_freq_limit", cpus))
        elif freq == "max":
            yield from cast(Generator[tuple[int, int], None, None],
                            self._get_prop_cpus_mnames("max_freq_limit", cpus))
        elif freq in {"base", "hfm", "P1"}:
            yield from cast(Generator[tuple[int, int], None, None],
                            self._get_prop_cpus_mnames("base_freq", cpus))
        elif freq in {"eff", "lfm", "Pn"}:
            idx = 0
            try:
                iterator = enumerate(cast(Generator[tuple[int, int], None, None],
                                          self._get_prop_cpus_mnames("max_eff_freq", cpus)))
                for idx, (cpu, max_eff_freq) in iterator:
                    yield cpu, max_eff_freq
            except ErrorNotSupported:
                if idx != 0:
                    # Already yielded something, consider this to be an error.
                    raise
                # Max. efficiency frequency may not be supported by the platform. Fall back to the
                # minimum frequency in this case.
                yield from cast(Generator[tuple[int, int], None, None],
                                self._get_prop_cpus_mnames("min_freq_limit", cpus))
        elif freq == "Pm":
            yield from cast(Generator[tuple[int, int], None, None],
                            self._get_prop_cpus_mnames("min_oper_freq", cpus))
        else:
            for cpu in cpus:
                yield cpu, cast(int, freq)

    def _set_cpu_freq(self,
                      pname: str,
                      val: str | int,
                      cpus: NumsType,
                      mname: MechanismNameType):
        """
        Set a CPU frequency property for specified CPUs using the given mechanism.

        Args:
            pname: Name of the frequency property to set (e.g., "min_freq" or "max_freq").
            val: The target frequency value to set. Can be a numeric value or a special string
                 (e.g., "max", "min", "base").
            cpus: CPU numbers to apply the frequency setting to.
            mname: Mechanism to use for setting the frequency (e.g., "sysfs" or "msr").
        """

        is_min = "min" in pname
        if mname == "sysfs":
            set_freq_method = self._set_freq_prop_cpus_sysfs
        elif mname == "msr":
            set_freq_method = self._set_freq_prop_cpus_msr
        else:
            raise Error(f"BUG: Unsupported mechanism '{mname}'")

        new_freq_iter = self._get_numeric_cpu_freq(val, cpus)
        min_limit_iter = self._get_prop_cpus_mnames("min_freq_limit", cpus, mnames=(mname,))
        max_limit_iter = self._get_prop_cpus_mnames("max_freq_limit", cpus, mnames=(mname,))
        cur_freq_limit_pname = "max_freq" if is_min else "min_freq"
        cur_freq_limit_iter = self._get_prop_cpus_mnames(cur_freq_limit_pname, cpus,
                                                         mnames=(mname,))

        iter_zip = zip(new_freq_iter, min_limit_iter, max_limit_iter, cur_freq_limit_iter)
        iterator = cast(Generator[tuple[tuple[int, int], tuple[int, int], tuple[int, int],
                                        tuple[int, int]], None, None], iter_zip)

        freq2cpus: dict[int, list[int]] = {}

        for (cpu, new_freq), (_, min_limit), (_, max_limit), (_, cur_freq_limit) in iterator:
            if new_freq < min_limit or new_freq > max_limit:
                what = f"CPU {cpu}"
                self._raise_freq_out_of_range(pname, new_freq, min_limit, max_limit, what=what)

            if is_min:
                if new_freq > cur_freq_limit:
                    # New min. frequency cannot be set to a value larger than current max.
                    # frequency.
                    what = f"CPU {cpu}"
                    self._raise_wrong_freq_order(pname, new_freq, cur_freq_limit, is_min, what=what)
            elif new_freq < cur_freq_limit:
                # New max. frequency cannot be set to a value smaller than current min. frequency.
                what = f"CPU {cpu}"
                self._raise_wrong_freq_order(pname, new_freq, cur_freq_limit, is_min, what=what)

            if new_freq not in freq2cpus:
                freq2cpus[new_freq] = []
            freq2cpus[new_freq].append(cpu)

        for new_freq, freq_cpus in freq2cpus.items():
            set_freq_method(pname, new_freq, freq_cpus)

    def _handle_epp_set_exception(self,
                                  val: str,
                                  mname: MechanismNameType,
                                  err: Error) -> str | None:
        """
        Handle a situation where setting the Energy Performance Preference (EPP) fails. The goal is
        to improve the error message to help the user understand the reason for the failure.

        Args:
            val: The attempted EPP value.
            mname: The method or interface name used for setting EPP.
            err: The exception object raised during the EPP set attempt.

        Returns:
            A string with a detailed error message, None if the error message was not improved.
        """

        # Newer Linux kernels with intel_pstate driver in active mode forbid changing EPP to
        # anything but 0 or "performance". Provide a helpful error message for this special case.

        if mname != "sysfs":
            return None
        if val in ("0", "performance"):
            return None
        if not hasattr(err, "cpu"):
            return None

        cpus = [err.cpu]
        _, driver = next(self._get_prop_cpus_mnames("driver", cpus))
        if driver != "intel_pstate":
            return None
        _, mode = next(self._get_prop_cpus_mnames("intel_pstate_mode", cpus))
        if mode != "active":
            return None
        _, governor = next(self._get_prop_cpus_mnames("governor", cpus))
        if governor != "performance":
            return None

        return f"{err}\nThe 'performance' governor of the 'intel_pstate' driver sets EPP to 0 " \
               f"(performance) and does not allow for changing it."

    def _set_prop_cpus(self,
                       pname: str,
                       val: typing.Any,
                       cpus: "NumsType",
                       mname: "MechanismNameType") -> MechanismNameType:
        """
        Set the specified property to a given value for for specified CPUs using a specified
        mechanism.

        Args:
            pname: Name of the property to set (e.g., 'epp', 'epb', 'turbo', etc.).
            val: The value to assign to the property.
            cpus: CPU numbers to apply the property setting to.
            mname: Name of the mechanism to use for setting the property.

        Returns:
            The name of the mechanism used to set the property (e.g., 'sysfs', 'msr', etc.).
        """

        if pname == "epp":
            try:
                return self._get_eppobj().set_vals(val, cpus=cpus, mnames=(mname,))
            except Error as err:
                msg = self._handle_epp_set_exception(val, mname, err)
                if msg is None:
                    raise
                raise type(err)(msg) from err

        if pname == "epb":
            return self._get_epbobj().set_vals(val, cpus=cpus, mnames=(mname,))
        if pname == "turbo":
            return self._set_turbo(val, cpus)
        if pname == "intel_pstate_mode":
            return self._set_intel_pstate_mode(val, cpus)
        if pname == "governor":
            return self._set_governor(val, cpus)
        if pname in ("min_freq", "max_freq"):
            return self._set_cpu_freq(pname, val, cpus, mname)

        raise Error("BUG: Unsupported property '{pname}'")

    def _set_uncore_freq_prop_dies(self, pname: str, freq: int, dies: DieNumsType):
        """
        Set the minimum or maximum uncore frequency for specified dies.

        Args:
            pname: The property name, either "min_uncore_freq" or "max_uncore_freq".
            freq: The frequency value to set.
            dies: Dictionary mapping package numbers to collections of die numbers.
        """

        uncfreq_obj = self._get_uncfreq_sysfs_obj()

        if pname == "min_uncore_freq":
            uncfreq_obj.set_min_freq_dies(freq, dies)
        elif pname == "max_uncore_freq":
            uncfreq_obj.set_max_freq_dies(freq, dies)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _get_numeric_uncore_freq(self,
                                 freq: str | int,
                                 dies: DieNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Convert a user-provided uncore frequency value to its numeric representation in Hz for each
        die.

        Args:
            freq: The frequency value to convert. Can be a numeric value or a special string
                  ("min", "max", "mdl").
            dies: A dictionary mapping package numbers to collections of die numbers.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the resolved frequency in Hz.
        """

        if freq == "min":
            yield from cast(Generator[tuple[int, int, int], None, None],
                            self._get_prop_dies_mnames("min_uncore_freq_limit", dies))
        elif freq == "max":
            yield from cast(Generator[tuple[int, int, int], None, None],
                            self._get_prop_dies_mnames("max_uncore_freq_limit", dies))
        elif freq == "mdl":
            bclks_iter = self._get_bclks_dies(dies)
            min_limit_iter = self._get_prop_dies_mnames("min_uncore_freq_limit", dies)
            max_limit_iter = self._get_prop_dies_mnames("max_uncore_freq_limit", dies)
            iter_zip = zip(bclks_iter, min_limit_iter, max_limit_iter)
            iterator = cast(Generator[tuple[tuple[int, int, int], tuple[int, int, int],
                                            tuple[int, int, int]], None, None], iter_zip)
            for (package, die, bclk), (_, _, min_limit), (_, _, max_limit) in iterator:
                yield package, die, bclk * round(statistics.mean([min_limit, max_limit]) / bclk)
        elif isinstance(freq, int):
            for package, pkg_dies in dies.items():
                for die in pkg_dies:
                    yield package, die, freq
        else:
            raise Error(f"BUG: Unexpected non-integer uncore frequency value '{freq}'")

    def _set_uncore_freq(self,
                         pname: str,
                         val: str | int,
                         dies: DieNumsType,
                         mname: MechanismNameType) -> MechanismNameType:
        """
        Set the uncore frequency property for specified dies using a given method.

        Args:
            pname: Name of the uncore frequency property to set (e.g., 'min_uncore_freq',
                   'max_uncore_freq').
            val: The value to set for the property. Can be a numeric value or a special string
                 (e.g., 'min', 'max', 'mdl').
            dies: Mapping of package numbers to collections of die numbers.
            mname: Name of the method to use for setting the property.

        Returns:
            The name of the mechanism used to set the property (e.g., 'sysfs').
        """

        is_min = "min" in pname

        new_freq_iter = self._get_numeric_uncore_freq(val, dies)
        min_limit_iter = self._get_prop_dies_mnames("min_uncore_freq_limit", dies, mnames=(mname,))
        max_limit_iter = self._get_prop_dies_mnames("max_uncore_freq_limit", dies, mnames=(mname,))
        cur_freq_limit_pname = "max_uncore_freq" if is_min else "min_uncore_freq"
        cur_freq_limit_iter = self._get_prop_dies_mnames(cur_freq_limit_pname, dies,
                                                         mnames=(mname,))

        iter_zip = zip(new_freq_iter, min_limit_iter, max_limit_iter, cur_freq_limit_iter)
        iterator = cast(Generator[tuple[tuple[int, int, int], tuple[int, int, int],
                                        tuple[int, int, int], tuple[int, int, int]], None, None],
                        iter_zip)

        freq2dies: dict[int, dict[int, list[int]]] = {}
        for (package, die, new_freq), (_, _, min_limit), (_, _, max_limit), (_, _, cur_freq_limit) \
            in iterator:
            if new_freq < min_limit or new_freq > max_limit:
                what = f"package {package} die {die}"
                self._raise_freq_out_of_range(pname, new_freq, min_limit, max_limit, what=what)

            if is_min:
                if new_freq > cur_freq_limit:
                    # New min. frequency cannot be set to a value larger than current max.
                    # frequency.
                    what = f"package {package} die {die}"
                    self._raise_wrong_freq_order(pname, new_freq, cur_freq_limit, is_min, what=what)
            elif new_freq < cur_freq_limit:
                #  New max. frequency cannot be set to a value smaller than current min. frequency.
                what = f"package {package} die {die}"
                self._raise_wrong_freq_order(pname, new_freq, cur_freq_limit, is_min, what=what)

            if new_freq not in freq2dies:
                freq2dies[new_freq] = {}
            if package not in freq2dies[new_freq]:
                freq2dies[new_freq][package] = []
            freq2dies[new_freq][package].append(die)

        for new_freq, freq_dies in freq2dies.items():
            self._set_uncore_freq_prop_dies(pname, new_freq, freq_dies)

        return "sysfs"

    def _set_prop_dies(self,
                       pname: str,
                       val: typing.Any,
                       dies: DieNumsType,
                       mname: MechanismNameType) -> MechanismNameType:
        """
        Set the specified property to a given value for the provided dies using the specified
        mechanism.

        Args:
            pname: Name of the property to set.
            val: Value to assign to the property.
            dies: Mapping of package numbers to collections of die numbers.
            mname: Name of the mechanism to use for setting the property.

        Returns:
            Name of the mechanism used to set the property (e.g., 'sysfs', 'msr').
        """

        if pname not in ("min_uncore_freq", "max_uncore_freq"):
            return super()._set_prop_dies(pname, val, dies, mname)

        return self._set_uncore_freq(pname, val, dies, mname)

    def _set_sname(self, pname: str):
        """
        Set the scope name ('sname') for the specified property.

        Args:
            pname: The name of the property for which to set the scope name.
        """

        prop = self._props[pname]
        if prop["sname"]:
            return

        if pname == "epb":
            epbobj = self._get_epbobj() # pylint: disable=protected-access
            prop["sname"] = epbobj.sname
        elif pname == "bus_clock":
            try:
                fsbfreq = self._get_fsbfreq()
                prop["sname"] = fsbfreq.features["fsb"]["sname"]
            except ErrorNotSupported:
                prop["sname"] = "global"

        prop["iosname"] = prop["sname"]
        self.props[pname]["sname"] = prop["sname"]
