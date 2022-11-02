# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x772 (MSR_HWP_REQUEST_PKG). This is an architectural MSR found on
many Intel platforms.
"""

import logging
from pepclibs.msr import _FeaturedMSR, PMEnable

_LOG = logging.getLogger()

# The Hardware Power Management Request Package Model Specific Register.
MSR_HWP_REQUEST_PKG = 0x772

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "min_perf" : {
        "name" : "Minimum CPU performance",
        "sname": "package",
        "help" : """The minimum desired CPU performance.""",
        "cpuflags" : {"hwp"},
        "type" : "int",
        "bits" : (7, 0),
    },
    "max_perf" : {
        "name" : "Maximum CPU performance",
        "sname": "package",
        "help" : """The maximum desired CPU performance.""",
        "cpuflags" : {"hwp"},
        "type" : "int",
        "bits" : (15, 8),
    },
    "epp" : {
        "name" : "Energy Performance Preference",
        "sname": "package",
        "help" : """Energy Performance Preference is a hint to the CPU running in HWP mode about the
                    power and performance preference. Value 0 indicates highest performance and
                    value 255 indicates maximum energy savings.""",
        "cpuflags" : {"hwp", "hwp_epp"},
        "type" : "int",
        "bits" : (31, 24),
    },
}

class HWPRequestPkg(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x772 (MSR_HWP_REQUEST_PKG). This is an architectural MSR found
    on many Intel platforms.
    """

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_HWP_REQUEST_PKG
        self.regname = "MSR_HWP_REQUEST_PKG"

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

        for finfo in self._features.values():
            if "cpuflags" in finfo and "hwp" in finfo["cpuflags"]:
                for pkg in self._cpuinfo.get_packages():
                    cpus = self._cpuinfo.package_to_cpus(pkg)

                    if not finfo["supported"][cpus[0]]:
                        continue

                    # Accessing 'MSR_HWP_REQUEST' is allowed only if bit 0 is set in
                    # 'MSR_PM_ENABLE'.
                    if self._msr.read_cpu_bits(PMEnable.MSR_PM_ENABLE,
                                               PMEnable.FEATURES["hwp"]["bits"], cpus[0]):
                        continue

                    for cpu in cpus:
                        finfo["supported"][cpu] = False
