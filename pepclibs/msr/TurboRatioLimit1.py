# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0x1AE (MSR_TURBO_RATIO_LIMIT1). Depending on the platform, use this MSR to
retrieve either turbo ratio information or turbo ratio group encoding. In the latter case, refer to
it as 'MSR_TURBO_GROUP_CORECNT' (for Atom CPUs) or 'MSR_TURBO_RATIO_LIMIT_CORES' (for big cores).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs.msr import _FeaturedMSR, TurboRatioLimit

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Turbo Ratio Limit 1 Model Specific Register.
MSR_TURBO_RATIO_LIMIT1 = 0x1AE
MSR_TURBO_GROUP_CORECNT = 0x1AE
MSR_TURBO_RATIO_LIMIT_CORES = 0x1AE

# Description of CPU features controlled by the the Turbo Ratio Limit MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "g0_cpu_cnt": {
        "name": "Group 0 cores count",
        "sname": None,
        "iosname": None,
        "help": """Count of cores in group 0. This group is used in MSR 0x1AD
                   (MSR_TURBO_RATIO_LIMIT) for encoding the maximum group of cores turbo
                   frequency.""",
        "vfms": TurboRatioLimit.FEATURES["max_g0_turbo_ratio"]["vfms"],
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
}

class TurboRatioLimit1(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x1AE (MSR_TURBO_RATIO_LIMIT1). Depending on the platform, use this MSR
    to retrieve either turbo ratio information or turbo ratio group encoding. In the latter case,
    refer to it as 'MSR_TURBO_GROUP_CORECNT' (for Atom CPUs) or 'MSR_TURBO_RATIO_LIMIT_CORES' (for
    big cores).
    """

    regaddr = MSR_TURBO_RATIO_LIMIT1
    regname = "MSR_TURBO_RATIO_LIMIT1"
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
