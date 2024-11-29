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
# CPU models that include core turbo ratios in the MSR (as apposed to group turbo ratio). "CT" in
# the names stands for "Core Turbo".
#
_CT_CPUS = CPUModels.MODEL_GROUPS["METEORLAKE"] +  \
           CPUModels.MODEL_GROUPS["RAPTORLAKE"] +  \
           CPUModels.MODEL_GROUPS["ALDERLAKE"] +   \
           CPUModels.MODEL_GROUPS["ROCKETLAKE"] +  \
           CPUModels.MODEL_GROUPS["TIGERLAKE"] +   \
           CPUModels.MODEL_GROUPS["LAKEFIELD"] +   \
           CPUModels.MODEL_GROUPS["ICL_CLIENT"] +  \
           CPUModels.MODEL_GROUPS["SKL_CLIENT"] +  \
           CPUModels.MODEL_GROUPS["COMETLAKE"] +   \
           CPUModels.MODEL_GROUPS["KABYLAKE"] +    \
           CPUModels.MODEL_GROUPS["CANNONLAKE"] +  \
           CPUModels.MODEL_GROUPS["BROADWELL"] +   \
           (CPUModels.MODELS["ATOM_SILVERMONT_D"]["model"], ) + \
           CPUModels.MODEL_GROUPS["HASWELL"] +     \
           CPUModels.MODEL_GROUPS["IVYBRIDGE"] +   \
           CPUModels.MODEL_GROUPS["SANDYBRIDGE"] + \
           (CPUModels.MODELS["NEHALEM"]["model"],
            CPUModels.MODELS["NEHALEM_G"]["model"],
            CPUModels.MODELS["NEHALEM_EP"]["model"])

# CPU models that include group turbo ratios in the MSR. "GT" in the names stands for "Group
# Turbo". In this case MSR 0x1AE should be decoded to get count of cores in a group. In SDM, this
# MSR is named 'MSR_TURBO_GROUP_CORECNT' for Atom CPUs and 'MSR_TURBO_RATIO_LIMIT_CORES' for "big
# core" CPUs. The same MSR is called 'MSR_TURBO_RATIO_LIMIT1' for CPUs that do not have groups in
# 'MSR_TURBO_RATIO_LIMIT'.
_GT_CPUS = CPUModels.MODEL_GROUPS["GNR"] + \
           CPUModels.MODEL_GROUPS["CRESTMONT"] + \
           CPUModels.MODEL_GROUPS["EMR"] + \
           CPUModels.MODEL_GROUPS["SPR"] + \
           (CPUModels.MODELS["ATOM_TREMONT_D"]["model"],) +  \
           CPUModels.MODEL_GROUPS["ICX"] + \
           CPUModels.MODEL_GROUPS["SKX"] + \
           (CPUModels.MODELS["ATOM_GOLDMONT_D"]["model"],
            CPUModels.MODELS["ATOM_GOLDMONT"]["model"],
            CPUModels.MODELS["ATOM_GOLDMONT_PLUS"]["model"],)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_1c_turbo_ratio": {
        "name": "Max. 1 Core Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of maximum turbo frequency in case of 1 active core. This ratio
                   multiplied by bus clock speed gives the maximum 1 core turbo frequency.""",
        "cpumodels": _CT_CPUS,
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
        "cpumodels": _GT_CPUS,
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
