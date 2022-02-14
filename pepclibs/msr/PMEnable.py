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

import logging
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# The Power Management Enable Model Specific Register.
MSR_PM_ENABLE = 0x770

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "hwp" : {
        "name" : "Hardware Power Management enabled",
        "scope": "package",
        "help" : """When hardware power management is enabled, the platform autonomously scales CPU
                    frequency depending on the load.""",
        "cpuflags" : ("hwp",),
        "type" : "bool",
        "vals" : { "on" : 1, "off" : 0},
        "bits" : (0, 0),
    },
}

class PMEnable(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x770 (MSR_PM_ENABLE). This is an architectural MSR found on
    many Intel platforms.
    """

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_PM_ENABLE
        self.regname = "MSR_PM_ENABLE"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)
