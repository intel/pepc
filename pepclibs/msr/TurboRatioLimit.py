# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1AD (MSR_TURBO_RATIO_LIMIT). This MSR provides turbo ratio
information on Intel platforms.
"""

import logging
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# The Turbo Ratio Limit Model Specific Register.
MSR_TURBO_RATIO_LIMIT = 0x1AD

#
# CPU models that include core turbo ratios in the MSR (as apposed to group turbo ratio). "CT" in
# the names stands for "Core Turbo".
#
_CT_SKYLAKES = (CPUInfo.INTEL_FAM6_ICELAKE,   CPUInfo.INTEL_FAM6_ICELAKE_L)
_CT_ICELAKES = (CPUInfo.INTEL_FAM6_SKYLAKE_L, CPUInfo.INTEL_FAM6_SKYLAKE)
_CT_NEHALEMS = (CPUInfo.INTEL_FAM6_NEHALEM,   CPUInfo.INTEL_FAM6_NEHALEM_G,
                CPUInfo.INTEL_FAM6_NEHALEM_EP)
_CT_SILVERMONTS = (CPUInfo.INTEL_FAM6_ATOM_SILVERMONT_D, )

_CT_CPUS = CPUInfo.ROCKETLAKES +  \
           CPUInfo.ALDERLAKES +   \
           CPUInfo.TIGERLAKES +   \
           CPUInfo.LAKEFIELDS +   \
           _CT_ICELAKES +         \
           _CT_SKYLAKES +         \
           CPUInfo.COMETLAKES +   \
           CPUInfo.KABYLAKES +    \
           CPUInfo.BROADWELLS +   \
           CPUInfo.HASWELLS +     \
           CPUInfo.IVYBRIDGES +   \
           CPUInfo.SANDYBRIDGES + \
           _CT_NEHALEMS +         \
           _CT_SILVERMONTS

# CPU models that include group turbo ratios in the MSR. "GT" in the names stands for "Group
# Turbo". In this case MSR 0x1AE should be decoded to get count of cores in a group. In SDM, this
# MSR is named 'MSR_TURBO_GROUP_CORECNT' for Atom CPUs and 'MSR_TURBO_RATIO_LIMIT_CORES' for "big
# core" CPUs. The same MSR is called 'MSR_TURBO_RATIO_LIMIT1' for CPUs that do not have groups in
# 'MSR_TURBO_RATIO_LIMIT'.
_GT_CPUS = (CPUInfo.INTEL_FAM6_SAPPHIRERAPIDS_X,
            CPUInfo.INTEL_FAM6_ICELAKE_X,
            CPUInfo.INTEL_FAM6_ICELAKE_D,
            CPUInfo.INTEL_FAM6_SKYLAKE_X,
            CPUInfo.INTEL_FAM6_TREMONT_D,
            CPUInfo.INTEL_FAM6_GOLDMONT_D,
            CPUInfo.INTEL_FAM6_ATOM_GOLDMONT,
            CPUInfo.INTEL_FAM6_ATOM_GOLDMONT_PLUS,)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FearuredMSR.FEATURES' for more comments.
FEATURES = {
    "max_1c_turbo_ratio" : {
        "name" : "Maximum 1 Core Turbo Ratio",
        "scope": "package",
        "help" : """The ratio of maximum turbo frequency in case of 1 active core. This ratio
                    multiplied by bus clock speed gives the maximum 1 core turbo frequency.""",
        "cpumodels" : _CT_CPUS,
        "type"      : "int",
        "writable"  : False,
        "bits"      : (7, 0),
    },
    "max_g0_turbo_ratio" : {
        "name" : "Maximum Group 0 cores Turbo Ratio",
        "scope": "package",
        "help" : """The ratio of maximum turbo frequency in case "group 0" count of cores are
                    active. This ratio multiplied by bus clock speed gives the frequency. Count of
                    cores in group 0 is provided by MSR 0x1AE.""",
        "cpumodels" : _GT_CPUS,
        "type"      : "int",
        "writable"  : False,
        "bits"      : (7, 0),
    },
}

class TurboRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1AD (MSR_TURBO_RATIO_LIMIT). This MSR provides turbo ratio
    information on Intel platforms.
    """

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_TURBO_RATIO_LIMIT
        self.regname = "MSR_TURBO_RATIO_LIMIT"

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
