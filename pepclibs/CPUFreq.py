# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API for managing CPU frequency. Was used and tested only on Intel CPUs.
"""

import time
import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import FSHelpers, KernelModule, Procs, Trivial
from pepclibs import CPUInfo
from pepclibs.msr import MSR

# The keys in the CPU frequency information dictionary generated by 'get_cpufreq_info()', along with
# the description.
CPUFREQ_KEYS_DESCR = {
    "CPU": "CPU number",
    "base": "Base frequency",
    "max_eff": "Max efficiency frequency",
    "max_turbo": "Max 1-core turbo frequency",
    "cpu_min_limit": "Min supported CPU frequency",
    "cpu_max_limit": "Max supported CPU frequency",
    "cpu_min": "Min currently configured CPU frequency",
    "cpu_max": "Max currently configured CPU frequency",
    "hwp_supported": "Hardware P-States support",
    "hwp_enabled": "Hardware P-States enabled",
    "turbo_supported": "Turbo support",
    "turbo_enabled": "Turbo enabled",
    "driver": "CPU frequency driver",
    "governor": "CPU frequency governor",
    "governors": "Available governors",
    "epp_supported": "EPP support",
    "epp": "Energy Performance Preference",
    "epp_policy": "EPP policy",
    "epp_policies": "Available EPP policies",
    "epb_supported": "EPB support",
    "epb": "Energy Performance Bias",
    "epb_policy": "EPB policy",
    "epb_policies": "Available EPB policies",
}

UNCORE_KEYS_DESCR = {
    "pkg": "CPU package",
    "die": "Die within the CPU package",
    "uncore_min": "Min currently configured uncore frequency",
    "uncore_max": "Max currently configured uncore frequency",
    "uncore_min_limit": "Min initially platform pre-configured uncore frequency",
    "uncore_max_limit": "Max initially platform pre-configured uncore frequency",
}

_LOG = logging.getLogger()
_RAISE = object()

# This dictionary describes various CPU properties this module controls.
# Note, the "scope" names have to be the same as "level" names in 'CPUInfo'.
PROPS = {
    "turbo" : {
        "name"  : "turbo",
        "scope" : "global",
    },
    "epb" : {
        "name"  : "EPB",
        "scope" : "CPU",
    },
    "epp" : {
        "name"  : "EPP",
        "scope" : "CPU",
    },
    "governor" : {
        "name"  : "CPU frequency governor",
        "scope" : "CPU",
    },
    "cpu-freq" : {
        "scope" : "CPU",
    },
    "uncore-freq" : {
        "scope" : "package",
    },
}

class CPUFreq:
    """This class provides API for managing CPU frequency. Only Intel x86 systems are supported."""

    def _get_cpuinfo(self):
        """Returns a 'CPUInfo.CPUInfo()' object."""

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)
        return self._cpuinfo

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._proc, cpuinfo=self._cpuinfo)
        return self._msr

    def _get_bclk(self, cpu):
        """Discover bus clock speed."""

        if not self._bclk:
            from pepclibs import BClock #pylint: disable=import-outside-toplevel

            self._bclk = BClock.get_bclk(self._proc, cpu=cpu, cpuinfo=self._cpuinfo, msr=self._msr)

        return self._bclk

    def _get_epbobj(self):
        """Returns an 'EPB.EPB()' object."""

        if not self._epbobj:
            from pepclibs import EPB #pylint: disable=import-outside-toplevel

            cpuinfo = self._get_cpuinfo()
            msr = self._get_msr()
            self._epbobj = EPB.EPB(self._proc, cpuinfo=cpuinfo, msr=msr)

        return self._epbobj

    def _read(self, path):
        """Read cpufreq sysfs file."""

        return FSHelpers.read(path, proc=self._proc)

    def _read_int(self, path, default=_RAISE):
        """Read an integer from cpufreq sysfs file."""

        if default is _RAISE:
            return FSHelpers.read_int(path, proc=self._proc)
        return FSHelpers.read_int(path, default=default, proc=self._proc)

    def _write(self, path, data):
        """Write into cpufreq sysfs file."""

        FSHelpers.write(path, data, proc=self._proc)

    def _is_intel_cpu(self):
        """Check if we are dealing with an Intel CPU."""

        cpuinfo = self._get_cpuinfo()
        return cpuinfo.info["vendor"] == "GenuineIntel"

    def _get_cpu_epp_policy(self, cpu):
        """Get current EPP policy. Returns 'None' if read fails."""

        path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "energy_performance_preference"
        with contextlib.suppress(Error):
            return FSHelpers.read(path, proc=self._proc)
        return None

    def _get_epp_policies(self):
        """Returns a list of available EPP policies."""

        if self._epp_policies is not None:
            return self._epp_policies

        # EPP policies are per-CPU, but we get the list of policies for CPU0 and assume it is the
        # same for other CPUs.
        path = self._sysfs_epp_policies
        with contextlib.suppress(Error):
            self._epp_policies = FSHelpers.read(path, proc=self._proc).split()

        if not self._epp_policies:
            self._epp_policies = []

        return self._epp_policies

    def _get_platform_freqs(self, cpu):
        """Read various platform frequencies from MSRs for CPU 'cpu'."""

        freqs = {}
        if not self._is_intel_cpu():
            return freqs

        cpuinfo = self._get_cpuinfo()
        self._bclk = self._get_bclk(cpu)
        msr = self._get_msr()

        _LOG.debug("bus clock speed: %fMHz", self._bclk)

        #
        # Get base frequency and effeciency frequency from 'MSR_PLATFORM_INFO'.
        #
        # pylint: disable=import-outside-toplevel
        from pepclibs.msr import PlatformInfo

        platinfo = PlatformInfo.PlatformInfo(proc=self._proc, cpuinfo=cpuinfo, msr=msr)

        ratio = platinfo.read_cpu_feature("max_non_turbo_ratio", cpu)
        freqs["base"] = int(ratio * self._bclk * 1000)

        if platinfo.is_cpu_feature_supported("max_eff_ratio", cpu):
            ratio = platinfo.read_cpu_feature("max_eff_ratio", cpu)
            freqs["max_eff"] = int(ratio * self._bclk * 1000)

        #
        # Get max 1 core turbo frequency from 'MSR_TURBO_RATIO_LIMIT'.
        #
        from pepclibs.msr import TurboRatioLimit

        trl = TurboRatioLimit.TurboRatioLimit(proc=self._proc, cpuinfo=cpuinfo, msr=msr)
        ratio = None

        if trl.is_cpu_feature_supported("max_1c_turbo_ratio", cpu):
            ratio = trl.read_cpu_feature("max_1c_turbo_ratio", 0)
        elif trl.is_cpu_feature_supported("max_g0_turbo_ratio", cpu):
            # In this case 'MSR_TURBO_RATIO_LIMIT' encodes max. turbo ratio for groups of cores. We
            # can safely assume that group 0 will correspond to max. 1-core turbo, so we do not need
            # to look at 'MSR_TURBO_RATIO_LIMIT1'.
            ratio = trl.read_cpu_feature("max_g0_turbo_ratio", cpu)
        else:
            _LOG.warning("module 'TurboRatioLimit' does not support 'MSR_TURBO_RATIO_LIMIT' for "
                         "CPU '%s'%s\nPlease, contact project maintainers.",
                         cpuinfo.cpudescr, self._proc.hostmsg)

        if ratio is not None:
            freqs["max_turbo"] = int(ratio * self._bclk * 1000)

        # pylint: enable=import-outside-toplevel
        return freqs

    def _is_turbo_enabled(self):
        """Read turbo enabled status from sysfs."""

        path = self._sysfs_base / "intel_pstate" / "no_turbo"
        disabled = self._read_int(path, default=None)
        if disabled is None:
            path = self._sysfs_base / "cpufreq" / "boost"
            return bool(self._read_int(path, default=None))
        return not disabled

    def _get_base_freq(self, cpu):
        """Get base frequency for CPU 'cpu'."""

        cpu0_path = self._sysfs_base / "cpufreq" / f"policy{cpu}"

        if not self._is_intel_cpu():
            # Assume that on non-Intel CPUs the base frequency is the max. frequency of CPU0.
            try:
                return self._read_int(cpu0_path / "scaling_max_freq")
            except Error as err:
                raise Error("can't detect max. CPU frequency: {err}") from err

        base_freq = self._read_int(cpu0_path / "base_frequency", default=None)
        if not base_freq:
            # Only the 'intel_pstate' driver provides the base frequency attribute.
            platform_freqs = self._get_platform_freqs(cpu)
            base_freq = platform_freqs["base"]

        return base_freq

    def _is_turbo_supported(self):
        """Check if turbo mode is supported."""

        if not self._is_intel_cpu():
            return False

        platform_freqs = self._get_platform_freqs(0)
        return self._get_base_freq(0) != platform_freqs["max_turbo"]

    def _get_hwp_enabled(self, cpu):
        """
        Returnd 'True' if hardware power management is enabled, 'False' if it is disabled, and
        'None' if it is not supported by the CPU (and hence, not enabled).
        """

        from pepclibs.msr import PMEnable # pylint: disable=import-outside-toplevel

        msr = self._get_msr()
        cpuinfo = self._get_cpuinfo()
        pmenable = PMEnable.PMEnable(proc=self._proc, cpuinfo=cpuinfo, msr=msr)

        if not pmenable.is_cpu_feature_supported("hwp_enabled", cpu):
            return None

        return pmenable.is_cpu_feature_enabled("hwp_enabled", cpu)

    def _get_cpufreq_info(self, cpus, keys):
        """Implements 'get_cpufreq_info()'."""

        # Resolve global attributes first.
        if keys.intersection(["turbo_supported", "turbo_enabled"]):
            turbo_enabled = self._is_turbo_enabled()
            if turbo_enabled:
                turbo_supported = True
            else:
                turbo_supported = self._is_turbo_supported()

        if "driver" in keys:
            driver = self._read(self._sysfs_base / "cpufreq" / "policy0" / "scaling_driver")

        for cpu in cpus:
            if keys.intersection(["max_eff", "max_turbo"]):
                platform_freqs = self._get_platform_freqs(cpu)
            else:
                platform_freqs = {}
            basedir = self._sysfs_base / "cpufreq" / f"policy{cpu}"

            info = {}
            if "CPU" in keys:
                info["CPU"] = cpu
            if "base" in keys:
                info["base"] = self._get_base_freq(cpu)
            if "max_eff" in keys and platform_freqs.get("max_eff"):
                info["max_eff"] = platform_freqs["max_eff"]
            if "max_turbo" in keys and platform_freqs.get("max_turbo"):
                info["max_turbo"] = platform_freqs["max_turbo"]
            if "cpu_min_limit" in keys:
                info["min_limit"] = self._read_int(basedir / "cpuinfo_min_freq")
            if "cpu_max_limit" in keys:
                info["max_limit"] = self._read_int(basedir / "cpuinfo_max_freq")
            if "cpu_min" in keys:
                info["cpu_min"] = self._read_int(basedir / "scaling_min_freq")
            if "cpu_max" in keys:
                info["cpu_max"] = self._read_int(basedir / "scaling_max_freq")
            if "driver" in keys:
                info["driver"] = driver
            if "governor" in keys:
                info["governor"] = self._read(basedir / "scaling_governor")
            if "governors" in keys:
                info["governors"] = self._read(basedir / "scaling_available_governors").split()
            if "hwp_supported" in keys:
                cpuinfo = self._get_cpuinfo()
                info["hwp_supported"] = "hwp" in cpuinfo.info["flags"]
            if "hwp_enabled" in keys:
                info["hwp_enabled"] = self._get_hwp_enabled(cpu) is True
            if "turbo_supported" in keys:
                info["turbo_supported"] = turbo_supported
            if "turbo_enabled" in keys:
                info["turbo_enabled"] = turbo_enabled
            if "epp_supported" in keys:
                info["epp_supported"] = self._is_epp_supported(cpu)
            if self._is_epp_supported(cpu):
                if "epp" in keys:
                    info["epp"] = self.get_cpu_epp(cpu)
                if "epp_policy" in keys:
                    epp_policy = self._get_cpu_epp_policy(cpu)
                    if epp_policy:
                        info["epp_policy"] = epp_policy
                if "epp_policies" in keys:
                    epp_policies = self._get_epp_policies()
                    if epp_policies:
                        info["epp_policies"] = epp_policies

            if keys.intersection(["epb_supported", "epb", "epb_policy", "epb_policies"]):
                epbobj = self._get_epbobj()

                if "epb_supported" in keys:
                    info["epb_supported"] = epbobj.is_epb_supported(cpu)

                if epbobj.is_epb_supported(cpu):
                    if keys.intersection(["epb", "epb_policy"]):
                        epb = epbobj.get_cpu_epb(cpu)

                    if "epb" in keys:
                        info["epb"] = epb
                    if "epb_policy" in keys:
                        info["epb_policy"] = epbobj.get_cpu_epb_policy(cpu, epb=epb)
                    if "epb_policies" in keys:
                        info["epb_policies"] = epbobj.get_cpu_epb_policies(cpu)

            yield info

    def get_cpufreq_info(self, cpus, keys=None):
        """
        Yield CPU frequency information. The arguments are as follows.
          * cpus - the CPUs to yield the information for, same as the 'cpus' argument of the
                   'CPUIdle.get_cstates_info()' function.
          * keys - By default this generator yields all the information in form of a dictionary,
                   where each key represents a piece of information. For example, the "base" key
                   contains the base frequency value. However, if only some of the keys are needed,
                   their names can be specified in 'keys'. For example, in order to ask for base
                   frequency and nothing else, use 'keys=("base",)".
        """

        if not keys:
            keys = CPUFREQ_KEYS_DESCR
        keys = set(keys)

        cpus = self._get_cpuinfo().normalize_cpus(cpus)
        return self._get_cpufreq_info(cpus, keys)

    def _ensure_uncore_freq_support(self):
        """
        Make sure that the uncore frequency control is supported. Load the uncore frequency
        control driver if necessary.
        """

        if self._ufreq_supported is not None:
            return

        if not self._is_intel_cpu():
            # Only Intel CPUs are supported have uncore frequency control driver.
            self._ufreq_supported = False
            return

        ufreq_dir = self._sysfs_base / "intel_uncore_frequency"
        self._ufreq_supported = FSHelpers.exists(ufreq_dir, self._proc)
        if self._ufreq_supported:
            return

        drvname = "intel_uncore_frequency"
        msg = f"uncore frequency operations are not supported{self._proc.hostmsg}, either " \
              f"because the hardware does not support it, or the driver does not support this " \
              f"hardware, or the driver is simply not enabled. Make sure your kernel has the " \
              f"'{drvname}' driver enabled (CONFIG_INTEL_UNCORE_FREQ_CONTROL)."

        try:
            self._ufreq_drv = KernelModule.KernelModule(self._proc, drvname)
            loaded = self._ufreq_drv.is_loaded()
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

        if loaded:
            raise Error(msg)

        try:
            self._ufreq_drv.load()
            self._unload_ufreq_drv = True
            FSHelpers.wait_for_a_file(ufreq_dir, timeout=1, proc=self._proc)
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

        self._ufreq_supported = True

    def _get_uncore_info(self, pkgs, keys):
        """Implements 'get_uncore_info()'."""

        for name, basedir, _ in FSHelpers.lsdir(self._sysfs_base / "intel_uncore_frequency",
                                                proc=self._proc):
            # Example of directory name: package_01_die_00
            items = name.split("_")
            if len(items) != 4:
                raise Error(f"unexpected number or items when splitting directory name '{name}'"
                            f"{self._proc.hostmsg}, expected directory name like "
                            f"'package_01_die_00'")
            _, pkg, _, die = items
            pkg = int(pkg)
            die = int(die)

            if pkg not in pkgs:
                continue

            info = {}
            if "pkg" in keys:
                info["pkg"] = pkg
            if "die" in keys:
                info["die"] = die
            if "uncore_max" in keys:
                info["uncore_max"] = self._read_int(basedir / "max_freq_khz")
            if "uncore_min" in keys:
                info["uncore_min"] = self._read_int(basedir / "min_freq_khz")
            if "uncore_max_limit" in keys:
                info["uncore_max_limit"] = self._read_int(basedir / "initial_max_freq_khz")
            if "uncore_min_limit" in keys:
                info["uncore_min_limit"] = self._read_int(basedir / "initial_min_freq_khz")

            yield info

    def get_uncore_info(self, pkgs="all", keys=None):
        """
        Yield information about the uncore, which is per-package or per die in multi-die systems.
        The arguments are as follows.
          * pkgs - the CPU packages to yield the information for. This could be a list or a
                   comma-speated string listing package numbers or package ranges. For example,
                   '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and 3. 'None'
                   and 'all' mean "all packages".
          * keys - By default this generator yields all the information in form of a dictionary,
                   where each key represents a piece of information. For example, the "max" key
                   contains the maximum uncore frequency value. However, if only some of the keys
                   are needed, their names can be specified in 'keys'. For example, in order to ask
                   for the maximum uncore frequency and nothing else, use 'keys=("max",)".
        """

        self._ensure_uncore_freq_support()
        pkgs = set(self._get_cpuinfo().normalize_packages(pkgs))

        if not keys:
            keys = UNCORE_KEYS_DESCR
        keys = set(keys)

        return self._get_uncore_info(pkgs, keys)

    @staticmethod
    def _pre_parse_freq(freq, specifiers):
        """
        Parse a user-provided frequency value 'freq'. If possible, return the frequency as and
        integer amount of kHz. In case the convertion depends on the CPU number (e.g., 'freq'
        isspecified as 'hfm'), this function just returns 'freq' value as is. In other words, this
        is function implements partial parsing, and only handles CPU-independent situations.
        """

        if not freq or freq in specifiers:
            return freq

        val = freq
        if not Trivial.is_int(val):
            val = val.lower()
            for unit, mult in [("ghz", 1000000), ("mhz", 1000), ("khz", 1), ("hz", 0.001)]:
                split = val.split(unit, 1)
                if len(split) == 2 and not split[1].strip() and Trivial.is_float(split[0]):
                    val = float(split[0]) * mult
                    break

            if not Trivial.is_int(val):
                specifiers_str = ", ".join(specifiers)
                raise Error(f"invalid frequency value '{freq}', should be an integer amount of kHz"
                            f" or one of: {specifiers_str}")

        val = int(val)
        if val < 0:
            raise Error(f"invalid frequency value '{freq}', should not be negative")
        return val

    def _get_cpus_to_pkgs_map(self):
        """
        Turn list of CPU numbers into dictionary where CPU number is key and corresponding package
        number is the value.
        """
        cpus_pkg_map = {}

        for pkg in self._get_cpuinfo().get_packages():
            for cpu in self._get_cpuinfo().packages_to_cpus(packages=pkg):
                cpus_pkg_map[cpu] = pkg

        return cpus_pkg_map

    def get_freq_info(self, cpus, keys):
        """
        A unified version of 'get_cpufreq_info()' and 'get_uncore_info()'. The 'keys' argument can
        contain keys from either 'CPUFREQ_KEYS_DESCR' or 'UNCORE_KEYS_DESCR'.
        """

        if not keys:
            keys = CPUFREQ_KEYS_DESCR
            keys.update(UNCORE_KEYS_DESCR)
        keys = set(keys)

        uc_infos = {}
        if keys.intersection(set(UNCORE_KEYS_DESCR)):
            if self._ufreq_supported:
                pkgs = self._get_cpuinfo().get_packages()
                for pkg, uc_info in zip(pkgs, self._get_uncore_info(pkgs, keys)):
                    uc_infos[pkg] = uc_info

        cpu_pkg_map = self._get_cpus_to_pkgs_map()
        for cpu, info in zip(cpus, self.get_cpufreq_info(cpus, keys=keys)):
            if uc_infos:
                info |= uc_infos[cpu_pkg_map[cpu]]
            yield info

    def _set_freq(self, minfreq, maxfreq, cpus, uncore=False):
        """
        Implements 'set_freq()' and 'set_uncore_freq()'. There are so much similarity between the
        two so that it made sence having a single implementation. This differences are mostly in the
        messages and sysfs paths.
        """

        if uncore:
            name = "uncore"
        else:
            name = "CPU"

        if minfreq is None and maxfreq is None:
            raise Error(f"please provide minimum and/or maximum {name} frequency")

        # The allowed specifiers.
        specifiers = set(["min", "max"])
        if not uncore:
            specifiers.update(["lfm", "eff", "base", "hfm"])

        # Pre-parsed frequencies.
        pre_parsed_freqs = {}
        pre_parsed_freqs["min"] = self._pre_parse_freq(minfreq, specifiers)
        pre_parsed_freqs["max"] = self._pre_parse_freq(maxfreq, specifiers)

        # Mapping from specifiers to CPUFreq/uncore info key names.
        specifiers_map = {"min" : "min_limit", "max" : "max_limit"}
        if not uncore:
            specifiers_map.update({"lfm" : "min_limit", "eff" : "max_eff",
                                   "base" : "base", "hfm" : "base"})

        # Form the list of CPUFreq/uncore info key names that we'll need for handeling the frequency
        # change request.
        info_keys = set(["min", "max", "min_limit", "max_limit"])
        prefixed_keys = {f"{name.lower()}_{key}" : key for key in info_keys}
        info_keys.update(set(prefixed_keys))

        if not uncore:
            info_keys.update(["CPU"])
            # The below loop covers the "eff", "base", and "lfm" specifier cases.
            for freq in pre_parsed_freqs.values():
                if freq in specifiers:
                    info_keys.update((specifiers_map[freq], ))
        else:
            info_keys.update(("pkg", "die"))

        # Initialize the CPUFreq/uncore generator, which will yield CPU or package information.
        if uncore:
            # Note, 'cpus' is actually the list of packages in this case.
            infos = self.get_uncore_info(cpus, keys=info_keys)
        else:
            infos = self.get_cpufreq_info(cpus, keys=info_keys)

        nums = []
        freqs = {}
        for info in infos:
            if uncore:
                pkg, die = info["pkg"], info["die"]
                basedir = self._sysfs_base / "intel_uncore_frequency"
                basedir /= "package_%02d_die_%02d" % (pkg, die)
                cpuname = f"package {pkg} die {die}"
                nums.append(pkg)
            else:
                cpu = info["CPU"]
                basedir = self._sysfs_base / "cpufreq" / f"policy{cpu}"
                cpuname = f"CPU{cpu}"
                nums.append(cpu)

            for key in prefixed_keys:
                if key in info:
                    info[prefixed_keys[key]] = info[key]

            # Resolve possible frequency specifiers and somewhat validate them first.
            for key, freq in pre_parsed_freqs.items():
                if freq is None:
                    continue

                if freq in specifiers:
                    freq = info[specifiers_map[freq]]
                _LOG.debug("setting %s %s frequency to %s kHz", cpuname, key, freq)

                if freq < info["min_limit"] or freq > info['max_limit']:
                    raise Error(f"{cpuname} frequency {freq} kHz is out of range"
                                f"{self._proc.hostmsg}, valid range is "
                                f"[{info['min_limit']}, {info['max_limit']}] kHz")
                freqs[key] = freq

            # Make sure that new min. frequency is always greater than new max. frequency.
            if len(freqs) == 2 and freqs["min"] > freqs["max"]:
                raise Error(f"refusing to change {cpuname} frequencies{self._proc.hostmsg}: "
                            f"requested min. frequency of {freqs['min']} kHz is greater than "
                            f"requested max. frequency of {freqs['max']} kHz.")

            # OK, now we have the frequencies to set in 'freqs'. And our goal it to apply them, but
            # make sure that:
            #  * new min. frequency is not greater that the currently configured max. frequency.
            #  * new max. frequency is not smaller that the currently configured min. frequency.
            # Note, the currently configured min. and max. frequency values are available in 'info'.

            what = None
            change_order = ("min", "max")
            if freqs.get("min") and freqs["min"] > info["max"]:
                if freqs.get("max"):
                    change_order = ("max", "min")
                else:
                    # New min. frequency is greater the current max. frequency, but we cannot
                    # resolve this because we are not modifying the max. frequency.
                    key, what, cur_key = "min", "greater", "max"
            elif freqs.get("max") and freqs["max"] < info["min"]:
                if not freqs.get("min"):
                    key, what, cur_key = "max", "smaller", "min"

            if what:
                raise Error(f"refusing to set {cpuname} {key} frequency to {freqs[key]} kHz"
                            f"{self._proc.hostmsg}: it is {what} than currently configured "
                            f"{cur_key} frequency of {info[cur_key]} kHz")

            verify_list = []
            for key in change_order:
                if key not in freqs:
                    continue

                freq = freqs[key]
                if uncore:
                    path = basedir / f"{key}_freq_khz"
                else:
                    path = basedir / f"scaling_{key}_freq"

                verify_list.append((freq, path))
                self._write(path, freq)

            for freq, path in verify_list:
                freq_verify = self._read_int(path)
                if freq != freq_verify:
                    # Sometimes the frequency update does not happen immediately. We observed this
                    # on systems with HWP enabled, for example. Wait a little bit and try again.
                    time.sleep(0.1)
                    freq_verify = self._read_int(path)
                    if freq != freq_verify:
                        raise Error(f"failed to set {cpuname} frequency to {freq} kHz"
                                    f"{self._proc.hostmsg}.\nWrote '{freq}' to file '{path}', but "
                                    f"read '{freq_verify}' back")

        return (nums, freqs.get("min"), freqs.get("max"))

    def set_freq(self, minfreq=None, maxfreq=None, cpus="all"):
        """
        Set minimum and maximum frequency of CPUs in 'cpus' to 'minfreq' and 'maxfreq', which may be
        integer values or strings. In the former case, the value should be in kHz units. In the
        latter case, the default unit is 'kHz', but 'Hz', 'MHz', and 'GHz' can also be specified
        (e.g., example '900MHz'). It is also allowed to use one of the following specifiers for the
        frequency:
          * min, lfm - the minimum supported frequency (LFM)
          * eff - the maximum effeciency frequency
          * base,hfm - the base frequency (HFM)
          * max - the maximum supported frequency
        The 'cpus' argument is the same as in 'get_cpufreq_info()'.

        Returns tuple with 3 elements:
          * list of CPU numbers the frequency was set for.
          * minimum frequency applied in kHz, or 'None' if not changed.
          * maximum frequencies applied in kHz, or 'None if not changed.
        """

        return self._set_freq(minfreq, maxfreq, cpus, uncore=False)

    def set_uncore_freq(self, minfreq=None, maxfreq=None, pkgs="all"):
        """
        Set minimum and maximum uncore frequency of packages in 'pkgs' to 'minfreq' and 'maxfreq'.
        Format of 'minfreq' and 'maxfreq' is the same as in set_freq(). It is also allowed to use
        one of the following specifiers for the frequency:
          * min - the minimum supported uncore frequency
          * max - the maximum supported uncore frequency
        The 'pkgs' argument is the same as in get_uncore_info().

        Returns tuple with 3 elements:
          * list of package numbers the uncore frequency was set for.
          * minimum frequency applied in kHz, or 'None' if not changed.
          * maximum frequencies applied in kHz, or 'None if not changed.
        """

        return self._set_freq(minfreq, maxfreq, pkgs, uncore=True)

    def set_governor(self, governor, cpus="all"):
        """Set scaling governor for CPUs in 'cpus'."""

        keys = set(["CPU", "governors"])
        for info in self.get_cpufreq_info(cpus, keys=keys):
            cpu = info["CPU"]
            _LOG.debug("setting CPU%d governor to '%s'", cpu, governor)
            basedir = self._sysfs_base / "cpufreq" / f"policy{cpu}"

            if governor not in info["governors"]:
                governors_str = ", ".join(info["governors"])
                raise Error(f"governor '{governor}' is not supported on CPU{cpu}"
                            f"{self._proc.hostmsg}, use one of: {governors_str}")

            gov_path = basedir / "scaling_governor"
            self._write(gov_path, governor)
            gov_verify = self._read(gov_path)
            if governor != gov_verify:
                raise Error(f"failed to set CPU{cpu} governor to '{governor}'{self._proc.hostmsg}."
                            f"\nWrote '{governor}' to file '{gov_path}', but read '{gov_verify}' "
                            f"back")

    def set_turbo(self, enable: bool):
        """Enable or disable turbo mode."""

        info = next(self.get_cpufreq_info([0], ("turbo_supported", "turbo_enabled", "driver")))

        if not info["turbo_supported"]:
            raise Error(f"turbo is not supported{self._proc.hostmsg}.")

        if enable == info["turbo_enabled"]:
            return

        if info["driver"] == "intel_pstate" or info["driver"] == "intel_cpufreq":
            turbo_path = self._sysfs_base / "intel_pstate" / "no_turbo"
            value = int(not enable)
        else:
            turbo_path = self._sysfs_base / "cpufreq" / "boost"
            value = int(enable)

        self._write(turbo_path, value)
        value_verify = self._read_int(turbo_path)
        if value_verify != value:
            status = "enable" if enable else "disable"
            raise Error(f"failed to {status} turbo mode{self._proc.hostmsg}.\nWrote '{value}' "
                        f"to file '{turbo_path}', but read '{value_verify}' back")

    def _check_epp_supported(self, cpu):
        """Raise an error if Energy Performance Preference is not supported or it is not enabled."""

        if self._epp_supported:
            return

        self._epp_supported = False
        cpuinfo = self._get_cpuinfo()
        if "hwp_epp" not in cpuinfo.info["flags"]:
            raise Error(f"EPP (Energy Performance Preference) is not supported"
                        f"{self._proc.hostmsg}.")

        if not self._get_hwp_enabled(cpu):
            raise Error(f"EPP (Energy Performance Preference) is not available{self._proc.hostmsg} "
                        f"because it has HWP (Hardware Power Management) disabled")
        self._epp_supported = True

    def _is_epp_supported(self, cpu):
        """Returns 'True' if Energy Performance Preference is supported, otherwise 'False'."""

        if self._epp_supported is not None:
            return self._epp_supported

        with contextlib.suppress(Error):
            self._check_epp_supported(cpu)
            return True
        return False

    def _validate_epp_policy(self, policy):
        """Validate EPP (Energy Performance Preference) policy string."""

        policies = self._get_epp_policies()

        if policy not in policies:
            if policies:
                policy_names = ", ".join(policies)
                msg = f"please provide one of the following EPP policy names: '{policy_names}'"
            else:
                path = self._sysfs_epp_policies
                msg = f"the system does not support EPP policies,\nfile '{path}' does not exist " \
                      f"or lists no policies."
            raise Error(f"EPP policy '{policy}' is not supported{self._proc.hostmsg}, {msg}")

    def get_epp(self, cpus="all"):
        """Yield (CPU number, Energy Performance Preference value) pairs for CPUs in 'cpus'."""

        from pepclibs.msr import HWPRequest, HWPRequestPkg # pylint: disable=import-outside-toplevel

        msr = self._get_msr()
        cpuinfo = self._get_cpuinfo()
        hwpreq = HWPRequest.HWPRequest(proc=self._proc, cpuinfo=cpuinfo, msr=msr)

        hwpreq_pkg = None
        cpus = self._get_cpuinfo().normalize_cpus(cpus)

        for cpu in cpus:
            self._check_epp_supported(cpu)

            # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
            pkg_control = hwpreq.is_cpu_feature_enabled("pkg_control", cpu)
            epp_valid = hwpreq.is_cpu_feature_enabled("epp_valid", cpu)
            if pkg_control and not epp_valid:
                if not hwpreq_pkg:
                    hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(proc=self._proc, cpuinfo=cpuinfo,
                                                             msr=msr)
                hwpreq_msr = hwpreq_pkg
            else:
                hwpreq_msr = hwpreq

            yield (cpu, hwpreq_msr.read_cpu_feature("epp", cpu))

    def get_cpu_epp(self, cpu):
        """Return EPP value for CPU number 'cpu'."""

        cpus = self._get_cpuinfo().normalize_cpus(cpu)
        for _, epp in self.get_epp(cpus=cpus):
            return epp

    def set_epp(self, epp, cpus="all"):
        """
        Set Energy Performance Preference for CPUs in 'cpus'. The 'cpus' argument is the same as the
        'cpus' argument of the 'CPUIdle.get_cstates_info()' function - please, refer to the
        'CPUIdle' module for the exact format description.
        """

        from pepclibs.msr import HWPRequest # pylint: disable=import-outside-toplevel

        msr = self._get_msr()
        cpuinfo = self._get_cpuinfo()
        hwpreq = HWPRequest.HWPRequest(proc=self._proc, cpuinfo=cpuinfo, msr=msr)

        if Trivial.is_int(epp):
            Trivial.validate_int_range(epp, 0, 255, what="EPP")

            hwpreq.write_feature("epp_valid", "on", cpus=cpus)
            hwpreq.write_feature("epp", epp, cpus=cpus)
        else:
            cpus = self._get_cpuinfo().normalize_cpus(cpus)
            for cpu in cpus:
                self._validate_epp_policy(epp)
                path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / \
                       "energy_performance_preference"
                FSHelpers.write(path, epp, proc=self._proc)

    def set_epb(self, epb, cpus="all"):
        """
        Set EPB to value in 'epb' for CPUs in 'cpus'. The arguments are the same as in
        'EPB.set_epb()'.
        """

        self._get_epbobj().set_epb(epb, cpus=cpus)

    @staticmethod
    def _check_prop(prop):
        """Raise an error if a property 'prop' is not supported."""

        if prop not in PROPS:
            props_str = ", ".join(set(PROPS))
            raise Error(f"property '{prop}' not supported, use one of the following: "
                        f"{props_str}")

    def set_prop(self, prop, val, cpus="all"):
        """
        Set value 'val' for property 'prop' for CPUs 'cpus'. This will call the corresponding
        "set" method, e.g. 'set_prop("turbo", val)' is the same as 'set_turbo(val)'. The
        arguments are as follows.
          * prop - name of the property to set (see 'PROPS' for the full list).
          * val - the value to set for the property.
          * cpus - same as in 'CPUIdle.get_cstates_info()'.
        """

        self._check_prop(prop)

        method = getattr(self, f"set_{prop}")
        if prop == "turbo":
            method(val == "on")
        else:
            method(val, cpus=cpus)

    @staticmethod
    def get_scope(prop):
        """Get scope of property 'prop'. The 'prop' argument is same as in 'set_prop()'."""

        CPUFreq._check_prop(prop)
        return PROPS[prop]["scope"]

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._bclk = None
        self._epbobj = None
        self._ufreq_supported = None
        self._epp_supported = None
        self._epp_policies = None

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self._sysfs_epp_policies = self._sysfs_base / "cpufreq" / "policy0" / \
                                   "energy_performance_available_preferences"

        self._ufreq_drv = None
        self._unload_ufreq_drv = False

        if not self._proc:
            self._proc = Procs.Proc()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_ufreq_drv", None):
            if self._unload_ufreq_drv:
                self._ufreq_drv.unload()
            self._ufreq_drv = None

        for attr in ("_epbobj", "_msr", "_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if hasattr(self, f"_close{attr}"):
                    if getattr(self, f"_close{attr}", False):
                        getattr(obj, "close")()
                else:
                    getattr(obj, "close")()

                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
