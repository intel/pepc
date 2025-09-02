# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide an API for MSR 0x1FC (MSR_POWER_CTL), a model-specific register available on many Intel
platforms.

Notes:
    - The C-state pre-wake feature is available on "big core" server CPUs. Artem Bityutskiy verified
      that it works using the 'wult' tool using timer-based interrupts, which clearly shows very low
      CC6 exit latency when C-state prewake was enabled, and much higher latency when it was
      disabled.
    - Artem Bityutskiy verified many Atom-based server platforms and Client platforms - the C-state
      pre-wake bit is a "no-op" on those platforms. The 'wult' tool showed no difference in CC6
      exit latency when the C-state pre-wake bit was toggled. The verified platforms include:
      Knights Landing, Snow Ridge, Denverton.
    - Artem Bityutskiy verified that the C-state pre-wake feature is a "no-op" on many client
      platforms, including Alder Lake, Raptor Lake, Meteor Lake, Arrow Lake, and Lunar Lake.
    - On some platforms BIOS may have a "C-state pre-wake" option, but the platform does not really
      implement the feature, the feature is a "no-op".
    - This module reports a feature as "supported" only if it is known to work and is not a "no-op".
      Otherwise, the feature is reported as "not supported".
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

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

# Description of CPU features controlled by the Power Control MSR.
#
# Note: while the "C-state prewake" feature available on many CPUs, in practice it works only on
#       some platforms, like Ice Lake Xeon. Therefore we mark it as "supported" only for those
#       platforms where we know it works.
FEATURES: dict[str, PartialFeatureTypedDict] = {
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
        "vfms": set(_CSTATE_PREWAKE_VFMS),
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
        "vfms": set(LTR_VFMS),
        "type": "bool",
        "vals": {"on": 0, "off": 1},
        "bits": (35, 35),
    },
}

class PowerCtl(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x1FC (MSR_POWER_CTL), a model-specific register available on many Intel
    platforms.
    """

    regaddr = MSR_POWER_CTL
    regname = "MSR_POWER_CTL"
    vendor = "GenuineIntel"

    def __init__(self,
                 cpuinfo: CPUInfo.CPUInfo,
                 pman: ProcessManagerType | None = None,
                 msr: MSR.MSR | None = None):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object.
            pman: The Process manager object that defines the host to run the measurements on. If
                  not provided, a local process manager will be used.
            msr: An optional 'MSR.MSR()' object to use for writing to the MSR register. If not
                 provided, a new MSR object will be created.

        Raises:
            ErrorNotSupported: If CPU vendor is not supported or if the CPU does not the MSR.
        """

        self._partial_features = FEATURES

        sname = _FeaturedMSR.get_clx_ap_adjusted_msr_scope(cpuinfo)
        for finfo in self._partial_features.values():
            finfo["sname"] = finfo["iosname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)
