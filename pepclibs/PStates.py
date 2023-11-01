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
from pepclibs.helperlibs import Trivial, KernelModule, FSHelpers, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported

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
        "mnames" : ("sysfs", "msr"),
        "writable" : False,
    },
    "bus_clock" : {
        "name" : "Bus clock speed",
        "unit" : "Hz",
        "type" : "float",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "min_oper_freq" : {
        "name" : "Min. CPU operating frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "mnames" : ("msr", ),
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
        "mnames" : ("msr", ),
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
        """Read bus clock speed from 'MSR_FSB_FREQ' and return it in Hz."""

        try:
            bclk = self._get_fsbfreq().read_cpu_feature("fsb", cpu)
        except ErrorNotSupported:
            # Fall back to 100MHz clock speed.
            if self._cpuinfo.info["vendor"] == "GenuineIntel":
                return 100000000.0
            return None

        # Convert MHz to Hz.
        return bclk * 1000000.0

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

    def _prop_not_supported(self, cpus, mnames, action, what, errors, exception=True):
        """
        Rase an exception or print a debug message from a property "get" or "set" method in a
        situation when the property could not be read or set using mechanisms in 'mnames'
        """

        if len(mnames) > 1:
            mnames_str = f"using {','.join(mnames)} methods"
        else:
            mnames_str = f"using the {mnames[0]} method"

        if len(cpus) > 1:
            cpus_msg = f"the following CPUs: {Human.rangify(cpus)}"
        else:
            cpus_msg = f"for CPU {cpus[0]}"

        if errors:
            sub_errmsgs = "\n" + "\n".join([err.indent(2) for err in errors])
        else:
            sub_errmsgs = ""

        msg = f"cannot {action} {what} {mnames_str} for {cpus_msg}{sub_errmsgs}"
        if exception:
            raise ErrorNotSupported(msg)
        _LOG.debug(msg)

    def __is_uncore_freq_supported(self):
        """Implements '_is_uncore_freq_supported()'."""

        if self._pman.exists(self._sysfs_base_uncore):
            return True

        from pepclibs.msr import UncoreRatioLimit # pylint: disable=import-outside-toplevel

        cpumodel = self._cpuinfo.info["model"]

        # If the CPU supports MSR_UNCORE_RATIO_LIMIT, the uncore frequency driver is
        # "intel_uncore_frequency".
        if cpumodel in UncoreRatioLimit.FEATURES["max_ratio"]["cpumodels"]:
            drvname = "intel_uncore_frequency"
            kopt = "CONFIG_INTEL_UNCORE_FREQ_CONTROL"
            msr_addr = UncoreRatioLimit.MSR_UNCORE_RATIO_LIMIT

            msg = f"Uncore frequency operations are not supported{self._pman.hostmsg}. Here are " \
                  f"the possible reasons:\n" \
                  f" 1. the '{drvname}' driver is not enabled. Try to compile the kernel " \
                  f"with the '{kopt}' option.\n" \
                  f" 2. the kernel is old and does not have the '{drvname}' driver.\n" \
                  f"Address these issues or contact project maintainers and request" \
                  f"implementing uncore frequency support via MSR {msr_addr:#x}"
        else:
            drvname = "intel_uncore_frequency_tpmi"
            kopt = "CONFIG_INTEL_UNCORE_FREQ_CONTROL_TPMI"

            msg = f"Uncore frequency operations are not supported{self._pman.hostmsg}. Here are " \
                  f"the possible reasons:\n" \
                  f" 1. the hardware does not support uncore frequency management.\n" \
                  f" 2. the '{drvname}' driver does not support this hardware.\n" \
                  f" 3. the kernel is old and does not have the '{drvname}' driver. This driver " \
                  f"is supported since kernel version 6.5.\n" \
                  f" 4. the '{drvname}' driver is not enabled. Try to compile the kernel " \
                  f"with the '{kopt}' option"

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

        path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "base_frequency"
        val = self._read_prop_from_sysfs("base_freq", path)
        if val is not None:
            return val

        path = self._sysfs_base / f"cpu{cpu}/cpufreq/bios_limit"
        return self._read_prop_from_sysfs("base_freq", path)

    def _get_base_freq_msr(self, cpu):
        """Read base frequency from sysfs."""

        try:
            platinfo = self._get_platinfo()
            ratio = platinfo.read_cpu_feature("max_non_turbo_ratio", cpu)

            val = self._get_bclk(cpu)
            if val is not None:
                return int(ratio * val)
        except ErrorNotSupported:
            return None

        return None

    def _get_base_freq_pvinfo(self, cpu, mnames):
        """
        Determine the base frequency for the system and return the property value dictionary.
        """

        val, mname = None, None
        prop = self._props["base_freq"]

        for mname in mnames:
            if mname == "sysfs":
                with contextlib.suppress(ErrorNotFound):
                    val, _ = self._pcache.find("base_freq", cpu, mnames=(mname,))
                    return self._construct_pvinfo("base_freq", cpu, mname, val)

                val = self._get_base_freq_sysfs(cpu)
                self._pcache.add("base_freq", cpu, val, mname, sname=prop["sname"])
                if val is not None:
                    break
            elif mname == "msr":
                # The MSR layer has caching, so do not use 'self._pcache'.
                val = self._get_base_freq_msr(cpu)
            else:
                mnames = ",".join(mnames)
                raise Error("BUG: unsupported mechanisms '{mnames}' from 'base_freq' property")

            if val is not None:
                break

        return self._construct_pvinfo("base_freq", cpu, mname, val)

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
            val = int(ratio * val)

        return self._construct_pvinfo("max_eff_freq", cpu, "msr", val)

    def _get_min_oper_freq_pvinfo(self, cpu):
        """
        Read the minimum operating frequency from 'MSR_PLATFORM_INFO' and return the property value
        dictionary.
        """

        try:
            platinfo = self._get_platinfo()
            ratio = platinfo.read_cpu_feature("min_oper_ratio", cpu)
        except ErrorNotSupported:
            return self._construct_pvinfo("min_oper_freq", cpu, "msr", None)

        if ratio != 0:
            val = self._get_bclk(cpu)
            if val is not None:
                val = int(ratio * val)
        else:
            val = None
            _LOG.warn_once("BUG: 'Minimum Operating Ratio' is '0' on CPU %d, MSR address '%#x' "
                            "bit field '55:48'\nPlease, contact project maintainers.",
                            cpu, platinfo.regaddr)

        return self._construct_pvinfo("min_oper_freq", cpu, "msr", val)

    def _get_max_turbo_freq_pvinfo(self, cpu):
        """
        Read the maximum turbo frequency for CPU 'cpu' from 'MSR_TURBO_RATIO_LIMIT' and return the
        property value dictionary.
        """

        try:
            trl = self._get_trl()
        except ErrorNotSupported:
            return self._construct_pvinfo("max_turbo_freq", cpu, "msr", None)

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
                return self._construct_pvinfo("max_turbo_freq", cpu, "msr", None)

        val = self._get_bclk(cpu)
        if val is not None:
            val = int(val * ratio)

        return self._construct_pvinfo("max_turbo_freq", cpu, "msr", val)

    def _get_bus_clock_pvinfo(self, cpu):
        """Read bus clock speed from 'MSR_FSB_FREQ' and return the property value dictionary."""

        val = self._get_bclk(cpu)
        return self._construct_pvinfo("bus_closk", cpu, "msr", val)

    def _read_int(self, path):
        """Read an integer from file 'path' via the process manager."""

        val = self._pman.read(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_turbo_pvinfo(self, cpu):
        """Return property value dictionary for the "trubo" property."""

        val = None

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop("driver", cpu)

        try:
            if driver == "intel_pstate":
                if self._get_cpu_prop("intel_pstate_mode", cpu) == "off":
                    return self._construct_pvinfo("turbo", cpu, "sysfs", None)

                path = self._sysfs_base / "intel_pstate" / "no_turbo"
                disabled = self._read_int(path)
                val = "off" if disabled else "on"

            if driver == "acpi-cpufreq":
                path = self._sysfs_base / "cpufreq" / "boost"
                enabled = self._read_int(path)
                val = "on" if enabled else "off"
        except ErrorNotFound:
            # If the sysfs file does not exist, the system does not support turbo.
            return self._construct_pvinfo("turbo", cpu, "sysfs", None)

        if val is None:
            _LOG.debug("CPU %d: can't check if turbo is enabled%s: unsupported CPU frequency "
                       "driver %s'", cpu, self._pman.hostmsg, driver)

        return self._construct_pvinfo("turbo", cpu, "sysfs", val)

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
        if self._is_uncore_prop(pname):
            levels = self._cpuinfo.get_cpu_levels(cpu, levels=("package", "die"))
            pkg = levels["package"]
            die = levels["die"]
            return self._sysfs_base_uncore / f"package_{pkg:02d}_die_{die:02d}" / prop["fname"]

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / prop["fname"]

    def _get_cpu_prop_pvinfo_sysfs(self, pname, cpu):
        """
        This is a helper for '_get_cpu_prop_pvinfo()' which handles the properties backed by a sysfs
        file.
        """

        if self._is_uncore_prop(pname) and not self._is_uncore_freq_supported():
            _LOG.debug(self._uncore_errmsg)
            return self._construct_pvinfo(pname, cpu, "sysfs", None)

        path = self._get_sysfs_path(pname, cpu)
        val = self._read_prop_from_sysfs(pname, path)
        return self._construct_pvinfo(pname, cpu, "sysfs", val)

    def _get_driver_pvinfo(self, cpu):
        """Read the CPU frequency driver name and return the property value dictionary."""

        pname = "driver"
        path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_driver"

        driver = self._read_prop_from_sysfs(pname, path)
        if driver is None:
            # The 'intel_pstate' driver may be in the 'off' mode, in which case the 'scaling_driver'
            # sysfs file does not exist. So just check if the 'intel_pstate' sysfs directory exists.
            if self._pman.exists(self._sysfs_base / "intel_pstate"):
                return self._construct_pvinfo(pname, cpu, "sysfs", "intel_pstate")

            _LOG.debug("can't read value of property '%s', path '%s' missing", pname, path)
            return self._construct_pvinfo(pname, cpu, "sysfs", None)

        # The 'intel_pstate' driver calls itself 'intel_pstate' when it is in active mode, and
        # 'intel_cpufreq' when it is in passive mode. But we always report the 'intel_pstate' name,
        # because reporting 'intel_cpufreq' is just confusing.
        if driver == "intel_cpufreq":
            driver = "intel_pstate"

        return self._construct_pvinfo(pname, cpu, "sysfs", driver)

    def _get_intel_pstate_mode_pvinfo(self, pname, cpu):
        """
        Read the 'intel_pstate' driver operation mode and return the property value dictionary.
        """

        val = None
        driver = self._get_cpu_prop("driver", cpu)

        if driver == "intel_pstate":
            path = self._sysfs_base / "intel_pstate" / "status"
            val = self._read_prop_from_sysfs(pname, path)

        return self._construct_pvinfo("intel_pstate_mode", cpu, "sysfs", val)

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
            val = freq - (freq % int(val))

        return val

    def _get_cpu_freq_pvinfo(self, pname, cpu, mnames):
        """Read and return the minimum or maximum CPU frequency."""

        for mname in mnames:
            if mname == "msr":
                # Note, MSR modules have built-in caching, so 'self._pcache' is not used.
                val = self._get_cpu_freq_msr(pname, cpu)
                if val is None:
                    continue
                return self._construct_pvinfo(pname, cpu, mname, val)

            if mname == "sysfs":
                with contextlib.suppress(ErrorNotFound):
                    val, mname = self._pcache.find(pname, cpu, mnames=mnames)
                    return self._construct_pvinfo(pname, cpu, mname, val)

                pvinfo = self._get_cpu_prop_pvinfo_sysfs(pname, cpu)
                self._pcache.add(pname, cpu, pvinfo["val"], mname,
                                 sname=self._props[pname]["sname"])

                if pvinfo["val"] is None:
                    continue

                return pvinfo

            raise Error(f"BUG: unexpected mechanism name {mname}")


        self._prop_not_supported((cpu,), mnames, "get", "CPU frequency", [], exception=False)
        return self._construct_pvinfo(pname, cpu, mnames[0], val)

    def _get_epp_epb_pvinfo(self, pname, cpu, mnames):
        """
        Return property value dictionary for EPP or EPB. Return 'None' if 'pname' is not one of the
        EPP/EPB properties.
        """

        val, mname = None, None

        try:
            if pname == "epp":
                cpu, val, mname = self._get_eppobj().get_cpu_val(cpu, mnames=mnames)
            elif pname == "epb":
                cpu, val, mname = self._get_epbobj().get_cpu_val(cpu, mnames=mnames)
            else:
                return None
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return self._construct_pvinfo(pname, cpu, mnames[0], None)

        return self._construct_pvinfo(pname, cpu, mname, val)

    def _get_cpu_prop_pvinfo(self, pname, cpu, mnames=None):
        """
        Return property value dictionary ('pvinfo') for property 'pname', CPU 'cpu', using
        mechanisms in 'mnames'. The arguments and the same as in 'get_prop()'.
        """

        prop = self._props[pname]
        if mnames is None:
            mnames = prop["mnames"]

        # First handle the MSR-based properties. The 'MSR', 'EPP', and 'EPB' modules have their own
        # caching,'self._pcache' is not used for the MSR-based properties.

        pvinfo = self._get_epp_epb_pvinfo(pname, cpu, mnames)
        if pvinfo:
            return pvinfo

        if pname == "max_eff_freq":
            return self._get_max_eff_freq_pvinfo(cpu)
        if pname == "hwp":
            return self._get_hwp_pvinfo(cpu)
        if pname == "min_oper_freq":
            return self._get_min_oper_freq_pvinfo(cpu)
        if pname == "max_turbo_freq":
            return self._get_max_turbo_freq_pvinfo(cpu)
        if pname == "bus_clock":
            return self._get_bus_clock_pvinfo(cpu)
        if pname in {"min_freq", "max_freq"}:
            return self._get_cpu_freq_pvinfo(pname, cpu, mnames)
        if "getter" in prop:
            return prop["getter"](cpu, mnames)

        # All the other properties support only one mechanism - sysfs.
        assert "sysfs" in mnames

        with contextlib.suppress(ErrorNotFound):
            val, mname = self._pcache.find(pname, cpu, mnames=mnames)
            return self._construct_pvinfo(pname, cpu, mname, val)

        if "fname" in prop:
            pvinfo = self._get_cpu_prop_pvinfo_sysfs(pname, cpu)
        elif pname == "turbo":
            pvinfo = self._get_turbo_pvinfo(cpu)
        elif pname == "driver":
            pvinfo = self._get_driver_pvinfo(cpu)
        elif pname == "intel_pstate_mode":
            pvinfo = self._get_intel_pstate_mode_pvinfo(pname, cpu)
        else:
            raise Error(f"BUG: unsupported property '{pname}'")

        self._pcache.add(pname, cpu, pvinfo["val"], pvinfo["mname"], sname=prop["sname"])
        return pvinfo

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

        raise_error = True

        name = Human.uncapitalize(pname)
        what = self._get_num_str(pname, cpu)
        short_freq = Human.num2si(freq, unit="Hz")
        msg = f"failed to set {name} to {short_freq} for {what}{self._pman.hostmsg}: wrote " \
              f"'{freq // 1000}' to '{path}', but read '{read_freq // 1000}' back."

        with contextlib.suppress(Error):
            bclk = self._get_bclk(cpu)
            if bclk and freq % bclk:
                msg += f"\nHint: consider using frequency value aligned to {bclk // 1000000}MHz."

            if self._get_turbo_pvinfo(cpu)["val"] == "off":
                base_freq = self._get_cpu_prop("base_freq", cpu)

                if base_freq and freq > base_freq:
                    base_freq = Human.num2si(base_freq, unit="Hz")
                    msg += f"\nHint: turbo is disabled, base frequency is {base_freq}, and this " \
                           f"may be the limiting factor."

            if self._cpuinfo.info["vendor"] == "AuthenticAMD":
                # This is a limited quirk for an AMD system. It does not allow setting max.frequency
                # to any value above base frequency. At the moment we do not support reading base
                # frequency for AMD systems, so we only support the 'freq == max_freq_limit' case.
                # But it should really be 'if freq > base_freq'.
                max_freq_limit = self._get_cpu_prop("max_freq_limit", cpu)
                driver = self._get_cpu_prop("driver", cpu)
                if freq == max_freq_limit and driver == "acpi-cpufreq":
                    msg += "\nThis is expected 'acpi-cpufreq' driver behavior on AMD systems."
                    raise_error = False

        if raise_error:
            raise Error(msg)

        _LOG.debug(msg)

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

    def _set_own_prop(self, pname, val, cpus):
        """
        Sets property 'pname'. The 'own' part in function name refers to the fact that this
        method sets only properties implemented by this module, as opposed to properties like "epp",
        which are implemented by the 'EPP' module.
        """

        # All properties use the 'sysfs' mechanism at the moment.
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

    def _set_freq_props(self, min_freq, max_freq, cpus, mname, min_freq_pname, max_freq_pname,
                        min_freq_limit_pname, max_freq_limit_pname, uncore, write_func):
        """Implements 'set_freq_props()."""

        for cpu in cpus:
            new_min_freq = None
            new_max_freq = None

            if min_freq:
                new_min_freq = self._parse_freq(min_freq, cpu, uncore)
            if max_freq:
                new_max_freq = self._parse_freq(max_freq, cpu, uncore)

            cur_min_freq = self._get_cpu_prop(min_freq_pname, cpu, mnames=(mname,))
            cur_max_freq = self._get_cpu_prop(max_freq_pname, cpu, mnames=(mname,))

            if not cur_min_freq:
                name = Human.uncapitalize(self._props[max_freq_pname]["name"])
                raise ErrorNotSupported(f"CPU {cpu} does not support min. and {name}"
                                        f"{self._pman.hostmsg}")

            min_limit = self._get_cpu_prop(min_freq_limit_pname, cpu, mnames=(mname,))
            max_limit = self._get_cpu_prop(max_freq_limit_pname, cpu, mnames=(mname,))

            what = self._get_num_str(min_freq_pname, cpu)
            for pname, val in ((min_freq_pname, new_min_freq), (max_freq_pname, new_max_freq)):
                if val is None:
                    continue

                if val < min_limit or val > max_limit:
                    name = Human.uncapitalize(self._props[pname]["name"])
                    val = Human.num2si(val, unit="Hz")
                    min_limit = Human.num2si(min_limit, unit="Hz")
                    max_limit = Human.num2si(max_limit, unit="Hz")
                    raise ErrorFreqRange(f"{name} value of '{val}' for {what} is out of range, "
                                         f"must be within [{min_limit}, {max_limit}]")

            if new_min_freq and new_max_freq:
                if new_min_freq > new_max_freq:
                    name_min = Human.uncapitalize(self._props[min_freq_pname]["name"])
                    name_max = Human.uncapitalize(self._props[max_freq_pname]["name"])
                    new_min_freq = Human.num2si(new_min_freq, unit="Hz")
                    new_max_freq = Human.num2si(new_max_freq, unit="Hz")
                    raise Error(f"can't set {name_min} to {new_min_freq} and {name_max} to "
                                f"{new_max_freq} for {what}: minimum can't be greater than maximum")
                if new_min_freq != cur_min_freq or new_max_freq != cur_max_freq:
                    if cur_max_freq < new_min_freq:
                        write_func(max_freq_pname, new_max_freq, cpu)
                        write_func(min_freq_pname, new_min_freq, cpu)
                    else:
                        write_func(min_freq_pname, new_min_freq, cpu)
                        write_func(max_freq_pname, new_max_freq, cpu)
            elif not new_max_freq:
                if new_min_freq > cur_max_freq:
                    name = Human.uncapitalize(self._props[min_freq_pname]["name"])
                    new_min_freq = Human.num2si(new_min_freq, unit="Hz")
                    cur_max_freq = Human.num2si(cur_max_freq, unit="Hz")
                    raise ErrorFreqOrder(f"can't set {name} of {what} to {new_min_freq} - it is "
                                         f"higher than currently configured maximum frequency of "
                                         f"{cur_max_freq}")
                if new_min_freq != cur_min_freq:
                    write_func(min_freq_pname, new_min_freq, cpu)
            elif not new_min_freq:
                if new_max_freq < cur_min_freq:
                    name = Human.uncapitalize(self._props[max_freq_pname]["name"])
                    new_max_freq = Human.num2si(new_max_freq, unit="Hz")
                    cur_min_freq = Human.num2si(cur_min_freq, unit="Hz")
                    raise ErrorFreqOrder(f"can't set {name} of {what} to {new_max_freq} - it is "
                                         f"lower than currently configured minimum frequency of "
                                         f"{cur_min_freq}")
                if new_max_freq != cur_max_freq:
                    write_func(max_freq_pname, new_max_freq, cpu)

    def set_freq_props(self, min_freq, max_freq, cpus, freq_type="core", mnames=None):
        """
        Set minimum and maximum frequency properties. The arguments are as follows:
          * min_freq - minimum frequency value to set (can be in Human form, like 1GHz). Value
                       'None' means that minimum frequency should not be set.
          * max_freq - maximum frequency value to set.
          * cpus - collection of integer CPU numbers to set the frequencies for. Special value 'all'
                   means "all CPUs".
          * freq_type - defines the frequency properties that should be set. Here are the allowed
                        values:
                          o "core" - set 'min_freq' and 'max_freq' properties.
                          o "uncore" - set 'min_uncore_freq' and 'max_uncore_freq' properties.

        The reason this method exists is because the order the frequency properties are set matters.
        Otherwise, just 'set_prop()' would be enough. This method is basically like 'set_prop()',
        but it sets the frequency limits in the correct order.

        Raise 'ErrorFreqOrder' if only one frequency is provided (either 'min_freq' is 'None' or
        'max_freq' is 'None'), but it cannot be set because of the ordering constraints.

        Here is an example illustrating why order matters. Suppose current min. and max. frequencies
        and new min. and max. frequencies are as follows:
         ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->

        Where the dotted line represents the horizontal frequency axis. Setting min. frequency
        before max frequency leads to a failure. Indeed, at step #2 current minimum frequency would
        be set to a value higher that current maximum frequency.
         1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
         2. ----------------- Cur. Max -------- Cur. Min -- New Max ---------->

        If max. frequency is set first, the operation succeeds.
        Make sure we first set the new maximum frequency (New Max):
         1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
         2. ---- Cur. Min --------------------- New Min --- Cur. Max --------->
         3. ----------------------------------- Cur. Min -- Cur. Max --------->
        """

        if not min_freq and not max_freq:
            raise Error("BUG: provide at least one frequency value")

        cpus = self._cpuinfo.normalize_cpus(cpus)

        errors = []

        if freq_type == "core":
            uncore = False
            min_freq_pname = "min_freq"
            max_freq_pname = "max_freq"
        elif freq_type == "uncore":
            uncore = True
            min_freq_pname = "min_uncore_freq"
            max_freq_pname = "max_uncore_freq"
        else:
            raise Error(f"BUG: bad requency type {freq_type}")

        if min_freq:
            min_freq = self._normalize_inprop(min_freq_pname, min_freq)
            self._set_sname(min_freq_pname)
            self._validate_cpus_vs_scope(min_freq_pname, cpus)
            mnames = self._normalize_mnames(mnames, pname=min_freq_pname, allow_readonly=False)

        if max_freq:
            max_freq = self._normalize_inprop(max_freq_pname, max_freq)
            self._set_sname(max_freq_pname)
            self._validate_cpus_vs_scope(max_freq_pname, cpus)
            mnames = self._normalize_mnames(mnames, pname=max_freq_pname, allow_readonly=False)

        for mname in mnames:
            if uncore:
                min_freq_limit_pname = "min_uncore_freq_limit"
                max_freq_limit_pname = "max_uncore_freq_limit"
                write_func = self._write_freq_prop_to_sysfs
            else:
                if mname == "sysfs":
                    min_freq_limit_pname = "min_freq_limit"
                    max_freq_limit_pname = "max_freq_limit"
                    write_func = self._write_freq_prop_to_sysfs
                elif mname == "msr":
                    min_freq_limit_pname = "min_oper_freq"
                    max_freq_limit_pname = "max_turbo_freq"
                    write_func = self._write_freq_prop_to_msr

            if min_freq:
                min_freq = self._normalize_inprop(min_freq_pname, min_freq)
                self._set_sname(min_freq_pname)
                self._validate_cpus_vs_scope(min_freq_pname, cpus)
                self._normalize_mnames(mnames, pname=min_freq_pname, allow_readonly=False)

            if max_freq:
                max_freq = self._normalize_inprop(max_freq_pname, max_freq)
                self._set_sname(max_freq_pname)
                self._validate_cpus_vs_scope(max_freq_pname, cpus)
                self._normalize_mnames(mnames, pname=max_freq_pname, allow_readonly=False)

            try:
                self._set_freq_props(min_freq, max_freq, cpus, mname, min_freq_pname,
                                     max_freq_pname, min_freq_limit_pname, max_freq_limit_pname,
                                     uncore, write_func)

            except (ErrorNotSupported, ErrorFreqRange) as err:
                errors.append(err)
                continue

            return mname

        # Raise an 'ErrorNotSupported' exception.
        self._prop_not_supported(cpus, mnames, "set", f"{freq_type} frequency", errors)

    def _set_prop(self, pname, val, cpus, mnames=None):
        """Refer to '_PropsClassBase.PropsClassBase.set_prop()'."""

        if pname == "min_freq":
            return self.set_freq_props(val, None, cpus, freq_type="core", mnames=mnames)
        if pname == "max_freq":
            return self.set_freq_props(None, val, cpus, freq_type="core", mnames=mnames)
        if pname == "min_uncore_freq":
            return self.set_freq_props(val, None, cpus, freq_type="uncore", mnames=mnames)
        if pname == "max_uncore_freq":
            return self.set_freq_props(None, val, cpus, freq_type="uncore", mnames=mnames)

        if pname == "governor":
            self._validate_governor_name(val)
        elif pname == "intel_pstate_mode":
            self._validate_intel_pstate_mode(val)
        elif self._is_uncore_prop(pname) and not self._is_uncore_freq_supported():
            raise Error(self._uncore_errmsg)

        if pname == "epp":
            return self._get_eppobj().set_vals(val, cpus=cpus, mnames=mnames)
        if pname == "epb":
            return self._get_epbobj().set_vals(val, cpus=cpus, mnames=mnames)

        return self._set_own_prop(pname, val, cpus)

    def _set_sname(self, pname):
        """Set scope "sname" for property 'pname'."""

        if self._props[pname]["sname"]:
            return

        if pname == "epb":
            try:
                _epb = self._get_epbobj() # pylint: disable=protected-access
            except Error:
                self._props[pname]["sname"] = "CPU"
            else:
                self._props[pname]["sname"] = _epb.sname
        elif pname == "bus_clock":
            self._props[pname]["sname"] = self._get_fsbfreq().features["fsb"]["sname"]
        else:
            raise Error(f"BUG: couldn't get scope for property '{pname}'")

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # Some properties are read/written to using different mechanisms ("sysfs", "msr", etc),
        # depending on configurations. Properties like this have a dedicated "getter" method.
        self._props["base_freq"]["getter"] = self._get_base_freq_pvinfo

        # Properties backed by a single sysfs file.
        self._props["min_freq"]["fname"] = "scaling_min_freq"
        self._props["max_freq"]["fname"] = "scaling_max_freq"
        self._props["min_freq_limit"]["fname"] = "cpuinfo_min_freq"
        self._props["max_freq_limit"]["fname"] = "cpuinfo_max_freq"
        self._props["min_uncore_freq"]["fname"] = "min_freq_khz"
        self._props["max_uncore_freq"]["fname"] = "max_freq_khz"
        self._props["min_uncore_freq_limit"]["fname"] = "initial_min_freq_khz"
        self._props["max_uncore_freq_limit"]["fname"] = "initial_max_freq_khz"
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

        # Will be 'True' if uncore frequency operations are supported, 'False' otherwise.
        self._uncore_freq_supported = None
        self._uncore_errmsg = None
        self._ufreq_drv = None
        self._unload_ufreq_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self._sysfs_base_uncore = Path("/sys/devices/system/cpu/intel_uncore_frequency")

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        if self._unload_ufreq_drv:
            self._ufreq_drv.unload()

        close_attrs = ("_eppobj", "_epbobj", "_pmenable", "_hwpreq", "_hwpreq_pkg", "_platinfo",
                       "_trl", "_fsbfreq", "_ufreq_drv")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
