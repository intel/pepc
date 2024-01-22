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

from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

# The Power Control Model Specific Register.
MSR_PLATFORM_INFO = 0xCE

# CPU models supporting the "maximum efficiency ratio" feature.
_EFREQ_CPUS = CPUInfo.CPU_GROUPS["GNR"] +         \
              CPUInfo.CPU_GROUPS["EMR"] +         \
              CPUInfo.CPU_GROUPS["METEORLAKE"] +  \
              CPUInfo.CPU_GROUPS["SPR"] +         \
              CPUInfo.CPU_GROUPS["RAPTORLAKE"] +  \
              CPUInfo.CPU_GROUPS["ALDERLAKE"] +   \
              CPUInfo.CPU_GROUPS["ROCKETLAKE"] +  \
              CPUInfo.CPU_GROUPS["TIGERLAKE"] +   \
              CPUInfo.CPU_GROUPS["ICELAKE"] +     \
              CPUInfo.CPU_GROUPS["COMETLAKE"] +   \
              CPUInfo.CPU_GROUPS["KABYLAKE"] +    \
              CPUInfo.CPU_GROUPS["CANNONLAKE"] +  \
              CPUInfo.CPU_GROUPS["SKYLAKE"] +     \
              CPUInfo.CPU_GROUPS["BROADWELL"] +   \
              CPUInfo.CPU_GROUPS["HASWELL"] +     \
              CPUInfo.CPU_GROUPS["IVYBRIDGE"] +   \
              CPUInfo.CPU_GROUPS["SANDYBRIDGE"] + \
              CPUInfo.CPU_GROUPS["WESTMERE"] +    \
              CPUInfo.CPU_GROUPS["NEHALEM"] +     \
              CPUInfo.CPU_GROUPS["CRESTMONT"] +   \
              CPUInfo.CPU_GROUPS["TREMONT"] +     \
              CPUInfo.CPU_GROUPS["GOLDMONT"] +    \
              CPUInfo.CPU_GROUPS["PHI"]

# CPU models supporting the "minimum operating ratio" feature.
_MIN_OPER_RATIO_CPUS = CPUInfo.CPU_GROUPS["GNR"] +                      \
                       CPUInfo.CPU_GROUPS["EMR"] +                      \
                       CPUInfo.CPU_GROUPS["METEORLAKE"] +               \
                       CPUInfo.CPU_GROUPS["SPR"] +                      \
                       CPUInfo.CPU_GROUPS["RAPTORLAKE"] +               \
                       CPUInfo.CPU_GROUPS["ALDERLAKE"] +                \
                       CPUInfo.CPU_GROUPS["ROCKETLAKE"] +               \
                       CPUInfo.CPU_GROUPS["TIGERLAKE"] +                \
                       CPUInfo.CPU_GROUPS["ICELAKE"] +                  \
                       CPUInfo.CPU_GROUPS["COMETLAKE"] +                \
                       CPUInfo.CPU_GROUPS["KABYLAKE"] +                 \
                       CPUInfo.CPU_GROUPS["CANNONLAKE"] +               \
                       CPUInfo.CPU_GROUPS["SKYLAKE"] +                  \
                       CPUInfo.CPU_GROUPS["BROADWELL"] +                \
                       CPUInfo.CPU_GROUPS["HASWELL"] +                  \
                       (CPUInfo.CPUS["IVYBRIDGE"]["model"], ) +  \
                       CPUInfo.CPU_GROUPS["CRESTMONT"] +                \
                       CPUInfo.CPU_GROUPS["TREMONT"] +                  \
                       CPUInfo.CPU_GROUPS["GOLDMONT"] +                 \
                       CPUInfo.CPU_GROUPS["PHI"]

# CPU models supporting the "maximum non-turbo ratio" feature.
_BASEFREQ_CPUS = _EFREQ_CPUS + CPUInfo.CPU_GROUPS["SILVERMONT"] + CPUInfo.CPU_GROUPS["AIRMONT"]

# Description of CPU features controlled by the the Platform Information MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_non_turbo_ratio": {
        "name": "Max. Non-Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of the maximum non-turbo frequency. This ratio multiplied by bus
                   clock speed gives the maximum non-turbo frequency.""",
        "cpumodels": _BASEFREQ_CPUS,
        "type": "int",
        "writable": False,
        "bits": (15, 8),
    },
    "max_eff_ratio": {
        "name": "Max. Efficiency Ratio",
        "sname": None,
        "iosname": None,
        "help": """The maximum efficiency CPU ratio (in practice, the minimum ratio the OS can
                   request the CPU to run at). This ratio multiplied by bus clock speed gives the
                   efficiency CPU frequency.""",
        "cpumodels": _EFREQ_CPUS,
        "type": "int",
        "writable": False,
        "bits": (47, 40),
    },
    "min_oper_ratio": {
        "name": "Min. Operating Ratio",
        "sname": None,
        "iosname": None,
        "help": """The minimum operating CPU ratio. This ratio multiplied by bus clock speed gives
                   the minimum operating CPU frequency.""",
        "cpumodels": _MIN_OPER_RATIO_CPUS,
        "type": "int",
        "writable": False,
        "bits": (55, 48),
    },
}

class PlatformInfo(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xCE (MSR_PLATFORM_INFO). This MSR provides power and thermal
    information on Intel platforms.
    """

    regaddr = MSR_PLATFORM_INFO
    regname = "MSR_PLATFORM_INFO"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
