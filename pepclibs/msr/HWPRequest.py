# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x774 (MSR_HWP_REQUEST). This is an architectural MSR found on many
Intel platforms.
"""

import logging
from pepclibs.msr import _FeaturedMSR, PMEnable
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

_LOG = logging.getLogger()

# The Hardware Power Management Request Model Specific Register.
MSR_HWP_REQUEST = 0x774

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "min_perf" : {
        "name" : "Min. CPU performance",
        "sname": "CPU",
        "help" : """The minimum desired CPU performance.""",
        "cpuflags" : {"hwp"},
        "type" : "int",
        "bits" : (7, 0),
    },
    "max_perf" : {
        "name" : "Max. CPU performance",
        "sname": "CPU",
        "help" : """The maximum desired CPU performance.""",
        "cpuflags" : {"hwp"},
        "type" : "int",
        "bits" : (15, 8),
    },
    "epp" : {
        "name" : "Energy Performance Preference",
        "sname": "CPU",
        "help" : """Energy Performance Preference is a hint to the CPU running in HWP mode about the
                    power and performance preference. Value 0 indicates highest performance and
                    value 255 indicates maximum energy savings.""",
        "cpuflags" : {"hwp", "hwp_epp"},
        "type" : "int",
        "bits" : (31, 24),
    },
    "pkg_control" : {
        "name" : "HWP is controlled by MSR_HWP_REQUEST_PKG",
        "sname": "CPU",
        "help" : f"""When enabled, the CPU ignores this per-CPU ignores MSR {MSR_HWP_REQUEST}
                     (MSR_HWP_REQUEST), and instead, uses per-package MSR 0x772
                     (MSR_HWP_REQUEST_PKG).""",
        "cpuflags" : {"hwp", "hwp_pkg_req"},
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (42, 42),
    },
    "epp_valid" : {
        "name" : "EPP is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "help" : f"""When set, the CPU reads the EPP value from per-CPU MSR {MSR_HWP_REQUEST}
                     (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags" : {"hwp", "hwp_epp"},
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (60, 60),
    },
    "max_perf_valid" : {
        "name" : "Max. performance is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "help" : f"""When set, the CPU reads the Maximum performance value from per-CPU MSR
                     {MSR_HWP_REQUEST} (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags" : {"hwp"},
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (62, 62),
    },
    "min_perf_valid" : {
        "name" : "Min. performance is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "help" : f"""When set, the CPU reads the Minimum performance value from per-CPU MSR
                     {MSR_HWP_REQUEST} (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags" : {"hwp"},
        "type" : "bool",
        "vals" : {"on" : 1, "off" : 0},
        "bits" : (63, 63),
    },
}

class HWPRequest(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x774 (MSR_HWP_REQUEST). This is an architectural MSR found on
    many Intel platforms.
    """

    regaddr = MSR_HWP_REQUEST
    regname = "MSR_HWP_REQUEST"
    vendor = "GenuineIntel"

    def is_cpu_feature_pkg_controlled(self, fname, cpu):
        """
        Returns 'True' if an HWP feature is controlled by 'MSR_HWP_REQUEST_PKG' or 'False' if it is
        controlled by 'MSR_HWP_REQUEST'. The arguments are as follows.
         * fname - name of the 'MSR_HWP_REQUEST' feature to check.
         * cpu - CPU number to check the feature for.
        """

        try:
            pkg_control = self.is_cpu_feature_enabled("pkg_control", cpu)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return False

        if pkg_control:
            # Even if package control is enabled, it can be overridden by the 'fname' "valid" bit.
            valid = self.is_cpu_feature_enabled(f"{fname}_valid", cpu)
            if not valid:
                return True

        return False

    def disable_cpu_feature_pkg_control(self, fname, cpu):
        """
        Disable 'MSR_HWP_REQUEST_PKG' control over an HWP feature. The arguments are as follows.
         * fname - name of the 'MSR_HWP_REQUEST' feature.
         * cpu - CPU number for which to disable package control.
        """

        try:
            pkg_control = self.is_cpu_feature_enabled("pkg_control", cpu)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return

        if pkg_control:
            self.write_cpu_feature(f"{fname}_valid", "on", cpu)

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES

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
