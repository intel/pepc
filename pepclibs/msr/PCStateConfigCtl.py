# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides API for managing settings in MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is a
model-specific register found on many Intel platforms.
"""

import copy
import logging
from pepclibs.helperlibs import Procs, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.CPUInfo import CPU_DESCR as _CPU_DESCR

_LOG = logging.getLogger()

# Package C-state configuration control Model Specific Register.
MSR_PKG_CST_CONFIG_CONTROL = 0xE2
CFG_LOCK = 15
C1_AUTO_DEMOTION_ENABLE = 26
C1_UNDEMOTION_ENABLE = 28
MAX_PKG_C_STATE_MASK = 0xF

# Ice Lake and Sapphire Rapids Xeon package C-state limits.
_ICX_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6":2, "unlimited" : 7},
                       "aliases" : {"pc6n": "pc6"}}
# Sky-/Cascade-/Cooper- lake Xeon package C-state limits.
_SKX_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6n":2, "pc6r": 3, "unlimited": 7},
                       "aliases" : {"pc6": "pc6r"}}
# Haswell and many other CPUs package C-state limits
_HSW_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc3": 2, "pc6": 3, "unlimited": 8},
                       "aliases" : {}}
# Ivy Town (Ivybridge Xeon) package C-state limits.
_IVT_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6n": 2, "pc6r": 3, "unlimited": 7},
                       "aliases" : {"pc6": "pc6r"}}
# Denverton SoC (Goldmont Atom) package C-state limits.
_DNV_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc6": 3},
                       "aliases" : {}}
# Snow Ridge SoC (Tremont Atom) package C-state limits.
_SNR_PKG_CST_LIMITS = {"codes"   : {"pc0": 0},
                       "aliases" : {}}

# Package C-state limits are platform specific.
_PKG_CST_LIMIT_MAP = {CPUInfo.INTEL_FAM6_SAPPHIRERAPIDS_X: _ICX_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ICELAKE_D:        _ICX_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ICELAKE_X:        _ICX_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_SKYLAKE_X:        _SKX_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ICELAKE_L:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ALDERLAKE:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ALDERLAKE_L:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_ROCKETLAKE:       _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_LAKEFIELD:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_TIGERLAKE:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_TIGERLAKE_L:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_CANNONLAKE_L:     _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_COMETLAKE:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_COMETLAKE_L:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_KABYLAKE:         _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_KABYLAKE_L:       _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_SKYLAKE:          _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_SKYLAKE_L:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_BROADWELL:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_BROADWELL_X:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_BROADWELL_D:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_BROADWELL_G:      _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_HASWELL:          _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_HASWELL_X:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_HASWELL_G:        _HSW_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_IVYBRIDGE_X:      _IVT_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_GOLDMONT_D:       _DNV_PKG_CST_LIMITS,
                      CPUInfo.INTEL_FAM6_TREMONT_D:        _SNR_PKG_CST_LIMITS}

# Map of features available on various CPU models.
#
# Note 1: consider using the 'PCStateConfigCtl.features' dicionary instead of this one.
# Note 2, the "scope" names have to be the same as "level" names in 'CPUInfo'.
FEATURES = {
    "pkg_cstate_limit" : {
        "name" : "Package C-state limit",
        "cpumodels" : list(_PKG_CST_LIMIT_MAP),
        "choices" : "",
        "scope": "package",
        "help" : """The deepest package C-state the platform is allowed to enter. The package
                    C-state limit is configured via MSR {hex(MSR_PKG_CST_CONFIG_CONTROL)}
                    (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                    BIOS, in which case the package C-state limit can only be read, but cannot be
                    modified.""",
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "enabled" : 1,
        "bitnr" : C1_AUTO_DEMOTION_ENABLE,
        "choices" : ["on", "off"],
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "enabled" : 1,
        "bitnr" : C1_UNDEMOTION_ENABLE,
        "choices" : ["on", "off"],
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                    C6/C7.""",
    },
}

class PCStateConfigCtl:
    """
    This class provides API for managing settings in MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is
    a model-specific register found on many Intel platforms.
    """

    def _get_cpuinfo(self):
        """Return an instance of 'CPUInfo' class."""

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)
        return self._cpuinfo

    def _check_feature_support(self, feature):

        if feature not in self.features:
            features_str = ", ".join(set(self.features))
            raise Error(f"unknown feature '{feature}', known features are: {features_str}")

        finfo = self.features[feature]
        if finfo["supported"]:
            return

        model = self._lscpu_info["model"]
        fmt = "%s (CPU model %#x)"
        cpus_str = "\n* ".join([fmt % (CPUInfo.CPU_DESCR[model], model) for model in \
                                finfo["cpumodels"]])
        msg = f"The '{finfo['name']}' feature is not supported{self._proc.hostmsg} - CPU " \
              f"'{self._lscpu_info['vendor']}, (CPU model {hex(model)})' is not supported.\n" \
              f"The currently supported CPU models are:\n* {cpus_str}"
        raise ErrorNotSupported(msg)

    def _get_pkg_cstate_limit_value(self, pcs_limit):
        """
        Convert a package C-state name to integer package C-state limit value suitable for the
        'MSR_PKG_CST_CONFIG_CONTROL' register.
        """

        model = self._lscpu_info["model"]

        pcs_limit = str(pcs_limit).lower()
        codes = _PKG_CST_LIMIT_MAP[model]["codes"]
        aliases = _PKG_CST_LIMIT_MAP[model]["aliases"]

        if pcs_limit in aliases:
            pcs_limit = aliases[pcs_limit]

        limit_val = codes.get(pcs_limit)
        if limit_val is None:
            codes_str = ", ".join(codes)
            aliases_str = ", ".join(aliases)
            raise Error(f"cannot limit package C-state{self._proc.hostmsg}, '{pcs_limit}' is "
                        f"not supported for CPU {_CPU_DESCR[model]} (CPU model {hex(model)}).\n"
                        f"Supported package C-states are: {codes_str}.\n"
                        f"Supported package C-state alias names are: {aliases_str}")
        return limit_val

    def _get_pkg_cstate_limit(self, cpus, pcs_rmap):
        """
        Read 'PKG_CST_CONFIG_CONTROL' MSR for all CPUs 'cpus'. The 'cpus' argument is the same as
        in 'set_feature()' method. The 'pcs_rmap' is reversed dictionary with package C-state code
        and name pairs. Returns a tuple of C-state limit value and locked bit boolean.
        """

        pcs_code = max(pcs_rmap)
        locked = False
        for _, regval in self._msr.read_iter(MSR_PKG_CST_CONFIG_CONTROL, cpus=cpus):
            # The C-state limit value is smallest found among all CPUs and locked bit is 'True' if
            # any of the registers has locked bit set, otherwise it is 'False'.
            pcs_code = min(pcs_code, regval & MAX_PKG_C_STATE_MASK)
            locked = any((locked, regval & MSR.bit_mask(CFG_LOCK)))

            if pcs_code not in pcs_rmap:
                known_codes = ", ".join([str(code) for code in pcs_rmap])
                msg = f"unexpected package C-state limit code '{pcs_code}' read from " \
                      f"'PKG_CST_CONFIG_CONTROL' MSR ({MSR_PKG_CST_CONFIG_CONTROL})" \
                      f"{self._proc.hostmsg}, known codes are: {known_codes}"

                # No exact match. The limit is the closest lower known number. For example, if the
                # known numbers are 0(PC0), 2(PC6), and 7(unlimited), and 'pcs_code' is 3, then the
                # limit is PC6.
                for code in sorted(pcs_rmap, reverse=True):
                    if code <= pcs_code:
                        pcs_code = code
                        break
                else:
                    raise Error(msg)

                _LOG.debug(msg)

        return (pcs_code, locked)

    def feature_supported(self, feature):
        """
        Returns 'True' if feature 'feature' is supported, returns 'False' otherwise. The 'feature'
        argument is one of the keys in the 'FEATURES' dictionary.
        """

        try:
            self._check_feature_support(feature)
            return True
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return False

    def get_available_pkg_cstate_limits(self):
        """
        Return list of all available package C-state limits. Raises an Error if CPU model is not
        supported.
        """

        self._check_feature_support("pkg_cstate_limit")
        return _PKG_CST_LIMIT_MAP[self._lscpu_info["model"]]

    def get_pkg_cstate_limit(self, cpus="all"):
        """
        Get package C-state limit for CPUs 'cpus'. Returns a dictionary with integer CPU numbers
        as keys, and values also being dictionaries with the following 2 elements.
          * limit - the package C-state limit name (small letters, e.g., pc0)
          * locked - a boolean, 'True' if the 'MSR_PKG_CST_CONFIG_CONTROL' register has the
            'CFG_LOCK' bit set, so it is impossible to change the package C-state limit, and 'False'
            otherwise.

        Note, even thought the 'MSR_PKG_CST_CONFIG_CONTROL' register is per-core, it anyway has
        package scope. This function checks the register on all cores and returns the resulting
        shallowest C-state limit. Returns dictionary with package C-state limit and MSR lock
        information.
        """

        self._check_feature_support("pkg_cstate_limit")

        cpuinfo = self._get_cpuinfo()
        model = self._lscpu_info["model"]
        # Get package C-state integer code -> name dictionary.
        pcs_rmap = {code:name for name, code in _PKG_CST_LIMIT_MAP[model]["codes"].items()}

        cpus = set(cpuinfo.get_cpu_list(cpus))
        pkg_to_cpus = {}
        for pkg in cpuinfo.get_packages():
            pkg_cpus = cpuinfo.packages_to_cpus(packages=[pkg])
            if set(pkg_cpus) & cpus:
                pkg_to_cpus[pkg] = []
                for core in cpuinfo.packages_to_cores(packages=[pkg]):
                    core_cpus = cpuinfo.cores_to_cpus(cores=[core])
                    pkg_to_cpus[pkg].append(core_cpus[0])

        limits = {}
        for pkg in pkg_to_cpus:
            limits[pkg] = {}
            pcs_code, locked = self._get_pkg_cstate_limit(pkg_to_cpus[pkg], pcs_rmap)
            limits[pkg] = {"limit" : pcs_rmap[pcs_code], "locked" : locked}

        return limits

    def _set_pkg_cstate_limit(self, pcs_limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        self._check_feature_support("pkg_cstate_limit")
        limit_val = self._get_pkg_cstate_limit_value(pcs_limit)

        cpuinfo = self._get_cpuinfo()
        cpus = set(cpuinfo.get_cpu_list(cpus))

        # Package C-state limit has package scope, but the MSR is per-core.
        pkg_to_cpus = []
        for pkg in cpuinfo.get_packages():
            pkg_cpus = cpuinfo.packages_to_cpus(packages=[pkg])
            if set(pkg_cpus) & cpus:
                for core in cpuinfo.packages_to_cores(packages=[pkg]):
                    core_cpus = cpuinfo.cores_to_cpus(cores=[core])
                    pkg_to_cpus.append(core_cpus[0])

        for cpu, regval in self._msr.read_iter(MSR_PKG_CST_CONFIG_CONTROL, cpus=pkg_to_cpus):
            if MSR.is_bit_set(CFG_LOCK, regval):
                raise Error(f"cannot set package C-state limit{self._proc.hostmsg} for CPU "
                            f"'{cpu}', MSR ({MSR_PKG_CST_CONFIG_CONTROL}) is locked. Sometimes, "
                            f"depending on the vendor, there is a BIOS knob to unlock it.")

            regval = (regval & ~0x07) | limit_val
            self._msr.write(MSR_PKG_CST_CONFIG_CONTROL, regval, cpus=cpu)

    def feature_enabled(self, feature, cpu):
        """
        Returns 'True' if the feature 'feature' is enabled for CPU 'cpu', otherwise returns 'False'.
        The 'feature' argument is one of the keys in 'FEATURES' dictionary. Raises an error if the
        feature cannot be switched simply on or off.
        """

        self._check_feature_support(feature)
        if "enabled" not in self.features[feature]:
            raise Error("feature '{feature}' doesn't support boolean enabled/disabled status")

        regval = self._msr.read(MSR_PKG_CST_CONFIG_CONTROL, cpu=cpu)
        bitval = int(bool(MSR.bit_mask(self.features[feature]["bitnr"]) & regval))
        return self.features[feature]["enabled"] == bitval

    def _set_feature_bool(self, feature, val, cpus):
        """
        Enable or disable feature 'feature' for CPUs 'cpus'. Value 'val' can be boolean or
        string "on" or "off".
        """

        finfo = self.features[feature]
        if isinstance(val, str):
            val = val == "on"
        enable = finfo["enabled"] == val
        self._msr.toggle_bit(MSR_PKG_CST_CONFIG_CONTROL, finfo["bitnr"], enable, cpus=cpus)

    def set_feature(self, feature, val, cpus="all"):
        """
        Set feature 'feature' value to 'val' for CPUs 'cpus'. The 'feature' argument is one of the
        keys in 'FEATURES' dictionary. The 'cpus' argument is the same as the 'cpus' argument of the
        'CPUIdle.get_cstates_info()' function - please, refer to the 'CPUIdle' module for the exact
        format description.
        """

        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if "enabled" in self.features[feature]:
                enable_str = "enable" if val else "disable"
                msg = f"{enable_str} feature '{feature}'"
            else:
                msg = f"set feature '{feature}' value to {val}"

            cpus_range = Human.rangify(self._cpuinfo.get_cpu_list(cpus))
            _LOG.debug("%s on CPU(s) %s%s", msg, cpus_range, self._proc.hostmsg)

        self._check_feature_support(feature)
        if "enabled" in self.features[feature]:
            self._set_feature_bool(feature, val, cpus)
        else:
            set_method = getattr(self, f"_set_{feature}")
            set_method(val, cpus=cpus)

    def _create_features_dict(self):
        """Create an extended version of the 'FEATURES' dictionary."""

        features = copy.deepcopy(FEATURES)

        # Add the "supported" flag.
        for finfo in features.values():
            if not "cpumodels" in finfo:
                # No CPU models list, which means that "all models".
                finfo["supported"] = True
            else:
                cpu_model = self._lscpu_info["model"]
                finfo["supported"] = cpu_model in finfo["cpumodels"]

        return features

    def __init__(self, proc=None, cpuinfo=None, lscpu_info=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * lscpu_info - CPU information generated by 'CPUInfo.get_lscpu_info()'.
        """

        if not proc:
            proc = Procs.Proc()

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._lscpu_info = lscpu_info
        self._msr = MSR.MSR(proc=self._proc)

        self.featres = None

        if self._lscpu_info is None:
            self._lscpu_info = CPUInfo.get_lscpu_info(proc=self._proc)

        if self._lscpu_info["vendor"] != "GenuineIntel":
            msg = f"unsupported CPU model '{self._lscpu_info['vendor']}', model-specific " \
                  f"register {hex(MSR_PKG_CST_CONFIG_CONTROL)} (MSR_PKG_CST_CONFIG_CONTROL) is " \
                  f"not available{self._proc.hostmsg}. MSR_PKG_CST_CONFIG_CONTROL is available " \
                  f"only on Intel platforms."
            raise ErrorNotSupported(msg)

        if self._lscpu_info["model"] not in CPUInfo.CPU_DESCR:
            raise ErrorNotSupported(f"unsupported CPU model '{self._lscpu_info['vendor']}'"
                                    f"{self._proc.hostmsg}")

        self.features = self._create_features_dict()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_proc", None):
            self._proc = None
        if getattr(self, "_msr", None):
            self._msr.close()
            self._msr = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
