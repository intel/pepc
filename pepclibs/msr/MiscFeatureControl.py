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

import logging
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# The Hardware Power Management Request Model Specific Register.
MSR_MISC_FEATURE_CONTROL = 0x1A4

# CPU models that support only the 'l2_hw_prefetcher' and 'dcu_hw_prefetcher' features.
_L2_AND_DCU_CPUS = CPUInfo.TREMONTS +  \
                   CPUInfo.GOLDMONTS + \
                   (CPUInfo.INTEL_FAM6_ATOM_SILVERMONT_D,) + \
                   CPUInfo.PHIS

# CPU models that support 'l2_hw_prefetcher', 'l1_adj_prefetcher', 'dcu_hw_prefetcher', and
# 'dcu_ip_prefetcher' prefetchers.
_ALL_PREFETCHERS_CPUS = CPUInfo.NEHALEMS +     \
                        CPUInfo.WESTMERES +    \
                        CPUInfo.SANDYBRIDGES + \
                        CPUInfo.IVYBRIDGES +   \
                        CPUInfo.HASWELLS +     \
                        CPUInfo.BROADWELLS +   \
                        CPUInfo.SKYLAKES +     \
                        CPUInfo.CANNONLAKES +  \
                        CPUInfo.KABYLAKES +    \
                        CPUInfo.COMETLAKES +   \
                        CPUInfo.ICELAKES +     \
                        CPUInfo.TIGERLAKES +   \
                        CPUInfo.SPRS +         \
                        CPUInfo.ALDERLAKES +   \
                        CPUInfo.ROCKETLAKES

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "l2_hw_prefetcher" : {
        "name" : "L2 hardware prefetcher",
        "scope": "core",
        "help" : """Enable/disable the L2 cache hardware prefetcher.""",
        "cpumodels" : _L2_AND_DCU_CPUS + _ALL_PREFETCHERS_CPUS,
        "type" : "bool",
        "vals" : { "on" : 0, "off" : 1},
        "bits" : None,
    },
    "l1_adj_prefetcher" : {
        "name" : "L2 adjacent cache line prefetcher",
        "scope": "core",
        "help" : """Enable/disable the L2 adjacent cache lines prefetcher, which fetches cache
                    lines that comprise a cache line pair.""",
        "cpumodels" : _ALL_PREFETCHERS_CPUS,
        "type" : "bool",
        "vals" : { "on" : 0, "off" : 1},
        "bits" : None,
    },
    "dcu_hw_prefetcher" : {
        "name" : "DCU hardware prefetcher",
        "scope": "core",
        "help" : """Enable/disable the DCU hardware prefetcher, which fetches the next cache line
                    into L1 data cache.""",
        "cpumodels" : _L2_AND_DCU_CPUS + _ALL_PREFETCHERS_CPUS,
        "type" : "bool",
        "vals" : { "on" : 0, "off" : 1},
        "bits" : None,
    },
    "dcu_ip_prefetcher" : {
        "name" : "DCU IP prefetcher",
        "scope": "core",
        "help" : """Enable/disable the DCU IP prefetcher, which uses sequential load history (based
                    on instruction pointer of previous loads) to determine whether to prefetch
                    additional lines.""",
        "cpumodels" : _ALL_PREFETCHERS_CPUS,
        "type" : "bool",
        "vals" : { "on" : 0, "off" : 1},
        "bits" : None,
    },
}

class MiscFeatureControl(_FeaturedMSR.FeaturedMSR):
    """
    This module provides API to MSR 0x1A4 (MSR_MISC_FEATURE_CONTROL). This MSR provides knobs for
    various CPU prefetchers on many Intel platforms.
    """

    def _init_features_dict_bits(self):
        """Initialize the 'bits' key in the 'self._features' dictionary."""

        cpumodel = self._cpuinfo.info["model"]
        if cpumodel in CPUInfo.PHIS:
            # Xeon Phi platforms have different bit numbers comparing to all other platforms.
            self._features["l2_hw_prefetcher"]["bits"]  = (1, 1)
            self._features["dcu_hw_prefetcher"]["bits"] = (0, 0)
        else:
            self._features["l2_hw_prefetcher"]["bits"]  = (0, 0)
            self._features["l1_adj_prefetcher"]["bits"] = (1, 1)
            self._features["dcu_hw_prefetcher"]["bits"] = (2, 2)
            self._features["dcu_ip_prefetcher"]["bits"] = (3, 3)

    def _init_features_dict(self):
        """Intitialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_bits()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_MISC_FEATURE_CONTROL
        self.regname = "MSR_MISC_FEATURE_CONTROL"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)
