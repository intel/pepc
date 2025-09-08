# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for accessing MSR 0x771 (MSR_HWP_CAPABILITIES), an architectural MSR available on
many Intel platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import cast
from pepclibs.msr import _FeaturedMSR, PMEnable

if typing.TYPE_CHECKING:
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Hardware Power Management Capabilities Model Specific Register.
MSR_HWP_CAPABILITIES = 0x771

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "max_perf": {
        "name": "Max. CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The maximum CPU performance (P01).""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (7, 0),
    },
    "base_perf": {
        "name": "Base CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The base (guaranteed) CPU performance (P1).""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (15, 8),
    },
    "eff_perf": {
        "name": "Max. efficiency CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The maximum efficiency CPU performance (Pn).""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (23, 16),
    },
    "min_perf": {
        "name": "Min. CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The minimum CPU performance (Pm).""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (31, 24),
    },
}

class HWPCapabilities(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for accessing MSR 0x771 (MSR_HWP_CAPABILITIES), an architectural MSR available on
    many Intel platforms.
    """

    regaddr = MSR_HWP_CAPABILITIES
    regname = "MSR_HWP_CAPABILITIES"
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

        super().__init__(cpuinfo, pman=pman, msr=msr)

        unsupported_cpus = []
        for pkg in cpuinfo.get_packages():
            cpus = cpuinfo.package_to_cpus(pkg)

            # Make sure the CPU supports HWP and has HWP is enabled.
            cpuflags = cpuinfo.info["flags"][cpus[0]]
            if "hwp" in cpuflags:
                if self._msr.read_cpu_bits(PMEnable.MSR_PM_ENABLE,
                                           cast(tuple[int, int], PMEnable.FEATURES["hwp"]["bits"]),
                                           cpus[0]):
                    continue

            # If HWP is not supported or not enabled for any CPU in the package, all the other CPUs
            # are expected to be the same.
            unsupported_cpus += cpus

        for finfo in self._features.values():
            if "cpuflags" in finfo and "hwp" in finfo["cpuflags"]:
                for cpu in unsupported_cpus:
                    finfo["supported"][cpu] = False
