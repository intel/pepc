# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x770 (MSR_PM_ENABLE). This is an architectural MSR found on
many Intel platforms.
"""

from pepclibs.msr import _FeaturedMSR

# The Power Management Enable Model Specific Register.
MSR_PM_ENABLE = 0x770

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "hwp": {
        "name": "Hardware Power Management enabled",
        "sname": None,
        "iosname": None,
        "help": """When hardware power management is enabled, the platform autonomously scales CPU
                   frequency depending on the load.""",
        "cpuflags": {"hwp",},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (0, 0),
    },
}

class PMEnable(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x770 (MSR_PM_ENABLE). This is an architectural MSR found on
    many Intel platforms.
    """

    regaddr = MSR_PM_ENABLE
    regname = "MSR_PM_ENABLE"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
