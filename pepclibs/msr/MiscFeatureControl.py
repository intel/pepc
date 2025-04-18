# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1A4 (MSR_MISC_FEATURE_CONTROL). This MSR provides knobs for
various CPU prefetchers on many Intel platforms.
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Hardware Power Management Request Model Specific Register.
MSR_MISC_FEATURE_CONTROL = 0x1A4

# CPUs that support only the 'l2_hw_prefetcher' and 'dcu_hw_prefetcher' features.
_L2_AND_DCU_VFMS = CPUModels.CPU_GROUPS["TREMONT"] +   \
                   CPUModels.CPU_GROUPS["GOLDMONT"] +  \
                   (CPUModels.MODELS["ATOM_SILVERMONT_D"]["vfm"],) + \
                   CPUModels.CPU_GROUPS["PHI"]

# CPUs that support 'l2_hw_prefetcher', 'l2_adj_prefetcher', 'dcu_hw_prefetcher', and
# 'dcu_ip_prefetcher' prefetchers.
_ALL_PREFETCHERS_VFMS = CPUModels.CPU_GROUPS["CRESTMONT"] +   \
                        CPUModels.CPU_GROUPS["GNR"] +         \
                        CPUModels.CPU_GROUPS["METEORLAKE"] +  \
                        CPUModels.CPU_GROUPS["EMR"] +         \
                        CPUModels.CPU_GROUPS["RAPTORLAKE"] +  \
                        CPUModels.CPU_GROUPS["ALDERLAKE"] +   \
                        CPUModels.CPU_GROUPS["ROCKETLAKE"] +  \
                        CPUModels.CPU_GROUPS["SPR"] +         \
                        CPUModels.CPU_GROUPS["TIGERLAKE"] +   \
                        CPUModels.CPU_GROUPS["ICELAKE"] +     \
                        CPUModels.CPU_GROUPS["COMETLAKE"] +   \
                        CPUModels.CPU_GROUPS["KABYLAKE"] +    \
                        CPUModels.CPU_GROUPS["CANNONLAKE"] +  \
                        CPUModels.CPU_GROUPS["SKYLAKE"] +     \
                        CPUModels.CPU_GROUPS["BROADWELL"] +   \
                        CPUModels.CPU_GROUPS["HASWELL"] +     \
                        CPUModels.CPU_GROUPS["IVYBRIDGE"] +   \
                        CPUModels.CPU_GROUPS["SANDYBRIDGE"] + \
                        CPUModels.CPU_GROUPS["WESTMERE"]

# 'l2_hw_prefetcher' feature has core scope, except for the following CPUs.
_MODULE_SCOPE_L2_HW_PREFETCHER = CPUModels.CPU_GROUPS["TREMONT"] + \
                                 CPUModels.CPU_GROUPS["PHI"] +     \
                                 CPUModels.CPU_GROUPS["GOLDMONT"]

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "l2_hw_prefetcher": {
        "name": "L2 hardware prefetcher",
        "sname": None,
        "iosname": None,
        "help": """Enable/disable the L2 cache hardware prefetcher.""",
        "vfms": _L2_AND_DCU_VFMS + _ALL_PREFETCHERS_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": None,
    },
    "l2_adj_prefetcher": {
        "name": "L2 adjacent cache line prefetcher",
        "sname": "core",
        "iosname": "core",
        "help": """Enable/disable the L2 adjacent cache lines prefetcher, which fetches cache
                    lines that comprise a cache line pair.""",
        "vfms": _ALL_PREFETCHERS_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": None,
    },
    "dcu_hw_prefetcher": {
        "name": "DCU hardware prefetcher",
        "sname": "core",
        "iosname": "core",
        "help": """Enable/disable the DCU hardware prefetcher, which fetches the next cache line
                    into L1 data cache.""",
        "vfms": _L2_AND_DCU_VFMS + _ALL_PREFETCHERS_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": None,
    },
    "dcu_ip_prefetcher": {
        "name": "DCU IP prefetcher",
        "sname": "core",
        "iosname": "core",
        "help": """Enable/disable the DCU IP prefetcher, which uses sequential load history (based
                    on instruction pointer of previous loads) to determine whether to prefetch
                    additional lines.""",
        "vfms": _ALL_PREFETCHERS_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": None,
    },
}

class MiscFeatureControl(_FeaturedMSR.FeaturedMSR):
    """
    This module provides API to MSR 0x1A4 (MSR_MISC_FEATURE_CONTROL). This MSR provides knobs for
    various CPU prefetchers on many Intel platforms.
    """

    regaddr = MSR_MISC_FEATURE_CONTROL
    regname = "MSR_MISC_FEATURE_CONTROL"
    vendor = "GenuineIntel"

    def _init_features_dict_bits(self):
        """Initialize the 'bits' key in the 'self._features' dictionary."""

        vfm = self._cpuinfo.info["vfm"]
        if vfm in CPUModels.CPU_GROUPS["PHI"]:
            # Xeon Phi platforms have different bit numbers comparing to all other platforms.
            self._features["l2_hw_prefetcher"]["bits"] = (1, 1)
            self._features["dcu_hw_prefetcher"]["bits"] = (0, 0)
        else:
            self._features["l2_hw_prefetcher"]["bits"] = (0, 0)
            self._features["l2_adj_prefetcher"]["bits"] = (1, 1)
            self._features["dcu_hw_prefetcher"]["bits"] = (2, 2)
            self._features["dcu_ip_prefetcher"]["bits"] = (3, 3)

    def _init_features_dict(self):
        """Initialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_bits()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        vfm = self._cpuinfo.info["vfm"]

        if vfm in _MODULE_SCOPE_L2_HW_PREFETCHER:
            sname = "module"
        else:
            sname = "core"

        finfo = self.features["l2_hw_prefetcher"]
        finfo["sname"] = finfo["iosname"] = sname
