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
    from typing import Final, Generator, Literal, Sequence, Iterable
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
        "help": f"""When enabled, the CPU ignores this per-CPU MSR {MSR_HWP_REQUEST}
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

        proc_percpuinfo = self._cpuinfo.get_proc_percpuinfo()
        unsupported_cpus = []

        for pkg in self._cpuinfo.get_packages():
            cpus = self._cpuinfo.package_to_cpus(pkg)

            # Make sure the CPU supports HWP and HWP is enabled.
            cpuflags = proc_percpuinfo["flags"][cpus[0]]
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

    def is_feature_pkg_controlled_nonorm(self, fname: str, cpus: Sequence[int]) -> \
                                                            Generator[tuple[int, bool], None, None]:
        """
        Same as 'is_feature_pkg_controlled_norm()', no CPU normalization.
        """

        # Check if pkg_control is supported.
        try:
            self.validate_feature_supported_nonorm("pkg_control", cpus=cpus)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            for cpu in cpus:
                yield cpu, False
            return

        # Determine which features to read.
        valid_fname = f"{fname}_valid"
        fnames = ["pkg_control"]

        try:
            self.validate_feature_supported_nonorm(valid_fname, cpus=cpus)
            fnames.append(valid_fname)
        except ErrorNotSupported:
            pass

        # Read features in bulk.
        for cpu, vals in self.read_features_nonorm(fnames, cpus=cpus):
            pkg_control = vals["pkg_control"] in {"on", "enabled"}
            if not pkg_control:
                yield cpu, False
                continue

            # Package control is enabled. Check if it can be overridden by the valid bit.
            if valid_fname in vals:
                valid = vals[valid_fname] in {"on", "enabled"}
                if valid:
                    # The valid bit is set, so per-CPU control overrides package control.
                    yield cpu, False
                else:
                    yield cpu, True
            else:
                # No valid bit exists for this feature, so package control applies.
                yield cpu, True

    def is_feature_pkg_controlled_norm(self, fname: str,
                                       cpus: Iterable[int] | Literal["all"] = "all") -> \
                                                            Generator[tuple[int, bool], None, None]:
        """
        Check whether the specified HWP feature is managed by the package-level MSR
        ('MSR_HWP_REQUEST_PKG') or by the per-CPU MSR ('MSR_HWP_REQUEST'). If package control is not
        supported, the feature is considered to be controlled per-CPU. If package control is
        enabled, further check if the feature's "valid" bit allows per-CPU override.

        Args:
            fname: Name of the feature to check.
            cpus: CPU numbers to check the feature for. Special value "all" selects all CPUs.

        Yields:
            Tuples of (cpu, pkg_controlled), where 'cpu' is the CPU number and 'pkg_controlled' is
            True if the feature is controlled by the package-level MSR, False if controlled per-CPU.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        yield from self.is_feature_pkg_controlled_nonorm(fname, cpus=cpus)

    def is_cpu_feature_pkg_controlled_nonorm(self, fname: str, cpu: int) -> bool:
        """
        Same as 'is_cpu_feature_pkg_controlled_norm()', no CPU normalization.
        """

        try:
            pkg_control = self.is_cpu_feature_enabled_nonorm("pkg_control", cpu)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return False

        if pkg_control:
            # Even if package control is enabled, it can be overridden by the 'fname' "valid" bit.
            valid = self.is_cpu_feature_enabled_nonorm(f"{fname}_valid", cpu)
            if not valid:
                return True

        return False

    def is_cpu_feature_pkg_controlled_norm(self, fname: str, cpu: int) -> bool:
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

        cpu = self._cpuinfo.normalize_cpus([cpu])[0]
        return self.is_cpu_feature_pkg_controlled_nonorm(fname, cpu)

    def disable_feature_pkg_control_nonorm_remote(self, fname: str, cpus: Sequence[int]):
        """
        An implementation of 'disable_feature_pkg_control_nonorm()' optimized for a remote host,
        where it is more optimal to read the package control state for all CPUs in a single bulk
        operation and then update the necessary CPUs in a single bulk write operation.
        """

        try:
            self.validate_feature_supported_nonorm("pkg_control", cpus=cpus)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return

        # Find CPUs where pkg_control is enabled.
        cpus_to_update: list[int] = []
        for cpu, vals in self.read_features_nonorm(["pkg_control"], cpus=cpus):
            if vals["pkg_control"] in {"on", "enabled"}:
                cpus_to_update.append(cpu)

        # Set the valid bit for all CPUs that need it in a single bulk operation.
        if cpus_to_update:
            self.write_feature_nonorm(f"{fname}_valid", "on", cpus=cpus_to_update)

    def disable_feature_pkg_control_nonorm(self, fname: str, cpus: Sequence[int]):
        """
        Same as 'disable_feature_pkg_control_norm()', no CPU normalization.
        """

        if self._pman.is_remote:
            self.disable_feature_pkg_control_nonorm_remote(fname, cpus=cpus)
        else:
            for cpu in cpus:
                self.disable_cpu_feature_pkg_control_nonorm(fname, cpu)

    def disable_feature_pkg_control_norm(self, fname: str,
                                         cpus: Iterable[int] | Literal["all"] = "all"):
        """
        Disable the 'MSR_HWP_REQUEST_PKG' control for the specified HWP feature, allowing the
        feature to be managed on a per-CPU basis instead of at the package level. If package-level
        control is not supported on the target CPUs, return without making changes.

        Args:
            fname: Name of the HWP feature associated with 'MSR_HWP_REQUEST'.
            cpus: CPU numbers for which to disable package-level control. Special value "all"
                  selects all CPUs.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        self.disable_feature_pkg_control_nonorm(fname, cpus=cpus)

    def disable_cpu_feature_pkg_control_nonorm(self, fname: str, cpu: int):
        """
        Same as 'disable_cpu_feature_pkg_control_norm()', no CPU normalization.
        """

        try:
            pkg_control = self.is_cpu_feature_enabled_nonorm("pkg_control", cpu)
        except ErrorNotSupported:
            # If package control is not supported, 'fname' is controlled on a per-CPU basis.
            return

        if pkg_control:
            self.write_cpu_feature_nonorm(f"{fname}_valid", "on", cpu)

    def disable_cpu_feature_pkg_control_norm(self, fname: str, cpu: int):
        """
        Disable the 'MSR_HWP_REQUEST_PKG' control for the specified HWP feature, allowing the
        feature to be managed on a per-CPU basis instead of at the package level. If package-level
        control is not supported on the target CPU, the return without making changes.

        Args:
            fname: Name of the HWP feature associated with 'MSR_HWP_REQUEST'.
            cpu: CPU number for which to disable package-level control.
        """

        cpu = self._cpuinfo.normalize_cpus([cpu])[0]
        self.disable_cpu_feature_pkg_control_nonorm(fname, cpu)
