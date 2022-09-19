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
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs import KernelModule, FSHelpers, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs import _PCStatesBase

_LOG = logging.getLogger()

# This dictionary describes the CPU properties this module supports.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'PStates' objects. Use the full dictionary via
# 'PStates.props'.
PROPS = {
    "min_freq" : {
        "name" : "Minimum CPU frequency",
        "help" : "Minimum frequency the operating system will configure the CPU to run at.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "max_freq" : {
        "name" : "Maximum CPU frequency",
        "help" : "Maximum frequency the operating system will configure the CPU to run at.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "min_freq_limit" : {
        "name" : "Minimum supported CPU frequency",
        "help" : "Minimum supported CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "max_freq_limit" : {
        "name" : "Maximum supported CPU frequency",
        "help" : "Maximum supported CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "base_freq" : {
        "name" : "Base CPU frequency",
        "help" : "Base CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "max_eff_freq" : {
        "name" : "Maximum CPU efficiency frequency",
        "help" : "Maximum energy efficient CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "turbo" : {
        "name" : "Turbo",
        "help" : """When turbo is enabled, the CPUs can automatically run at a frequency greater
                    than base frequency.""",
        "type" : "bool",
        "sname": "global",
        "writable" : True,
    },
    "max_turbo_freq" : {
        "name" : "Maximum CPU turbo frequency",
        "help" : "Maximum frequency CPU can run at in turbo mode.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "CPU",
        "writable" : False,
    },
    "min_uncore_freq" : {
        "name" : "Minimum uncore frequency",
        "help" : "Minimum frequency the operating system will configure the uncore to run at.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : True,
    },
    "max_uncore_freq" : {
        "name" : "Maximum uncore frequency",
        "help" : "Maximum frequency the operating system will configure the uncore to run at.",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : True,
    },
    "min_uncore_freq_limit" : {
        "name" : "Minimum supported uncore frequency",
        "help" : "Minimum supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : False,
    },
    "max_uncore_freq_limit" : {
        "name" : "Maximum supported uncore frequency",
        "help" : "Maximum supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "sname": "die",
        "writable" : False,
    },
    "hwp" : {
        "name" : "Hardware power mangement",
        "help" : """When hardware power management is enabled, CPUs can automatically scale their
                    frequency without active OS involvement.""",
        "type" : "bool",
        "sname": "global",
        "writable" : False,
    },
    "epp" : {
        "name" : "Energy Performance Preference",
        "help" : """Energy Performance Preference (EPP) is a hint to the CPU on energy efficiency vs
                    performance. EPP has an effect only when the CPU is in the hardware power
                    management (HWP) mode.""",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "epp_policy" : {
        "name" : "EPP policy",
        "help" : """EPP policy is a name, such as 'performance', which Linux maps to an EPP value,
                    which may depend on the platform.""",
        "type" : "str",
        "sname": "CPU",
        "writable" : True,
        "subprops" : {
            "epp_policies" : {
                "name" : "Available EPP policies",
                "help" : "Available Linux EPP policy names.",
                "type" : "list[str]",
                "sname": "global",
                "writable" : False,
            },
        },
    },
    "epb" : {
        "name" : "Energy Performance Bias",
        "help" : """Energy Performance Bias (EPB) is a hint to the CPU on energy efficiency vs
                    performance. Value 0 means maximum performance, value 15 means maximum energy
                    efficiency. EPP may have an effect in both HWP enabled and disabled modes (HWP
                    stands for Hardware Power Management).""",
        "type" : "int",
        "sname": "CPU",
        "writable" : True,
    },
    "epb_policy" : {
        "name" : "EPB policy",
        "help" : """EPB policy is a name, such as 'performance', which Linux maps to an EPB value,
                    which may depend on the platform.""",
        "type" : "str",
        "sname": "CPU",
        "writable" : True,
        "subprops" : {
            "epb_policies" : {
                "name" : "Available EPB policies",
                "help" : "Available Linux EPB policy names.",
                "type" : "list[str]",
                "writable" : False,
                "sname": "global",
            },
        },
    },
    "driver" : {
        "name" : "CPU frequency driver",
        "help" : """CPU frequency driver enumerates and requests the P-states available on the
                    platform.""",
        "type" : "str",
        "sname": "global",
        "writable" : False,
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
            from pepclibs.msr import MSR #pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

        return self._msr

    def _get_eppobj(self):
        """Returns an 'EPP.EPP()' object."""

        if not self._eppobj:
            from pepclibs import EPP #pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._eppobj

    def _get_epbobj(self):
        """Returns an 'EPB.EPB()' object."""

        if not self._epbobj:
            from pepclibs import EPB #pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._epbobj = EPB.EPB(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._epbobj

    def _get_bclk(self, cpu):
        """Discover bus clock speed."""

        if cpu not in self._bclk:
            from pepclibs import BClock #pylint: disable=import-outside-toplevel

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

    def _get_base_eff_freqs(self, cpu):
        """
        Read and return a tuple of the following CPU 'cpu' frequencies.
          * The base frequency ("base_freq").
          * Max. efficiency frequency ("max_eff_freq").

        The frequencies are read from 'MSR_PLATFORM_INFO'.
        """

        bclk = self._get_bclk(cpu)
        platinfo = self._get_platinfo()

        ratio = platinfo.read_cpu_feature("max_non_turbo_ratio", cpu)
        base = int(ratio * bclk * 1000 * 1000)

        max_eff_freq = None
        if platinfo.is_cpu_feature_supported("max_eff_ratio", cpu):
            ratio = platinfo.read_cpu_feature("max_eff_ratio", cpu)
            max_eff_freq = int(ratio * bclk * 1000 * 1000)

        return base, max_eff_freq

    def _get_max_turbo_freq_freq(self, cpu):
        """
        Read and return the maximum turbo frequency for CPU 'cpu' from 'MSR_TURBO_RATIO_LIMIT'.
        """

        bclk = self._get_bclk(cpu)
        trl = self._get_trl()

        ratio = None

        if trl.is_cpu_feature_supported("max_1c_turbo_ratio", cpu):
            ratio = trl.read_cpu_feature("max_1c_turbo_ratio", 0)
        elif trl.is_cpu_feature_supported("max_g0_turbo_ratio", cpu):
            # In this case 'MSR_TURBO_RATIO_LIMIT' encodes max. turbo ratio for groups of cores. We
            # can safely assume that group 0 will correspond to max. 1-core turbo, so we do not need
            # to look at 'MSR_TURBO_RATIO_LIMIT1'.
            ratio = trl.read_cpu_feature("max_g0_turbo_ratio", cpu)
        else:
            _LOG.warn_once("CPU %d: module 'TurboRatioLimit' doesn't support "
                           "'MSR_TURBO_RATIO_LIMIT' for CPU '%s'%s\nPlease, contact project "
                           "maintainers.", cpu, self._cpuinfo.cpudescr, self._pman.hostmsg)

        max_turbo_freq = None
        if ratio is not None:
            max_turbo_freq = int(ratio * bclk * 1000 * 1000)

        return max_turbo_freq

    def _is_turbo_supported(self, cpu):
        """Returns 'True' if turbo is supported and 'False' otherwise."""

        base_freq = self._get_cpu_prop_value("base_freq", cpu)
        max_turbo_freq = self._get_cpu_prop_value("max_turbo_freq", cpu)

        # Just a sanity check.
        if max_turbo_freq < base_freq:
            max_turbo_freq = Human.largenum(max_turbo_freq, unit="Hz")
            base_freq =Human.largenum(base_freq, unit="Hz")
            _LOG.warning("something is not right: max. turbo frequency %s is lower than base "
                         "frequency %s%s", max_turbo_freq, base_freq, self._pman.hostmsg)

        return max_turbo_freq is not None or max_turbo_freq > base_freq

    def _get_cpu_turbo(self, cpu):
        """
        Returns "on" if turbo is enabled, "off" if it is disabled, and 'None' if it is not
        supported.
        """

        if not self._is_turbo_supported(cpu):
            return None

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_value("driver", cpu)

        try:
            if driver in {"intel_pstate", "intel_cpufreq"}:
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
        if not pmenable.is_cpu_feature_supported("hwp", cpu):
            return None
        return "on" if pmenable.is_cpu_feature_enabled("hwp", cpu) else "off"

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

    def _read_int(self, path):
        """Read an integer from file 'path' via the process manager."""

        val = self._pman.read(path).strip()
        if not Trivial.is_int(val):
            raise Error(f"read an unexpected non-integer value from '{path}'"
                        f"{self._pman.hostmsg}")
        return int(val)

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        if prop is None:
            prop = self._props[pname]

        _LOG.debug("getting '%s' (%s) for CPU %d%s", pname, prop["name"], cpu, self._pman.hostmsg)

        if pname.startswith("epp"):
            obj = self._get_eppobj()
            return getattr(obj, f"get_cpu_{pname}")(cpu, True)

        if pname.startswith("epb"):
            obj = self._get_epbobj()
            return getattr(obj, f"get_cpu_{pname}")(cpu)

        if self._pcache.is_cached(pname, cpu):
            return self._pcache.get(pname, cpu)

        if "fname" in prop:
            if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
                _LOG.debug(self._uncore_errmsg)
                return None

            path = self._get_sysfs_path(prop, cpu)
            try:
                val = self._read_prop_value_from_sysfs(prop, path)
                self._pcache.add(pname, cpu, val, sname=prop["sname"])
                return val
            except ErrorNotFound:
                # The sysfs file was not found. The base frequency can be figured out from the MSR
                # registers.
                if pname != "base_freq":
                    path = self._get_sysfs_path(prop, cpu)
                    _LOG.debug("can't read value of property '%s', path '%s' is not found",
                               pname, path)
                    return None

        if pname in ("base_freq", "max_eff_freq"):
            base, max_eff_freq = self._get_base_eff_freqs(cpu)
            self._pcache.add("base_freq", cpu, base, sname=self._props["base_freq"]["sname"])
            self._pcache.add("max_eff_freq", cpu, max_eff_freq,
                             sname=self._props["max_eff_freq"]["sname"])
            if pname == "base_freq":
                return base
            return max_eff_freq

        if pname == "hwp":
            hwp = self._get_cpu_hwp(cpu)
            self._pcache.add("hwp", cpu, hwp, sname=prop["sname"])
            return hwp

        if pname == "max_turbo_freq":
            max_turbo_freq = self._get_max_turbo_freq_freq(cpu)
            if max_turbo_freq is None:
                # Assume that max. turbo is the Linux max. frequency.
                path = self._get_sysfs_path(self._props["max_freq"], cpu)
                max_turbo_freq = self._read_prop_value_from_sysfs(prop, path)
            self._pcache.add("max_turbo_freq", cpu, max_turbo_freq, sname=prop["sname"])
            return max_turbo_freq

        if pname == "turbo":
            turbo = self._get_cpu_turbo(cpu)
            self._pcache.add("turbo", cpu, turbo, sname=prop["sname"])
            return turbo

        raise Error(f"BUG: unsupported property '{pname}'")

    def _set_turbo(self, cpu, enable):
        """Enable or disable turbo."""

        if not self._is_turbo_supported(cpu):
            raise ErrorNotSupported(f"turbo is not supported{self._pman.hostmsg}")

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop_value("driver", cpu)

        if driver in {"intel_pstate", "intel_cpufreq"}:
            path = self._sysfs_base / "intel_pstate" / "no_turbo"
            self._write_prop_value_to_sysfs(self._props["turbo"], path, int(not enable))
        elif driver == "acpi-cpufreq":
            path = self._sysfs_base / "cpufreq" / "boost"
            self._write_prop_value_to_sysfs(self._props["turbo"], path, int(enable))
        else:
            raise Error(f"failed to enable or disable turbo{self._pman.hostmsg}: unsupported CPU "
                        f"frequency driver '{driver}'")

        self._pcache.add("turbo", cpu, "on" if enable else "off",
                         sname=self._props["turbo"]["sname"])

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

    def _write_freq_prop_value_to_sysfs(self, pname, freq, cpu):
        """
        Write frequency value 'freq' of a CPU frequency property 'pname' to the corresponding sysfs
        file.
        """

        prop = self._props[pname]
        path = self._get_sysfs_path(prop, cpu)

        # Sysfs files use kHz.
        self._pman.write(path, str(freq // 1000))

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

        if pname == "max_freq":
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
            if val in {"min", "lfm"}:
                freq = self._get_cpu_prop_value("min_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop_value("max_freq_limit", cpu)
            elif val in {"base", "hfm"}:
                freq = self._get_cpu_prop_value("base_freq", cpu)
            elif val == "eff":
                freq = self._get_cpu_prop_value("max_eff_freq", cpu)
            else:
                freq = Human.parse_freq(val, name=Human.untitle(self._props[pname]["name"]))

        return freq

    def _validate_and_set_freq(self, inprops, cpu, uncore=False):
        """
        Validate frequency-related properties in 'inprops' and if they are alright, go ahead and set
        them on the target system. This function handles either CPU or uncore frequency, depending
        on the 'uncore' argument.

        If both min frequency and max frequency have to be set, set them in order to never overlap,
        in other words min frequency should never be larger than max frequency and vice versa.

        Example:
         ---- Cur. Min --- Cur. Max -------- New Min --- New Max ----------> (Frequency)

        Make sure we first set the new maximum frequency (New Max):
         ---- Cur. Min --------------------- New Min --- Cur. Max ---------> (Frequency)
        And then new minimum frequency (New Min):
         ----------------------------------- Cur. Min -- Cur. Max ---------> (Frequency)

        Otherwise Cur. Max will be smaler that Cur. Min:
         ----------------- Cur. Max -------- Cur. Min -- New Max ----------> (Frequency)
        """

        if uncore:
            min_freq_key = "min_uncore_freq"
            max_freq_key = "max_uncore_freq"
            min_freq_limit_key = "min_uncore_freq_limit"
            max_freq_limit_key = "max_uncore_freq_limit"
        else:
            min_freq_key = "min_freq"
            max_freq_key = "max_freq"
            min_freq_limit_key = "min_freq_limit"
            max_freq_limit_key = "max_freq_limit"

        new_min_freq = None
        new_max_freq = None

        if min_freq_key in inprops:
            new_min_freq = self._parse_freq(min_freq_key, inprops[min_freq_key], cpu, uncore=uncore)
        if max_freq_key in inprops:
            new_max_freq = self._parse_freq(max_freq_key, inprops[max_freq_key], cpu, uncore=uncore)

        cur_min_freq = self._get_cpu_prop_value(min_freq_key, cpu)
        cur_max_freq = self._get_cpu_prop_value(max_freq_key, cpu)

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
                raise Error(f"{name} value of '{val}' for {what} is out of range, must be within "
                            f"[{min_limit}, {max_limit}]")

        if min_freq_key in inprops and max_freq_key in inprops:
            if new_min_freq > new_max_freq:
                name_min = Human.untitle(self._props[min_freq_key]["name"])
                name_max = Human.untitle(self._props[max_freq_key]["name"])
                new_min_freq = Human.largenum(new_min_freq, unit="Hz")
                new_max_freq = Human.largenum(new_max_freq, unit="Hz")
                raise Error(f"can't set {name_min} to {new_min_freq} and {name_max} to "
                            f"{new_max_freq} for {what}: minimum can't be greater than maximum")
            if new_min_freq != cur_min_freq or new_max_freq != cur_max_freq:
                if cur_max_freq < new_min_freq:
                    self._write_freq_prop_value_to_sysfs(max_freq_key, new_max_freq, cpu)
                    self._write_freq_prop_value_to_sysfs(min_freq_key, new_min_freq, cpu)
                else:
                    self._write_freq_prop_value_to_sysfs(min_freq_key, new_min_freq, cpu)
                    self._write_freq_prop_value_to_sysfs(max_freq_key, new_max_freq, cpu)
        elif max_freq_key not in inprops:
            if new_min_freq > cur_max_freq:
                name = Human.untitle(self._props[min_freq_key]["name"])
                new_min_freq = Human.largenum(new_min_freq, unit="Hz")
                cur_max_freq = Human.largenum(cur_max_freq, unit="Hz")
                raise Error(f"can't set {name} of {what} to {new_min_freq} - it is higher than "
                            f"currently configured maximum frequency of {cur_max_freq}")
            if new_min_freq != cur_min_freq:
                self._write_freq_prop_value_to_sysfs(min_freq_key, new_min_freq, cpu)
        elif min_freq_key not in inprops:
            if new_max_freq < cur_min_freq:
                name = Human.untitle(self._props[max_freq_key]["name"])
                new_max_freq = Human.largenum(new_max_freq, unit="Hz")
                cur_min_freq = Human.largenum(cur_min_freq, unit="Hz")
                raise Error(f"can't set {name} of {what} to {new_max_freq} - it is lower than "
                            f"currently configured minimum frequency of {cur_min_freq}")
            if new_max_freq != cur_max_freq:
                self._write_freq_prop_value_to_sysfs(max_freq_key, new_max_freq, cpu)

    def _set_prop_value(self, pname, val, cpus):
        """Sets user-provided property 'pname' to value 'val' for CPUs 'cpus'."""

        if pname.startswith("epp"):
            self._get_eppobj().set_epp(val, cpus=cpus)
            return

        if pname.startswith("epb"):
            self._get_epbobj().set_epb(val, cpus=cpus)
            return

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
                self._set_turbo(cpu, val in {True, "on", "enable"})
            elif "fname" in prop:
                path = self._get_sysfs_path(prop, cpu)
                self._write_prop_value_to_sysfs(prop, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the "fellow" CPUs. For example, if property scope
                # name is "package", 'val' will be cached for all CPUs in the package that contains
                # CPU number 'cpu'.
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

            if prop.get("type") == "bool":
                self._validate_bool_type_value(prop, val)

            self._validate_cpus_vs_scope(prop, cpus)

            if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
                raise Error(self._uncore_errmsg)

        # Setting frequency may be tricky, because there are ordering constraints, so it is done
        # separately.
        if "min_freq" in inprops or "max_freq" in inprops:
            for cpu in cpus:
                self._validate_and_set_freq(inprops, cpu, uncore=False)
        if "min_uncore_freq" in inprops or "max_uncore_freq" in inprops:
            for cpu in cpus:
                self._validate_and_set_freq(inprops, cpu, uncore=True)

        for pname, val in inprops.items():
            if pname in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
                # Were already set.
                continue

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
        self._props["driver"]["fname"] = "scaling_driver"
        self._props["governor"]["fname"] = "scaling_governor"
        self._props["governor"]["subprops"]["governors"]["fname"] = "scaling_available_governors"

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
        self._pcache = _PropsCache._PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                               enable_cache=self._enable_cache)

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_ufreq_drv", None):
            if getattr(self, "_unload_ufreq_drv", None):
                self._ufreq_drv.unload()
                self._unload_ufreq_drv = None
            self._ufreq_drv = None

        close_attrs = ("_eppobj", "_epbobj", "_pmenable", "_platinfo", "_trl", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
