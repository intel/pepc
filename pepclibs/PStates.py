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

from typing import Generator
import contextlib
import statistics

from pepclibs import _PropsClassBase
from pepclibs.helperlibs import Trivial, Human, ClassHelpers

from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed
from pepclibs._PropsClassBase import ErrorTryAnotherMechanism

from pepclibs.msr import MSR, FSBFreq
from pepclibs import _SysfsIO, EPP, EPB, _CPUFreq, _UncoreFreq
from pepclibs.CPUInfo import CPUInfo

from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs._PropsClassBase import PropertyTypedDict, NumsType, MechanismNameType

# Make the exception class be available for users.
from pepclibs._PropsClassBase import ErrorUsePerCPU # pylint: disable=unused-import

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
        "mnames": ("sysfs", "doc"),
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

    def _get_epb(self, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is EPB value for CPU 'cpu'.
        """

        for cpu, val, _ in self._get_epbobj().get_vals(cpus=cpus, mnames=(mname,)):
            yield cpu, val

    def _get_max_eff_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the maximum efficiency
        frequency in Hz for CPU 'cpu'.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()
        yield from cpufreq_obj.get_max_eff_freq(cpus=cpus)

    def _get_hwp(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the hardware power
        management on/off status for CPU 'cpu'.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()
        yield from cpufreq_obj.get_hwp(cpus=cpus)

    def _get_cppc_freq(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the value of property
        'pname' for CPU 'cpu', read from an ACPI CPPC sysfs file.
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
                raise Error(f"BUG: unexpected property {pname}")
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

    def _get_min_oper_freq(self, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is  the minimum operating
        frequency for CPU 'cpu'. Use method 'mname'.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_min_oper_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("min_oper_freq", cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_max_turbo_freq(self, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is  the maximum 1-core
        turbo frequency for CPU 'cpu'. Use method 'mname'.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_max_turbo_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("max_turbo_freq", cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_base_freq(self, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is base frequency of CPU
        'cpu'. Use method 'mname'.
        """

        if mname == "sysfs":
            cpufreq_obj = self._get_cpufreq_sysfs_obj()
            yield from cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("base_freq", cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_freq_sysfs(self, pname, cpus):
        """YIeld the minimum or maximum CPU frequency read from Linux "cpufreq" sysfs files."""

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

    def _get_freq_msr(self, pname, cpus):
        """Yield the minimum or maximum CPU frequency read from 'MSR_HWP_REQUEST'."""

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        else:
            raise Error(f"BUG: unexpected CPU frequency property {pname}")

    def _get_freq(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the frequency of CPU
        'cpu'. Use method 'mname'.
        """

        if mname == "sysfs":
            yield from self._get_freq_sysfs(pname, cpus)
            return

        if mname == "msr":
            yield from self._get_freq_msr(pname, cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_freq_limit(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the frequency limit for
        CPU 'cpu'. Use the 'sysfs' method.
        """

        yield from self._get_freq_sysfs(pname, cpus)

    def _get_uncore_freq_cpus(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is uncore frequency or
        uncore frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. Use
        the "sysfs" method.
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

        raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _get_bclks_cpus(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the bus clock speed for
        CPU 'cpu' in Hz.
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

    def _get_bclks_dies(self, dies):
        """
        For every die in 'dies', yield a '(package, die, val)' tuple, where 'val' is the bus clock
        speed in Hz for die 'die' in package 'package'.
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
            raise Error("BUG: not implemented, contact project maintainers")

    def _get_bclk(self, cpu):
        """Return bus clock speed in Hz."""

        _, val = next(self._get_bclks_cpus((cpu,)))
        return val

    def _get_frequencies_intel(self, cpus):
        """
        For every CPU in 'cpus', yield the list of CPU frequencies for CPU 'cpu' on an Intel
        platform.
        """

        driver_iter = self._get_prop_cpus_mnames("driver", cpus)
        min_freq_iter = self._get_prop_cpus_mnames("min_freq", cpus)
        max_freq_iter = self._get_prop_cpus_mnames("max_freq", cpus)
        bclks_iter = self._get_bclks_cpus(cpus)
        iterator = zip(driver_iter, min_freq_iter, max_freq_iter, bclks_iter)

        for (cpu, driver), (_, min_freq), (_, max_freq), (_, bclk) in iterator:
            if driver != "intel_pstate":
                raise ErrorNotSupported("only 'intel_pstate' was verified to accept any frequency "
                                        "value that is multiple of bus clock")

            freqs = []
            freq = min_freq
            while freq <= max_freq:
                freqs.append(freq)
                freq += bclk

            yield cpu, freqs

    def _get_frequencies(self, cpus, mname):
        """
        For every CPU in 'cpus', yield the list of CPU frequencies available for CPU 'cpu'. Use
        method 'mname'.
        """

        if mname == "sysfs":
            cpufreq_obj = self._get_cpufreq_sysfs_obj()
            yield from cpufreq_obj.get_available_frequencies(cpus)
            return

        if mname == "doc":
            yield from self._get_frequencies_intel(cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_bus_clock(self, cpus, mname):
        """
        For every CPU in 'cpus', yield the the bus clock speed for CPU 'cpu'. Use method 'mname'.
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
                    raise ErrorNotSupported(f"unsupported CPU model '{self._cpuinfo.cpudescr}"
                                            f"{self._pman.hostmsg}") from None
                for cpu in cpus:
                    # Modern Intel platforms use 100MHz bus clock.
                    yield cpu, 100000000
                return
            raise ErrorTryAnotherMechanism(f"use 'msr' method for {self._cpuinfo.cpudescr}")

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _read_int(self, path):
        """Read an integer from file 'path' via the process manager."""

        val = self._pman.read(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_turbo(self, cpus):
        """
        For every CPU in 'cpus', yield the turbo on/off status for CPU 'cpu'. Use method 'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_turbo(cpus)

    def _get_driver(self, cpus):
        """
        For every CPU in 'cpus', yield the Linux CPU frequency driver name. Use method 'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_driver(cpus)

    def _get_intel_pstate_mode(self, cpus):
        """
        For every CPU in 'cpus', yield the 'intel_pstate' mode name. Use method 'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_intel_pstate_mode(cpus)

    def _get_governor(self, cpus):
        """
        For every CPU in 'cpus', yield the Linux CPU frequency governor name. Use method 'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_governor(cpus)

    def _get_governors(self, cpus):
        """
        For every CPU in 'cpus', yield the list of available Linux CPU frequency governors. Use
        method 'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_available_governors(cpus)

    def _get_prop_cpus(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, 'val' is property 'pname' value for CPU
        'cpu'. Use mechanism 'mname'.
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
            yield from self._get_frequencies(cpus, mname)
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
            raise Error(f"BUG: unknown property '{pname}'")

    def _get_uncore_freq_dies(self, pname, dies):
        """
        For every die in 'dies', yield a '(package, die, val)' tuple, where 'val' is uncore
        frequency or uncore frequency limit for die 'die' in package 'package'. Use the "sysfs"
        method.
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

    def _get_prop_dies(self, pname, dies, mname):
        """
        For every die in 'dies', yield a '(package, die, val)' tuple, where 'val' is property
        'pname' value for die 'die' of package 'package'.
        """

        if not self._is_uncore_prop(pname):
            # Use the default implementation for anything but uncore frequency.
            yield from super()._get_prop_dies(pname, dies, mname)
        else:
            # In case of uncore frequency, there may be I/O dies, which have no CPUs, so implement
            # per-die access.
            yield from self._get_uncore_freq_dies(pname, dies)

    def _set_turbo(self, enable, cpus):
        """Enable or disable turbo for CPUs in 'cpus'. Use method 'sysfs'."""

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_turbo(enable, cpus=cpus)
        return "sysfs"

    def _set_intel_pstate_mode(self, mode, cpus):
        """Set 'intel_pstate' driver mode to 'mode' for CPUs in 'cpus'. Use method 'sysfs'."""

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_intel_pstate_mode(mode, cpus=cpus)
        return "sysfs"

    def _set_governor(self, governor, cpus):
        """
        Set 'intel_pstate' Linux CPU frequency governor to 'governor' for CPUs in 'cpus'. Use method
        'sysfs'.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_governor(governor, cpus=cpus)
        return "sysfs"

    def _set_freq_prop_cpus_msr(self, pname, freq, cpus):
        """
        Set 'intel_pstate' Linux CPU frequency governor to 'governor' for CPUs in 'cpus'. Use method
        'msr'.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            cpufreq_obj.set_min_freq(freq, cpus)
        elif pname == "max_freq":
            cpufreq_obj.set_max_freq(freq, cpus)
        else:
            raise Error(f"BUG: unexpected CPU frequency property {pname}")

    def _handle_write_and_read_freq_mismatch(self, err):
        """
        This is a helper function fo '_write_cpu_freq_prop_sysfs()' and it is called when there
        is a mismatch between what was written to a CPU frequency sysfs file and what was read back.
        """

        freq = err.expected
        read_freq = err.actual
        cpu = err.cpu
        msg = str(err)

        with contextlib.suppress(Error):
            frequencies = self._get_cpu_prop_mnames("frequencies", cpu)
            frequencies_set = set(frequencies)
            if freq not in frequencies_set and read_freq in frequencies_set:
                fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                freq_human = Human.num2si(freq, unit="Hz", decp=4)
                msg += f".\n  Linux kernel CPU frequency driver does not support " \
                       f"{freq_human}, use one of the following values instead:\n  {fvals}"

        with contextlib.suppress(Error):
            if self._get_cpu_prop_mnames("turbo", cpu) == "off":
                base_freq = self._get_cpu_prop_mnames("base_freq", cpu)
                if base_freq and freq > base_freq:
                    base_freq = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f".\n  Hint: turbo is disabled, base frequency is {base_freq}, and " \
                           f"this may be the limiting factor."

        raise ErrorVerifyFailed(msg) from err

    def _set_freq_prop_cpus_sysfs(self, pname, freq, cpus):
        """Set min. or max. CPU frequency to 'freq' for CPUs in 'cpus', use mechanism 'sysfs'."""

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        try:
            if pname == "min_freq":
                cpufreq_obj.set_min_freq(freq, cpus)
            elif pname == "max_freq":
                cpufreq_obj.set_max_freq(freq, cpus)
            else:
                raise Error(f"BUG: unexpected CPU frequency property {pname}")
        except ErrorVerifyFailed as err:
            self._handle_write_and_read_freq_mismatch(err)

    def _raise_freq_out_of_range(self, pname, val, min_limit, max_limit, what):
        """Raise an exception if CPU or uncore frequency is out of range."""

        name = Human.uncapitalize(self._props[pname]["name"])
        val = Human.num2si(val, unit="Hz", decp=4)
        min_limit = Human.num2si(min_limit, unit="Hz", decp=4)
        max_limit = Human.num2si(max_limit, unit="Hz", decp=4)
        raise ErrorFreqRange(f"{name} value of '{val}' for {what} is out of range"
                             f"{self._pman.hostmsg}, must be within [{min_limit}, {max_limit}]")

    def _raise_wrong_freq_order(self, pname, new_freq, cur_freq, is_min, what):
        """
        Raise and exception in case of failure to set CPU or uncore frequency due to ordering
        constraints.
        """

        name = Human.uncapitalize(self._props[pname]["name"])
        new_freq = Human.num2si(new_freq, unit="Hz", decp=4)
        cur_freq = Human.num2si(cur_freq, unit="Hz", decp=4)
        if is_min:
            msg = f"larger than currently configured max. frequency of {cur_freq}"
        else:
            msg = f"lower than currently configured min. frequency of {cur_freq}"
        raise ErrorFreqOrder(f"can't set {name} of {what} to {new_freq} - it is {msg}")

    def _get_numeric_cpu_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is a numeric version of the
        user-provided frequency value 'freq' in Hz. E.g., if 'val' is "max", yield the maximum
        supported CPU frequency.
        """

        if freq == "min":
            yield from self._get_prop_cpus_mnames("min_freq_limit", cpus)
        elif freq == "max":
            yield from self._get_prop_cpus_mnames("max_freq_limit", cpus)
        elif freq in {"base", "hfm", "P1"}:
            yield from self._get_prop_cpus_mnames("base_freq", cpus)
        elif freq in {"eff", "lfm", "Pn"}:
            idx = 0
            try:
                iterator = enumerate(self._get_prop_cpus_mnames("max_eff_freq", cpus))
                for idx, (cpu, max_eff_freq) in iterator:
                    yield cpu, max_eff_freq
            except ErrorNotSupported:
                if idx != 0:
                    # Already yielded something, consider this to be an error.
                    raise
                # Max. efficiency frequency may not be supported by the platform. Fall back to the
                # minimum frequency in this case.
                yield from self._get_prop_cpus_mnames("min_freq_limit", cpus)
        elif freq == "Pm":
            yield from self._get_prop_cpus_mnames("min_oper_freq", cpus)
        else:
            for cpu in cpus:
                yield cpu, freq

    def _set_cpu_freq(self, pname, val, cpus, mname):
        """
        Set CPU frequency property 'pname' to value 'val' for CPUs in 'cpus' using method 'mname'.
        """

        is_min = "min" in pname
        if mname == "sysfs":
            set_freq_method = self._set_freq_prop_cpus_sysfs
        elif mname == "msr":
            set_freq_method = self._set_freq_prop_cpus_msr

        new_freq_iter = self._get_numeric_cpu_freq(val, cpus)
        min_limit_iter = self._get_prop_cpus_mnames("min_freq_limit", cpus, mnames=(mname,))
        max_limit_iter = self._get_prop_cpus_mnames("max_freq_limit", cpus, mnames=(mname,))
        cur_freq_limit_pname = "max_freq" if is_min else "min_freq"
        cur_freq_limit = self._get_prop_cpus_mnames(cur_freq_limit_pname, cpus, mnames=(mname,))

        iterator = zip(new_freq_iter, min_limit_iter, max_limit_iter, cur_freq_limit)

        freq2cpus = {}
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

    def _handle_epp_set_exception(self, val, mname, err):
        """Check for the conditions when EPP cannot be changed."""

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

    def _set_prop_cpus(self, pname, val, cpus, mname):
        """Set property 'pname' to value 'val' for CPUs in 'cpus'. Use mechanism 'mname'."""

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

        raise Error("BUG: unsupported property '{pname}'")

    def _set_uncore_freq_prop_dies(self, pname, freq, dies):
        """Set min. or max. uncore frequency to 'freq' for the dies in 'dies'."""

        uncfreq_obj = self._get_uncfreq_sysfs_obj()

        if pname == "min_uncore_freq":
            uncfreq_obj.set_min_freq_dies(freq, dies)
        elif pname == "max_uncore_freq":
            uncfreq_obj.set_max_freq_dies(freq, dies)
        else:
            raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _get_numeric_uncore_freq(self, freq, dies):
        """
        For every die in 'dies', yield a '(package, die, val)' tuple, where 'val' is a numeric
        version of the user-provided frequency value 'freq' in Hz. E.g., if 'val' is "max", yield
        the maximum supported CPU frequency.
        """

        if freq == "min":
            yield from self._get_prop_dies_mnames("min_uncore_freq_limit", dies)
        elif freq == "max":
            yield from self._get_prop_dies_mnames("max_uncore_freq_limit", dies)
        elif freq == "mdl":
            bclks_iter = self._get_bclks_dies(dies)
            min_limit_iter = self._get_prop_dies_mnames("min_uncore_freq_limit", dies)
            max_limit_iter = self._get_prop_dies_mnames("max_uncore_freq_limit", dies)
            iterator = zip(bclks_iter, min_limit_iter, max_limit_iter)
            for (package, die, bclk), (_, _, min_limit), (_, _, max_limit) in iterator:
                yield package, die, bclk * round(statistics.mean([min_limit, max_limit]) / bclk)
        else:
            for package, pkg_dies in dies.items():
                for die in pkg_dies:
                    yield package, die, freq

    def _set_uncore_freq(self, pname, val, dies, mname):
        """
        Set uncore frequency property 'pname' to value 'val' for dies in 'dies' using method
        'mname'.
        """

        is_min = "min" in pname

        new_freq_iter = self._get_numeric_uncore_freq(val, dies)
        min_limit_iter = self._get_prop_dies_mnames("min_uncore_freq_limit", dies, mnames=(mname,))
        max_limit_iter = self._get_prop_dies_mnames("max_uncore_freq_limit", dies, mnames=(mname,))
        cur_freq_limit_pname = "max_uncore_freq" if is_min else "min_uncore_freq"
        cur_freq_limit = self._get_prop_dies_mnames(cur_freq_limit_pname, dies, mnames=(mname,))

        iterator = zip(new_freq_iter, min_limit_iter, max_limit_iter, cur_freq_limit)

        freq2dies = {}
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

    def _set_prop_dies(self, pname, val, dies, mname):
        """Set property 'pname' to value 'val' for dies in 'dies'. Use mechanism 'mname'."""

        if pname not in ("min_uncore_freq", "max_uncore_freq"):
            return super()._set_prop_dies(pname, val, dies, mname)

        return self._set_uncore_freq(pname, val, dies, mname)

    def _set_sname(self, pname):
        """Set scope name for property 'pname'."""

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
