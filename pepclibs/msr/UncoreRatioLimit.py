# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0x620 (MSR_UNCORE_RATIO_LIMIT), which allows you to control and limit
uncore frequency on some older Intel platforms. Note, newer Intel platforms use TPMI for this
instead.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Uncore Ratio Limit Model Specific Register.
MSR_UNCORE_RATIO_LIMIT = 0x620

#
# CPUs that support the uncore ratio limit MSR.
#
_VMFS = CPUModels.CPU_GROUPS["EMR"] + \
        CPUModels.CPU_GROUPS["METEORLAKE"] + \
        CPUModels.CPU_GROUPS["SPR"] + \
        CPUModels.CPU_GROUPS["RAPTORLAKE"] + \
        (CPUModels.MODELS["ALDERLAKE"]["vfm"],
         CPUModels.MODELS["ALDERLAKE_L"]["vfm"]) + \
        CPUModels.CPU_GROUPS["ICX"] + \
        CPUModels.CPU_GROUPS["SKX"] + \
        (CPUModels.MODELS["BROADWELL_G"]["vfm"],
         CPUModels.MODELS["BROADWELL_D"]["vfm"],
         CPUModels.MODELS["BROADWELL_X"]["vfm"])

# Description of CPU features controlled by the the Turbo Ratio Limit MSR.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "max_ratio": {
        "name": "Maximum uncore ratio",
        "sname": None,
        "iosname": None,
        "help": """The maximum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                   the maximum allowed uncore frequency.""",
        "vfms": set(_VMFS),
        "type": "int",
        "writable": True,
        "bits": (6, 0),
    },
    "min_ratio": {
        "name": "Minimum uncore ratio",
        "sname": None,
        "iosname": None,
        "help": """The minimum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                   the minimum allowed uncore frequency.""",
        "vfms": set(_VMFS),
        "type": "int",
        "writable": True,
        "bits": (14, 8),
    },
}

class UncoreRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x620 (MSR_UNCORE_RATIO_LIMIT), which allows you to control and limit
    uncore frequency on some older Intel platforms. Note, newer Intel platforms use TPMI for this
    instead.
    """

    regaddr = MSR_UNCORE_RATIO_LIMIT
    regname = "MSR_UNCORE_RATIO_LIMIT"
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
            finfo["sname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)
