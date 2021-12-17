# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is a model-specific register
found on many Intel platforms.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo
from pepclibs.msr import MSR, _FeaturedMSR
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
        "scope": "package",
        "help" : """The deepest package C-state the platform is allowed to enter. The package
                    C-state limit is configured via MSR {hex(MSR_PKG_CST_CONFIG_CONTROL)}
                    (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                    BIOS, in which case the package C-state limit can only be read, but cannot be
                    modified.""",
        "cpumodels" : tuple(_PKG_CST_LIMIT_MAP.keys()),
        "type" : "int",
        "bits" : (3, 0)
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (C1_AUTO_DEMOTION_ENABLE, C1_AUTO_DEMOTION_ENABLE),
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                    C6/C7.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (C1_UNDEMOTION_ENABLE, C1_UNDEMOTION_ENABLE),
    },
}

class PCStateConfigCtl(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is a model-specific
    register found on many Intel platforms.
    """

    def _get_pkg_cstate_limit(self, cpu):
        """
        Get package C-state limit for CPU 'cpus'. Returns a dictionary with the following keys.
          * CPU - the CPU number the limit was read at.
          * limit - the package C-state limit name (small letters, e.g., pc0).
          * locked - a boolean, 'True' if the 'MSR_PKG_CST_CONFIG_CONTROL' register is locked, so it
                     is impossible to change the package C-state limit, and 'False' otherwise.
          * limits - list of possible package C-state limits.
          * aliases - some package C-state may have multiple names, which means the same limit. This
                      module uses one name as the primary name, and it is provided in the 'limits'
                      list. The other names are considered to be aliases, and they are provided in
                      the 'aliases'.
        """

        self._check_feature_support("pkg_cstate_limit")

        feature = self.features["pkg_cstate_limit"]
        regval = self._msr.read(self.msr_addr, cpu=cpu)
        code = MSR.fetch_bits(feature["bits"], regval)
        locked = bool(regval & MSR.bit_mask(CFG_LOCK))

        model = self._lscpu_info["model"]
        if not self._pcs_rmap:
            # Build the code -> name map.
            pcs_map = _PKG_CST_LIMIT_MAP[model]["codes"]
            self._pcs_rmap = {code:name for name, code in pcs_map.items()}

        if code not in self._pcs_rmap:
            known_codes = ", ".join([str(cde) for cde in self._pcs_rmap])
            msg = f"unexpected package C-state limit code '{code}' read from '{self.msr_name}' " \
                  f"MSR ({self.msr_addr}){self._proc.hostmsg}, known codes are: {known_codes}"

            # No exact match. The limit is the closest lower known number. For example, if the
            # known numbers are 0(PC0), 2(PC6), and 7(unlimited), and 'code' is 3, then the limit is
            # PC6.
            for cde in sorted(self._pcs_rmap, reverse=True):
                if cde <= code:
                    code = cde
                    break
            else:
                raise Error(msg)

            _LOG.debug(msg)

        codes = _PKG_CST_LIMIT_MAP[model]["codes"]
        aliases = _PKG_CST_LIMIT_MAP[model]["aliases"]

        return {"CPU" : self._cpuinfo.normalize_cpu(cpu),
                "pkg_cstate_limit" : self._pcs_rmap[code],
                "pkg_cstate_limit_locked" : locked,
                "pkg_cstate_limits" : list(codes.keys()),
                "pkg_cstate_limit_aliases" : aliases}

    def _normalize_pkg_cstate_limit(self, limit):
        """
        Convert a package C-state limit name, alias, or code (whatever user provides) into an
        integer value suitable for the 'MSR_PKG_CST_CONFIG_CONTROL' register.
        """

        model = self._lscpu_info["model"]

        limit = str(limit).lower()
        codes = _PKG_CST_LIMIT_MAP[model]["codes"]
        aliases = _PKG_CST_LIMIT_MAP[model]["aliases"]

        if limit in aliases:
            limit = aliases[limit]

        code = codes.get(limit)
        if code is None:
            codes_str = ", ".join(codes)
            aliases_str = ", ".join(aliases)
            raise Error(f"cannot limit package C-state{self._proc.hostmsg}, '{limit}' is not "
                        f"supported for CPU {_CPU_DESCR[model]} (CPU model {hex(model)}).\n"
                        f"Supported package C-states are: {codes_str}.\n"
                        f"Supported package C-state alias names are: {aliases_str}")

        return code

    def _set_pkg_cstate_limit(self, limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        self._check_feature_support("pkg_cstate_limit")
        code = self._normalize_pkg_cstate_limit(limit)

        for cpu, regval in self._msr.read_iter(MSR_PKG_CST_CONFIG_CONTROL, cpus=cpus):
            if MSR.is_bit_set(CFG_LOCK, regval):
                raise Error(f"cannot set package C-state limit{self._proc.hostmsg} for CPU "
                            f"'{cpu}', MSR ({MSR_PKG_CST_CONFIG_CONTROL}) is locked. Sometimes, "
                            f"depending on the vendor, there is a BIOS knob to unlock it.")

            regval = (regval & ~0x07) | code
            self._msr.write(MSR_PKG_CST_CONFIG_CONTROL, regval, cpus=cpu)

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        self.msr_addr = MSR_PKG_CST_CONFIG_CONTROL
        self.msr_name = "MSR_PKG_CST_CONFIG_CONTROL"

    def __init__(self, proc=None, cpuinfo=None, lscpu_info=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * lscpu_info - CPU information generated by 'CPUInfo.get_lscpu_info()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, lscpu_info=lscpu_info, msr=msr)

        # The package C-state integer code -> package C-state name dictionary.
        self._pcs_rmap = None
