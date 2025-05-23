# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1AE (MSR_TURBO_RATIO_LIMIT1). Depending on the platform, this MSR
provides either turbo ratio information, or the turbo ratio groups encoding. In the latter case it
is called either 'MSR_TURBO_GROUP_CORECNT' (Atoms) or 'MSR_TURBO_RATIO_LIMIT_CORES' (big cores).
"""

from pepclibs.msr import _FeaturedMSR, TurboRatioLimit

# The Turbo Ratio Limit 1 Model Specific Register.
MSR_TURBO_RATIO_LIMIT1 = 0x1AE
MSR_TURBO_GROUP_CORECNT = 0x1AE
MSR_TURBO_RATIO_LIMIT_CORES = 0x1AE

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "g0_cpu_cnt": {
        "name": "Group 0 cores count",
        "sname": None,
        "iosname": None,
        "help": """Count of cores in group 0. This group is used in MSR 0x1AD
                   (MSR_TURBO_RATIO_LIMIT) for encoding the maximum group of cores turbo
                   frequency.""",
        "vfms": TurboRatioLimit.FEATURES["max_g0_turbo_ratio"]["vfms"],
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
}

class TurboRatioLimit1(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1AE (MSR_TURBO_RATIO_LIMIT1). Depending on the platform, this
    MSR provides either turbo ratio information, or the turbo ratio groups encoding. In the latter
    case it is called either 'MSR_TURBO_GROUP_CORECNT' (Atoms) or 'MSR_TURBO_RATIO_LIMIT_CORES' (big
    cores).
    """

    regaddr = MSR_TURBO_RATIO_LIMIT1
    regname = "MSR_TURBO_RATIO_LIMIT1"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
