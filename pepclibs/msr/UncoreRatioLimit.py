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
from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict


# The Uncore Ratio Limit Model Specific Register.
MSR_UNCORE_RATIO_LIMIT = 0x620

#
# CPUs that support the uncore ratio limit MSR.
#
_VMFS = CPUModels.CPU_GROUPS["EMR"] + \
        CPUModels.CPU_GROUPS["METEORLAKE"] + \
        CPUModels.CPU_GROUPS["SPR"] + \
        CPUModels.CPU_GROUPS["RAPTORLAKE"] + \
        (CPUModels.MODELS["ALDERLAKE"]["vfm"],
         CPUModels.MODELS["ALDERLAKE_L"]["vfm"]) + \
        CPUModels.CPU_GROUPS["ICX"] + \
        CPUModels.CPU_GROUPS["SKX"] + \
        (CPUModels.MODELS["BROADWELL_G"]["vfm"],
         CPUModels.MODELS["BROADWELL_D"]["vfm"],
         CPUModels.MODELS["BROADWELL_X"]["vfm"])

# Description of CPU features controlled by the the Turbo Ratio Limit MSR.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "max_ratio": {
        "name": "Maximum uncore ratio",
        "sname": None,
        "iosname": None,
        "help": """The maximum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                   the maximum allowed uncore frequency.""",
        "vfms": _VMFS,
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
        "vfms": _VMFS,
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
