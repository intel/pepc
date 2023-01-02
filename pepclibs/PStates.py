# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides P-state management API.
"""

import time
import logging
import contextlib
from pathlib import Path
from pepclibs import _PropsCache
from pepclibs import _PCStatesBase
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs import KernelModule, FSHelpers, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.msr import EnergyPerfBias, HWPRequest, HWPRequestPkg

_LOG = logging.getLogger()

_CPU_FREQ_VALS_HELP = """The default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used (for
                         example "900MHz"). The following special values are supported: "min" -
                         minimum CPU frequency supported by the OS (via Linux sysfs files), "hfm",
                         "base", "P1" - base CPU frequency, "max" - maximum CPU frequency supported
                         by the OS (via Linux sysfs), "eff", "lfm", "Pn" - maximum CPU efficiency
                         frequency"""

_UNCORE_FREQ_VALS_HELP = """The default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used
                            (for example "900MHz"). The following special values are supported:
                            "min" - minimum uncore frequency supported by the OS (via Linux sysfs
                            files), "max" - maximum uncore frequency supported by the OS (via Linux
                            sysfs)"""

# This dictionary describes the CPU properties this module supports.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'PStates' objects. Use the full dictionary via
# 'PStates.props'.
PROPS = {
    "min_freq" : {
        "name" : "Min. CPU frequency",
        "help" : f"""Minimum CPU frequency is the lowest frequency the operating system configured
                     the CPU to run at (via sysfs knobs). {_CPU_FREQ_VALS_HELP}.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "max_freq" : {
        "name" : "Max. CPU frequency",
        "help" : f"""Maximum CPU frequency is the highest frequency the operating system configured
                    the CPU to run at (via sysfs knobs). {_CPU_FREQ_VALS_HELP}.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "min_freq_limit" : {
        "name" : "Min. supported CPU frequency",
        "help" : """Minimum supported CPU frequency is the lowest frequency supported by the
                    operating system (reported via sysfs knobs).""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "max_freq_limit" : {
        "name" : "Max. supported CPU frequency",
        "help" : """Maximum supported CPU frequency is the maximum CPU frequency supported by the
                    operating system (reported via sysfs knobs).""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "base_freq" : {
        "name" : "Base CPU frequency",
        "help" : """Base CPU frequency is the highest sustainable CPU frequency. This frequency is
                    also referred to as \"guaranteed frequency\", HFM (High Frequency Mode), or P1.
                    The base frequency is acquired from a sysfs file of from an MSR register, if
                    the sysfs file does not exist.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "min_freq_hw" : {
        "name" : "Min. CPU frequency (OS bypass)",
        "help" : """Minimum frequency the CPU is configured by the OS to run at. This value is
                    read directly from the MSR(s), bypassing the OS.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "max_freq_hw" : {
        "name" : "Max. CPU frequency (OS bypass)",
        "help" : """Maximum frequency the CPU is configured by the OS to run at. This value is
                    read directly from the MSR(s), bypassing the OS.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "min_oper_freq" : {
        "name" : "Min. CPU operating frequency",
        "help" : """Minimum operating frequency is the lowest possible frequency the CPU can operate
                    at. Depending on the CPU model, this frequency may or may not be directly
                    available to the operating system, but the platform may use it in certain
                    situations (e.g., in some C-states). This frequency is also referred to as Pm.
                    Min. operating frequency is acquired from an MSR register, bypassing the OS.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "max_eff_freq" : {
        "name" : "Max. CPU efficiency frequency",
        "help" : """Maximum efficiency frequency is the most energy efficient CPU frequency. This
                    frequency is also referred to as LFM (Low Frequency Mode) or Pn. Max. efficiency
                    frequency is acquired from an MSR register, bypassing the OS.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "turbo" : {
        "name" : "Turbo",
        "help" : """When turbo is enabled, the CPUs can automatically run at a frequency greater
                    than base frequency. Turbo on/off status is acquired and modified via sysfs
                    knobs.""",
        "type" : "bool",
        "sname": "global",
        "writable" : True,
    },
    "max_turbo_freq" : {
        "name" : "Max. CPU turbo frequency",
        "help" : """Maximum 1-core turbo frequency is the highest frequency a single CPU can operate
                    at. This frequency is also referred to as max. 1-core turbo and P01. It is
                    acquired from an MSR register, bypassing the OS.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "min_uncore_freq" : {
        "name" : "Min. uncore frequency",
        "help" : f"""Minimum uncore frequency is the lowest frequency the operating system
                     configured the uncore to run at. {_UNCORE_FREQ_VALS_HELP}.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : True,
    },
    "max_uncore_freq" : {
        "name" : "Max. uncore frequency",
        "help" : f"""Maximum uncore frequency is the highest frequency the operating system
                     configured the uncore to run at. {_UNCORE_FREQ_VALS_HELP}.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : True,
    },
    "min_uncore_freq_limit" : {
        "name" : "Min. supported uncore frequency",
        "help" : """Minimum supported uncore frequency is the lowest uncore frequency supported by
                    the operating system. """,
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : False,
    },
    "max_uncore_freq_limit" : {
        "name" : "Max. supported uncore frequency",
        "help" : """Maximum supported uncore frequency is the highest uncore frequency supported by
                    the operating system.""",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : False,
    },
    "hwp" : {
        "name" : "Hardware power management",
        "help" : """When hardware power management is enabled, CPUs can automatically scale their
                    frequency without active OS involvement.""",
        "type" : "bool",
        "sname": "global",
        "writable" : False,
    },
    "epp" : {
        "name" : "EPP (via sysfs)",
        "help" : """Energy Performance Preference is a hint to the CPU on energy efficiency vs
                    performance. EPP value is a number in range of 0-255 (maximum energy efficiency
                    to maximum performance), or a policy name. The value is read from or written
                    to the 'energy_performance_preference' Linux sysfs file.""",
        "type" : "str",
        "sname": "CPU",
        "writable" : True,
    },
    "epp_hw" : {
        "name" : f"EPP (via MSR {HWPRequest.MSR_HWP_REQUEST:#x})",
        "help" : f"""Energy Performance Preference is a hint to the CPU on energy efficiency vs
                    performance. EPP value is a number in range of 0-255 (maximum energy efficiency
                    to maximum performance). When package control is enabled the value is read from
                    MSR {HWPRequestPkg.MSR_HWP_REQUEST_PKG:#x}, but when written package control is
                    disabled and value is written to MSR {HWPRequest.MSR_HWP_REQUEST:#x}, both
                    require the 'msr' Linux kernel driver.""",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "epb" : {
        "name" : "EPB (via sysfs)",
        "help" : """Energy Performance Bias is a hint to the CPU on energy efficiency vs
                    performance. EBP value is a number in range of 0-15 (maximum performance to
                    maximum energy efficiency), or a policy name. The value is read from or written
                    to the 'energy_perf_bias' Linux sysfs file.""",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "epb_hw" : {
        "name" : f"EPB (via MSR {EnergyPerfBias.MSR_ENERGY_PERF_BIAS:#x})",
        "help" : f"""Energy Performance Bias is a hint to the CPU on energy efficiency vs
                     performance. EBP value is a number in range of 0-15 (maximum performance to
                     maximum energy efficiency). The value is read from or written to MSR
                     {EnergyPerfBias.MSR_ENERGY_PERF_BIAS:#x}, which requires the 'msr' Linux kernel
                     driver.""",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "driver" : {
        "name" : "CPU frequency driver",
        "help" : """CPU frequency driver enumerates and requests the P-states available on the
                    platform.""",
        "type" : "str",
        "sname": "global",
        "writable" : False,
    },
    "intel_pstate_mode" : {
        "name" : "Operation mode of 'intel_pstate' driver",
        "help" : """The 'intel_pstate' driver has 3 operation modes: 'active', 'passive' and 'off'.
                    The main difference between the active and passive mode is in what frequency
                    governors are used - the generic Linux governors (passive mode) or the custom,
                    built-in 'intel_pstate' driver governors (active mode).""",
        "type" : "str",
        "sname": "global",
        "writable" : True,
    },
    "governor" : {
        "name" : "CPU frequency governor",
        "help" : """CPU frequency governor decides which P-state to select on a CPU depending
                    on CPU business and other factors.""",
        "type" : "str",
        "sname": "CPU",
        "writable" : True,
        "subprops" : {
            "governors" : {
                "name" : "Available CPU frequency governors",
                "help" : """CPU frequency governors decide which P-state to select on a CPU
                            depending on CPU business and other factors. Different governors
                            implement different selection policy.""",
                "type" : "list[str]",
                "sname": "global",
                "writable" : False,
            },
        },
    },
}

def _is_uncore_prop(prop):
    """
    Returns 'True' if property 'prop' is an uncore property, otherwise returns 'False'.
    """

    if "fname" in prop and prop["fname"].endswith("khz"):
        return True
    return False

class PStates(_PCStatesBase.PCStatesBase):
    """
    This class provides API for managing platform settings related to P-states.

    Public methods overview.

    Get/set P-state properties for:
       * multiple properties and multiple CPUs: 'get_props()', 'set_props()'.
       * single property and multiple CPUs: 'set_prop()'.
       * multiple properties and single CPU: 'get_cpu_props()', 'set_cpu_props()'.
       * single property and single CPU: 'get_cpu_prop()', 'set_cpu_prop()'.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

        return self._msr

    def _get_eppobj(self):
        """Returns an 'EPP.EPP()' object."""

        if not self._eppobj:
            from pepclibs import EPP # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            hwpreq = self._get_hwpreq()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr, hwpreq=hwpreq,
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

    def _get_bclk(self, cpu):
        """Discover bus clock speed."""

        if cpu not in self._bclk:
            from pepclibs import BClock # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._bclk[cpu] = BClock.get_bclk(self._pman, cpu=cpu, cpuinfo=self._cpuinfo, msr=msr)
            _LOG.debug("CPU %d: bus clock speed: %fMHz", cpu, self._bclk[cpu])

        return self._bclk[cpu]

    def _get_pmenable(self):
        """Returns an 'PMEnable.PMEnable()' object."""

        if not self._pmenable:
            from pepclibs.msr import PMEnable # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._pmenable = PMEnable.PMEnable(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._pmenable

    def _get_hwpreq(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_platinfo(self):
        """Returns an 'PlatformInfo.PlatformInfo()' object."""

        if not self._platinfo:
            from pepclibs.msr import PlatformInfo # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._platinfo = PlatformInfo.PlatformInfo(pman=self._pman, cpuinfo=self._cpuinfo,
                                                       msr=msr)
        return self._platinfo

    def _get_trl(self):
        """Returns an 'TurboRatioLimit.TurboRatioLimit()' object."""

        if not self._trl:
            from pepclibs.msr import TurboRatioLimit # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._trl = TurboRatioLimit.TurboRatioLimit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=msr)
        return self._trl

    def __is_uncore_freq_supported(self):
        """Implements '_is_uncore_freq_supported()'."""

        if self._pman.exists(self._sysfs_base_uncore):
            return True

        drvname = "intel_uncore_frequency"
        msg = f"Uncore frequency operations are not supported{self._pman.hostmsg}. Here are the " \
              f"possible reasons:\n" \
              f" 1. the hardware does not support uncore frequency management.\n" \
              f" 2. the '{drvname}' driver does not support this hardware.\n" \
              f" 3. the '{drvname}' driver is not enabled. Try to compile the kernel with " \
              f"the 'CONFIG_INTEL_UNCORE_FREQ_CONTROL' option."

        try:
            self._ufreq_drv = KernelModule.KernelModule(drvname, pman=self._pman)
            loaded = self._ufreq_drv.is_loaded()
        except Error as err:
            _LOG.debug("%s\n%s", err, msg)
            self._uncore_errmsg = msg
            return False

        if loaded:
            # The sysfs directories do not exist, but the driver is loaded.
            _LOG.debug("The uncore frequency driver '%s' is loaded, but the sysfs directory '%s' "
                       "does not exist.\n%s", drvname, self._sysfs_base_uncore, msg)
            self._uncore_errmsg = msg

        try:
            self._ufreq_drv.load()
            self._unload_ufreq_drv = True
            FSHelpers.wait_for_a_file(self._sysfs_base_uncore, timeout=1, pman=self._pman)
        except Error as err:
            _LOG.debug("%s\n%s", err, msg)
            self._uncore_errmsg = msg
            return False

        return True

    def _is_uncore_freq_supported(self):
        """
        Make sure that the uncore frequency control is supported. Load the uncore frequency
        control driver if necessary.
        """

        if self._uncore_freq_supported is not None:
            return self._uncore_freq_supported

        self._uncore_freq_supported = self.__is_uncore_freq_supported()
        return self._uncore_freq_supported

    def _get_base_freq(self, cpu):
        """Read base frequency from 'MSR_PLATFORM_INFO' and return it."""

        platinfo = self._get_platinfo()

        try:
            ratio = platinfo.read_cpu_feature("max_non_turbo_ratio", cpu)
        except ErrorNotSupported:
            return None

        bclk = self._get_bclk(cpu)
        return int(ratio * bclk * 1000 * 1000)

    def _get_max_eff_freq(self, cpu):
        """Read max. efficiency frequency from 'MSR_PLATFORM_INFO' and return it."""

        platinfo = self._get_platinfo()

        try:
            ratio = platinfo.read_cpu_feature("max_eff_ratio", cpu)
        except ErrorNotSupported:
            return None

        bclk = self._get_bclk(cpu)
        return int(ratio * bclk * 1000 * 1000)

    def _get_min_oper_freq(self, cpu):
        """Read the minimum operating frequency from 'MSR_PLATFORM_INFO' and return it."""

        platinfo = self._get_platinfo()

        try:
            ratio = platinfo.read_cpu_feature("min_oper_ratio", cpu)
        except ErrorNotSupported:
            return None

        if ratio == 0:
            _LOG.warn_once("BUG: 'Minimum Operating Ratio' is '0' on CPU %d, MSR address '%#x' "
                            "bit field '55:48'\nPlease, contact project maintainers.",
                            cpu, platinfo.regaddr)
            return None

        bclk = self._get_bclk(cpu)
        return int(ratio * bclk * 1000 * 1000)

    def _get_max_turbo_freq(self, cpu):
        """
        Read and return the maximum turbo frequency for CPU 'cpu' from 'MSR_TURBO_RATIO_LIMIT'.
        """

        trl = self._get_trl()

        try:
            ratio = trl.read_cpu_feature("max_1c_turbo_ratio", cpu)
        except ErrorNotSupported:
            try:
                # In this case 'MSR_TURBO_RATIO_LIMIT' encodes max. turbo ratio for groups of cores.
                # We can safely assume that group 0 will correspond to max. 1-core turbo, so we do
                # not need to look at 'MSR_TURBO_RATIO_LIMIT1'.
                ratio = trl.read_cpu_feature("max_g0_turbo_ratio", cpu)
            except ErrorNotSupported:
                _LOG.warn_once("CPU %d: module 'TurboRatioLimit' doesn't support "
                               "'MSR_TURBO_RATIO_LIMIT' for CPU '%s'%s\nPlease, contact project "
                               "maintainers.", cpu, self._cpuinfo.cpudescr, self._pman.hostmsg)
                return None

        bclk = self._get_bclk(cpu)
        return int(ratio * bclk * 1000 * 1000)

    def _read_int(self, path):
        """Read an integer from file 'path' via the process manager."""

        val = self._pman.read(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_cpu_turbo(self, cpu):
        """
        Returns "on" if turbo is enabled, "off" if it is disabled, and 'None' if it is not
        supported.
        """

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_value("driver", cpu)

        try:
            if driver == "intel_pstate":
                if self._get_cpu_prop_value("intel_pstate_mode", cpu) == "off":
                    return None

                path = self._sysfs_base / "intel_pstate" / "no_turbo"
                disabled = self._read_int(path)
                return "off" if disabled else "on"

            if driver == "acpi-cpufreq":
                path = self._sysfs_base / "cpufreq" / "boost"
                enabled = self._read_int(path)
                return "on" if enabled else "off"
        except ErrorNotFound:
            # If the sysfs file does not exist, the system does not support turbo.
            return None

        _LOG.debug("CPU %d: can't check if turbo is enabled%s: unsupported CPU frequency driver "
                   "'%s'", cpu, self._pman.hostmsg, driver)

        return None

    def _get_cpu_hwp(self, cpu):
        """
        Returns "on" if HWP is enabled, "off" if it is disabled, and 'None' if it is not supported.
        """

        pmenable = self._get_pmenable()
        try:
            enabled = pmenable.is_cpu_feature_enabled("hwp", cpu)
        except ErrorNotSupported:
            return None

        return "on" if enabled else "off"

    def _get_sysfs_path(self, prop, cpu):
        """
        Construct and return path to the sysfs file corresponding to property 'prop' and CPU 'cpu'.
        """

        if _is_uncore_prop(prop):
            levels = self._cpuinfo.get_cpu_levels(cpu)
            pkg = levels["package"]
            die = levels["die"]
            return self._sysfs_base_uncore / f"package_{pkg:02d}_die_{die:02d}" / prop["fname"]

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / prop["fname"]

    def _get_cpu_prop_value_sysfs(self, prop, cpu):
        """
        This is a helper for '_get_cpu_prop_value()' which handles the properties backed by a sysfs
        file.
        """

        if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
            _LOG.debug(self._uncore_errmsg)
            return None

        path = self._get_sysfs_path(prop, cpu)
        val = None

        try:
            val = self._read_prop_value_from_sysfs(prop, path)
        except ErrorNotFound as err1:
            _LOG.debug("can't read value of property '%s', path '%s' missing", prop["name"], path)

            if "getter" in prop:
                _LOG.debug("running the fallback function property '%s'", prop["name"])
                try:
                    val = prop["getter"](cpu)
                except Error as err2:
                    raise Error(f"{err1}\nThe fall-back method failed too:\n{err2.indent(2)}") \
                                from err2

        return val

    def _get_driver(self, cpu):
        """Returns the CPU frequency driver."""

        prop = self._props["driver"]
        path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_driver"

        try:
            driver = self._read_prop_value_from_sysfs(prop, path)
        except ErrorNotFound:
            # The 'intel_pstate' driver may be in the 'off' mode, in which case the 'scaling_driver'
            # sysfs file does not exist. So just check if the 'intel_pstate' sysfs directory exists.
            if self._pman.exists(self._sysfs_base / "intel_pstate"):
                return "intel_pstate"

            _LOG.debug("can't read value of property '%s', path '%s' missing", prop["name"], path)
            return None

        # The 'intel_pstate' driver calls itself 'intel_pstate' when it is in active mode, and
        # 'intel_cpufreq' when it is in passive mode. But we always report the 'intel_pstate' name,
        # because reporting 'intel_cpufreq' is just confusing.
        if driver == "intel_cpufreq":
            return "intel_pstate"

        return driver

    def _get_intel_pstate_mode(self, pname, cpu):
        """Returns the 'intel_pstate' driver operation mode."""

        driver = self._get_cpu_prop_value("driver", cpu)

        if driver == "intel_pstate":
            path = self._sysfs_base / "intel_pstate" / "status"
            return self._read_prop_value_from_sysfs(self._props[pname], path)

        return None

    def _get_cpu_freq_hw(self, pname, cpu):
        """Reads and returns the minimum or maximum CPU frequency from 'MSR_HWP_REQUEST'."""

        # The "min" or "max" property name prefix.
        prefix = pname[0:3]
        # The corresponding 'MSR_HWP_REQUEST' feature name.
        fname = f"{prefix}_perf"

        hwpreq = self._get_hwpreq()
        if hwpreq.is_cpu_feature_pkg_controlled(fname, cpu):
            hwpreq = self._get_hwpreq_pkg()

        try:
            perf = hwpreq.read_cpu_feature(fname, cpu)
        except ErrorNotSupported:
            _LOG.debug("CPU %d: HWP %s performance is not supported", cpu, prefix)
            return None

        # Convert the performance to frequency in Hz.
        freq = perf * 100000000
        return freq

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        if prop is None:
            prop = self._props[pname]

        _LOG.debug("getting '%s' (%s) for CPU %d%s", pname, prop["name"], cpu, self._pman.hostmsg)

        if pname == "epp":
            return self._get_eppobj().get_cpu_epp(cpu)
        if pname == "epp_hw":
            return self._get_eppobj().get_cpu_epp_hw(cpu)
        if pname == "epb":
            return self._get_epbobj().get_cpu_epb(cpu)
        if pname == "epb_hw":
            return self._get_epbobj().get_cpu_epb_hw(cpu)
        if pname == "max_eff_freq":
            return self._get_max_eff_freq(cpu)
        if pname == "hwp":
            return self._get_cpu_hwp(cpu)
        if pname == "min_oper_freq":
            return self._get_min_oper_freq(cpu)
        if pname == "max_turbo_freq":
            return self._get_max_turbo_freq(cpu)
        if pname.endswith("_freq_hw"):
            return self._get_cpu_freq_hw(pname, cpu)

        # Properties above have their own cache. Properties below use PStates module cache.
        if self._pcache.is_cached(pname, cpu):
            return self._pcache.get(pname, cpu)

        if "fname" in prop:
            val = self._get_cpu_prop_value_sysfs(prop, cpu)
        elif pname == "turbo":
            val = self._get_cpu_turbo(cpu)
        elif pname == "driver":
            val = self._get_driver(cpu)
        elif pname == "intel_pstate_mode":
            val = self._get_intel_pstate_mode(pname, cpu)
        else:
            raise Error(f"BUG: unsupported property '{pname}'")

        self._pcache.add(pname, cpu, val, sname=prop["sname"])
        return val

    def _set_turbo(self, cpu, enable):
        """Enable or disable turbo."""

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_value("driver", cpu)

        status = "on" if enable else "off"
        errmsg = f"failed to switch turbo {status}{self._pman.hostmsg}"

        if driver == "intel_pstate":
            if self._get_cpu_prop_value("intel_pstate_mode", cpu) == "off":
                raise ErrorNotSupported(f"{errmsg}: 'intel_pstate' driver is in 'off' mode")

            path = self._sysfs_base / "intel_pstate" / "no_turbo"
            sysfs_val = int(not enable)
        elif driver == "acpi-cpufreq":
            path = self._sysfs_base / "cpufreq" / "boost"
            sysfs_val = int(enable)
        else:
            raise ErrorNotSupported(f"{errmsg}: unsupported CPU frequency driver '{driver}'")

        try:
            self._write_prop_value_to_sysfs(self._props["turbo"], path, sysfs_val)
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"{errmsg}: turbo is not supported") from err

        self._pcache.add("turbo", cpu, status, sname=self._props["turbo"]["sname"])

    def _get_num_str(self, prop, cpu):
        """
        If 'prop' has CPU scope, returns "CPU <num>" string. If 'prop' has die scope, returns
        "package <pkgnum> die <dienum>" string.
        """

        if _is_uncore_prop(prop):
            levels = self._cpuinfo.get_cpu_levels(cpu)
            pkg = levels["package"]
            die = levels["die"]
            what = f"package {pkg} die {die}"
        else:
            what = f"CPU {cpu}"

        return what

    def _set_cpu_freq_hw(self, pname, freq, cpu):
        """Set the minimum or maximum CPU frequency by programming 'MSR_HWP_REQUEST'."""

        # The "min" or "max" property name prefix.
        prefix = pname[0:3]
        # The corresponding 'MSR_HWP_REQUEST' feature name.
        fname = f"{prefix}_perf"
        prop = self._props[pname]

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control(fname, cpu)

        hwpreq.write_cpu_feature(fname, int(freq // 100000000), cpu)
        self._pcache.add(pname, cpu, freq, sname=prop["sname"])

    def _write_freq_prop_value_to_sysfs(self, pname, freq, cpu):
        """
        Write frequency value 'freq' of a CPU frequency property 'pname' to the corresponding sysfs
        file.
        """

        prop = self._props[pname]
        path = self._get_sysfs_path(prop, cpu)

        try:
            with self._pman.open(path, "r+") as fobj:
                # Sysfs files use kHz.
                fobj.write(str(freq // 1000))
        except Error as err:
            raise Error(f"failed to set '{prop['name']}'{self._pman.hostmsg}:\n{err.indent(2)}") \
                        from err

        count = 3
        while count > 0:
            # Returns frequency in Hz.
            read_freq = self._read_prop_value_from_sysfs(prop, path)

            if freq == read_freq:
                self._pcache.add(pname, cpu, freq, sname=prop["sname"])
                return

            # Sometimes the update does not happen immediately. For example, we observed this on
            # systems with frequency files when HWP was enabled, for example. Wait a little bit and
            # try again.
            time.sleep(0.1)
            count -= 1

        name = Human.untitle(prop["name"])
        what = self._get_num_str(prop, cpu)
        short_freq = Human.largenum(freq, unit="Hz")
        msg = f"failed to set {name} to {short_freq} for {what}: wrote '{freq // 1000}' to " \
              f"'{path}', but read '{read_freq // 1000}' back."

        bclk = None
        with contextlib.suppress(Error):
            bclk = self._get_bclk(cpu)

        if bclk and freq % (bclk * 1000000):
            msg += f"\nConsider using frequency value aligned to {bclk}MHz."
        elif pname == "max_freq":
            with contextlib.suppress(Error):
                if self._get_cpu_turbo(cpu) == "off":
                    base_freq = self._get_cpu_prop_value("base_freq", cpu)
                    if freq > base_freq:
                        base_freq = Human.largenum(base_freq, unit="Hz")
                        msg += f"\nHint: turbo is disabled, base frequency is {base_freq}, and " \
                               f"this may be the limiting factor."

        raise Error(msg)

    def _parse_freq(self, pname, val, cpu, uncore=False):
        """Turn a user-provided CPU or uncore frequency property value to hertz."""

        if uncore:
            if val == "min":
                freq = self._get_cpu_prop_value("min_uncore_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop_value("max_uncore_freq_limit", cpu)
            else:
                freq = Human.parse_freq(val, name=Human.untitle(self._props[pname]["name"]))
        else:
            if val == "min":
                freq = self._get_cpu_prop_value("min_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop_value("max_freq_limit", cpu)
            elif val in {"base", "hfm", "P1"}:
                freq = self._get_cpu_prop_value("base_freq", cpu)
            elif val in {"eff", "lfm", "Pn"}:
                freq = self._get_cpu_prop_value("max_eff_freq", cpu)
            elif val == "Pm":
                freq = self._get_cpu_prop_value("min_oper_freq", cpu)
            else:
                freq = Human.parse_freq(val, name=Human.untitle(self._props[pname]["name"]))

        if not freq:
            raise ErrorNotSupported(f"'{val}' is not supported{self._pman.hostmsg}")

        return freq

    def _validate_and_set_freq(self, inprops, cpus, freq_type):
        """
        Validate frequency-related properties in 'inprops' and if they are alright, go ahead and set
        them on the target system. This function handles either CPU or uncore frequency.

        If both min frequency and max frequency have to be set, set them in order to never overlap,
        in other words min frequency should never be larger than max frequency and vice versa.

        Example:
         ---- Cur. Min --- Cur. Max -------- New Min --- New Max ----------> (Frequency)

        Make sure we first set the new maximum frequency (New Max):
         ---- Cur. Min --------------------- New Min --- Cur. Max ---------> (Frequency)
        And then new minimum frequency (New Min):
         ----------------------------------- Cur. Min -- Cur. Max ---------> (Frequency)

        Otherwise Cur. Max will be smaller that Cur. Min:
         ----------------- Cur. Max -------- Cur. Min -- New Max ----------> (Frequency)
        """

        if freq_type == "freq":
            uncore = False
            min_freq_key = "min_freq"
            max_freq_key = "max_freq"
            min_freq_limit_key = "min_freq_limit"
            max_freq_limit_key = "max_freq_limit"
            write_func = self._write_freq_prop_value_to_sysfs
        elif freq_type == "freq_hw":
            uncore = False
            min_freq_key = "min_freq_hw"
            max_freq_key = "max_freq_hw"
            min_freq_limit_key = "min_oper_freq"
            max_freq_limit_key = "max_turbo_freq"
            write_func = self._set_cpu_freq_hw
        else:
            uncore = True
            min_freq_key = "min_uncore_freq"
            max_freq_key = "max_uncore_freq"
            min_freq_limit_key = "min_uncore_freq_limit"
            max_freq_limit_key = "max_uncore_freq_limit"
            write_func = self._write_freq_prop_value_to_sysfs

        for cpu in cpus:
            new_min_freq = None
            new_max_freq = None

            if min_freq_key in inprops:
                new_min_freq = self._parse_freq(min_freq_key, inprops[min_freq_key], cpu, uncore)
            if max_freq_key in inprops:
                new_max_freq = self._parse_freq(max_freq_key, inprops[max_freq_key], cpu, uncore)

            cur_min_freq = self._get_cpu_prop_value(min_freq_key, cpu)
            cur_max_freq = self._get_cpu_prop_value(max_freq_key, cpu)

            if not cur_min_freq:
                name = Human.untitle(self._props[max_freq_key]["name"])
                raise ErrorNotSupported(f"CPU {cpu} does not support min. and {name}"
                                        f"{self._pman.hostmsg}")

            min_limit = self._get_cpu_prop_value(min_freq_limit_key, cpu)
            max_limit = self._get_cpu_prop_value(max_freq_limit_key, cpu)

            what = self._get_num_str(self._props[min_freq_key], cpu)
            for pname, val in ((min_freq_key, new_min_freq), (max_freq_key, new_max_freq)):
                if val is None:
                    continue

                if val < min_limit or val > max_limit:
                    name = Human.untitle(self._props[pname]["name"])
                    val = Human.largenum(val, unit="Hz")
                    min_limit = Human.largenum(min_limit, unit="Hz")
                    max_limit = Human.largenum(max_limit, unit="Hz")
                    raise Error(f"{name} value of '{val}' for {what} is out of range, must be "
                                f"within [{min_limit}, {max_limit}]")

            if new_min_freq and new_max_freq:
                if new_min_freq > new_max_freq:
                    name_min = Human.untitle(self._props[min_freq_key]["name"])
                    name_max = Human.untitle(self._props[max_freq_key]["name"])
                    new_min_freq = Human.largenum(new_min_freq, unit="Hz")
                    new_max_freq = Human.largenum(new_max_freq, unit="Hz")
                    raise Error(f"can't set {name_min} to {new_min_freq} and {name_max} to "
                                f"{new_max_freq} for {what}: minimum can't be greater than maximum")
                if new_min_freq != cur_min_freq or new_max_freq != cur_max_freq:
                    if cur_max_freq < new_min_freq:
                        write_func(max_freq_key, new_max_freq, cpu)
                        write_func(min_freq_key, new_min_freq, cpu)
                    else:
                        write_func(min_freq_key, new_min_freq, cpu)
                        write_func(max_freq_key, new_max_freq, cpu)
            elif not new_max_freq:
                if new_min_freq > cur_max_freq:
                    name = Human.untitle(self._props[min_freq_key]["name"])
                    new_min_freq = Human.largenum(new_min_freq, unit="Hz")
                    cur_max_freq = Human.largenum(cur_max_freq, unit="Hz")
                    raise Error(f"can't set {name} of {what} to {new_min_freq} - it is higher than "
                                f"currently configured maximum frequency of {cur_max_freq}")
                if new_min_freq != cur_min_freq:
                    write_func(min_freq_key, new_min_freq, cpu)
            elif not new_min_freq:
                if new_max_freq < cur_min_freq:
                    name = Human.untitle(self._props[max_freq_key]["name"])
                    new_max_freq = Human.largenum(new_max_freq, unit="Hz")
                    cur_min_freq = Human.largenum(cur_min_freq, unit="Hz")
                    raise Error(f"can't set {name} of {what} to {new_max_freq} - it is lower than "
                                f"currently configured minimum frequency of {cur_min_freq}")
                if new_max_freq != cur_max_freq:
                    write_func(max_freq_key, new_max_freq, cpu)

    def _set_intel_pstate_mode(self, cpu, mode):
        """Change mode of the CPU frequency driver 'intel_pstate'."""

        path = self._sysfs_base / "intel_pstate" / "status"
        try:
            self._write_prop_value_to_sysfs(self._props["intel_pstate_mode"], path, mode)
            self._pcache.add("intel_pstate_mode", cpu, mode,
                             sname=self._props["intel_pstate_mode"]["sname"])
        except Error:
            # When 'intel_pstate' driver is 'off' it is not possible to write 'off' again.
            if mode != "off" or self._get_cpu_prop_value("intel_pstate_mode", cpu) != "off":
                raise

    def _validate_intel_pstate_mode(self, mode):
        """Validate 'intel_pstate_mode' mode."""

        if self._get_cpu_prop_value("intel_pstate_mode", 0) is None:
            driver = self._get_cpu_prop_value("driver", 0)
            raise Error(f"can't set property 'intel_pstate_mode'{self._pman.hostmsg}:\n  "
                        f"the CPU frequency driver is '{driver}', not 'inel_pstate'")

        modes = ("active", "passive", "off")
        if mode not in modes:
            modes = ", ".join(modes)
            raise Error(f"bad 'intel_pstate' mode '{mode}', use one of: {modes}")

    def _set_prop_value(self, pname, val, cpus):
        """Sets user-provided property 'pname' to value 'val' for CPUs 'cpus'."""

        # Removing 'cpus' from the cache will make sure the following '_pcache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_pcache.add()'
        # method.
        for cpu in cpus:
            self._pcache.remove(pname, cpu)

        prop = self._props[pname]

        for cpu in cpus:
            if self._pcache.is_cached(pname, cpu):
                if prop["sname"] == "global":
                    break
                continue

            if pname == "turbo":
                self._set_turbo(cpu, val)
            elif pname == "intel_pstate_mode":
                self._set_intel_pstate_mode(cpu, val)
            elif "fname" in prop:
                path = self._get_sysfs_path(prop, cpu)
                self._write_prop_value_to_sysfs(prop, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the 'sname' siblings. For example, if property
                # scope name is "package", 'val' will be cached for all CPUs in the package that
                # contains CPU number 'cpu'.
                self._pcache.add(pname, cpu, val, sname=prop["sname"])
            else:
                raise Error(f"BUG: unsupported property '{pname}'")

    def set_props(self, inprops, cpus="all"):
        """Refer to 'set_props() in '_PCStatesBase' class."""

        inprops = self._normalize_inprops(inprops)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        for pname, val in inprops.items():
            prop = self._props[pname]

            if pname == "governor":
                self._validate_governor_name(val)

            if pname == "intel_pstate_mode":
                self._validate_intel_pstate_mode(val)

            self._validate_cpus_vs_scope(prop, cpus)

            if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
                raise Error(self._uncore_errmsg)

        # Setting frequency may be tricky, because there are ordering constraints, so it is done
        # separately.
        if "min_freq" in inprops or "max_freq" in inprops:
            self._validate_and_set_freq(inprops, cpus, "freq")
        if "min_uncore_freq" in inprops or "max_uncore_freq" in inprops:
            self._validate_and_set_freq(inprops, cpus, "uncore_freq")
        if "min_freq_hw" in inprops or "max_freq_hw" in inprops:
            self._validate_and_set_freq(inprops, cpus, "freq_hw")

        for pname, val in inprops.items():
            if pname in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq",
                         "min_freq_hw", "max_freq_hw"}:
                # Were already set.
                continue

            if pname == "epp":
                self._get_eppobj().set_epp(val, cpus=cpus)
            elif pname == "epp_hw":
                self._get_eppobj().set_epp_hw(val, cpus=cpus)
            elif pname == "epb":
                self._get_epbobj().set_epb(val, cpus=cpus)
            elif pname == "epb_hw":
                self._get_epbobj().set_epb_hw(val, cpus=cpus)
            else:
                self._set_prop_value(pname, val, cpus)

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # These properties are backed by a sysfs file.
        self._props["min_freq"]["fname"] = "scaling_min_freq"
        self._props["max_freq"]["fname"] = "scaling_max_freq"
        self._props["min_freq_limit"]["fname"] = "cpuinfo_min_freq"
        self._props["max_freq_limit"]["fname"] = "cpuinfo_max_freq"
        self._props["base_freq"]["fname"] = "base_frequency"
        self._props["min_uncore_freq"]["fname"] = "min_freq_khz"
        self._props["max_uncore_freq"]["fname"] = "max_freq_khz"
        self._props["min_uncore_freq_limit"]["fname"] = "initial_min_freq_khz"
        self._props["max_uncore_freq_limit"]["fname"] = "initial_max_freq_khz"
        self._props["governor"]["fname"] = "scaling_governor"
        self._props["governor"]["subprops"]["governors"]["fname"] = "scaling_available_governors"

        # Some of the sysfs files may not exist, in which case they can be acquired using the
        # "getter" function. E.g., the "base_frequency" file is specific to the 'intel_pstate'
        # driver.
        self._props["base_freq"]["getter"] = self._get_base_freq

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

        self._eppobj = None
        self._epbobj = None
        self._bclk = {}
        self._pmenable = None
        self._hwpreq = None
        self._hwpreq_pkg = None
        self._platinfo = None
        self._trl = None

        # Will be 'True' if uncore frequency operations are supported, 'False' otherwise.
        self._uncore_freq_supported = None
        self._uncore_errmsg = None
        self._ufreq_drv = None
        self._unload_ufreq_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self._sysfs_base_uncore = Path("/sys/devices/system/cpu/intel_uncore_frequency")

        # The write-through per-CPU properties cache. The properties that are backed by MSR/EPP/EPB
        # are not cached, because they implement their own caching.
        self._enable_cache = enable_cache
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=self._enable_cache)

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_ufreq_drv", None):
            if getattr(self, "_unload_ufreq_drv", None):
                self._ufreq_drv.unload()
                self._unload_ufreq_drv = None
            self._ufreq_drv = None

        close_attrs = ("_eppobj", "_epbobj", "_pmenable", "_hwpreq","_hwpreq_pkg", "_platinfo",
                       "_trl", "_pcache", )
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
