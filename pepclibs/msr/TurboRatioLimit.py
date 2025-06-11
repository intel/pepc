# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0x1AD (MSR_TURBO_RATIO_LIMIT) to retrieve turbo ratio information on Intel
platforms.
"""

from pepclibs import CPUModels, CPUInfo
from pepclibs.msr import _FeaturedMSR, MSR
from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict
from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Turbo Ratio Limit Model Specific Register.
MSR_TURBO_RATIO_LIMIT = 0x1AD

#
# CPUs that include core turbo ratios in the MSR (as apposed to group turbo ratio). "CT" in
# the names stands for "Core Turbo".
#
_CT_VFMS = CPUModels.CPU_GROUPS["ARROWLAKE"] +  \
           CPUModels.CPU_GROUPS["METEORLAKE"] +  \
           CPUModels.CPU_GROUPS["RAPTORLAKE"] +  \
           CPUModels.CPU_GROUPS["ALDERLAKE"] +   \
           CPUModels.CPU_GROUPS["ROCKETLAKE"] +  \
           CPUModels.CPU_GROUPS["TIGERLAKE"] +   \
           CPUModels.CPU_GROUPS["LAKEFIELD"] +   \
           CPUModels.CPU_GROUPS["ICL_CLIENT"] +  \
           CPUModels.CPU_GROUPS["SKL_CLIENT"] +  \
           CPUModels.CPU_GROUPS["COMETLAKE"] +   \
           CPUModels.CPU_GROUPS["KABYLAKE"] +    \
           CPUModels.CPU_GROUPS["CANNONLAKE"] +  \
           CPUModels.CPU_GROUPS["BROADWELL"] +   \
           (CPUModels.MODELS["ATOM_SILVERMONT_D"]["vfm"], ) + \
           CPUModels.CPU_GROUPS["HASWELL"] +     \
           CPUModels.CPU_GROUPS["IVYBRIDGE"] +   \
           CPUModels.CPU_GROUPS["SANDYBRIDGE"] + \
           (CPUModels.MODELS["NEHALEM"]["vfm"],
            CPUModels.MODELS["NEHALEM_G"]["vfm"],
            CPUModels.MODELS["NEHALEM_EP"]["vfm"])

# CPUs that include group turbo ratios in the MSR. "GT" in the names stands for "Group
# Turbo". In this case MSR 0x1AE should be decoded to get count of cores in a group. In SDM, this
# MSR is named 'MSR_TURBO_GROUP_CORECNT' for Atom CPUs and 'MSR_TURBO_RATIO_LIMIT_CORES' for "big
# core" CPUs. The same MSR is called 'MSR_TURBO_RATIO_LIMIT1' for CPUs that do not have groups in
# 'MSR_TURBO_RATIO_LIMIT'.
_GT_VFMS = CPUModels.CPU_GROUPS["GNR"] + \
           CPUModels.CPU_GROUPS["CRESTMONT"] + \
           CPUModels.CPU_GROUPS["EMR"] + \
           CPUModels.CPU_GROUPS["SPR"] + \
           (CPUModels.MODELS["ATOM_TREMONT_D"]["vfm"],) +  \
           CPUModels.CPU_GROUPS["ICX"] + \
           CPUModels.CPU_GROUPS["SKX"] + \
           (CPUModels.MODELS["ATOM_GOLDMONT_D"]["vfm"],
            CPUModels.MODELS["ATOM_GOLDMONT"]["vfm"],
            CPUModels.MODELS["ATOM_GOLDMONT_PLUS"]["vfm"],)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "max_1c_turbo_ratio": {
        "name": "Max. 1 Core Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of maximum turbo frequency in case of 1 active core. This ratio
                   multiplied by bus clock speed gives the maximum 1 core turbo frequency.""",
        "vfms": set(_CT_VFMS),
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
    "max_g0_turbo_ratio": {
        "name": "Max. Group 0 cores Turbo Ratio",
        "sname": None,
        "iosname": None,
        "help": """The ratio of maximum turbo frequency in case "group 0" count of cores are
                   active. This ratio multiplied by bus clock speed gives the frequency. Count of
                   cores in group 0 is provided by MSR 0x1AE.""",
        "vfms": set(_GT_VFMS),
        "type": "int",
        "writable": False,
        "bits": (7, 0),
    },
}

class TurboRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x1AD (MSR_TURBO_RATIO_LIMIT) to retrieve turbo ratio information on
    Intel platforms.
    """

    regaddr = MSR_TURBO_RATIO_LIMIT
    regname = "MSR_TURBO_RATIO_LIMIT"
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
