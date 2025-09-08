# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0x772 (MSR_HWP_REQUEST_PKG), an architectural MSR available on many Intel
platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import cast
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR, PMEnable

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Hardware Power Management Request Package Model Specific Register.
MSR_HWP_REQUEST_PKG: Final = 0x772

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "min_perf": {
        "name": "Min. CPU performance",
        "sname": None,
        "iosname": None,
        "help": """The minimum desired CPU performance.""",
        "cpuflags": {"hwp", "hwp_pkg_req"},
        "type": "int",
        "bits": (7, 0),
    },
    "max_perf": {
        "name": "Max. CPU performance",
        "sname": None,
        "iosname": None,
        "help": """The maximum desired CPU performance.""",
        "cpuflags": {"hwp", "hwp_pkg_req"},
        "type": "int",
        "bits": (15, 8),
    },
    "epp": {
        "name": "Energy Performance Preference",
        "sname": None,
        "iosname": None,
        "help": """Energy Performance Preference is a hint to the CPU running in HWP mode about the
                   power and performance preference. Value 0 indicates highest performance and
                   value 255 indicates maximum energy savings.""",
        "cpuflags": {"hwp", "hwp_epp", "hwp_pkg_req"},
        "type": "int",
        "bits": (31, 24),
    },
}

class HWPRequestPkg(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x772 (MSR_HWP_REQUEST_PKG), an architectural MSR available on many Intel
    platforms.
    """

    regaddr = MSR_HWP_REQUEST_PKG
    regname = "MSR_HWP_REQUEST_PKG"
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

        for pfinfo in self._partial_features.values():
            pfinfo["sname"] = pfinfo["iosname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)

        unsupported_cpus = []
        for pkg in self._cpuinfo.get_packages():
            cpus = self._cpuinfo.package_to_cpus(pkg)

            # Make sure the CPU supports HWP and has HWP is enabled.
            cpuflags = self._cpuinfo.info["flags"][cpus[0]]
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
