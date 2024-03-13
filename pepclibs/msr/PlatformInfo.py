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

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Power Control Model Specific Register.
MSR_PLATFORM_INFO = 0xCE

# CPU models supporting the "maximum efficiency ratio" feature.
_EFREQ_CPUS = CPUModels.MODEL_GROUPS["GNR"] +         \
              CPUModels.MODEL_GROUPS["EMR"] +         \
              CPUModels.MODEL_GROUPS["METEORLAKE"] +  \
              CPUModels.MODEL_GROUPS["SPR"] +         \
              CPUModels.MODEL_GROUPS["RAPTORLAKE"] +  \
              CPUModels.MODEL_GROUPS["ALDERLAKE"] +   \
              CPUModels.MODEL_GROUPS["ROCKETLAKE"] +  \
              CPUModels.MODEL_GROUPS["TIGERLAKE"] +   \
              CPUModels.MODEL_GROUPS["ICELAKE"] +     \
              CPUModels.MODEL_GROUPS["COMETLAKE"] +   \
              CPUModels.MODEL_GROUPS["KABYLAKE"] +    \
              CPUModels.MODEL_GROUPS["CANNONLAKE"] +  \
              CPUModels.MODEL_GROUPS["SKYLAKE"] +     \
              CPUModels.MODEL_GROUPS["BROADWELL"] +   \
              CPUModels.MODEL_GROUPS["HASWELL"] +     \
              CPUModels.MODEL_GROUPS["IVYBRIDGE"] +   \
              CPUModels.MODEL_GROUPS["SANDYBRIDGE"] + \
              CPUModels.MODEL_GROUPS["WESTMERE"] +    \
              CPUModels.MODEL_GROUPS["NEHALEM"] +     \
              CPUModels.MODEL_GROUPS["CRESTMONT"] +   \
              CPUModels.MODEL_GROUPS["TREMONT"] +     \
              CPUModels.MODEL_GROUPS["GOLDMONT"] +    \
              CPUModels.MODEL_GROUPS["PHI"]

# CPU models supporting the "minimum operating ratio" feature.
_MIN_OPER_RATIO_CPUS = CPUModels.MODEL_GROUPS["GNR"] +              \
                       CPUModels.MODEL_GROUPS["EMR"] +              \
                       CPUModels.MODEL_GROUPS["METEORLAKE"] +       \
                       CPUModels.MODEL_GROUPS["SPR"] +              \
                       CPUModels.MODEL_GROUPS["RAPTORLAKE"] +       \
                       CPUModels.MODEL_GROUPS["ALDERLAKE"] +        \
                       CPUModels.MODEL_GROUPS["ROCKETLAKE"] +       \
                       CPUModels.MODEL_GROUPS["TIGERLAKE"] +        \
                       CPUModels.MODEL_GROUPS["ICELAKE"] +          \
                       CPUModels.MODEL_GROUPS["COMETLAKE"] +        \
                       CPUModels.MODEL_GROUPS["KABYLAKE"] +         \
                       CPUModels.MODEL_GROUPS["CANNONLAKE"] +       \
                       CPUModels.MODEL_GROUPS["SKYLAKE"] +          \
                       CPUModels.MODEL_GROUPS["BROADWELL"] +        \
                       CPUModels.MODEL_GROUPS["HASWELL"] +          \
                       (CPUModels.MODELS["IVYBRIDGE"]["model"],) +  \
                       CPUModels.MODEL_GROUPS["CRESTMONT"] +        \
                       CPUModels.MODEL_GROUPS["TREMONT"] +          \
                       CPUModels.MODEL_GROUPS["GOLDMONT"] +         \
                       CPUModels.MODEL_GROUPS["PHI"]

# CPU models supporting the "maximum non-turbo ratio" feature.
_BASEFREQ_CPUS = _EFREQ_CPUS + CPUModels.MODEL_GROUPS["SILVERMONT"] + \
                 CPUModels.MODEL_GROUPS["AIRMONT"]

# Description of CPU features controlled by the the Platform Information MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_non_turbo_ratio": {
        "name": "Max. Non-Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of the maximum non-turbo frequency. This ratio multiplied by bus
                   clock speed gives the base frequency.""",
        "cpumodels": _BASEFREQ_CPUS,
        "type": "int",
        "writable": False,
        "bits": (15, 8),
    },
    "max_eff_ratio": {
        "name": "Max. Efficiency Ratio",
        "sname": None,
        "iosname": None,
        "help": """The maximum efficiency CPU ratio. This ratio multiplied by bus clock speed gives
                   the efficiency CPU frequency (Pn).""",
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
                   the minimum operating CPU frequency (Pm).""",
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
