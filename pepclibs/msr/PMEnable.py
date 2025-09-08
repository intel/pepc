# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for accessing MSR 0x770 (MSR_PM_ENABLE), an architectural MSR present on many Intel
platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Power Management Enable Model Specific Register.
MSR_PM_ENABLE: Final = 0x770

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "hwp": {
        "name": "Hardware Power Management enabled",
        "sname": None,
        "iosname": None,
        "help": """When hardware power management is enabled, the platform autonomously scales CPU
                   frequency depending on the load.""",
        "cpuflags": {"hwp",},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (0, 0),
    },
}

class PMEnable(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for accessing MSR 0x770 (MSR_PM_ENABLE), an architectural MSR present on many
    Intel platforms.
    """

    regaddr = MSR_PM_ENABLE
    regname = "MSR_PM_ENABLE"
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
