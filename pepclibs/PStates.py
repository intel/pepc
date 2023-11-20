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

import time
import logging
import contextlib
import statistics
from pathlib import Path
from pepclibs import _PCStatesBase
from pepclibs.helperlibs import Trivial, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

class ErrorFreqOrder(Error):
    """
    An exception indicating that min. or max. frequency modification failed for the ordering
    reasons.
    """

class ErrorFreqRange(Error):
    """An exception indicating that min. or max. frequency values are out of the allowed range."""

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
        "sname": "CPU",
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

    def _get_bclk(self, cpu):
        """
        Return bus clock speed in Hz. Return 'None' if bus clock is not supported by the platform.
        """

        try:
            bclk = self._get_fsbfreq().read_cpu_feature("fsb", cpu)
        except ErrorNotSupported:
            # Fall back to 100MHz clock speed.
            if self._cpuinfo.info["vendor"] == "GenuineIntel":
                return 100000000
            return None

        # Convert MHz to Hz.
        return int(bclk * 1000000)

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

    def _get_uncfreq_obj(self):
        """Return an 'UncoreFreq' object."""

        if not self._uncfreq_obj:
            from pepclibs import _UncoreFreq # pylint: disable=import-outside-toplevel

            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreq(cpuinfo=self._cpuinfo, pman=self._pman,
                                                           enable_cache=self._enable_cache)
            except ErrorNotSupported as err:
                self._uncfreq_err = err

        return self._uncfreq_obj

    def _prop_not_supported(self, cpus, mnames, action, what, exceptions=None, exc_type=None):
        """
        Rase an exception or print a debug message from a property "get" or "set" method in a
        situation when the property could not be read or set using mechanisms in 'mnames'
        """

        if len(mnames) > 2:
            mnames_quoted = [f"'{mname}'" for mname in mnames]
            mnames_str = f"using {', '.join(mnames_quoted[:-1])} and {mnames_quoted[-1]} methods"
        elif len(mnames) == 2:
            mnames_str = f"using '{mnames[0]}' and '{mnames[1]}' methods"
        else:
            mnames_str = f"using the '{mnames[0]}' method"

        if len(cpus) > 1:
            cpus_msg = f"the following CPUs: {Human.rangify(cpus)}"
        else:
            cpus_msg = f"for CPU {cpus[0]}"

        if exceptions:
            errmsgs = Trivial.list_dedup([str(err) for err in exceptions])
            errmsgs = "\n" + "\n".join([Error(errmsg).indent(2) for errmsg in errmsgs])
        else:
            errmsgs = ""

        msg = f"cannot {action} {what} {mnames_str} for {cpus_msg}{errmsgs}"
        if exceptions:
            if exc_type:
                raise exc_type(msg)
            raise type(exceptions[0])(msg)
        _LOG.debug(msg)

    def _read_cppc_sysfs_file(self, fname, cpu):
        """Read an ACPI CPPC sysfs file."""

        val = None
        path = self._sysfs_base / f"cpu{cpu}/acpi_cppc" / fname

        try:
            val = self._read_int(path)
        except ErrorNotFound as err:
            _LOG.debug(err)
        except Error as err:
            _LOG.debug(err)
            _LOG.warn_once("ACPI CPPC sysfs file '%s' is not readable%s", path, self._pman.hostmsg)

        return val

    def _get_cppc_freq_sysfs(self, pname, cpu):
        """Read the ACPI CPPC sysfs files for property 'pname' and CPU 'cpu'."""

        mname = "cppc"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=(mname,))
            return val

        val = None

        if pname == "base_freq":
            val = self._read_cppc_sysfs_file("nominal_freq", cpu)
            if val:
                val *= 1000 * 1000
                self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
                return val

        base_freq = self._get_base_freq_pvinfo(cpu)["val"]
        if base_freq is None:
            return None

        nominal_perf = self._read_cppc_sysfs_file("nominal_perf", cpu)
        if nominal_perf is not None:
            if pname in ("max_turbo_freq"):
                highest_perf = self._read_cppc_sysfs_file("highest_perf", cpu)
                if highest_perf is not None:
                    val = int((base_freq * highest_perf) / nominal_perf)
            elif pname == "min_oper_freq":
                lowest_perf = self._read_cppc_sysfs_file("lowest_perf", cpu)
                if lowest_perf is not None:
                    val = int((base_freq * lowest_perf) / nominal_perf)

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return val

    def _get_cpu_perf_to_freq_factor(self, cpu):
        """
        In HWP mode, the OS can affect CPU frequency via HWP registers, such as 'IA32_HWP_REQUEST'.
        However, these HWP registers work in terms of performance, not in terms of frequency. On
        many CPUs, the performance is just frequency in 100MHz. However, on hybrid CPUs like
        Alder Lake, the performance must be scaled by ~7.8740157. In general, future CPUs may have
        use a different formula.

        Return integer factor, so that CPU performance multiplied by this factor results in CPU
        frequency in Hz.
        """

        if self._cpuinfo.info["hybrid"]:
            pcore_cpus = set(self._cpuinfo.get_hybrid_cpu_topology()["pcore"])
            if cpu in pcore_cpus:
                return 78740157

        return 100000000

    def _get_base_freq_sysfs(self, cpu):
        """Read base frequency from sysfs."""

        mname = "sysfs"
        pname = "base_freq"

        with contextlib.suppress(ErrorNotFound):
            val, _ = self._pcache.find(pname, cpu, mnames=(mname,))
            return val

        val = self._get_cpu_prop_pvinfo_sysfs(pname, cpu)["val"]
        if val is None:
            path = self._sysfs_base / f"cpu{cpu}/cpufreq/bios_limit"
            val = self._read_prop_from_sysfs(pname, path)

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return val

    def _get_base_freq_msr(self, cpu):
        """Read base frequency from sysfs."""

        try:
            platinfo = self._get_platinfo()
            ratio = platinfo.read_cpu_feature("max_non_turbo_ratio", cpu)

            val = self._get_bclk(cpu)
            if val is not None:
                return ratio * val
        except ErrorNotSupported:
            return None

        return None

    def _get_base_freq_pvinfo(self, cpu, mnames=None):
        """
        Determine the base frequency for the system and return the property value dictionary.
        """

        pname = "base_freq"
        val, mname = None, None

        if not mnames:
            mnames = self._props["base_freq"]["mnames"]

        for mname in mnames:
            if mname == "sysfs":
                val = self._get_base_freq_sysfs(cpu)
            elif mname == "msr":
                val = self._get_base_freq_msr(cpu)
            elif mname == "cppc":
                val = self._get_cppc_freq_sysfs(pname, cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "base CPU frequency")
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_max_eff_freq_pvinfo(self, cpu):
        """
        Read max. efficiency frequency from 'MSR_PLATFORM_INFO' and return the property value
        dictionary.
        """

        try:
            platinfo = self._get_platinfo()
            ratio = platinfo.read_cpu_feature("max_eff_ratio", cpu)
        except ErrorNotSupported:
            return self._construct_pvinfo("max_eff_freq", cpu, "msr", None)

        val = self._get_bclk(cpu)
        if val is not None:
            val = ratio * val

        return self._construct_pvinfo("max_eff_freq", cpu, "msr", val)

    def _get_min_oper_freq_msr(self, cpu):
        """
        Read the minimum operating frequency from 'MSR_PLATFORM_INFO' and return the property value
        dictionary.
        """

        try:
            platinfo = self._get_platinfo()
            ratio = platinfo.read_cpu_feature("min_oper_ratio", cpu)
        except ErrorNotSupported:
            return None

        if ratio != 0:
            val = self._get_bclk(cpu)
            if val is not None:
                val = ratio * val
        else:
            val = None
            _LOG.warn_once("BUG: 'Minimum Operating Ratio' is '0' on CPU %d, MSR address '%#x' "
                            "bit field '55:48'\nPlease, contact project maintainers.",
                            cpu, platinfo.regaddr)

        return val

    def _get_min_oper_freq_pvinfo(self, cpu, mnames):
        """Read the minimum operating frequency and return the property value dictionary."""

        pname = "min_oper_freq"
        val, mname = None, None

        if not mnames:
            mnames = self.props[pname]["mnames"]

        for mname in mnames:
            if mname == "msr":
                val = self._get_min_oper_freq_msr(cpu)
            elif mname == "cppc":
                val = self._get_cppc_freq_sysfs(pname, cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "min. operational frequency")
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_max_turbo_freq_msr(self, cpu):
        """
        Read the maximum turbo frequency for CPU 'cpu' from 'MSR_TURBO_RATIO_LIMIT' and return the
        property value dictionary.
        """

        try:
            trl = self._get_trl()
        except ErrorNotSupported:
            return None

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

        val = self._get_bclk(cpu)
        if val is not None:
            val = val * ratio

        return val

    def _get_max_turbo_freq_pvinfo(self, cpu, mnames=None):
        """Read the maximum turbo frequency for CPU 'cpu'."""

        pname = "max_turbo_freq"
        val, mname = None, None

        if not mnames:
            mnames = self._props[pname]["mnames"]

        for mname in mnames:
            if mname == "msr":
                val = self._get_max_turbo_freq_msr(cpu)
            elif mname == "cppc":
                val = self._get_cppc_freq_sysfs(pname, cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "max. CPU turbo frequency")
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_bus_clock_msr(self, cpu):
        """
        Read bus clock speed from 'MSR_FSB_FREQ' and return the value in Hz. Return 'None' if the
        MSR is not supported.

        Note: the difference between this method and '_get_bclk()' is that this method returns
        'None' for intel platforms that do not support 'MSR_FSB_FREQ'.
        """

        try:
            val = self._get_fsbfreq().read_cpu_feature("fsb", cpu)
        except ErrorNotSupported:
            return None

        return int(val * 1000000)

    def _get_bus_clock_intel(self, cpu):
        """
        Return bus clock speed in 'Hz' for Intel platforms that do not support 'MSR_FSB_FREQ'.
        Return 'None' for non-Intel platforms and for Intel platforms that do support
        'MSR_FSB_FREQ'.
        """

        pname = "bus_clock"
        mname = "doc"
        val = None

        with contextlib.suppress(ErrorNotFound):
            val, _ = self._pcache.find(pname, cpu, mnames=(mname,))
            return val

        if self._cpuinfo.info["vendor"] == "GenuineIntel":
            val = self._get_bus_clock_msr(cpu)
            if val is None:
                # Modern Intel platforms use 100MHz bus clock.
                val = 100000000

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return val

    def _get_bus_clock_pvinfo(self, cpu, mnames=None):
        """Read bus clock speed and return the property value dictionary."""

        pname = "bus_clock"
        val, mname = None, None

        if not mnames:
            mnames = self._props[pname]["mnames"]

        for mname in mnames:
            if mname == "msr":
                val = self._get_bus_clock_msr(cpu)
            elif mname == "doc":
                val = self._get_bus_clock_intel(cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "bus clock speed")
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _read_int(self, path):
        """Read an integer from file 'path' via the process manager."""

        val = self._pman.read(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_turbo_pvinfo(self, cpu):
        """Return property value dictionary for the "turbo" property."""

        pname = "turbo"
        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=(mname,))
            return self._construct_pvinfo(pname, cpu, mname, val)

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop("driver", cpu)

        try:
            if driver == "intel_pstate":
                if self._get_cpu_prop("intel_pstate_mode", cpu) == "off":
                    return self._construct_pvinfo(pname, cpu, mname, None)

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

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_frequencies_sysfs(self, cpu):
        """
        Get the list of available CPU frequency values for CPU 'cpu' from a Linux 'sysfs' file,
        which is provided by the 'acpi-cpufreq' driver.
        """

        pname = "frequencies"

        path = self._get_sysfs_path(pname, cpu)
        val = self._read_prop_from_sysfs(pname, path)
        if not val:
            return None

        freqs = []
        for freq in val.split():
            try:
                freq = Trivial.str_to_int(freq, what="CPU frequency value")
                freqs.append(freq * 1000)
            except Error as err:
                raise Error(f"bad contents of file '{path}'{self._pman.hostmsg}\n  {err}") from err

        return sorted(freqs)

    def _get_frequencies_intel(self, cpu):
        """Get the list of available CPU frequency values for CPU 'cpu' for an Intel platform."""

        driver = self._get_cpu_prop("driver", cpu)
        if driver != "intel_pstate":
            # Only 'intel_pstate' was verified to accept any frequency value that is multiple of bus
            # clock.
            return None

        bclk = self._get_bclk(cpu)
        if bclk is None:
            return None

        min_freq = self._get_cpu_prop_pvinfo_sysfs("min_freq", cpu)["val"]
        max_freq = self._get_cpu_prop_pvinfo_sysfs("max_freq", cpu)["val"]
        if min_freq is None or max_freq is None:
            return None

        freqs = []
        freq = min_freq
        while freq <= max_freq:
            freqs.append(freq)
            freq += bclk
        return freqs

    def _get_frequencies_pvinfo(self, cpu, mnames=None):
        """Get the list of acceptable CPU frequency values for CPU 'cpu'."""

        pname = "frequencies"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=mnames)
            return self._construct_pvinfo(pname, cpu, mname, val)

        mname, val = None, None
        if not mnames:
            mnames = self._props[pname]["mnames"]

        for mname in mnames:
            if mname == "sysfs":
                val = self._get_frequencies_sysfs(cpu)
            elif mname == "doc":
                val = self._get_frequencies_intel(cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "acceptable frequencies")

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_hwp_pvinfo(self, cpu):
        """Return property value dictionary for the "hwp" property."""

        val = None
        try:
            pmenable = self._get_pmenable()
            val = pmenable.is_cpu_feature_enabled("hwp", cpu)
        except ErrorNotSupported:
            pass

        return self._construct_pvinfo("hwp", cpu, "msr", val)

    def _get_sysfs_path(self, pname, cpu):
        """
        Construct and return path to the sysfs file for property 'pname' and CPU 'cpu'.
        """

        prop = self._props[pname]

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / prop["fname"]

    def _get_cpu_prop_pvinfo_sysfs(self, pname, cpu):
        """
        This is a helper for '_get_cpu_prop_pvinfo()' which handles the properties backed by a sysfs
        file.
        """

        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=(mname,))
            return self._construct_pvinfo(pname, cpu, mname, val)

        path = self._get_sysfs_path(pname, cpu)
        val = self._read_prop_from_sysfs(pname, path)

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_driver_pvinfo(self, cpu):
        """Read the CPU frequency driver name and return the property value dictionary."""

        pname = "driver"
        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=(mname,))
            return self._construct_pvinfo(pname, cpu, mname, val)

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

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_intel_pstate_mode_pvinfo(self, pname, cpu):
        """
        Read the 'intel_pstate' driver operation mode and return the property value dictionary.
        """

        mname = "sysfs"

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=(mname,))
            return self._construct_pvinfo(pname, cpu, mname, val)

        driver = self._get_cpu_prop("driver", cpu)
        if driver == "intel_pstate":
            path = self._sysfs_base / "intel_pstate" / "status"
            val = self._read_prop_from_sysfs(pname, path)
        else:
            val = None

        self._pcache.add(pname, cpu, val, mname, sname=self._props[pname]["sname"])
        return self._construct_pvinfo("intel_pstate_mode", cpu, mname, val)

    def _get_uncore_freq_pvinfo(self, pname, cpu):
        """Read and return the minimum or maximum uncore frequnecy."""

        self._uncfreq_obj = self._get_uncfreq_obj()

        val = None
        if self._uncfreq_obj:
            if pname == "min_uncore_freq":
                val = self._uncfreq_obj.get_min_freq(cpu)
            elif pname == "max_uncore_freq":
                val = self._uncfreq_obj.get_max_freq(cpu)
            elif pname == "min_uncore_freq_limit":
                val = self._uncfreq_obj.get_min_freq_limit(cpu)
            elif pname == "max_uncore_freq_limit":
                val = self._uncfreq_obj.get_max_freq_limit(cpu)
            else:
                raise Error(f"BUG: unexpected uncore frequency property {pname}")

        return self._construct_pvinfo(pname, cpu, "sysfs", val)

    def _get_cpu_freq_msr(self, pname, cpu):
        """Read and return the minimum or maximum CPU frequency from 'MSR_HWP_REQUEST'."""

        # The "min" or "max" property name prefix.
        prefix = pname[0:3]
        # The corresponding 'MSR_HWP_REQUEST' feature name.
        fname = f"{prefix}_perf"

        try:
            hwpreq = self._get_hwpreq()
        except ErrorNotSupported:
            return None

        if hwpreq.is_cpu_feature_pkg_controlled(fname, cpu):
            hwpreq = self._get_hwpreq_pkg()

        try:
            perf = hwpreq.read_cpu_feature(fname, cpu)
        except ErrorNotSupported:
            _LOG.debug("CPU %d: HWP %s performance is not supported", cpu, prefix)
            return None

        freq = perf * self._get_cpu_perf_to_freq_factor(cpu)

        val = self._get_bclk(cpu)
        if val is not None:
            # Round the frequency down to bus clock.
            # * Why rounding? Bus clock is normally the minimum CPU frequency change value.
            # * Why rounding down? Following how Linux 'intel_pstate' driver example.
            val = freq - (freq % val)

        return val

    def _get_cpu_freq_pvinfo(self, pname, cpu, mnames=None):
        """Read and return the minimum or maximum CPU frequency."""

        mname, val = None, None
        if not mnames:
            mnames = self._props[pname]["mnames"]

        for mname in mnames:
            if mname == "sysfs":
                val = self._get_cpu_prop_pvinfo_sysfs(pname, cpu)["val"]
            elif mname == "msr":
                val = self._get_cpu_freq_msr(pname, cpu)
            else:
                mnames = ",".join(mnames)
                raise Error(f"BUG: unsupported mechanisms '{mnames}' for '{pname}'")

            if val is not None:
                break

        if val is None:
            self._prop_not_supported((cpu,), mnames, "get", "CPU frequency")
        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_epp_pvinfo(self, pname, cpu, mnames):
        """Return property value dictionary for EPP."""

        val, mname = None, None

        try:
            cpu, val, mname = self._get_eppobj().get_cpu_val(cpu, mnames=mnames)
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return self._construct_pvinfo(pname, cpu, mnames[0], None)

        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_epb_pvinfo(self, pname, cpu, mnames):
        """Return property value dictionary for EPB."""

        val, mname = None, None

        try:
            cpu, val, mname = self._get_epbobj().get_cpu_val(cpu, mnames=mnames)
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return self._construct_pvinfo(pname, cpu, mnames[0], None)

        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_cpu_prop_pvinfo(self, pname, cpu, mnames=None):
        """
        Return property value dictionary ('pvinfo') for property 'pname', CPU 'cpu', using
        mechanisms in 'mnames'. The arguments and the same as in 'get_prop_cpus()'.
        """

        prop = self._props[pname]
        if not mnames:
            mnames = prop["mnames"]

        if pname == "epp":
            return self._get_epp_pvinfo(pname, cpu, mnames)
        if pname == "epb":
            return self._get_epb_pvinfo(pname, cpu, mnames)
        if pname == "max_eff_freq":
            return self._get_max_eff_freq_pvinfo(cpu)
        if pname == "hwp":
            return self._get_hwp_pvinfo(cpu)
        if pname == "min_oper_freq":
            return self._get_min_oper_freq_pvinfo(cpu, mnames=mnames)
        if pname == "max_turbo_freq":
            return self._get_max_turbo_freq_pvinfo(cpu, mnames=mnames)
        if pname == "bus_clock":
            return self._get_bus_clock_pvinfo(cpu, mnames=mnames)
        if pname in {"min_freq", "max_freq"}:
            return self._get_cpu_freq_pvinfo(pname, cpu, mnames=mnames)
        if pname == "base_freq":
            return self._get_base_freq_pvinfo(cpu, mnames=mnames)
        if pname == "turbo":
            return self._get_turbo_pvinfo(cpu)
        if pname == "frequencies":
            return self._get_frequencies_pvinfo(cpu, mnames=mnames)
        if pname == "driver":
            return self._get_driver_pvinfo(cpu)
        if self._is_uncore_prop(pname):
            return self._get_uncore_freq_pvinfo(pname, cpu)
        if "fname" in prop:
            return self._get_cpu_prop_pvinfo_sysfs(pname, cpu)
        if pname == "intel_pstate_mode":
            return self._get_intel_pstate_mode_pvinfo(pname, cpu)

        raise Error(f"BUG: unsupported property '{pname}'")

    def _set_turbo(self, cpu, enable):
        """Enable or disable turbo."""

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop("driver", cpu)

        status = "on" if enable else "off"
        errmsg = f"failed to switch turbo {status}{self._pman.hostmsg}"

        if driver == "intel_pstate":
            if self._get_cpu_prop("intel_pstate_mode", cpu) == "off":
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

        self._pcache.add("turbo", cpu, status, "sysfs", sname=self._props["turbo"]["sname"])

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

    def _write_freq_prop_to_msr(self, pname, freq, cpu):
        """Write the minimum or maximum CPU frequency by programming 'MSR_HWP_REQUEST'."""

        # The "min" or "max" property name prefix.
        prefix = pname[0:3]
        # The corresponding 'MSR_HWP_REQUEST' feature name.
        fname = f"{prefix}_perf"

        factor = self._get_cpu_perf_to_freq_factor(cpu)
        # Round the resulting performance the same way as Linux 'intel_pstate' driver does it.
        perf = int((freq + factor - 1) / factor)

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control(fname, cpu)
        hwpreq.write_cpu_feature(fname, perf, cpu)

    def _handle_write_and_read_freq_mismatch(self, pname, freq, read_freq, cpu, path):
        """
        This is a helper function fo '_write_freq_prop_to_sysfs()' and it is called when there
        is a mismatch between what was written to a frequency sysfs file and what was read back.
        """

        name = Human.uncapitalize(pname)
        what = self._get_num_str(pname, cpu)
        freq_human = Human.num2si(freq, unit="Hz", decp=4)
        msg = f"failed to set {name} to {freq_human} for {what}{self._pman.hostmsg}: wrote " \
              f"'{freq // 1000}' to '{path}', but read '{read_freq // 1000}' back."

        with contextlib.suppress(Error):
            frequencies = self._get_frequencies_pvinfo(cpu)["val"]
            if frequencies:
                frequencies_set = set(frequencies)
                if freq not in frequencies_set and read_freq in frequencies_set:
                    fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                    msg += f"\n  Linux kernel frequency driver does not support {freq_human}, " \
                           f"use one of the following values instead:\n  {fvals}"
            elif self._get_turbo_pvinfo(cpu)["val"] == "off":
                base_freq = self._get_cpu_prop("base_freq", cpu)
                if base_freq and freq > base_freq:
                    base_freq = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f"\nHint: turbo is disabled, base frequency is {base_freq}, and this " \
                           f"may be the limiting factor."

        raise ErrorVerifyFailed(msg)

    def _write_freq_prop_to_sysfs(self, pname, freq, cpu):
        """
        Write the minimum or maximum CPU or uncore frequency value 'freq' to the corresponding sysfs
        file.
        """

        path = self._get_sysfs_path(pname, cpu)

        try:
            with self._pman.open(path, "r+") as fobj:
                # Sysfs files use kHz.
                fobj.write(str(freq // 1000))
        except Error as err:
            raise Error(f"failed to set '{pname}'{self._pman.hostmsg}:\n{err.indent(2)}") \
                        from err

        count = 3
        while count > 0:
            # Returns frequency in Hz.
            read_freq = self._read_prop_from_sysfs(pname, path)
            if freq == read_freq:
                self._pcache.add(pname, cpu, freq, "sysfs", sname=self._props[pname]["sname"])
                return

            # Sometimes the update does not happen immediately. For example, we observed this on
            # systems with frequency files when HWP was enabled, for example. Wait a little bit and
            # try again.
            time.sleep(0.1)
            count -= 1

        self._handle_write_and_read_freq_mismatch(pname, freq, read_freq, cpu, path)

    def _write_uncore_freq_prop(self, pname, freq, cpu):
        """Write uncore frequency property."""

        self._uncfreq_obj = self._get_uncfreq_obj()

        if self._uncfreq_err:
            raise ErrorNotSupported(self._uncfreq_err)

        if pname == "min_uncore_freq":
            self._uncfreq_obj.set_min_freq(freq, cpu)
        elif pname == "max_uncore_freq":
            self._uncfreq_obj.set_max_freq(freq, cpu)
        else:
            raise Error(f"BUG: unexpected uncore frequency property {pname}")

    def _parse_freq(self, val, cpu, uncore=False):
        """Turn a user-provided CPU or uncore frequency property value to hertz."""

        if uncore:
            if val == "min":
                freq = self._get_cpu_prop("min_uncore_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop("max_uncore_freq_limit", cpu)
            elif val == "mdl":
                min_freq = self._get_cpu_prop("min_uncore_freq_limit", cpu)
                max_freq = self._get_cpu_prop("max_uncore_freq_limit", cpu)
                freq = round(statistics.mean([min_freq, max_freq]), -2)
            else:
                freq = val
        else:
            if val == "min":
                freq = self._get_cpu_prop("min_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop("max_freq_limit", cpu)
            elif val in {"base", "hfm", "P1"}:
                freq = self._get_cpu_prop("base_freq", cpu)
            elif val in {"eff", "lfm", "Pn"}:
                freq = self._get_cpu_prop("max_eff_freq", cpu)
                if not freq:
                    # Max. efficiency frequency may not be supported by the platform. Fall back to
                    # the minimum frequency in this case.
                    freq = self._get_cpu_prop("min_freq_limit", cpu)
            elif val == "Pm":
                freq = self._get_cpu_prop("min_oper_freq", cpu)
            else:
                freq = val

        if not freq:
            raise ErrorNotSupported(f"'{val}' is not supported{self._pman.hostmsg}")

        return freq

    def _set_intel_pstate_mode(self, cpu, mode):
        """Change mode of the CPU frequency driver 'intel_pstate'."""

        # Setting 'intel_pstate' driver mode to "off" is only possible in non-HWP (legacy) mode.
        if mode == "off" and self._get_cpu_prop("hwp", cpu) == "on":
            raise ErrorNotSupported("'intel_pstate' driver does not support \"off\" mode when "
                                    "hardware power management (HWP) is enabled")

        path = self._sysfs_base / "intel_pstate" / "status"
        try:
            self._write_prop_to_sysfs("intel_pstate_mode", path, mode)
            self._pcache.add("intel_pstate_mode", cpu, mode, "sysfs",
                             sname=self._props["intel_pstate_mode"]["sname"])
        except Error:
            # When 'intel_pstate' driver is 'off' it is not possible to write 'off' again.
            if mode != "off" or self._get_cpu_prop("intel_pstate_mode", cpu) != "off":
                raise

    def _validate_intel_pstate_mode(self, mode):
        """Validate 'intel_pstate_mode' mode."""

        if self._get_cpu_prop("intel_pstate_mode", 0) is None:
            driver = self._get_cpu_prop("driver", 0)
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
                path = self._get_sysfs_path(pname, cpu)
                self._write_prop_to_sysfs(pname, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the 'sname' siblings. For example, if property
                # scope name is "package", 'val' will be cached for all CPUs in the package that
                # contains CPU number 'cpu'.
                self._pcache.add(pname, cpu, val, mname, sname=prop["sname"])
            else:
                raise Error(f"BUG: unsupported property '{pname}'")

        return mname

    def __set_freq_prop(self, pname, val, cpus, mname):
        """Implements '_set_freq_prop()."""

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
                write_func = self._write_freq_prop_to_sysfs
            elif mname == "msr":
                min_freq_limit_pname = "min_oper_freq"
                max_freq_limit_pname = "max_turbo_freq"
                write_func = self._write_freq_prop_to_msr

        for cpu in cpus:
            new_freq = self._parse_freq(val, cpu, is_uncore)

            min_limit = self._get_cpu_prop(min_freq_limit_pname, cpu, mnames=(mname,))
            if not min_limit:
                _raise_not_supported(min_freq_limit_pname)
            max_limit = self._get_cpu_prop(max_freq_limit_pname, cpu, mnames=(mname,))
            if not max_limit:
                _raise_not_supported(max_freq_limit_pname)

            if new_freq < min_limit or new_freq > max_limit:
                _raise_out_of_range(pname, new_freq, min_limit, max_limit)

            if is_min:
                cur_max_freq = self._get_cpu_prop(max_freq_pname, cpu, mnames=(mname,))
                if not cur_max_freq:
                    _raise_not_supported(max_freq_pname)

                if new_freq > cur_max_freq:
                    # New min. frequency cannot be set to a value larger than current max.
                    # frequency.
                    _raise_order(pname, new_freq, cur_max_freq, is_min)

                write_func(pname, new_freq, cpu)
            else:
                cur_min_freq = self._get_cpu_prop(min_freq_pname, cpu, mnames=(mname,))
                if not cur_min_freq:
                    _raise_not_supported(min_freq_pname)

                if new_freq < cur_min_freq:
                    # New max. frequency cannot be set to a value smaller than current min.
                    # frequency.
                    _raise_order(pname, new_freq, cur_min_freq, is_min)

                write_func(pname, new_freq, cpu)

    def _set_freq_prop(self, pname, val, cpus, mnames=None):
        """Set core or uncore frequency property 'pname'."""

        if not mnames:
            mnames = self._props[pname]["mnames"]

        not_supported_exceptions = []
        freq_range_exceptions = []

        for mname in mnames:
            try:
                self.__set_freq_prop(pname, val, cpus, mname)
            except ErrorNotSupported as err:
                not_supported_exceptions.append(err)
                continue
            except ErrorFreqRange as err:
                # Different methods have different ranges, so continue.
                freq_range_exceptions.append(err)
                continue

            return mname

        if freq_range_exceptions:
            exceptions = freq_range_exceptions
            exc_type = ErrorFreqRange
        else:
            exceptions = not_supported_exceptions
            exc_type = ErrorNotSupported

        freq_type = "uncore" if "uncore" in pname else "core"
        self._prop_not_supported(cpus, mnames, "set", f"{freq_type} frequency",
                                 exceptions=exceptions, exc_type=exc_type)

    def _set_prop_cpus(self, pname, val, cpus, mnames=None):
        """Refer to '_PropsClassBase.PropsClassBase.set_prop_cpus()'."""

        if pname == "governor":
            self._validate_governor_name(val)
        elif pname == "intel_pstate_mode":
            self._validate_intel_pstate_mode(val)

        if pname == "epp":
            return self._get_eppobj().set_vals(val, cpus=cpus, mnames=mnames)
        if pname == "epb":
            return self._get_epbobj().set_vals(val, cpus=cpus, mnames=mnames)

        if pname in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
            return self._set_freq_prop(pname, val, cpus, mnames=mnames)

        return self._set_prop_sysfs(pname, val, cpus)

    def _set_sname(self, pname):
        """Set scope name for property 'pname'."""

        prop = self._props[pname]
        if prop["sname"]:
            return

        try:
            if pname == "epb":
                epbobj = self._get_epbobj() # pylint: disable=protected-access
                prop["sname"] = epbobj.sname
            elif pname == "bus_clock":
                try:
                    fsbfreq = self._get_fsbfreq()
                    prop["sname"] = fsbfreq.features["fsb"]["sname"]
                except ErrorNotSupported:
                    prop["sname"] = "global"
        except Error:
            prop["sname"] = "CPU"

        self.props[pname]["sname"] = prop["sname"]

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # Properties backed by a single sysfs file (only simple cases).
        #
        # Note, not all properties that may be backed by a sysfs file have "fname". For example,
        # "turbo" does not, because the sysfs knob path depends on what frequency driver is used.
        self._props["min_freq"]["fname"] = "scaling_min_freq"
        self._props["max_freq"]["fname"] = "scaling_max_freq"
        self._props["min_freq_limit"]["fname"] = "cpuinfo_min_freq"
        self._props["max_freq_limit"]["fname"] = "cpuinfo_max_freq"
        self._props["base_freq"]["fname"] = "base_frequency"
        self._props["frequencies"]["fname"] = "scaling_available_frequencies"
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
        self._hwpreq = None
        self._hwpreq_pkg = None
        self._platinfo = None
        self._trl = None

        self._uncfreq_obj = None
        self._uncfreq_err = None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_eppobj", "_epbobj", "_pmenable", "_hwpreq", "_hwpreq_pkg", "_platinfo",
                       "_trl", "_fsbfreq", "_uncfreq_obj")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
