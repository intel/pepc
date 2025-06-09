# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1B1 (MSR_ENERGY_PERF_BIAS). This is an architectural MSR found on
many Intel platforms.
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Energy Performance Bias Model Specific Register.
MSR_ENERGY_PERF_BIAS = 0x1B0

# MSR_ENERGY_PERF_BIAS features have CPU scope, except for the following CPUs.
_CORE_SCOPE_VFMS = CPUModels.CPU_GROUPS["SILVERMONT"]
_PACKAGE_SCOPE_VFMS = CPUModels.CPU_GROUPS["WESTMERE"] + CPUModels.CPU_GROUPS["SANDYBRIDGE"]

# Description of CPU features controlled by the the Power Control MSR.
FEATURES = {
    "epb": {
        "name": "Energy Performance Bias",
        "sname": None,
        "iosname": None,
        "help": """Energy Performance Bias is a hint to the CPU about the power and performance
                   preference. Value 0 indicates highest performance and value 15 indicates
                   maximum energy savings.""",
        "cpuflags": {"epb",},
        "type": "int",
        "bits": (3, 0),
    },
}

class EnergyPerfBias(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1B1 (MSR_ENERGY_PERF_BIAS). This is an architectural MSR found
    on many Intel platforms.
    """

    regaddr = MSR_ENERGY_PERF_BIAS
    regname = "MSR_ENERGY_PERF_BIAS"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        vfm = self._cpuinfo.info["vfm"]

        if vfm in _CORE_SCOPE_VFMS:
            sname = "core"
        elif vfm in _PACKAGE_SCOPE_VFMS:
            sname = "package"
        else:
            sname = "CPU"

        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
