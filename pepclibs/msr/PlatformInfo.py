# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0xCE (MSR_PLATFORM_INFO), a model-specific register present on many Intel
platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Power Control Model Specific Register.
MSR_PLATFORM_INFO: Final = 0xCE

# CPUs supporting the "minimum operating ratio" feature.
_MIN_OPER_RATIO_VFMS: Final = CPUModels.CPU_GROUPS["DMR"] +              \
                              CPUModels.CPU_GROUPS["GNR"] +              \
                              CPUModels.CPU_GROUPS["EMR"] +              \
                              CPUModels.CPU_GROUPS["ARROWLAKE"] +        \
                              CPUModels.CPU_GROUPS["METEORLAKE"] +       \
                              CPUModels.CPU_GROUPS["SPR"] +              \
                              CPUModels.CPU_GROUPS["RAPTORLAKE"] +       \
                              CPUModels.CPU_GROUPS["ALDERLAKE"] +        \
                              CPUModels.CPU_GROUPS["ROCKETLAKE"] +       \
                              CPUModels.CPU_GROUPS["TIGERLAKE"] +        \
                              CPUModels.CPU_GROUPS["ICELAKE"] +          \
                              CPUModels.CPU_GROUPS["COMETLAKE"] +        \
                              CPUModels.CPU_GROUPS["KABYLAKE"] +         \
                              CPUModels.CPU_GROUPS["CANNONLAKE"] +       \
                              CPUModels.CPU_GROUPS["SKYLAKE"] +          \
                              CPUModels.CPU_GROUPS["BROADWELL"] +        \
                              CPUModels.CPU_GROUPS["HASWELL"] +          \
                              (CPUModels.MODELS["IVYBRIDGE"]["vfm"],) +  \
                              CPUModels.CPU_GROUPS["DARKMONT"] +         \
                              CPUModels.CPU_GROUPS["CRESTMONT"] +        \
                              CPUModels.CPU_GROUPS["TREMONT"] +          \
                              CPUModels.CPU_GROUPS["GOLDMONT"] +         \
                              CPUModels.CPU_GROUPS["PHI"]

# CPUs supporting the "maximum efficiency ratio" feature.
_BASEFREQ_VFMS: Final = CPUModels.CPU_GROUPS["DMR"] +         \
                        CPUModels.CPU_GROUPS["GNR"] +         \
                        CPUModels.CPU_GROUPS["EMR"] +         \
                        CPUModels.CPU_GROUPS["ARROWLAKE"] +   \
                        CPUModels.CPU_GROUPS["METEORLAKE"] +  \
                        CPUModels.CPU_GROUPS["SPR"] +         \
                        CPUModels.CPU_GROUPS["RAPTORLAKE"] +  \
                        CPUModels.CPU_GROUPS["ALDERLAKE"] +   \
                        CPUModels.CPU_GROUPS["ROCKETLAKE"] +  \
                        CPUModels.CPU_GROUPS["TIGERLAKE"] +   \
                        CPUModels.CPU_GROUPS["ICELAKE"] +     \
                        CPUModels.CPU_GROUPS["COMETLAKE"] +   \
                        CPUModels.CPU_GROUPS["KABYLAKE"] +    \
                        CPUModels.CPU_GROUPS["CANNONLAKE"] +  \
                        CPUModels.CPU_GROUPS["SKYLAKE"] +     \
                        CPUModels.CPU_GROUPS["BROADWELL"] +   \
                        CPUModels.CPU_GROUPS["HASWELL"] +     \
                        CPUModels.CPU_GROUPS["IVYBRIDGE"] +   \
                        CPUModels.CPU_GROUPS["SANDYBRIDGE"] + \
                        CPUModels.CPU_GROUPS["WESTMERE"] +    \
                        CPUModels.CPU_GROUPS["NEHALEM"] +     \
                        CPUModels.CPU_GROUPS["DARKMONT"] +    \
                        CPUModels.CPU_GROUPS["CRESTMONT"] +   \
                        CPUModels.CPU_GROUPS["TREMONT"] +     \
                        CPUModels.CPU_GROUPS["GOLDMONT"] +    \
                        CPUModels.CPU_GROUPS["AIRMONT"] +     \
                        CPUModels.CPU_GROUPS["SILVERMONT"] +  \
                        CPUModels.CPU_GROUPS["PHI"]

# Description of CPU features controlled by the the Platform Information MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "max_non_turbo_ratio": {
        "name": "Max. Non-Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": "The maximum non-turbo ratio.",
        "vfms": set(_BASEFREQ_VFMS),
        "type": "int",
        "bits": (15, 8),
        "writable": False,
    },
    "min_oper_ratio": {
        "name": "Min. Operating Ratio",
        "sname": None,
        "iosname": None,
        "help": """The minimum CPU operating ratio.""",
        "vfms": set(_MIN_OPER_RATIO_VFMS),
        "type": "int",
        "bits": (55, 48),
        "writable": False,
    },
}

class PlatformInfo(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0xCE (MSR_PLATFORM_INFO), a model-specific register present on many Intel
    platforms.
    """

    regaddr = MSR_PLATFORM_INFO
    regname = "MSR_PLATFORM_INFO"
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

        self._partial_features = copy.deepcopy(FEATURES)

        sname = _FeaturedMSR.get_clx_ap_adjusted_msr_scope(cpuinfo)
        for finfo in self._partial_features.values():
            finfo["sname"] = finfo["iosname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        if self._cpuinfo.is_hybrid:
            # On hybrid platforms the MSR shows the performance, not the ratio.
            for finfo in self._partial_features.values():
                finfo["help"] = finfo["help"].replace("ratio", "performance")

        super()._init_features_dict()
