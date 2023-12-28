# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides P-state management API.
"""

import logging
import contextlib
import statistics
from pathlib import Path
from pepclibs import _PCStatesBase, _PropsCache
from pepclibs.helperlibs import Trivial, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

from pepclibs._PropsClassBase import ErrorTryAnotherMechanism
# Make the exception class be available for users.
from pepclibs._PropsClassBase import ErrorUsePerCPU # pylint: disable=unused-import

class ErrorFreqOrder(Error):
    """
    An exception indicating that min. or max. frequency modification failed for the ordering
    reasons.
    """

class ErrorFreqRange(ErrorTryAnotherMechanism):
    """
    An exception indicating that min. or max. frequency values are out of the allowed range. Since
    different mechanisms may have different ranges, sub-class '_ErrorTryAnotherMechanism' to
    indicate that another mechanism may succeed.
    """

_LOG = logging.getLogger()

# Special values for writable CPU frequency properties.
_SPECIAL_FREQ_VALS = {"min", "max", "base", "hfm", "P1", "eff", "lfm", "Pn", "Pm"}
# Special values for writable uncore frequency properties.
_SPECIAL_UNCORE_FREQ_VALS = {"min", "max", "mdl"}

# This dictionary describes the CPU properties this module supports.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'PStates' objects. Use the full dictionary via
# 'PStates.props'.
#
# Some properties have scope name set to 'None' because the scope may be different for different
# systems. In such cases, the scope can be obtained via 'PStates.get_sname()'.
PROPS = {
    "turbo" : {
        "name" : "Turbo",
        "type" : "bool",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : True,
    },
    "min_freq" : {
        "name" : "Min. CPU frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("sysfs", "msr"),
        "writable" : True,
        "special_vals" : _SPECIAL_FREQ_VALS,
    },
    "max_freq" : {
        "name" : "Max. CPU frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("sysfs", "msr"),
        "writable" : True,
        "special_vals" : _SPECIAL_FREQ_VALS,
    },
    "min_freq_limit" : {
        "name" : "Min. supported CPU frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "max_freq_limit" : {
        "name" : "Max. supported CPU frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "base_freq" : {
        "name" : "Base CPU frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("sysfs", "msr", "cppc"),
        "writable" : False,
    },
    "bus_clock" : {
        "name" : "Bus clock speed",
        "unit" : "Hz",
        "type" : "int",
        "sname": None,
        "mnames" : ("msr", "doc"),
        "writable" : False,
    },
    "min_oper_freq" : {
        "name" : "Min. CPU operating frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("msr", "cppc"),
        "writable" : False,
    },
    "max_eff_freq" : {
        "name" : "Max. CPU efficiency frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "max_turbo_freq" : {
        "name" : "Max. CPU turbo frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("msr", "cppc"),
        "writable" : False,
    },
    "frequencies" : {
        "name" : "Acceptable CPU frequencies",
        "unit" : "Hz",
        "type" : "list[int]",
        "sname": "CPU",
        "mnames" : ("sysfs", "doc"),
        "writable" : False,
    },
    "min_uncore_freq" : {
        "name" : "Min. uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "mnames" : ("sysfs", ),
        "writable" : True,
        "special_vals" : _SPECIAL_UNCORE_FREQ_VALS,
    },
    "max_uncore_freq" : {
        "name" : "Max. uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "mnames" : ("sysfs", ),
        "writable" : True,
        "special_vals" : _SPECIAL_UNCORE_FREQ_VALS,
    },
    "min_uncore_freq_limit" : {
        "name" : "Min. supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "max_uncore_freq_limit" : {
        "name" : "Max. supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "hwp" : {
        "name" : "Hardware power management",
        "type" : "bool",
        "sname": "global",
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "epp" : {
        "name" : "EPP",
        "type" : "str",
        "sname": "CPU",
        "mnames" : ("sysfs", "msr"),
        "writable" : True,
    },
    "epb" : {
        "name" : "EPB",
        "type" : "int",
        "sname": None,
        "mnames" : ("sysfs", "msr"),
        "writable" : True,
    },
    "driver" : {
        "name" : "CPU frequency driver",
        "type" : "str",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "intel_pstate_mode" : {
        "name" : "Mode of 'intel_pstate' driver",
        "type" : "str",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : True,
    },
    "governor" : {
        "name" : "CPU frequency governor",
        "type" : "str",
        "sname": "CPU",
        "mnames" : ("sysfs", ),
        "writable" : True,
    },
    "governors" : {
        "name" : "Available CPU frequency governors",
        "type" : "list[str]",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
}

class PStates(_PCStatesBase.PCStatesBase):
    """
    This class provides API for managing platform settings related to P-states. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def _is_uncore_prop(self, pname):
        """Returns 'True' if property 'pname' is an uncore property, otherwise returns 'False'."""

        return pname in {"min_uncore_freq", "max_uncore_freq",
                         "min_uncore_freq_limit", "max_uncore_freq_limit"}

    def _get_fsbfreq(self):
        """Discover bus clock speed."""

        if not self._fsbfreq:
            from pepclibs.msr import FSBFreq # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_pmenable(self):
        """Returns an 'PMEnable.PMEnable()' object."""

        if not self._pmenable:
            from pepclibs.msr import PMEnable # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._pmenable = PMEnable.PMEnable(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._pmenable

    def _get_eppobj(self):
        """Returns an 'EPP.EPP()' object."""

        if not self._eppobj:
            from pepclibs import EPP # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._eppobj

    def _get_epbobj(self):
        """Returns an 'EPB.EPB()' object."""

        if not self._epbobj:
            from pepclibs import EPB # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._epbobj = EPB.EPB(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._epbobj

    def _get_cpufreq_sysfs_obj(self):
        """Return a '_CPUFreqSysfs' object."""

        if not self._cpufreq_sysfs_obj:
            from pepclibs import _CPUFreq # pylint: disable=import-outside-toplevel

            self._cpufreq_sysfs_obj = _CPUFreq.CPUFreqSysfs(cpuinfo=self._cpuinfo, pman=self._pman,
                                                            enable_cache=self._enable_cache)
        return self._cpufreq_sysfs_obj

    def _get_cpufreq_cppc_obj(self):
        """Return a '_CPUFreqcppc' object."""

        if not self._cpufreq_cppc_obj:
            from pepclibs import _CPUFreq # pylint: disable=import-outside-toplevel

            self._cpufreq_cppc_obj = _CPUFreq.CPUFreqCPPC(cpuinfo=self._cpuinfo, pman=self._pman,
                                                          enable_cache=self._enable_cache)
        return self._cpufreq_cppc_obj

    def _get_cpufreq_msr_obj(self):
        """Return a '_CPUFreqMSR' object."""

        if not self._cpufreq_msr_obj:
            from pepclibs import _CPUFreq # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._cpufreq_msr_obj = _CPUFreq.CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman,
                                                        msr=msr, enable_cache=self._enable_cache)
        return self._cpufreq_msr_obj

    def _get_uncfreq_obj(self):
        """Return an '_UncoreFreq' object."""

        if self._uncfreq_err:
            raise ErrorNotSupported(self._uncfreq_err)

        if not self._uncfreq_obj:
            from pepclibs import _UncoreFreq # pylint: disable=import-outside-toplevel

            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreq(cpuinfo=self._cpuinfo, pman=self._pman,
                                                           enable_cache=self._enable_cache)
            except ErrorNotSupported as err:
                self._uncfreq_err = err
                raise

        return self._uncfreq_obj

    def _get_epp(self, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is EPP value for CPU 'cpu'.
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

        pmenable = self._get_pmenable()
        yield from pmenable.is_feature_enabled("hwp", cpus=cpus)

    def _get_cppc_freq(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the value of property
        'pname' for CPU 'cpu', eead from an ACPI CPPC sysfs file.
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

        base_freq_iter = self._get_prop_pvinfo_cpus("base_freq", cpus)
        nominal_perf_iter = cpufreq_obj.get_base_perf(cpus)

        if pname == "max_turbo_freq":
            perf_iter = cpufreq_obj.get_max_perf_limit(cpus)
        else:
            perf_iter = cpufreq_obj.get_min_perf_limit(cpus)

        iterator = zip(base_freq_iter, nominal_perf_iter, perf_iter)
        for pvinfo, (_, nominal_perf), (_, perf) in iterator:
            yield pvinfo["cpu"], int((pvinfo["val"] * perf) / nominal_perf)

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

    def _get_cpu_freq_sysfs(self, pname, cpus):
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

    def _get_cpu_freq_msr(self, pname, cpus):
        """Yield the minimum or maximum CPU frequency read from 'MSR_HWP_REQUEST'."""

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        else:
            raise Error(f"BUG: unexpected CPU frequency property {pname}")

    def _get_cpu_freq(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the frequency of CPU
        'cpu'. Use method 'mname'.
        """

        if mname == "sysfs":
            yield from self._get_cpu_freq_sysfs(pname, cpus)
            return

        if mname == "msr":
            yield from self._get_cpu_freq_msr(pname, cpus)
            return

        raise Error(f"BUG: unsupported mechanism '{mname}'")

    def _get_cpu_freq_limit(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the frequency limit for
        CPU 'cpu'. Use the 'sysfs' method.
        """

        yield from self._get_cpu_freq_sysfs(pname, cpus)

    def _get_uncore_freq(self, pname, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is uncore frequency or
        uncore frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. Use
        the "sysfs" method.
        """

        uncfreq_obj = self._get_uncfreq_obj()

        if pname == "min_uncore_freq":
            yield from uncfreq_obj.get_min_freq(cpus)
            return
        if pname == "max_uncore_freq":
            yield from uncfreq_obj.get_max_freq(cpus)
            return
        if pname == "min_uncore_freq_limit":
            yield from uncfreq_obj.get_min_freq_limit(cpus)
            return
        if pname == "max_uncore_freq_limit":
            yield from uncfreq_obj.get_max_freq_limit(cpus)
            return

        raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _get_bclks(self, cpus):
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

    def _get_bclk(self, cpu):
        """Return bus clock speed in Hz."""

        _, val = next(self._get_bclks((cpu,)))
        return val

    def _get_frequencies_intel(self, cpus):
        """
        For every CPU in 'cpus', yield the list of CPU frequencies for CPU 'cpu' on an Intel
        platform.
        """

        driver_iter = self._get_prop_pvinfo_cpus("driver", cpus)
        min_freq_iter = self._get_prop_pvinfo_cpus("min_freq", cpus)
        max_freq_iter = self._get_prop_pvinfo_cpus("max_freq", cpus)
        bclks_iter = self._get_bclks(cpus)
        iterator = zip(driver_iter, min_freq_iter, max_freq_iter, bclks_iter)

        for driver_pvinfo, min_freq_pvinfo, max_freq_pvinfo, (cpu, bclk) in iterator:
            if driver_pvinfo["val"] != "intel_pstate":
                raise ErrorNotSupported("only 'intel_pstate' was verified to accept any frequency "
                                        "value that is multiple of bus clock")

            freqs = []
            freq = min_freq_pvinfo["val"]
            while freq <= max_freq_pvinfo["val"]:
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

    def _get_turbo(self, cpu):
        """Return the turbo on/of status for CPU 'cpu', use the 'sysfs' method."""

        pname = "turbo"
        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get(pname, cpu, mname)

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_cache("driver", cpu)

        try:
            if driver == "intel_pstate":
                if self._get_cpu_prop_cache("intel_pstate_mode", cpu) == "off":
                    return None
                path = self._sysfs_base / "intel_pstate" / "no_turbo"
                disabled = self._read_int(path)
                val = "off" if disabled else "on"
            elif driver == "acpi-cpufreq":
                path = self._sysfs_base / "cpufreq" / "boost"
                enabled = self._read_int(path)
                val = "on" if enabled else "off"
            else:
                val = None
                _LOG.debug("CPU %d: can't check if turbo is enabled%s: unsupported CPU frequency "
                           "driver %s'", cpu, self._pman.hostmsg, driver)
        except ErrorNotFound:
            # If the sysfs file does not exist, the system does not support turbo.
            val = None

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["iosname"])
        return val

    def _get_driver(self, cpu):
        """Return the CPU frequency driver name for CPU 'cpu', use the 'sysfs' method."""

        pname = "driver"
        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get(pname, cpu, mname)

        path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_driver"

        val = self._read_prop_from_sysfs(pname, path)
        if val is None:
            # The 'intel_pstate' driver may be in the 'off' mode, in which case the 'scaling_driver'
            # sysfs file does not exist. So just check if the 'intel_pstate' sysfs directory exists.
            if self._pman.exists(self._sysfs_base / "intel_pstate"):
                val = "intel_pstate"
            else:
                _LOG.debug("can't read value of property '%s', path '%s' missing", pname, path)
        else:
            # The 'intel_pstate' driver calls itself 'intel_pstate' when it is in active mode, and
            # 'intel_cpufreq' when it is in passive mode. But we always report the 'intel_pstate'
            # name, because reporting 'intel_cpufreq' is confusing for users.
            if val == "intel_cpufreq":
                val = "intel_pstate"

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["iosname"])
        return val

    def _get_intel_pstate_mode(self, pname, cpu):
        """
        Return the 'intel_pstate' driver operation mode for CPU 'cpu', use the 'sysfs' method.
        """

        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get(pname, cpu, mname)

        driver = self._get_cpu_prop_cache("driver", cpu)
        if driver == "intel_pstate":
            path = self._sysfs_base / "intel_pstate" / "status"
            val = self._read_prop_from_sysfs(pname, path)
        else:
            val = None

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["iosname"])
        return val

    def _get_prop_sysfs_path(self, pname, cpu):
        """Return path to the sysfs file of property 'pname' for CPU 'cpu'."""

        prop = self._props[pname]
        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / prop["fname"]

    def _get_prop_from_sysfs(self, pname, cpu):
        """
        Return the governor or list of available governors for CPU 'cpu', use the 'sysfs' method.
        """

        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get(pname, cpu, mname)

        path = self._get_prop_sysfs_path(pname, cpu)
        val = self._read_prop_from_sysfs(pname, path)

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["iosname"])
        return val

    def _get_cpu_prop(self, pname, cpu, _):
        """Return 'pname' property value for CPU 'cpu', using mechanism 'mname'."""

        if pname == "turbo":
            return self._get_turbo(cpu)
        if pname == "driver":
            return self._get_driver(cpu)
        if pname == "intel_pstate_mode":
            return self._get_intel_pstate_mode(pname, cpu)
        if "fname" in self._props[pname]:
            return self._get_prop_from_sysfs(pname, cpu)

        raise Error(f"BUG: unsupported property '{pname}'")

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
            yield from self._get_cpu_freq(pname, cpus, mname)
        elif pname in {"min_freq_limit", "max_freq_limit"}:
            yield from self._get_cpu_freq_limit(pname, cpus)
        elif self._is_uncore_prop(pname):
            yield from self._get_uncore_freq(pname, cpus)
        elif pname == "frequencies":
            yield from self._get_frequencies(cpus, mname)
        elif pname == "bus_clock":
            yield from self._get_bus_clock(cpus, mname)
        else:
            for cpu in cpus:
                yield (cpu, self._get_cpu_prop(pname, cpu, mname))

    def _set_turbo(self, cpu, enable):
        """Enable or disable turbo."""

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_cache("driver", cpu)

        status = "on" if enable else "off"
        errmsg = f"failed to switch turbo {status}{self._pman.hostmsg}"

        if driver == "intel_pstate":
            if self._get_cpu_prop_cache("intel_pstate_mode", cpu) == "off":
                raise ErrorNotSupported(f"{errmsg}: 'intel_pstate' driver is in 'off' mode")

            path = self._sysfs_base / "intel_pstate" / "no_turbo"
            sysfs_val = int(not enable)
        elif driver == "acpi-cpufreq":
            path = self._sysfs_base / "cpufreq" / "boost"
            sysfs_val = int(enable)
        else:
            raise ErrorNotSupported(f"{errmsg}: unsupported CPU frequency driver '{driver}'")

        try:
            self._write_prop_to_sysfs("turbo", path, sysfs_val)
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"{errmsg}: turbo is not supported") from err

        self._pcache.add("turbo", cpu, status, "sysfs", sname=self._props["turbo"]["iosname"])

    def _get_num_str(self, pname, cpu):
        """
        If property 'pname' has CPU scope, returns "CPU <num>" string. If 'pname' has die scope,
        returns "package <pkgnum> die <dienum>" string.
        """

        if self._is_uncore_prop(pname):
            levels = self._cpuinfo.get_cpu_levels(cpu, levels=("package", "die"))
            pkg = levels["package"]
            die = levels["die"]
            what = f"package {pkg} die {die}"
        else:
            what = f"CPU {cpu}"

        return what

    def _write_cpu_freq_prop_msr(self, pname, freq, cpu):
        """Write CPU frequency property by programming 'MSR_HWP_REQUEST'."""

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            cpufreq_obj.set_cpu_min_freq(freq, cpu)
        elif pname == "max_freq":
            cpufreq_obj.set_cpu_max_freq(freq, cpu)
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
            frequencies = self._get_cpu_prop_cache("frequencies", cpu)
            if frequencies:
                frequencies_set = set(frequencies)
                if freq not in frequencies_set and read_freq in frequencies_set:
                    fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                    freq_human = Human.num2si(freq, unit="Hz", decp=4)
                    msg += f".\n  Linux kernel CPU frequency driver does not support " \
                           f"{freq_human}, use one of the following values instead:\n  {fvals}"
            elif self._get_turbo(cpu)["val"] == "off":
                base_freq = self._get_cpu_prop_cache("base_freq", cpu)
                if base_freq and freq > base_freq:
                    base_freq = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f".\n  Hint: turbo is disabled, base frequency is {base_freq}, and " \
                           f"this may be the limiting factor."

        raise ErrorVerifyFailed(msg) from err

    def _write_cpu_freq_prop_sysfs(self, pname, freq, cpu):
        """Write CPU frequency property via Linux "cpufreq" sysfs interfaces."""

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        try:
            if pname == "min_freq":
                cpufreq_obj.set_cpu_min_freq(freq, cpu)
            elif pname == "max_freq":
                cpufreq_obj.set_cpu_max_freq(freq, cpu)
            else:
                raise Error(f"BUG: unexpected CPU frequency property {pname}")
        except ErrorVerifyFailed as err:
            self._handle_write_and_read_freq_mismatch(err)

    def _write_uncore_freq_prop(self, pname, freq, cpu):
        """Write uncore frequency property."""

        uncfreq_obj = self._get_uncfreq_obj()

        if pname == "min_uncore_freq":
            uncfreq_obj.set_cpu_min_freq(freq, cpu)
        elif pname == "max_uncore_freq":
            uncfreq_obj.set_cpu_max_freq(freq, cpu)
        else:
            raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _parse_freq(self, val, cpu, uncore=False):
        """Turn a user-provided CPU or uncore frequency property value to hertz."""

        if uncore:
            if val == "min":
                freq = self._get_cpu_prop_cache("min_uncore_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop_cache("max_uncore_freq_limit", cpu)
            elif val == "mdl":
                bclk = self._get_bclk(cpu)
                min_freq = self._get_cpu_prop_cache("min_uncore_freq_limit", cpu)
                max_freq = self._get_cpu_prop_cache("max_uncore_freq_limit", cpu)
                if min_freq and max_freq:
                    # Mid-point between min. and max. frequencies, rounded to the nearest multiple
                    # of bus clock frequency.
                    freq = bclk * round(statistics.mean([min_freq, max_freq]) / bclk)
                else:
                    freq = None
            else:
                freq = val
        else:
            if val == "min":
                freq = self._get_cpu_prop_cache("min_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop_cache("max_freq_limit", cpu)
            elif val in {"base", "hfm", "P1"}:
                freq = self._get_cpu_prop_cache("base_freq", cpu)
            elif val in {"eff", "lfm", "Pn"}:
                freq = self._get_cpu_prop_cache("max_eff_freq", cpu)
                if not freq:
                    # Max. efficiency frequency may not be supported by the platform. Fall back to
                    # the minimum frequency in this case.
                    freq = self._get_cpu_prop_cache("min_freq_limit", cpu)
            elif val == "Pm":
                freq = self._get_cpu_prop_cache("min_oper_freq", cpu)
            else:
                freq = val

        if not freq:
            if uncore and self._uncfreq_err:
                raise ErrorNotSupported(self._uncfreq_err)
            raise ErrorNotSupported(f"'{val}' is not supported{self._pman.hostmsg}")

        return freq

    def _set_intel_pstate_mode(self, cpu, mode):
        """Change mode of the CPU frequency driver 'intel_pstate'."""

        # Setting 'intel_pstate' driver mode to "off" is only possible in non-HWP (legacy) mode.
        if mode == "off" and self._get_cpu_prop_cache("hwp", cpu) == "on":
            raise ErrorNotSupported("'intel_pstate' driver does not support \"off\" mode when "
                                    "hardware power management (HWP) is enabled")

        path = self._sysfs_base / "intel_pstate" / "status"
        try:
            self._write_prop_to_sysfs("intel_pstate_mode", path, mode)
            self._pcache.add("intel_pstate_mode", cpu, mode, "sysfs",
                             sname=self._props["intel_pstate_mode"]["iosname"])
        except Error:
            # When 'intel_pstate' driver is 'off' it is not possible to write 'off' again.
            if mode != "off" or self._get_cpu_prop_cache("intel_pstate_mode", cpu) != "off":
                raise

    def _validate_intel_pstate_mode(self, mode):
        """Validate 'intel_pstate_mode' mode."""

        if self._get_cpu_prop_cache("intel_pstate_mode", 0) is None:
            driver = self._get_cpu_prop_cache("driver", 0)
            raise Error(f"can't set property 'intel_pstate_mode'{self._pman.hostmsg}:\n  "
                        f"the CPU frequency driver is '{driver}', not 'intel_pstate'")

        modes = ("active", "passive", "off")
        if mode not in modes:
            modes = ", ".join(modes)
            raise Error(f"bad 'intel_pstate' mode '{mode}', use one of: {modes}")

    def _set_prop_sysfs(self, pname, val, cpus):
        """Sets property 'pname' using 'sysfs' mechanism."""

        mname = "sysfs"

        # Removing 'cpus' from the cache will make sure the following '_pcache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_pcache.add()'
        # method.
        for cpu in cpus:
            self._pcache.remove(pname, cpu, mname)

        prop = self._props[pname]

        for cpu in cpus:
            if self._pcache.is_cached(pname, cpu, mname):
                continue

            if pname == "turbo":
                self._set_turbo(cpu, val)
            elif pname == "intel_pstate_mode":
                self._set_intel_pstate_mode(cpu, val)
            elif "fname" in prop:
                path = self._get_prop_sysfs_path(pname, cpu)
                self._write_prop_to_sysfs(pname, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the 'sname' siblings. For example, if property
                # scope name is "package", 'val' will be cached for all CPUs in the package that
                # contains CPU number 'cpu'.
                self._pcache.add(pname, cpu, val, mname, sname=prop["iosname"])
            else:
                raise Error(f"BUG: unsupported property '{pname}'")

        return mname

    def _set_freq_prop(self, pname, val, cpus, mname):
        """
        Set core or uncore frequency property 'pname' to value 'val' for CPUs in 'cpus' using method
        'mname'.
        """

        def _raise_not_supported(pname):
            """Raise an exception if one of the required properties is not supported."""

            name = Human.uncapitalize(self._props[pname]["name"])
            raise ErrorNotSupported(f"CPU {cpu} does not support {name}{self._pman.hostmsg}")

        def _raise_out_of_range(pname, val, min_limit, max_limit):
            """Raise an exception if the frequency property is out of range."""

            name = Human.uncapitalize(self._props[pname]["name"])
            val = Human.num2si(val, unit="Hz", decp=4)
            min_limit = Human.num2si(min_limit, unit="Hz", decp=4)
            max_limit = Human.num2si(max_limit, unit="Hz", decp=4)
            what = self._get_num_str(pname, cpu)
            raise ErrorFreqRange(f"{name} value of '{val}' for {what} is out of range, "
                                 f"must be within [{min_limit}, {max_limit}]")

        def _raise_order(pname, new_freq, cur_freq, is_min):
            """Raise and exception in case of failure due to frequency ordering constraints."""

            name = Human.uncapitalize(self._props[pname]["name"])
            new_freq = Human.num2si(new_freq, unit="Hz", decp=4)
            cur_freq = Human.num2si(cur_freq, unit="Hz", decp=4)
            what = self._get_num_str(pname, cpu)
            if is_min:
                msg = f"larger than currently configured max. frequency of {cur_freq}"
            else:
                msg = f"lower than currently configured min. frequency of {cur_freq}"
            raise ErrorFreqOrder(f"can't set {name} of {what} to {cur_freq} - it is {msg}")

        is_min = "min" in pname
        is_uncore = "uncore" in pname

        if is_uncore:
            min_freq_pname = "min_uncore_freq"
            max_freq_pname = "max_uncore_freq"
            min_freq_limit_pname = "min_uncore_freq_limit"
            max_freq_limit_pname = "max_uncore_freq_limit"
            write_func = self._write_uncore_freq_prop
        else:
            min_freq_pname = "min_freq"
            max_freq_pname = "max_freq"
            if mname == "sysfs":
                min_freq_limit_pname = "min_freq_limit"
                max_freq_limit_pname = "max_freq_limit"
                write_func = self._write_cpu_freq_prop_sysfs
            elif mname == "msr":
                min_freq_limit_pname = "min_oper_freq"
                max_freq_limit_pname = "max_turbo_freq"
                write_func = self._write_cpu_freq_prop_msr

        for cpu in cpus:
            new_freq = self._parse_freq(val, cpu, is_uncore)

            min_limit = self._get_cpu_prop_cache(min_freq_limit_pname, cpu, mnames=(mname,))
            if not min_limit:
                _raise_not_supported(min_freq_limit_pname)
            max_limit = self._get_cpu_prop_cache(max_freq_limit_pname, cpu, mnames=(mname,))
            if not max_limit:
                _raise_not_supported(max_freq_limit_pname)

            if new_freq < min_limit or new_freq > max_limit:
                _raise_out_of_range(pname, new_freq, min_limit, max_limit)

            if is_min:
                cur_max_freq = self._get_cpu_prop_cache(max_freq_pname, cpu, mnames=(mname,))
                if not cur_max_freq:
                    _raise_not_supported(max_freq_pname)

                if new_freq > cur_max_freq:
                    # New min. frequency cannot be set to a value larger than current max.
                    # frequency.
                    _raise_order(pname, new_freq, cur_max_freq, is_min)

                write_func(pname, new_freq, cpu)
            else:
                cur_min_freq = self._get_cpu_prop_cache(min_freq_pname, cpu, mnames=(mname,))
                if not cur_min_freq:
                    _raise_not_supported(min_freq_pname)

                if new_freq < cur_min_freq:
                    # New max. frequency cannot be set to a value smaller than current min.
                    # frequency.
                    _raise_order(pname, new_freq, cur_min_freq, is_min)

                write_func(pname, new_freq, cpu)

    def _set_prop_cpus(self, pname, val, cpus, mname):
        """Set property 'pname' to value 'val' for CPUs in 'cpus'. Use mechanism 'mname'."""

        if pname == "governor":
            self._validate_governor_name(val)
        elif pname == "intel_pstate_mode":
            self._validate_intel_pstate_mode(val)

        if pname == "epp":
            return self._get_eppobj().set_vals(val, cpus=cpus, mnames=(mname,))
        if pname == "epb":
            return self._get_epbobj().set_vals(val, cpus=cpus, mnames=(mname,))

        if pname in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
            return self._set_freq_prop(pname, val, cpus, mname)

        return self._set_prop_sysfs(pname, val, cpus)

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

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # Properties backed by a single sysfs file (only simple cases).
        #
        # Note, not all properties that may be backed by a sysfs file have "fname". For example,
        # "turbo" does not, because the sysfs knob path depends on what frequency driver is used.
        self._props["governor"]["fname"] = "scaling_governor"
        self._props["governors"]["fname"] = "scaling_available_governors"

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._eppobj = None
        self._epbobj = None
        self._fsbfreq = None
        self._pmenable = None

        self._cpufreq_sysfs_obj = None
        self._cpufreq_cppc_obj = None
        self._cpufreq_msr_obj = None

        self._uncfreq_obj = None
        self._uncfreq_err = None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        self._init_props_dict()

        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=self._enable_cache)
    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcache", "_eppobj", "_epbobj", "_fsbfreq", "_pmenable",
                       "_cpufreq_sysfs_obj", "_cpufreq_cppc_obj", "_cpufreq_msr_obj",
                       "_uncfreq_obj")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
