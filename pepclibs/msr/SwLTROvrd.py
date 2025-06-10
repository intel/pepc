# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to Software LTR Override MSR 0xA02 (MSR_SW_LTR_OVRD). This is a
model-specific register allows the OS communicate software (as opposed to PCIe) LTR (Latency
Tolerance Report) requirements to the power management unit of the CPU.
"""

from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR, PowerCtl, MSR
from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict
from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Software LTR Override Model Specific Register.
MSR_SW_LTR_OVRD = 0xA02

# CPU models supporting the LTR feature.
_LTR_CPUS = PowerCtl.LTR_VFMS

# Description of CPU features controlled by the MSR.
#
# Note: only snoop latency bits and fields are supported. There are non-snoop latency bits and
# fields, but the do not seem to be useful.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "sxl": {
        "name": "Snoop latency software LTR",
        "sname": "package",
        "iosname": "package",
        "help": """Software (as opposed to PCIe) Latency Tolerance Report (LTR) value for
                   snoop latency in nanoseconds. Value 0 corresponds to best possible service
                   request.""",
        "cpumodels": _LTR_CPUS,
        "type": "int",
        "bits": (25, 16),
    },
    "sxlm": {
        "name": "Snoop latency LTR multiplier",
        "sname": "package",
        "iosname": "package",
        "help": "Multiplier for the snoop latency software LTR.",
        "cpumodels": _LTR_CPUS,
        "type": "int",
        "bits": (28, 26),
    },
    "force_sxl": {
        "name": "Force snoop latency software LTR",
        "sname": "package",
        "iosname": "package",
        "help": """When set, use snoop latency software LTR value from this MSR regardless of LTR
                   from PCIe controllers.""",
        "cpumodels": _LTR_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (30, 30),
    },
    "sxl_v": {
        "name": "Enable snoop latency software LTR",
        "sname": "package",
        "iosname": "package",
        "help": """When enabled, power management unit takes into account snoop latency software
                   LTR value from this MSR, otherwise ignores it.""",
        "cpumodels": _LTR_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (31, 31),
    },
}

class SwLTROvrd(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to Software LTR Override MSR 0xA02 (MSR_SW_LTR_OVRD).
    """

    regaddr = MSR_SW_LTR_OVRD
    regname = "MSR_SW_LTR_OVRD"
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

        super().__init__(cpuinfo, pman=pman, msr=msr)
