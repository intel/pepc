# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x620 (MSR_UNCORE_RATIO_LIMIT). This MSR provides a way to limit
uncore frequency on Intel platforms.
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Uncore Ratio Limit Model Specific Register.
MSR_UNCORE_RATIO_LIMIT = 0x620

#
# CPU models that support the uncore ratio limit MSR.
#
_CPUS = CPUModels.MODEL_GROUPS["EMR"] + \
        CPUModels.MODEL_GROUPS["METEORLAKE"] + \
        CPUModels.MODEL_GROUPS["SPR"] + \
        CPUModels.MODEL_GROUPS["RAPTORLAKE"] + \
        (CPUModels.MODELS["ALDERLAKE"]["model"],
         CPUModels.MODELS["ALDERLAKE_L"]["model"],) + \
        CPUModels.MODEL_GROUPS["ICX"] + \
        CPUModels.MODEL_GROUPS["SKX"] + \
        (CPUModels.MODELS["BROADWELL_G"]["model"],
         CPUModels.MODELS["BROADWELL_D"]["model"],
         CPUModels.MODELS["BROADWELL_X"]["model"],)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_ratio": {
        "name": "Maximum uncore ratio",
        "sname": None,
        "iosname": None,
        "help": """The maximum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                   the maximum allowed uncore frequency.""",
        "cpumodels": _CPUS,
        "type": "int",
        "writable": True,
        "bits": (6, 0),
    },
    "min_ratio": {
        "name": "Minimum uncore ratio",
        "sname": None,
        "iosname": None,
        "help": """The minimum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                   the minimum allowed uncore frequency.""",
        "cpumodels": _CPUS,
        "type": "int",
        "writable": True,
        "bits": (14, 8),
    },
}

class UncoreRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x620 (MSR_UNCORE_RATIO_LIMIT). This MSR provides a way to limit
    uncore frequency on Intel platforms.
    """

    regaddr = MSR_UNCORE_RATIO_LIMIT
    regname = "MSR_UNCORE_RATIO_LIMIT"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = sname
