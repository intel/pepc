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
_IVT_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6N": 2, "PC6R": 3, "unlimited": 7},
                       "aliases" : {"PC6": "PC6R"},
                       "bits"    : (2, 0)}
# Haswell Xeon package C-state limits.
_HSX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "unlimited": 7},
                       "bits"    : (2, 0)}
# Broadwell-D Xeon.
_BDWD_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3},
                        "bits"    : (3, 0)}
# Sky/Cascade/Cooper Lake Xeon, Skylake-D Xeon.
_SKX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6N": 2, "PC6R": 3, "unlimited": 7},
                       "aliases" : {"PC6": "PC6R"},
                       "bits"    : (2, 0)}
# Ice Lake and Sapphire Rapids Xeon.
_ICX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6": 2, "unlimited": 7},
                       "aliases" : {"PC6N": "PC6"},
                       "bits"    : (2, 0)}
#
# Atom-based micro servers.
#
# Denverton SoC (Goldmont).
_DNV_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC6": 1},
                       "bits"    : (3, 0)}
# Snow Ridge SoC (Tremont).
_SNR_PKG_CST_LIMITS = {"codes"   : {"PC0": 0},
                       "bits"    : (3, 0)}

#
# Clients.
#
_CLIENT_PC7S_CST_LIMITS = {"codes" : {"PC0" : 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5},
                           "bits" : (3, 0)}
_CLIENT_PC10_CST_LIMITS = {"codes" : {"PC0" : 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5,
                           "PC8": 6, "PC9": 7, "PC10": 8},
                           "bits" : (3, 0)}

# CPU ID -> Package C-state limit map.
_PKG_CST_LIMITS = {
        # Xeons.
        CPUInfo.INTEL_FAM6_SAPPHIRERAPIDS_X: _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_X:        _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_D:        _ICX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_SKYLAKE_X:        _SKX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_X:      _HSX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_D:      _BDWD_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL_G:      _BDWD_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_HASWELL_X:        _HSX_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_IVYBRIDGE_X:      _IVT_PKG_CST_LIMITS,
        # Atom microservers.
        CPUInfo.INTEL_FAM6_GOLDMONT_D:       _DNV_PKG_CST_LIMITS,
        CPUInfo.INTEL_FAM6_TREMONT_D:        _SNR_PKG_CST_LIMITS,
        # Clients.
        # Deepest: PC10.
        CPUInfo.INTEL_FAM6_ROCKETLAKE:       _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ALDERLAKE:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ALDERLAKE_L:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_TIGERLAKE:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_TIGERLAKE_L:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_LAKEFIELD:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_COMETLAKE:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_COMETLAKE_L:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_KABYLAKE_L:       _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_KABYLAKE:         _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_L:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_ICELAKE_NNPI:     _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_CANNONLAKE_L:     _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_SKYLAKE:          _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_SKYLAKE_L:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_BROADWELL:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.INTEL_FAM6_HASWELL_L:        _CLIENT_PC10_CST_LIMITS,
        # Deepest: PC7S.
        CPUInfo.INTEL_FAM6_HASWELL:          _CLIENT_PC7S_CST_LIMITS,
        CPUInfo.INTEL_FAM6_HASWELL_G:        _CLIENT_PC7S_CST_LIMITS,
}

# Map of features available on various CPU models. Please, refer to the notes for
# '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "pkg_cstate_limit" : {
        "name" : "Package C-state limit",
        "scope": "package",
        "help" : """The deepest package C-state the platform is allowed to enter. The package
                    C-state limit is configured via MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                    (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                    BIOS, in which case the package C-state limit can only be read, but cannot be
                    modified.""",
        "cpumodels" : tuple(_PKG_CST_LIMITS.keys()),
        "type"    : "choice",
        "vals"    : None,
        "aliases" : {},
        "bits"    : None,
    },
    "locked" :  {
        "name" : "MSR lock",
        "scope": "package",
        "help" : """Lock/unlock bits 15:0 of MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                    (MSR_PKG_CST_CONFIG_CONTROL), which include the Package C-state limit. This bit
                    is typically set by BIOS, and sometimes there is a BIOS menu to lock/unlock the
                    MSR.""",
        "type" : "bool",
        "vals" : { "on" : 1, "off" : 0},
        "bits" : (15, 15),
        "writable" : False,
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "scope": "core",
        "help" : """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
        "type" : "bool",
        "vals" : { "on" : 1, "off" : 0},
        "bits" : (26, 26),
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "scope": "core",
        "help" : """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                    C6/C7.""",
        "type" : "bool",
        "vals" : { "on" : 1, "off" : 0},
        "bits" : (28, 28),
    },
}

class PCStateConfigCtl(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is a model-specific
    register found on many Intel platforms.
    """

    def _get_pkg_cstate_limit(self, cpus="all"):
        """
        Get package C-state limit for CPUs in 'cpus'. For every CPU in 'cpus', yields a tuple of
        '(cpunum, info)', where 'cpunum' is the CPU number the limits were read from, and 'info' is
        the package C-state information dictionary. Here are the 'info' dictionary keys.
          * limit - the package C-state limit name (small letters, e.g., PC0).
          * limits - list of possible package C-state limits.
          * aliases - some package C-state may have multiple names, which means the same limit. This
                      module uses one name as the primary name, and it is provided in the 'limits'
                      list. The other names are considered to be aliases, and they are provided in
                      the 'aliases'.
        """

        finfo = self._features["pkg_cstate_limit"]

        for cpu, code in self._msr.read_bits(self.regaddr, finfo["bits"], cpus=cpus):
            if code not in finfo["rvals"]:
                # No exact match. The limit is the closest lower known number. For example, if the
                # known numbers are 0(PC0), 2(PC6), and 7(unlimited), and 'code' is 3, then the
                # limit is PC6.
                for cde in sorted(finfo["rvals"], reverse=True):
                    if cde <= code:
                        code = cde
                        break

                known_codes = ", ".join([str(cde) for cde in finfo["rvals"]])
                raise Error(f"unexpected package C-state limit code '{code}' read from "
                            f"'{self.regname}' MSR ({self.regaddr}){self._proc.hostmsg}, known "
                            f"codes are: {known_codes}")

            res = {"pkg_cstate_limit" : finfo["rvals"][code],
                   "pkg_cstate_limits" : list(finfo["vals"].keys()),
                   "pkg_cstate_limit_aliases" : finfo["aliases"]}
            yield (cpu, res)

    def _set_pkg_cstate_limit(self, limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        finfo = self._features["pkg_cstate_limit"]

        for cpu, regval in self._msr.read(self.regaddr, cpus=cpus):
            if self._msr.get_bits(regval, self._features["locked"]["bits"]):
                raise Error(f"cannot set package C-state limit{self._proc.hostmsg} for CPU "
                            f"'{cpu}', MSR {MSR_PKG_CST_CONFIG_CONTROL:#x} is locked. Sometimes, "
                            f"depending on the vendor, there is a BIOS knob to unlock it.")

            regval = self._msr.set_bits(regval, finfo["bits"], limit)
            self._msr.write_cpu(self.regaddr, regval, cpu)

    def _init_features_dict_pkg_cstate_limit(self):
        """Initialize the 'pkg_cstate_limit' information in the 'self._features' dictionary."""

        if not self._features["pkg_cstate_limit"]["supported"]:
            _LOG.notice("no package C-state limit table available for %s%s. Try to contact "
                        "project maintainers.", self._cpuinfo.cpudescr, self._proc.hostmsg)
            return

        cpumodel = self._cpuinfo.info["model"]
        cpumodel_info = _PKG_CST_LIMITS[cpumodel]

        finfo = self._features["pkg_cstate_limit"]
        finfo["bits"] = cpumodel_info["bits"]
        finfo["vals"] = cpumodel_info["codes"]
        if "aliases" in cpumodel_info:
            finfo["aliases"] = cpumodel_info["aliases"]

    def _init_features_dict(self):
        """Intitialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_pkg_cstate_limit()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_PKG_CST_CONFIG_CONTROL
        self.regname = "MSR_PKG_CST_CONFIG_CONTROL"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)
