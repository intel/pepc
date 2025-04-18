# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1FC (MSR_POWER_CTL). This is a model-specific register found on
many Intel platforms.
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Power Control Model Specific Register.
MSR_POWER_CTL = 0x1FC

# CPUs supporting the C-state pre-wake feature.
_CSTATE_PREWAKE_VFMS = (CPUModels.MODELS["GRANITERAPIDS_X"]["vfm"],
                        CPUModels.MODELS["GRANITERAPIDS_D"]["vfm"],
                        CPUModels.MODELS["EMERALDRAPIDS_X"]["vfm"],
                        CPUModels.MODELS["SAPPHIRERAPIDS_X"]["vfm"],
                        CPUModels.MODELS["ICELAKE_X"]["vfm"],
                        CPUModels.MODELS["ICELAKE_D"]["vfm"],
                        CPUModels.MODELS["SKYLAKE_X"]["vfm"],
                        CPUModels.MODELS["BROADWELL_X"]["vfm"],
                        CPUModels.MODELS["HASWELL_X"]["vfm"],
                        CPUModels.MODELS["IVYBRIDGE_X"]["vfm"],)

# CPU supporting the LTR feature.
LTR_VFMS = (CPUModels.MODELS["GRANITERAPIDS_X"]["vfm"],
            CPUModels.MODELS["EMERALDRAPIDS_X"]["vfm"],
            CPUModels.MODELS["SAPPHIRERAPIDS_X"]["vfm"],
            CPUModels.MODELS["ICELAKE_X"]["vfm"],)

# Description of CPU features controlled by the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
#
# Note: while the "C-state prewake" feature available on many CPUs, in practice it works only on
#       some platforms, like Ice Lake Xeon. Therefore we mark it as "supported" only for those
#       platforms where we know it works.
FEATURES = {
    "c1e_autopromote": {
        "name": "C1E autopromote",
        "sname": None,
        "iosname": None,
        "help": "When enabled, the CPU automatically converts all C1 requests to C1E requests.",
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (1, 1),
    },
    "cstate_prewake": {
        "name": "C-state prewake",
        "sname": None,
        "iosname": None,
        "help": """When enabled, the CPU will start exiting the C6 idle state in advance, prior to
                   the next local APIC timer event.""",
        "vfms": _CSTATE_PREWAKE_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": (30, 30),
    },
    "ltr": {
        "name": "LTR (Latency Tolerance Reporting)",
        "sname": "package",
        "iosname": None,
        "help": """When enabled, the CPU will take LTR constraints into account when making power
                   management decisions, such as selecting package C-state.""",
        "vfms": LTR_VFMS,
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": (35, 35),
    },
}

class PowerCtl(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1FC (MSR_POWER_CTL). This is a model-specific register found on
    many Intel platforms.
    """

    regaddr = MSR_POWER_CTL
    regname = "MSR_POWER_CTL"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
