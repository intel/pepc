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

from pepclibs import CPUModels
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.msr import _FeaturedMSR
from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict


_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

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
_ICX_PKG_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC6": 2, "unlimited": 7},
                       "bits": (2, 0)}
# Emerald Rapids, Sapphire Rapids, Cooper Lake, Cascade Lake, Sky Lake Xeons. Knights Mill and
# Knights Landing Xeon Phis.
_SKX_PKG_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC6": 2, "PC6R": 3, "unlimited": 7},
                       "bits": (2, 0)}
# Broadwell-D Xeon.
_BDWD_PKG_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3}, "bits": (3, 0)}
# Broadwell and Haswell Xeons.
_HSX_PKG_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "unlimited": 7},
                       "bits": (2, 0)}
# Ivy Bridge Xeon (Ivy Town).
_IVT_PKG_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC6": 2, "PC6R": 3, "unlimited": 7},
                       "bits": (2, 0)}

#
# Atom-based micro servers.
#
# Denverton SoC (Goldmont). Note, successor of Denverton is Snow Ridge, and its successor is Grand
# Ridge. They do not support package C-states.
_DNV_PKG_CST_LIMITS = {"codes": {"PC2": 2, "PC6": 3, "unlimited": 0}, "bits": (3, 0)}

#
# Clients.
#
_CLIENT_LNL_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC6": 3, "PC10": 8}, "bits": (3, 0)}
_CLIENT_PC10_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5,
                                     "PC8": 6, "PC9": 7, "PC10": 8},
                           "bits": (3, 0)}
_CLIENT_PC7S_CST_LIMITS = {"codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5},
                           "bits": (3, 0)}

# CPU ID -> Package C-state limit map.
_PKG_CST_LIMITS = {
    # Xeons.
    CPUModels.MODELS["ATOM_DARKMONT_X"]["vfm"]:  _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["ATOM_CRESTMONT_X"]["vfm"]: _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["GRANITERAPIDS_X"]["vfm"]:  _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["GRANITERAPIDS_D"]["vfm"]:  _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["EMERALDRAPIDS_X"]["vfm"]:  _SKX_PKG_CST_LIMITS,
    CPUModels.MODELS["SAPPHIRERAPIDS_X"]["vfm"]: _SKX_PKG_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_X"]["vfm"]:        _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_D"]["vfm"]:        _ICX_PKG_CST_LIMITS,
    CPUModels.MODELS["SKYLAKE_X"]["vfm"]:        _SKX_PKG_CST_LIMITS,
    CPUModels.MODELS["BROADWELL_X"]["vfm"]:      _HSX_PKG_CST_LIMITS,
    CPUModels.MODELS["BROADWELL_D"]["vfm"]:      _BDWD_PKG_CST_LIMITS,
    CPUModels.MODELS["BROADWELL_G"]["vfm"]:      _BDWD_PKG_CST_LIMITS,
    CPUModels.MODELS["HASWELL_X"]["vfm"]:        _HSX_PKG_CST_LIMITS,
    CPUModels.MODELS["IVYBRIDGE_X"]["vfm"]:      _IVT_PKG_CST_LIMITS,
    # Xeon Phi.
    CPUModels.MODELS["XEON_PHI_KNM"]["vfm"]:     _SKX_PKG_CST_LIMITS,
    CPUModels.MODELS["XEON_PHI_KNL"]["vfm"]:     _SKX_PKG_CST_LIMITS,
    # Atom microservers.
    CPUModels.MODELS["ATOM_GOLDMONT_D"]["vfm"]:  _DNV_PKG_CST_LIMITS,
    # Clients.
    # Deepest: PC10.
    CPUModels.MODELS["ARROWLAKE"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ARROWLAKE_H"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ARROWLAKE_U"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE"]["vfm"]:       _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE_L"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE"]["vfm"]:       _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE_S"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE_P"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE_L"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE_N"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ROCKETLAKE"]["vfm"]:       _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["TIGERLAKE"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["TIGERLAKE_L"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["LAKEFIELD"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["COMETLAKE"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["COMETLAKE_L"]["vfm"]:      _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["KABYLAKE_L"]["vfm"]:       _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["KABYLAKE"]["vfm"]:         _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_L"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_NNPI"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["CANNONLAKE_L"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["SKYLAKE"]["vfm"]:          _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["SKYLAKE_L"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["BROADWELL"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["HASWELL_L"]["vfm"]:        _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE_L"]["vfm"]:     _CLIENT_PC10_CST_LIMITS,
    CPUModels.MODELS["LUNARLAKE_M"]["vfm"]:      _CLIENT_LNL_CST_LIMITS,
    # Deepest: PC7S.
    CPUModels.MODELS["HASWELL"]["vfm"]:          _CLIENT_PC7S_CST_LIMITS,
    CPUModels.MODELS["HASWELL_G"]["vfm"]:        _CLIENT_PC7S_CST_LIMITS,
}

# MSR_PKG_CST_CONFIG_CONTROL features have core scope, except for the following CPUs.
_MODULE_IO_SCOPE_VFMS = CPUModels.CPU_GROUPS["SILVERMONT"] + CPUModels.CPU_GROUPS["AIRMONT"]
_PACKAGE_IO_SCOPE_VFMS = CPUModels.CPU_GROUPS["PHI"]

# Platforms that where C1 demotion/undemotion I/O scope is "core".
_CORE_C1D_SCOPE_VFMS = CPUModels.CPU_GROUPS["EMR"] + \
                       CPUModels.CPU_GROUPS["SPR"] + \
                       CPUModels.CPU_GROUPS["ICX"]

# Map of features available on various CPUs.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "pkg_cstate_limit": {
        "name": "Package C-state limit",
        "sname": None,
        "iosname": None,
        "help": """The deepest package C-state the platform is allowed to enter. The package
                   C-state limit is configured via MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                   (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be locked by the
                   BIOS, in which case the package C-state limit can only be read, but cannot be
                   modified.""",
        "vfms": tuple(_PKG_CST_LIMITS.keys()),
        "type": "str",
        "vals": None,
        "bits": None,
    },
    "pkg_cstate_limit_lock":  {
        "name": "MSR lock",
        "sname": None,
        "iosname": None,
        "help": """Lock/unlock bits 15:0 of MSR {MSR_PKG_CST_CONFIG_CONTROL:#x}
                   (MSR_PKG_CST_CONFIG_CONTROL), which include the Package C-state limit. This bit
                   is typically set by BIOS, and sometimes there is a BIOS menu to lock/unlock the
                   MSR.""",
        "vfms": tuple(_PKG_CST_LIMITS.keys()),
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (15, 15),
        "writable": False,
    },
    "c1_demotion": {
        "name": "C1 demotion",
        "sname": None,
        "iosname": None,
        "help": """Allow/disallow the CPU to demote C6/C7 requests to C1.""",
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (26, 26),
    },
    "c1_undemotion": {
        "name": "C1 undemotion",
        "sname": None,
        "iosname": None,
        "help": """Allow/disallow the CPU to un-demote previously demoted requests back from C1 to
                   C6/C7.""",
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (28, 28),
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
        '(cpu, info)', where 'cpu' is the CPU number the limits were read from, and 'info' is
        the package C-state limit name in lower case, e.g., pc0.
        """

        finfo = self._features["pkg_cstate_limit"]

        for cpu, code in self._msr.read_bits(self.regaddr, finfo["bits"], cpus=cpus,
                                             iosname=finfo["iosname"]):
            if code not in finfo["rvals"]:
                # No exact match. The limit is the closest lower known number. For example, if the
                # known numbers are 0(PC0), 2(PC6), and 7(unlimited), and 'code' is 3, then the
                # limit is PC6.
                #
                # On some platforms code 0 is "unlimited" (e.g., Denverton). Do not resolve unknown
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

            yield (cpu, limit)

    def _set_pkg_cstate_limit(self, limit, cpus="all"):
        """Set package C-state limit for CPUs in 'cpus'."""

        finfo = self._features["pkg_cstate_limit"]
        regvals = {}

        for cpu, regval in self._msr.read(self.regaddr, cpus=cpus, iosname=finfo["iosname"]):
            if self._msr.get_bits(regval, self._features["pkg_cstate_limit_lock"]["bits"]):
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
            self._msr.write(self.regaddr, regval, regval_cpus, iosname=finfo["iosname"])

    def _init_features_dict_pkg_cstate_limit(self):
        """Initialize the 'pkg_cstate_limit' information in the 'self._features' dictionary."""

        if not self.is_feature_supported("pkg_cstate_limit", cpus="all"):
            _LOG.debug("no package C-state limit table available for %s%s",
                       self._cpuinfo.cpudescr, self._pman.hostmsg)
            return

        cpumodel = self._cpuinfo.info["vfm"]
        cpumodel_info = _PKG_CST_LIMITS[cpumodel]

        finfo = self._features["pkg_cstate_limit"]
        finfo["bits"] = cpumodel_info["bits"]
        finfo["vals"] = cpumodel_info["codes"]

    def _init_features_dict(self):
        """Initialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_pkg_cstate_limit()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        model = self._cpuinfo.info["vfm"]

        if model in _MODULE_IO_SCOPE_VFMS:
            iosname = "module"
        elif model in _PACKAGE_IO_SCOPE_VFMS:
            iosname = "package"
        else:
            iosname = "core"

        # For the package C-state limit/lock features the scope is always "package", except for
        # CLX-AP, which is one very special platform. And it is different to the I/O scope on most
        # platforms.
        sname = self._get_clx_ap_adjusted_msr_scope()

        for fname, finfo in self.features.items():
            if fname.startswith("pkg_") or model in _CORE_C1D_SCOPE_VFMS:
                finfo["sname"] = sname
            else:
                finfo["sname"] = iosname
            finfo["iosname"] = iosname
