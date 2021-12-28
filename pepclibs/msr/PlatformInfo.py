# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0xCE (MSR_PLATFORM_INFO). This MSR provides power and thermal
information on Intel platforms.
"""

import logging
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# The Power Control Model Specific Register.
MSR_PLATFORM_INFO = 0xCE

# CPU models supporting the "maximum efficiency ratio" feature.
_EFREQ_CPUS = CPUInfo.GOLDMONTS +    \
              CPUInfo.TREMONTS +     \
              CPUInfo.PHIS +         \
              CPUInfo.NEHALEMS +     \
              CPUInfo.WESTMERES +    \
              CPUInfo.SANDYBRIDGES + \
              CPUInfo.IVYBRIDGES +   \
              CPUInfo.HASWELLS +     \
              CPUInfo.BROADWELLS +   \
              CPUInfo.SKYLAKES +     \
              CPUInfo.CANNONLAKE+    \
              CPUInfo.KABYLAKES +    \
              CPUInfo.COMETLAKES +   \
              CPUInfo.ICELAKES +     \
              CPUInfo.TIGERLAKES +   \
              CPUInfo.SPR +          \
              CPUInfo.ALDERLAKES +   \
              CPUInfo.ROCKETLAKE

# CPU models supporting the "maximum non-turbo ratio" feature.
_BASEFREQ_CPUS = _EFREQ_CPUS + CPUInfo.SILVERMONTS + CPUInfo.AIRMONT

# Description of CPU features controlled by the the Platform Information MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_non_turbo_ratio" : {
        "name" : "Maximum Non-Turbo Ratio",
        "scope": "package",
        "help" : """The ratio of the maximum non-turbo frequency. This ratio multiplied by bus
                    clock speed gives the maximum non-turbo frequency.""",
        "cpumodels" : _BASEFREQ_CPUS,
        "type"      : "int",
        "writable"  : False,
        "bits"      : (15, 8),
    },
    "max_eff_ratio" : {
        "name" : "Maximum Efficiency Ratio",
        "scope": "package",
        "help" : """The maximum efficiency CPU ratio (in practice, the minimum ratio the OS can
                    request the CPU to run at). This ratio multiplied by bus clock speed gives the
                    efficiency CPU frequency.""",
        "cpumodels" : _EFREQ_CPUS,
        "type"      : "int",
        "writable"  : False,
        "bits"      : (47, 40),
    },
}

class PlatformInfo(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xCE (MSR_PLATFORM_INFO). This MSR provides power and thermal
    information on Intel platforms.
    """

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        self.regaddr = MSR_PLATFORM_INFO
        self.regname = "MSR_PLATFORM_INFO"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)
