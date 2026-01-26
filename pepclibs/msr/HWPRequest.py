# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide an API for MSR 0x774 (MSR_HWP_REQUEST), an architectural MSR available on many Intel
platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import cast
from pepclibs.msr import _FeaturedMSR, PMEnable
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The Hardware Power Management Request Model Specific Register.
MSR_HWP_REQUEST: Final = 0x774

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "min_perf": {
        "name": "Min. CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The minimum desired CPU performance.""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (7, 0),
        "writable": True,
    },
    "max_perf": {
        "name": "Max. CPU performance",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """The maximum desired CPU performance.""",
        "cpuflags": {"hwp"},
        "type": "int",
        "bits": (15, 8),
        "writable": True,
    },
    "epp": {
        "name": "Energy Performance Preference",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """Energy Performance Preference is a hint to the CPU running in HWP mode about the
                   power and performance preference. Value 0 indicates highest performance and
                   value 255 indicates maximum energy savings.""",
        "cpuflags": {"hwp", "hwp_epp"},
        "type": "int",
        "bits": (31, 24),
        "writable": True,
    },
    "pkg_control": {
        "name": "HWP is controlled by MSR_HWP_REQUEST_PKG",
        "sname": "CPU",
        "iosname": "CPU",
        "help": f"""When enabled, the CPU ignores this per-CPU ignores MSR {MSR_HWP_REQUEST}
                    (MSR_HWP_REQUEST), and instead, uses per-package MSR 0x772
                    (MSR_HWP_REQUEST_PKG).""",
        "cpuflags": {"hwp", "hwp_pkg_req"},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (42, 42),
        "writable": True,
    },
    "epp_valid": {
        "name": "EPP is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "iosname": "CPU",
        "help": f"""When set, the CPU reads the EPP value from per-CPU MSR {MSR_HWP_REQUEST}
                    (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags": {"hwp", "hwp_epp"},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (60, 60),
        "writable": True,
    },
    "max_perf_valid": {
        "name": "Max. performance is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "iosname": "CPU",
        "help": f"""When set, the CPU reads the Maximum performance value from per-CPU MSR
                   {MSR_HWP_REQUEST} (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags": {"hwp"},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (62, 62),
        "writable": True,
    },
    "min_perf_valid": {
        "name": "Min. performance is controlled by MSR_HWP_REQUEST",
        "sname": "CPU",
        "iosname": "CPU",
        "help": f"""When set, the CPU reads the Minimum performance value from per-CPU MSR
                    {MSR_HWP_REQUEST} (MSR_HWP_REQUEST), even if bit 42 ('pkg_control') is set.""",
        "cpuflags": {"hwp"},
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (63, 63),
        "writable": True,
    },
}

class HWPRequest(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x774 (MSR_HWP_REQUEST), an architectural MSR available on many Intel
    platforms.
    """

    regaddr = MSR_HWP_REQUEST
    regname = "MSR_HWP_REQUEST"
    vendor_name = "GenuineIntel"

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
            cpuflags = cpuinfo.proc_cpuinfo["flags"][cpus[0]]
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

    def is_cpu_feature_pkg_controlled(self, fname: str, cpu: int) -> bool:
        """
        Check whether the specified HWP feature is managed by the package-level MSR
        ('MSR_HWP_REQUEST_PKG') or by the per-CPU MSR ('MSR_HWP_REQUEST'). If package control is not
        supported, the feature is considered to be controlled per-CPU. If package control is
        enabled, further check if the feature's "valid" bit allows per-CPU override.

        Args:
            fname: Name of the feature to check.
            cpu: CPU number to check the feature for.

        Returns:
           True if the feature is controlled by the package-level MSR, False if controlled per-CPU.
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

    def disable_cpu_feature_pkg_control(self, fname: str, cpu: int):
        """
        Disable the 'MSR_HWP_REQUEST_PKG' control for the specified HWP feature, allowing the
        feature to be managed on a per-CPU basis instead of at the package level. If package-level
        control is not supported on the target CPU, the return without making changes.

        Args:
            fname: Name of the HWP feature associated with 'MSR_HWP_REQUEST'.
            cpu: CPU number for which to disable package-level control.
        """

        try:
            pkg_control = self.is_cpu_feature_enabled("pkg_control", cpu)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return

        if pkg_control:
            self.write_cpu_feature(f"{fname}_valid", "on", cpu)
