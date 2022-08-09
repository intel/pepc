# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
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
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs import KernelModule, FSHelpers, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs import _PCStatesBase, _Common

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
        "scope": "CPU",
        "writable" : True,
    },
    "max_freq" : {
        "name" : "Maximum CPU frequency",
        "help" : "Maximum frequency the operating system will configure the CPU to run at.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : True,
    },
    "min_freq_limit" : {
        "name" : "Minimum supported CPU frequency",
        "help" : "Minimum supported CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : False,
    },
    "max_freq_limit" : {
        "name" : "Maximum supported CPU frequency",
        "help" : "Maximum supported CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : False,
    },
    "base_freq" : {
        "name" : "Base CPU frequency",
        "help" : "Base CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : False,
    },
    "max_eff_freq" : {
        "name" : "Maximum CPU efficiency frequency",
        "help" : "Maximum energy efficient CPU frequency.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : False,
    },
    "turbo" : {
        "name" : "Turbo",
        "help" : """When turbo is enabled, the CPUs can automatically run at a frequency greater
                    than base frequency.""",
        "type" : "bool",
        "scope": "global",
        "writable" : True,
    },
    "max_turbo_freq" : {
        "name" : "Maximum CPU turbo frequency",
        "help" : "Maximum frequency CPU can run at in turbo mode.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "CPU",
        "writable" : False,
    },
    "min_uncore_freq" : {
        "name" : "Minimum uncore frequency",
        "help" : "Minimum frequency the operating system will configure the uncore to run at.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "die",
        "writable" : True,
    },
    "max_uncore_freq" : {
        "name" : "Maximum uncore frequency",
        "help" : "Maximum frequency the operating system will configure the uncore to run at.",
        "unit" : "Hz",
        "type" : "int",
        "scope": "die",
        "writable" : True,
    },
    "min_uncore_freq_limit" : {
        "name" : "Minimum supported uncore frequency",
        "help" : "Minimum supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "scope": "die",
        "writable" : False,
    },
    "max_uncore_freq_limit" : {
        "name" : "Maximum supported uncore frequency",
        "help" : "Maximum supported uncore frequency",
        "unit" : "Hz",
        "type" : "int",
        "scope": "die",
        "writable" : False,
    },
    "hwp" : {
        "name" : "Hardware power mangement",
        "help" : """When hardware power management is enabled, CPUs can automatically scale their
                    frequency without active OS involemenent.""",
        "type" : "bool",
        "scope": "global",
        "writable" : False,
    },
    "epp" : {
        "name" : "Energy Performance Preference",
        "help" : """Energy Performance Preference (EPP) is a hint to the CPU on energy efficiency vs
                    performance. EPP has an effect only when the CPU is in the hardware power
                    management (HWP) mode.""",
        "type" : "int",
        "scope": "CPU",
        "writable" : True,
    },
    "epp_policy" : {
        "name" : "EPP policy",
        "help" : """EPP policy is a name, such as 'performance', which Linux maps to an EPP value,
                    which may depend on the platform.""",
        "type" : "str",
        "scope": "CPU",
        "writable" : True,
        "subprops" : {
            "epp_policies" : {
                "name" : "Available EPP policies",
                "help" : "Available Linux EPP policy names.",
                "type" : "list[str]",
                "scope": "global",
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
        "type" : "str",
        "scope": "CPU",
        "writable" : True,
    },
    "epb_policy" : {
        "name" : "EPB policy",
        "help" : """EPB policy is a name, such as 'performance', which Linux maps to an EPB value,
                    which may depend on the platform.""",
        "type" : "str",
        "scope": "CPU",
        "writable" : True,
        "subprops" : {
            "epb_policies" : {
                "name" : "Available EPB policies",
                "help" : "Available Linux EPB policy names.",
                "type" : "list[str]",
                "writable" : False,
                "scope": "global",
            },
        },
    },
    "driver" : {
        "name" : "CPU frequency driver",
        "help" : """CPU frequency driver enumerates and requests the P-states available on the
                    platform.""",
        "type" : "str",
        "scope": "global",
        "writable" : False,
    },
    "governor" : {
        "name" : "CPU frequency governor",
        "help" : """CPU frequency governor decides which P-state to select on a CPU depending
                    on CPU business and other factors.""",
        "type" : "str",
        "scope": "CPU",
        "writable" : True,
        "subprops" : {
            "governors" : {
                "name" : "Available CPU frequency governors",
                "help" : """CPU frequency governors decide which P-state to select on a CPU
                            depending on CPU business and other factors. Different governors
                            implement different selection policy.""",
                "type" : "list[str]",
                "scope": "global",
                "writable" : False,
            },
        },
    },
}

def _is_uncore_prop(prop):
    """
    Returns 'True' if propert 'prop' is an uncore property, otherwise returns 'False'.
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

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo)

        return self._msr

    def _get_eppobj(self):
        """Returns an 'EPP.EPP()' object."""

        if not self._eppobj:
            from pepclibs import EPP #pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._eppobj

    def _get_epbobj(self):
        """Returns an 'EPB.EPB()' object."""

        if not self._epbobj:
            from pepclibs import EPB #pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._epbobj = EPB.EPB(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

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

    def _is_cached(self, pname, cpu):
        """Returns 'True' if there is a cached value for property or sub-property 'pname'."""

        if cpu in self._cache and pname in self._cache[cpu]:
            return True
        return False

    def _remove_from_cache(self, pname, cpu):
        """Remove CPU 'cpu' property or sub-property 'pname' from the cache."""

        if cpu in self._cache and pname in self._cache[cpu]:
            del self._cache[cpu][pname]

    def _add_to_cache(self, pname, prop, val, cpu):
        """Add property or sub-property 'pname' to the cache."""

        scope = prop["scope"]
        if scope == "global":
            cpus = self._cpuinfo.get_cpus()
        elif scope == "die":
            levels = self._cpuinfo.get_cpu_levels(cpu)
            dies = (levels["die"], )
            packages = (levels["package"], )

            cpus = self._cpuinfo.dies_to_cpus(dies=dies, packages=packages)
        else:
            cpus = (cpu, )

        for cpu in cpus: # pylint: disable=redefined-argument-from-local
            if cpu not in self._cache:
                self._cache[cpu] = {}
            self._cache[cpu][pname] = val

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

        base_freq = self._get_cpu_prop("base_freq", cpu)
        max_turbo_freq = self._get_cpu_prop("max_turbo_freq", cpu)

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
        driver = self._get_cpu_prop("driver", cpu)

        if driver in {"intel_pstate", "intel_cpufreq"}:
            path = self._sysfs_base / "intel_pstate" / "no_turbo"
            disabled = self._read_int(path)
            return "off" if disabled else "on"

        if driver == "acpi-cpufreq":
            path = self._sysfs_base / "cpufreq" / "boost"
            enabled = self._read_int(path)
            return "on" if enabled else "off"

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

    def _get_cpu_prop_or_subprop(self, pname, prop, cpu):
        """Returns property or sub-property 'pname' for CPU 'cpu'."""

        _LOG.debug("getting '%s' (%s) for CPU %d%s", pname, prop["name"], cpu, self._pman.hostmsg)

        if self._is_cached(pname, cpu):
            return self._cache[cpu][pname]

        if "fname" in prop:
            if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
                _LOG.debug(self._uncore_errmsg)
                return None

            path = self._get_sysfs_path(prop, cpu)
            try:
                val = self._get_prop_from_sysfs(prop, path)
                self._add_to_cache(pname, prop, val, cpu)
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
            self._add_to_cache("base_freq", self._props["base_freq"], base, cpu)
            self._add_to_cache("max_eff_freq", self._props["max_eff_freq"], max_eff_freq, cpu)
            return self._cache[cpu][pname]

        if pname == "hwp":
            hwp = self._get_cpu_hwp(cpu)
            self._add_to_cache("hwp", prop, hwp, cpu)
            return hwp

        if pname == "max_turbo_freq":
            max_turbo_freq = self._get_max_turbo_freq_freq(cpu)
            if max_turbo_freq is None:
                # Assume that max. turbo is the Linux max. frequency.
                path = self._get_sysfs_path(self._props["max_freq"], cpu)
                max_turbo_freq = self._get_prop_from_sysfs(prop, path)
            self._add_to_cache("max_turbo_freq", prop, max_turbo_freq, cpu)
            return max_turbo_freq

        if pname == "turbo":
            turbo = self._get_cpu_turbo(cpu)
            self._add_to_cache("turbo", prop, turbo, cpu)
            return turbo

        raise Error(f"BUG: unsupported property '{pname}'")

    def _get_cpu_subprop(self, pname, subpname, cpu):
        """Returns sup-property 'subpname' of property 'pname' for CPU 'cpu'."""

        subprop = self._props[pname]["subprops"][subpname]
        return self._get_cpu_prop_or_subprop(subpname, subprop, cpu)

    def _get_cpu_prop(self, pname, cpu):
        """Returns property 'pname' for CPU 'cpu'."""

        prop = self._props[pname]
        return self._get_cpu_prop_or_subprop(pname, prop, cpu)

    def _get_cpu_props(self, pnames, cpu):
        """Returns all properties in 'pnames' for CPU 'cpu'."""

        pinfo = {}

        for pname in pnames:
            pinfo[pname] = {}

            # Get the 'pname' property.
            pinfo[pname][pname] = self._get_cpu_prop(pname, cpu)
            if pinfo[pname][pname] is None:
                _LOG.debug("CPU %d: %s is not supported", cpu, pname)
                continue
            _LOG.debug("CPU %d: %s = %s", cpu, pname, pinfo[pname][pname])

            # Get all the sub-properties.
            for subpname in self._props[pname]["subprops"]:
                if pinfo[pname][pname] is not None:
                    # Get the 'subpname' sub-property.
                    pinfo[pname][subpname] = self._get_cpu_subprop(pname, subpname, cpu)
                else:
                    # The property is not supported, so all sub-properties are not supported either.
                    pinfo[pname][subpname] = None
                _LOG.debug("CPU %d: %s = %s", cpu, subpname, pinfo[pname][subpname])

        return pinfo

    def _populate_cache(self, pnames, cpus):
        """
        Populate the properties cache for properties in 'pnames' for CPUs in 'cpus'. The idea is
        that some properties may be more effecient to read in one go for all CPUs.
        """

        for pname in pnames:
            if pname.startswith("epp") or pname.startswith("epb"):
                # Get list of CPUs which do not have 'pname' property cached yet.
                uncached_cpus = []
                for cpu in cpus:
                    if not self._is_cached(pname, cpu):
                        uncached_cpus.append(cpu)

                if not uncached_cpus:
                    continue

                # Figure out the feature name ("epp" or "epb").
                feature = pname.split("_")
                if len(feature) == 2:
                    feature = feature[0]
                else:
                    feature = pname

                obj = getattr(self, f"_get_{feature}obj")()
                kwargs = {"cpus" : uncached_cpus}
                if pname.startswith("epp"):
                    kwargs["not_supported_ok"] = True

                for cpu, val in getattr(obj, f"get_{pname}")(**kwargs):
                    self._add_to_cache(pname, self._props[pname], val, cpu)

                for subpname, subprop in self._props[pname]["subprops"].items():
                    for cpu, val in getattr(obj, f"get_{subpname}")(**kwargs):
                        self._add_to_cache(subpname, subprop, val, cpu)

    def get_props(self, pnames, cpus="all"):
        """
        Read all properties specified in the 'pnames' list for CPUs in 'cpus', and for every CPU
        yield a ('cpu', 'pinfo') tuple, where 'pinfo' is dictionary containing the read values of
        all the properties. The arguments are as follows.
          * pnames - list or an iterable collection of properties to read and yield the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).

        The yielded 'pinfo' dictionaries have the following format.

        { property1_name: { property1_name : property1_value,
                            subprop1_key : subprop1_value,
                            subprop2_key : subprop2_value,
                            ... etc for every key ...},
          property2_name: { property2_name : property2_value,
                            subprop1_key : subprop2_value,
                            ... etc ...},
          ... etc ... }

        So each property has the (main) value, and possibly sub-properties, which provide additional
        read-only information related to the property. For example, the 'epp_policy' property comes
        with the 'epp_policies' sub-property. Most properties have no sub-properties.

        If a property is not supported, its value will be 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        for pname in pnames:
            self._check_prop(pname)

        self._populate_cache(pnames, cpus)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, self._get_cpu_props(pnames, cpu)

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for _, pinfo in self.get_props(pnames, cpus=(cpu,)):
            pass
        return pinfo

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_props()', but for a single CPU and a single property."""

        pinfo = None
        for _, pinfo in self.get_props((pname,), cpus=(cpu,)):
            pass
        return pinfo[pname]

    def _set_turbo(self, cpu, enable):
        """Enable or disable turbo."""

        if not self._is_turbo_supported(cpu):
            raise ErrorNotSupported(f"turbo is not supported{self._pman.hostmsg}")

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        driver = self._get_cpu_prop("driver", cpu)

        if driver in {"intel_pstate", "intel_cpufreq"}:
            path = self._sysfs_base / "intel_pstate" / "no_turbo"
            self._pman.write(path, str(int(not enable)))
        elif driver == "acpi-cpufreq":
            path = self._sysfs_base / "cpufreq" / "boost"
            self._pman.write(path, str(int(enable)))
        else:
            raise Error(f"failed to enable or disable turbo{self._pman.hostmsg}: unsupported CPU "
                        f"frequency driver '{driver}'")

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

    def _set_prop_in_sysfs(self, pname, val, cpu):
        """Set property 'pname' to value 'val' by writing to the corresponding syfs file."""

        prop = self._props[pname]
        path = self._get_sysfs_path(prop, cpu)
        orig_val = val
        if prop.get("unit") == "Hz":
            # Sysfs files use kHz
            val //= 1000
        self._pman.write(path, str(val))

        count = 3
        while count > 0:
            read_val = self._get_prop_from_sysfs(prop, path)

            if orig_val == read_val:
                self._add_to_cache(pname, prop, orig_val, cpu)
                return

            # Sometimes the update does not happen immediately. For example, we observed this on
            # systems with frequency files when HWP was enabled, for example. Wait a little bit and
            # try again.
            time.sleep(0.1)
            count -= 1

        name = Human.untitle(prop["name"])
        what = self._get_num_str(prop, cpu)

        if prop.get("unit") == "Hz":
            freq = Human.largenum(orig_val, unit="Hz")
            msg = f"failed to set {name} to {freq} for {what}: wrote '{val}' to '{path}', but " \
                  f"read '{read_val // 1000}' back."
        else:
            msg = f"failed to set {name} to value '{val} for {what}'.\nWrote '{val}' to " \
                  f"'{path}', but read back value '{read_val}'."

        if pname == "max_freq":
            with contextlib.suppress(Error):
                if self._get_cpu_turbo(cpu) == "off":
                    base_freq = self._get_cpu_prop("base_freq", cpu)
                    if orig_val > base_freq:
                        base_freq = Human.largenum(base_freq, unit="Hz")
                        msg += f"\nHint: turbo is disabled, base frequency is {base_freq}, and " \
                               f"this may be the limiting factor."

        raise Error(msg)

    def _validate_and_order_freq(self, inprops, cpu, uncore=False):
        """
        Validate the 'min_freq' and 'max_freq' properties in 'inprops' and possibly re-order
        them. Returns the re-ordered 'inprops' version.
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

        what = self._get_num_str(self._props[min_freq_key], cpu)

        if min_freq_key not in inprops and max_freq_key not in inprops:
            return inprops

        cur_min_freq = self._get_cpu_prop(min_freq_key, cpu)
        cur_max_freq = self._get_cpu_prop(max_freq_key, cpu)

        if min_freq_key in inprops:
            min_freq = inprops[min_freq_key]
        else:
            min_freq = None

        if max_freq_key in inprops:
            max_freq = inprops[max_freq_key]
        else:
            max_freq = None

        min_limit = self._get_cpu_prop(min_freq_limit_key, cpu)
        max_limit = self._get_cpu_prop(max_freq_limit_key, cpu)

        for pname, val in ((min_freq_key, min_freq), (max_freq_key, max_freq)):
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
            if min_freq > max_freq:
                name_min = Human.untitle(self._props[min_freq_key]["name"])
                name_max = Human.untitle(self._props[max_freq_key]["name"])
                min_freq = Human.largenum(min_freq, unit="Hz")
                max_freq = Human.largenum(max_freq, unit="Hz")
                raise Error(f"can't set {name_min} to {min_freq} and {name_max} to {max_freq} for "
                            f"{what}: minimum can't be greater than maximum")
        elif max_freq_key not in inprops:
            if min_freq > cur_max_freq:
                name = Human.untitle(self._props[min_freq_key]["name"])
                min_freq = Human.largenum(min_freq, unit="Hz")
                cur_max_freq = Human.largenum(cur_max_freq, unit="Hz")
                raise Error(f"can't set {name} of {what} to {min_freq} - it is higher than "
                            f"currently configured maximum frequency of {cur_max_freq}")
        elif min_freq_key not in inprops:
            if max_freq < cur_min_freq:
                name = Human.untitle(self._props[max_freq_key]["name"])
                max_freq = Human.largenum(max_freq, unit="Hz")
                cur_min_freq = Human.largenum(cur_min_freq, unit="Hz")
                raise Error(f"can't set {name} of {what} to {max_freq} - it is lower than "
                            f"currently configured minimum frequency of {cur_min_freq}")

        # Make sure we change the frequencies in the right order.
        if min_freq_key in inprops and max_freq_key in inprops:
            if min_freq >= cur_max_freq:
                # The situation is the following:
                #   ---- Cur. Min --- Cur. Max -------- New Min --- New Max ----------> (Frequency)
                # Make sure we first configure the new maximum frequency, and then new minimum
                # frequency.
                inprops = inprops.copy()
                del inprops[min_freq_key]
                inprops[min_freq_key] = min_freq
            if max_freq <= cur_min_freq:
                # The situation is the following:
                #   ---- New Min --- New Max -------- Cur. Min --- Cur. Max ----------> (Frequency)
                # Make sure we first configure the new minimum frequency, and then new maximum
                # frequency.
                inprops = inprops.copy()
                del inprops[max_freq_key]
                inprops[max_freq_key] = max_freq

        return inprops

    def _parse_freq(self, pname, prop, val, cpu):
        """Turn a user-provided CPU or uncore frequency property value to hertz."""

        if "uncore" in pname:
            if val == "min":
                freq = self._get_cpu_prop("min_uncore_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop("max_uncore_freq_limit", cpu)
            else:
                freq = Human.parse_freq(val, name=Human.untitle(prop["name"]))
        else:
            if val in {"min", "lfm"}:
                freq = self._get_cpu_prop("min_freq_limit", cpu)
            elif val == "max":
                freq = self._get_cpu_prop("max_freq_limit", cpu)
            elif val in {"base", "hfm"}:
                freq = self._get_cpu_prop("base_freq", cpu)
            elif val == "eff":
                freq = self._get_cpu_prop("max_eff_freq", cpu)
            else:
                freq = Human.parse_freq(val, name=Human.untitle(prop["name"]))

        return freq

    def _set_cpu_props(self, inprops, cpu):
        """Sets user-provided properties in 'inprops' for CPU 'cpu'."""

        for pname, val in inprops.items():
            prop = self._props[pname]

            if _is_uncore_prop(prop) and not self._is_uncore_freq_supported():
                raise Error(self._uncore_errmsg)

            if prop.get("unit", None) == "Hz":
                inprops[pname] = self._parse_freq(pname, prop, val, cpu)

            if pname == "governor":
                governors = self._get_cpu_subprop("governor", "governors", cpu)
                if val not in governors:
                    governors = ", ".join(governors)
                    raise Error(f"bad governor name '{val}', use one of: {governors}")

            if prop.get("type") == "bool":
                vals = (True, False, "on", "off", "enable", "disable")
                if val not in vals:
                    name = Human.untitle(prop['name'])
                    use = ", ".join([str(val1) for val1 in vals])
                    raise Error(f"bad value '{val}' for {name}, use one of: {use}")

        inprops = self._validate_and_order_freq(inprops, cpu, uncore=False)
        inprops = self._validate_and_order_freq(inprops, cpu, uncore=True)

        for pname, val in inprops.items():
            prop = self._props[pname]

            # Invalidate the cache record for this CPU/property.
            self._remove_from_cache(pname, cpu)

            if pname.startswith("epp") or pname.startswith("epb"):
                # Figure out the feature name ("epp" or "epb").
                feature = pname.split("_")
                if len(feature) == 2:
                    feature = feature[0]
                else:
                    feature = pname

                obj = getattr(self, f"_get_{feature}obj")()
                getattr(obj, f"set_cpu_{feature}")(val, cpu)
            elif pname == "turbo":
                self._set_turbo(cpu, val in {True, "on", "enable"})
            else:
                if "fname" not in prop:
                    raise Error(f"BUG: unsupported property '{pname}'")

                self._set_prop_in_sysfs(pname, val, cpu)

    def set_props(self, inprops, cpus="all"):
        """
        Set multiple properties described by 'inprops' to values also provided in 'inprops'.
          * inprops - an iterable collection of property names and values.
          * cpus - same as in 'get_props()'.

        This method accepts two 'inprops' formats.

        1. An iterable collection (e.g., list or a tuple) of ('pname', 'val') pairs. For example:
           * [("min_freq", "1GHz"), ("epp_policy", "performance")]
        2. A dictionary with property names as keys. For example:
           * {"min_freq" : "1GHz", "epp_policy" : "performance"}

        Properties of "bool" type accept the following values:
           * True, "on", "enable" for enabling the feature.
           * False, "off", "disable" for disabling the feature.
        """

        inprops = self._normalize_inprops(inprops)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        for pname in inprops:
            _Common.validate_prop_scope(self._props[pname], cpus, self._cpuinfo, self._pman.hostmsg)

        for cpu in cpus:
            self._set_cpu_props(inprops, cpu)

    def set_cpu_prop(self, pname, val, cpu):
        """Same as 'set_props()', but for a single CPU and a single property."""

        self.set_props(((pname, val),), cpus=(cpu,))

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

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

        self._eppobj = None
        self._epbobj = None
        self._bclk = {}
        self._pmenable = None
        self._platinfo = None
        self._trl = None

        # The write-through per-CPU properties cache.
        self._cache = {}

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

        if getattr(self, "_ufreq_drv", None):
            if getattr(self, "_unload_ufreq_drv", None):
                self._ufreq_drv.unload()
                self._unload_ufreq_drv = None
            self._ufreq_drv = None

        close_attrs = ("_eppobj", "_epbobj", "_pmenable", "_platinfo", "_trl")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
