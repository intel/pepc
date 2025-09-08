# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API to MSR 0x1B1 (MSR_ENERGY_PERF_BIAS). This is an architectural MSR found on many Intel
platforms.
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
    from pepclibs.CPUInfoTypes import ScopeNameType

# The Energy Performance Bias Model Specific Register.
MSR_ENERGY_PERF_BIAS = 0x1B0

# MSR_ENERGY_PERF_BIAS features have CPU scope, except for the following CPUs.
_CORE_SCOPE_VFMS = CPUModels.CPU_GROUPS["SILVERMONT"]
_PACKAGE_SCOPE_VFMS = CPUModels.CPU_GROUPS["WESTMERE"] + CPUModels.CPU_GROUPS["SANDYBRIDGE"]

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: dict[str, PartialFeatureTypedDict] = {
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
        vfm = cpuinfo.info["vfm"]

        sname: ScopeNameType
        if vfm in _CORE_SCOPE_VFMS:
            sname = "core"
        elif vfm in _PACKAGE_SCOPE_VFMS:
            sname = "package"
        else:
            sname = "CPU"

        for finfo in self._partial_features.values():
            finfo["sname"] = finfo["iosname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)
