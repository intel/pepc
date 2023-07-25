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
# Ice Lake and Granite Rapids Xeons.
_ICX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6": 2, "unlimited": 7},
                       "aliases" : {"PC6N": "PC6"},
                       "bits"    : (2, 0)}
# Emerald Rapids, Sapphire Rapids, Cooper Lake, Cascade Lake, Sky Lake Xeons. Knights Mill and
# Knights Landing Xeon Phis.
_SKX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6N": 2, "PC6R": 3, "unlimited": 7},
                       "aliases" : {"PC6": "PC6R"},
                       "bits"    : (2, 0)}
# Broadwell-D Xeon.
_BDWD_PKG_CST_LIMITS = {"codes"  : {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3},
                        "bits"   : (3, 0)}
# Broadwell and Haswell Xeons.
_HSX_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "unlimited": 7},
                       "bits"    : (2, 0)}
# Ivy Bridge Xeon (Ivy Town).
_IVT_PKG_CST_LIMITS = {"codes"   : {"PC0": 0, "PC2": 1, "PC6N": 2, "PC6R": 3, "unlimited": 7},
                       "aliases" : {"PC6": "PC6R"},
                       "bits"    : (2, 0)}

#
# Atom-based micro servers.
#
# Grand Ridge (Crestmont) and Snow Ridge (Tremont) SoCs.
_SNR_PKG_CST_LIMITS = {"codes"   : {"PC2": 2, "unlimited": 0},
                       "bits"    : (3, 0)}
# Denverton SoC (Goldmont).
_DNV_PKG_CST_LIMITS = {"codes"   : {"PC2": 2, "PC6": 3, "unlimited": 0},
                       "bits"    : (3, 0)}

#
# Clients.
#
_CLIENT_PC10_CST_LIMITS = {"codes" : {"PC0" : 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5,
                           "PC8": 6, "PC9": 7, "PC10": 8},
                           "bits" : (3, 0)}
_CLIENT_PC7S_CST_LIMITS = {"codes" : {"PC0" : 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5},
                           "bits" : (3, 0)}

# CPU ID -> Package C-state limit map.
_PKG_CST_LIMITS = {
        # Xeons.
        CPUInfo.CPUS["SIERRAFOREST_X"]["model"]:   _ICX_PKG_CST_LIMITS,
        CPUInfo.CPUS["GRANITERAPIDS_X"]["model"]:  _ICX_PKG_CST_LIMITS,
        CPUInfo.CPUS["GRANITERAPIDS_D"]["model"]:  _ICX_PKG_CST_LIMITS,
        CPUInfo.CPUS["EMERALDRAPIDS_X"]["model"]:  _SKX_PKG_CST_LIMITS,
        CPUInfo.CPUS["SAPPHIRERAPIDS_X"]["model"]: _SKX_PKG_CST_LIMITS,
        CPUInfo.CPUS["ICELAKE_X"]["model"]:        _ICX_PKG_CST_LIMITS,
        CPUInfo.CPUS["ICELAKE_D"]["model"]:        _ICX_PKG_CST_LIMITS,
        CPUInfo.CPUS["SKYLAKE_X"]["model"]:        _SKX_PKG_CST_LIMITS,
        CPUInfo.CPUS["BROADWELL_X"]["model"]:      _HSX_PKG_CST_LIMITS,
        CPUInfo.CPUS["BROADWELL_D"]["model"]:      _BDWD_PKG_CST_LIMITS,
        CPUInfo.CPUS["BROADWELL_G"]["model"]:      _BDWD_PKG_CST_LIMITS,
        CPUInfo.CPUS["HASWELL_X"]["model"]:        _HSX_PKG_CST_LIMITS,
        CPUInfo.CPUS["IVYBRIDGE_X"]["model"]:      _IVT_PKG_CST_LIMITS,
        # Xeon Phi.
        CPUInfo.CPUS["XEON_PHI_KNM"]["model"]:     _SKX_PKG_CST_LIMITS,
        CPUInfo.CPUS["XEON_PHI_KNL"]["model"]:     _SKX_PKG_CST_LIMITS,
        # Atom microservers.
        CPUInfo.CPUS["GRANDRIDGE"]["model"]:       _SNR_PKG_CST_LIMITS,
        CPUInfo.CPUS["TREMONT_D"]["model"]:        _SNR_PKG_CST_LIMITS,
        CPUInfo.CPUS["GOLDMONT_D"]["model"]:       _DNV_PKG_CST_LIMITS,
        # Clients.
        # Deepest: PC10.
        CPUInfo.CPUS["ROCKETLAKE"]["model"]:       _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["ALDERLAKE"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["ALDERLAKE_L"]["model"]:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["ALDERLAKE_N"]["model"]:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["TIGERLAKE"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["TIGERLAKE_L"]["model"]:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["LAKEFIELD"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["COMETLAKE"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["COMETLAKE_L"]["model"]:      _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["KABYLAKE_L"]["model"]:       _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["KABYLAKE"]["model"]:         _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["ICELAKE_L"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["ICELAKE_NNPI"]["model"]:     _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["CANNONLAKE_L"]["model"]:     _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["SKYLAKE"]["model"]:          _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["SKYLAKE_L"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["BROADWELL"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        CPUInfo.CPUS["HASWELL_L"]["model"]:        _CLIENT_PC10_CST_LIMITS,
        # Deepest: PC7S.
        CPUInfo.CPUS["HASWELL"]["model"]:          _CLIENT_PC7S_CST_LIMITS,
        CPUInfo.CPUS["HASWELL_G"]["model"]:        _CLIENT_PC7S_CST_LIMITS,
}

# MSR_PKG_CST_CONFIG_CONTROL features have core scope, except for the following CPU models.
_MODULE_SCOPE_CPUS = CPUInfo.SILVERMONTS + CPUInfo.AIRMONTS
_PACKAGE_SCOPE_CPUS = CPUInfo.PHIS

# Map of features available on various CPU models. Please, refer to the notes for
# '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "pkg_cstate_limit" : {
        "name" : "Package C-state limit",
        "sname": None,
        "help" : """The deepest package C-state the platform is allowed to enter. The package
                    C-state limit is configured via MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                    (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                    BIOS, in which case the package C-state limit can only be read, but cannot be
                    modified.""",
        "cpumodels" : tuple(_PKG_CST_LIMITS.keys()),
        "type"    : "dict",
        "vals"    : None,
        "aliases" : {},
        "bits"    : None,
    },
    "lock" :  {
        "name" : "MSR lock",
        "sname": None,
        "help" : """Lock/unlock bits 15:0 of MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                    (MSR_PKG_CST_CONFIG_CONTROL), which include the Package C-state limit. This bit
                    is typically set by BIOS, and sometimes there is a BIOS menu to lock/unlock the
                    MSR.""",
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (15, 15),
        "writable" : False,
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "sname": None,
        "help" : """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (26, 26),
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "sname": None,
        "help" : """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                    C6/C7.""",
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (28, 28),
    },
}

class PCStateConfigCtl(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL). This is a model-specific
    register found on many Intel platforms.
    """

    regaddr = MSR_PKG_CST_CONFIG_CONTROL
    regname = "MSR_PKG_CST_CONFIG_CONTROL"
    vendor = "GenuineIntel"

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

        for cpu, code in self._msr.read_bits(self.regaddr, finfo["bits"], cpus=cpus,
                                             sname=finfo["sname"]):
            if code not in finfo["rvals"]:
                # No exact match. The limit is the closest lower known number. For example, if the
                # known numbers are 0(PC0), 2(PC6), and 7(unlimited), and 'code' is 3, then the
                # limit is PC6.
                #
                # On some platforms code 0 is "unlimited" (e.g., Denverton). Do not resolve unkown
                # numbers to "unlimited".
                for cde in sorted(finfo["rvals"], reverse=True):
                    if cde <= code and finfo["rvals"][cde] != "unlimited":
                        limit = finfo["rvals"][cde]
                        break
                else:
                    known_codes = [f"{cde} ({lmt})" for cde, lmt in finfo["rvals"].items()]
                    _LOG.warn_once("unexpected package C-state limit code '%d' read from '%s' MSR "
                                   "(%#x) on CPU %d%s. Known codes are: %s", code, self.regname,
                                   self.regaddr, cpu, self._pman.hostmsg, ", ".join(known_codes))
                    limit = str(code)
            else:
                limit = finfo["rvals"][code]

            res = {"pkg_cstate_limit" : limit,
                   "pkg_cstate_limits" : list(finfo["vals"].keys()),
                   "pkg_cstate_limit_aliases" : finfo["aliases"]}
            yield (cpu, res)

    def _set_pkg_cstate_limit(self, limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        finfo = self._features["pkg_cstate_limit"]
        regvals = {}

        for cpu, regval in self._msr.read(self.regaddr, cpus=cpus, sname=finfo["sname"]):
            if self._msr.get_bits(regval, self._features["lock"]["bits"]):
                raise Error(f"cannot set package C-state limit{self._pman.hostmsg} for CPU "
                            f"'{cpu}', MSR {MSR_PKG_CST_CONFIG_CONTROL:#x} is locked. Sometimes, "
                            f"depending on the vendor, there is a BIOS knob to unlock it")

            new_regval = self._msr.set_bits(regval, finfo["bits"], limit)
            if regval == new_regval:
                continue

            if new_regval not in regvals:
                regvals[new_regval] = []
            regvals[new_regval].append(cpu)

        for regval, regval_cpus in regvals.items():
            self._msr.write(self.regaddr, regval, regval_cpus, sname=finfo["sname"])

    def _init_features_dict_pkg_cstate_limit(self):
        """Initialize the 'pkg_cstate_limit' information in the 'self._features' dictionary."""

        if not self.is_feature_supported("pkg_cstate_limit", cpus="all"):
            _LOG.notice("no package C-state limit table available for %s%s. Try to contact "
                        "project maintainers.", self._cpuinfo.cpudescr, self._pman.hostmsg)
            return

        cpumodel = self._cpuinfo.info["model"]
        cpumodel_info = _PKG_CST_LIMITS[cpumodel]

        finfo = self._features["pkg_cstate_limit"]
        finfo["bits"] = cpumodel_info["bits"]
        finfo["vals"] = cpumodel_info["codes"]
        if "aliases" in cpumodel_info:
            finfo["aliases"] = cpumodel_info["aliases"]

    def _init_features_dict(self):
        """Initialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_pkg_cstate_limit()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        model = self._cpuinfo.info["model"]

        if model in _MODULE_SCOPE_CPUS:
            sname = "module"
        elif model in _PACKAGE_SCOPE_CPUS:
            sname = "package"
        else:
            sname = "core"

        for finfo in self.features.values():
            finfo["sname"] = sname

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
