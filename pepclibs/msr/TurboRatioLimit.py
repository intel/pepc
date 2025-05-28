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

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Turbo Ratio Limit Model Specific Register.
MSR_TURBO_RATIO_LIMIT = 0x1AD

#
# CPUs that include core turbo ratios in the MSR (as apposed to group turbo ratio). "CT" in
# the names stands for "Core Turbo".
#
_CT_VFMS = CPUModels.CPU_GROUPS["ARROWLAKE"] +  \
           CPUModels.CPU_GROUPS["METEORLAKE"] +  \
           CPUModels.CPU_GROUPS["RAPTORLAKE"] +  \
           CPUModels.CPU_GROUPS["ALDERLAKE"] +   \
           CPUModels.CPU_GROUPS["ROCKETLAKE"] +  \
           CPUModels.CPU_GROUPS["TIGERLAKE"] +   \
           CPUModels.CPU_GROUPS["LAKEFIELD"] +   \
           CPUModels.CPU_GROUPS["ICL_CLIENT"] +  \
           CPUModels.CPU_GROUPS["SKL_CLIENT"] +  \
           CPUModels.CPU_GROUPS["COMETLAKE"] +   \
           CPUModels.CPU_GROUPS["KABYLAKE"] +    \
           CPUModels.CPU_GROUPS["CANNONLAKE"] +  \
           CPUModels.CPU_GROUPS["BROADWELL"] +   \
           (CPUModels.MODELS["ATOM_SILVERMONT_D"]["vfm"], ) + \
           CPUModels.CPU_GROUPS["HASWELL"] +     \
           CPUModels.CPU_GROUPS["IVYBRIDGE"] +   \
           CPUModels.CPU_GROUPS["SANDYBRIDGE"] + \
           (CPUModels.MODELS["NEHALEM"]["vfm"],
            CPUModels.MODELS["NEHALEM_G"]["vfm"],
            CPUModels.MODELS["NEHALEM_EP"]["vfm"])

# CPUs that include group turbo ratios in the MSR. "GT" in the names stands for "Group
# Turbo". In this case MSR 0x1AE should be decoded to get count of cores in a group. In SDM, this
# MSR is named 'MSR_TURBO_GROUP_CORECNT' for Atom CPUs and 'MSR_TURBO_RATIO_LIMIT_CORES' for "big
# core" CPUs. The same MSR is called 'MSR_TURBO_RATIO_LIMIT1' for CPUs that do not have groups in
# 'MSR_TURBO_RATIO_LIMIT'.
_GT_VFMS = CPUModels.CPU_GROUPS["GNR"] + \
           CPUModels.CPU_GROUPS["CRESTMONT"] + \
           CPUModels.CPU_GROUPS["EMR"] + \
           CPUModels.CPU_GROUPS["SPR"] + \
           (CPUModels.MODELS["ATOM_TREMONT_D"]["vfm"],) +  \
           CPUModels.CPU_GROUPS["ICX"] + \
           CPUModels.CPU_GROUPS["SKX"] + \
           (CPUModels.MODELS["ATOM_GOLDMONT_D"]["vfm"],
            CPUModels.MODELS["ATOM_GOLDMONT"]["vfm"],
            CPUModels.MODELS["ATOM_GOLDMONT_PLUS"]["vfm"],)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_1c_turbo_ratio": {
        "name": "Max. 1 Core Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of maximum turbo frequency in case of 1 active core. This ratio
                   multiplied by bus clock speed gives the maximum 1 core turbo frequency.""",
        "vfms": _CT_VFMS,
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
    "max_g0_turbo_ratio": {
        "name": "Max. Group 0 cores Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of maximum turbo frequency in case "group 0" count of cores are
                   active. This ratio multiplied by bus clock speed gives the frequency. Count of
                   cores in group 0 is provided by MSR 0x1AE.""",
        "vfms": _GT_VFMS,
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
}

class TurboRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1AD (MSR_TURBO_RATIO_LIMIT). This MSR provides turbo ratio
    information on Intel platforms.
    """

    regaddr = MSR_TURBO_RATIO_LIMIT
    regname = "MSR_TURBO_RATIO_LIMIT"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
