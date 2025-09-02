# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL), a model-specific register
present on many Intel platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUModels
from pepclibs.helperlibs import Logging
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from typing import TypedDict
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import ScopeNameType

    class _LimitsTypedDict(TypedDict, total=False):
        """
        The type of the package C-state limits dictionary.

        Attributes:
            codes: A dictionary mapping package C-state names to their codes.
            bits: A tuple of two integers, the first is the start bit and the second is the end bit
                  of the package C-state limit bits in MSR_PKG_CST_CONFIG_CONTROL.
        """

        codes: dict[str, int]
        bits: tuple[int, int]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Package C-state configuration control Model Specific Register.
MSR_PKG_CST_CONFIG_CONTROL = 0xE2

#
# Package C-state limits are documented in Intel SDM, but it describes all the possible package
# C-states for a CPU model. In practice, however, specific platforms often do not support many of
# those package C-states. For example, Xeons typically do not support anything deeper than PC6.
#

#
# Xeons.
#
# Ice Lake, Granite Rapids, Sierra Forest, Clear Water Forest Xeons.
_ICX_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC6": 2, "unlimited": 7},
    "bits": (2, 0)
}

# Emerald Rapids, Sapphire Rapids, Cooper Lake, Cascade Lake, Sky Lake Xeons. Knights Mill and
# Knights Landing Xeon Phis.
_SKX_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC6": 2, "PC6R": 3, "unlimited": 7},
    "bits": (2, 0)
}

# Broadwell-D Xeon.
_BDWD_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3},
    "bits": (3, 0)
}

# Broadwell and Haswell Xeons.
_HSX_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "unlimited": 7},
    "bits": (2, 0)
}

# Ivy Bridge Xeon (Ivy Town).
_IVT_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC6": 2, "PC6R": 3, "unlimited": 7},
    "bits": (2, 0)
}

#
# Atom-based micro servers.
#
# Denverton SoC (Goldmont). Note, successor of Denverton is Snow Ridge, and its successor is Grand
# Ridge. They do not support package C-states.
_DNV_PKG_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC2": 2, "PC6": 3, "unlimited": 0},
    "bits": (3, 0)
}

#
# Clients.
#
_CLIENT_LNL_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC6": 3, "PC10": 8},
    "bits": (3, 0)
}

_CLIENT_PC8_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5, "PC8": 6, "PC9": 7,
              "PC10": 8},
    "bits": (3, 0)
}

_CLIENT_PC7S_CST_LIMITS: _LimitsTypedDict = {
    "codes": {"PC0": 0, "PC2": 1, "PC3": 2, "PC6": 3, "PC7": 4, "PC7S": 5},
    "bits": (3, 0)
}

# CPU model -> Package C-state limit map.
_PKG_CST_LIMITS: dict[int, _LimitsTypedDict] = {
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
    CPUModels.MODELS["LUNARLAKE_M"]["vfm"]:      _CLIENT_LNL_CST_LIMITS,
    CPUModels.MODELS["ARROWLAKE"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ARROWLAKE_H"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ARROWLAKE_U"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE_L"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE"]["vfm"]:       _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["METEORLAKE_L"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE"]["vfm"]:       _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE_S"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["RAPTORLAKE_P"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE_L"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ALDERLAKE_N"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ROCKETLAKE"]["vfm"]:       _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["TIGERLAKE"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["TIGERLAKE_L"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["LAKEFIELD"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["COMETLAKE"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["COMETLAKE_L"]["vfm"]:      _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["KABYLAKE_L"]["vfm"]:       _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["KABYLAKE"]["vfm"]:         _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_L"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["ICELAKE_NNPI"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["CANNONLAKE_L"]["vfm"]:     _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["SKYLAKE"]["vfm"]:          _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["SKYLAKE_L"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["BROADWELL"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
    CPUModels.MODELS["HASWELL_L"]["vfm"]:        _CLIENT_PC8_CST_LIMITS,
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
        "vfms": set(_PKG_CST_LIMITS),
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
        "vfms": set(_PKG_CST_LIMITS),
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
    Provide an API for MSR 0xE2 (MSR_PKG_CST_CONFIG_CONTROL), a model-specific register present on
    many Intel platforms.
    """

    regaddr = MSR_PKG_CST_CONFIG_CONTROL
    regname = "MSR_PKG_CST_CONFIG_CONTROL"
    vendor = "GenuineIntel"

    def __init__(self,
                 cpuinfo: CPUInfo.CPUInfo,
                 pman: ProcessManagerType | None = None,
                 msr: MSR.MSR | None = None):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object.
            pman: The Process manager object that defines the host to run the measurements on. If
                  not provided, a local process manager will be used.
            msr: An optional 'MSR.MSR()' object to use for writing to the MSR register. If not
                 provided, a new MSR object will be created.

        Raises:
            ErrorNotSupported: If CPU vendor is not supported or if the CPU does not the MSR.
        """

        self._partial_features = FEATURES

        model = cpuinfo.info["vfm"]

        iosname: ScopeNameType
        if model in _MODULE_IO_SCOPE_VFMS:
            iosname = "module"
        elif model in _PACKAGE_IO_SCOPE_VFMS:
            iosname = "package"
        else:
            iosname = "core"

        # For the package C-state limit/lock features the scope is always "package", except for
        # CLX-AP, which is one very special platform. And it is different to the I/O scope on most
        # platforms.
        sname = _FeaturedMSR.get_clx_ap_adjusted_msr_scope(cpuinfo)

        for fname, finfo in self._partial_features.items():
            if fname.startswith("pkg_") or model in _CORE_C1D_SCOPE_VFMS:
                finfo["sname"] = sname
            else:
                finfo["sname"] = iosname
            finfo["iosname"] = iosname

        super().__init__(cpuinfo, pman=pman, msr=msr)

    def _init_features_dict_pkg_cstate_limit(self):
        """
        Populate the 'pkg_cstate_limit' entry in the 'self._features' dictionary with
        platform-specific information.
        """

        vfm = self._cpuinfo.info["vfm"]
        if vfm in _PKG_CST_LIMITS:
            limits = _PKG_CST_LIMITS[vfm]
        else:
            # Populate with something, do not leave them as None to comply with the type
            # definition. Just randomly picked '_ICX_PKG_CST_LIMITS'.
            limits = _ICX_PKG_CST_LIMITS

        finfo = self._features["pkg_cstate_limit"]
        finfo["bits"] = limits["bits"]
        finfo["vals"] = limits["codes"]

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        self._init_features_dict_pkg_cstate_limit()

        super()._init_features_dict()
