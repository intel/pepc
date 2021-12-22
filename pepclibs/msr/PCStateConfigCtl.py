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
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# Package C-state configuration control Model Specific Register.
MSR_PKG_CST_CONFIG_CONTROL = 0xE2

#
# Package C-state limits are documented in Intel SDM, but it describes all the possible package
# C-states for a CPU model. In practice, however, specific platforms often do not support many of
# those package C-states. For example, Xeons typically do not support anything deeper than PC6.
#
# In this file we are trying to define package C-states limits for platforms that we actually
# verified.
#

#
# Xeons.
#
# Ivy Bridge Xeon (Ivy Town).
_IVT_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6n": 2, "pc6r": 3, "unlimited": 7},
                       "aliases" : {"pc6": "pc6r"},
                       "bits"    : (2, 0)}
# Haswell Xeon package C-state limits.
_HSX_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc3": 2, "pc6": 3, "unlimited": 7},
                       "bits"    : (2, 0)}
# Broadwell-D Xeon.
_BDWD_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc3": 2, "pc6": 3},
                        "bits"    : (3, 0)}
# Sky/Cascade/Cooper Lake Xeon, Skylake-D Xeon.
_SKX_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6n": 2, "pc6r": 3, "unlimited": 7},
                       "aliases" : {"pc6": "pc6r"},
                       "bits"    : (2, 0)}
# Ice Lake and Sapphire Rapids Xeon.
_ICX_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc2": 1, "pc6":2, "unlimited" : 7},
                       "aliases" : {"pc6n": "pc6"},
                       "bits"    : (2, 0)}

#
# Atom-based micro servers.
#
# Denverton SoC (Goldmont).
_DNV_PKG_CST_LIMITS = {"codes"   : {"pc0": 0, "pc6": 1},
                       "bits"    : (3, 0)}
# Snow Ridge SoC (Tremont).
_SNR_PKG_CST_LIMITS = {"codes"   : {"pc0": 0},
                       "bits"    : (3, 0)}

# CPU ID -> Package C-state limit map.
_PKG_CST_LIMITS = {
        # Xeons.
        CPUInfo.INTEL_FAM6_SAPPHIRERAPIDS_X: _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_X:        _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_D:        _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_SKYLAKE_X:        _SKX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_IVYBRIDGE_X:      _IVT_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_HASWELL_X:        _HSX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_X:      _HSX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_D:      _BDWD_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_G:      _BDWD_PKG_CST_LIMITS,
        # Atom microservers.
        CPUInfo.INTEL_FAM6_GOLDMONT_D:       _DNV_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_TREMONT_D:        _SNR_PKG_CST_LIMITS,
}

# Map of features available on various CPU models.
#
# Note: this is only the initial, general definition. Many things are platform-depeondent, so full
#       dictionary is available in 'PCStateConfigCtl.features'.
FEATURES = {
    "pkg_cstate_limit" : {
        "name" : "Package C-state limit",
        "scope": "package",
        "help" : """The deepest package C-state the platform is allowed to enter. The package
                    C-state limit is configured via MSR {hex(MSR_PKG_CST_CONFIG_CONTROL)}
                    (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                    BIOS, in which case the package C-state limit can only be read, but cannot be
                    modified.""",
        "cpumodels" : tuple(_PKG_CST_LIMITS.keys()),
        "type" : "int",
        "bits" : None,
    },
    "locked" :  {
        "name" : "MSR is locked",
        "scope": "package",
        "help" : """Lock/unlock bits 15:0 of MSR {hex(MSR_PKG_CST_CONFIG_CONTROL)}
                    (MSR_PKG_CST_CONFIG_CONTROL), which include the Package C-state limit. This bit
                    is typically set by BIOS, and sometimes there is a BIOS menu to lock/unlock the
                    MSR.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (15, 15),
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (26, 26),
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "scope": "CPU",
        "help" : """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                    C6/C7.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (28, 28),
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
        code = self._msr.read_bits(self.msr_addr, feature["bits"], cpu=cpu)

        model = self._cpuinfo.info["model"]
        if not self._pcs_rmap:
            # Build the code -> name map.
            pcs_map = _PKG_CST_LIMITS[model]["codes"]
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

        codes = _PKG_CST_LIMITS[model]["codes"]
        aliases = _PKG_CST_LIMITS[model].get("aliases", {})

        return {"CPU" : self._cpuinfo.normalize_cpu(cpu),
                "pkg_cstate_limit" : self._pcs_rmap[code],
                "pkg_cstate_limits" : list(codes.keys()),
                "pkg_cstate_limit_aliases" : aliases}

    def _normalize_pkg_cstate_limit(self, limit):
        """
        Convert a package C-state limit name, alias, or code (whatever user provides) into an
        integer value suitable for the 'MSR_PKG_CST_CONFIG_CONTROL' register.
        """

        model = self._cpuinfo.info["model"]
        limit = str(limit).lower()
        codes = _PKG_CST_LIMITS[model]["codes"]
        aliases = _PKG_CST_LIMITS[model].get("aliases", {})

        if limit in aliases:
            limit = aliases[limit]

        code = codes.get(limit)
        if code is None:
            codes_str = ", ".join(codes)
            aliases_str = ", ".join(aliases)
            raise Error(f"cannot limit package C-state{self._proc.hostmsg}, '{limit}' is not "
                        f"supported for {self._cpuinfo.cpudescr}).\n"
                        f"Supported package C-states are: {codes_str}.\n"
                        f"Supported package C-state alias names are: {aliases_str}")

        return code

    def _set_pkg_cstate_limit(self, limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        self._check_feature_support("pkg_cstate_limit")
        code = self._normalize_pkg_cstate_limit(limit)

        for cpu, regval in self._msr.read_iter(MSR_PKG_CST_CONFIG_CONTROL, cpus=cpus):
            if self._msr.get_bits(regval, self.features["locked"]["bits"]):
                raise Error(f"cannot set package C-state limit{self._proc.hostmsg} for CPU "
                            f"'{cpu}', MSR ({MSR_PKG_CST_CONFIG_CONTROL}) is locked. Sometimes, "
                            f"depending on the vendor, there is a BIOS knob to unlock it.")

            regval = (regval & ~0x07) | code
            self._msr.write(MSR_PKG_CST_CONFIG_CONTROL, regval, cpus=cpu)

    def _init_features_dict(self):
        """Intitialize the 'features' dictionary with platform-specific information."""

        super()._init_features_dict()

        pcs_feature = self.features["pkg_cstate_limit"]
        cpumodel = self._cpuinfo.info["model"]

        if not pcs_feature["supported"]:
            _LOG.notice("no package C-state limit table available for %s%s. Try to contact "
                        "project maintainers.", self._cpuinfo.cpudescr, self._proc.hostmsg)
            return

        limits_info = _PKG_CST_LIMITS[cpumodel]
        pcs_feature["bits"] = limits_info["bits"]

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        self.msr_addr = MSR_PKG_CST_CONFIG_CONTROL
        self.msr_name = "MSR_PKG_CST_CONFIG_CONTROL"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)

        # The package C-state integer code -> package C-state name dictionary.
        self._pcs_rmap = None
