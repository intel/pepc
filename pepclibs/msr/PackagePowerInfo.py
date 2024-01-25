# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module provides API to MSR 0x614 (MSR_PKG_POWER_INFO).
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR
from pepclibs.helperlibs import ClassHelpers

# The Package Power Info Model Specific Register.
MSR_PKG_POWER_INFO = 0x614

# CPU models supporting the "Package Power Info" MSR.
_PPI_CPUS = CPUModels.MODEL_GROUPS["GNR"] +         \
            CPUModels.MODEL_GROUPS["EMR"] +         \
            CPUModels.MODEL_GROUPS["METEORLAKE"] +  \
            CPUModels.MODEL_GROUPS["SPR"] +         \
            CPUModels.MODEL_GROUPS["RAPTORLAKE"] +  \
            CPUModels.MODEL_GROUPS["ALDERLAKE"] +   \
            CPUModels.MODEL_GROUPS["ROCKETLAKE"] +  \
            CPUModels.MODEL_GROUPS["TIGERLAKE"] +   \
            CPUModels.MODEL_GROUPS["ICELAKE"] +     \
            CPUModels.MODEL_GROUPS["COMETLAKE"] +   \
            CPUModels.MODEL_GROUPS["KABYLAKE"] +    \
            CPUModels.MODEL_GROUPS["CANNONLAKE"] +  \
            CPUModels.MODEL_GROUPS["SKYLAKE"] +     \
            CPUModels.MODEL_GROUPS["BROADWELL"] +   \
            CPUModels.MODEL_GROUPS["HASWELL"] +     \
            CPUModels.MODEL_GROUPS["IVYBRIDGE"] +   \
            CPUModels.MODEL_GROUPS["SANDYBRIDGE"] + \
            CPUModels.MODEL_GROUPS["WESTMERE"] +    \
            CPUModels.MODEL_GROUPS["TREMONT"] +     \
            CPUModels.MODEL_GROUPS["GOLDMONT"] +    \
            CPUModels.MODEL_GROUPS["PHI"]

# Description of CPU features controlled by the Package Power Info MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "tdp": {
        "name": "CPU package thermal design power",
        "sname": "package",
        "iosname": "package",
        "help": """CPU package thermal design power in Watts.""",
        "cpumodels": _PPI_CPUS,
        "type": "float",
        "bits": (14, 0),
        "writable": False,
    },
}

class PackagePowerInfo(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x614 (MSR_PKG_POWER_INFO).
    """

    regaddr = MSR_PKG_POWER_INFO
    regname = "MSR_PKG_POWER_INFO"
    vendor = "GenuineIntel"

    def _get_unitobj(self):
        """Returns a 'RaplPowerUnit.RaplPowerUnit()' object."""

        if not self._unitobj:
            from pepclibs.msr import RaplPowerUnit # pylint: disable=import-outside-toplevel
            self._unitobj = RaplPowerUnit.RaplPowerUnit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=self._msr)

        return self._unitobj

    def _get_units(self, unitname):
        """Returns the named system unit value."""

        cpu = self._cpuinfo.get_cpus()[0]
        return self._get_unitobj().read_cpu_feature(unitname, cpu)

    def _get_power_units(self):
        """Returns the system 'power units' value in Watts."""

        if not self._power_units:
            self._power_units = self._get_units("power_units")
        return self._power_units

    def _get_feature(self, fname, cpus="all"):
        """Returns the value for a feature."""

        bits = self._features[fname]["bits"]

        for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus,
                                            iosname=self._features[fname]["iosname"]):
            val *= self._get_power_units()

            yield (cpu, val)

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        self._unitobj = None
        self._power_units = None

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_unitobj",))

        super().close()
