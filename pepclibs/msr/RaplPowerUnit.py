# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module provides API to MSR 0x606 (RAPL_POWER_UNIT).
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Energy Performance Bias Model Specific Register.
RAPL_POWER_UNIT = 0x606

# CPUs supporting the "RAPL Power Unit" MSR.
_RPU_VFMS = CPUModels.CPU_GROUPS["GNR"] +         \
            CPUModels.CPU_GROUPS["EMR"] +         \
            CPUModels.CPU_GROUPS["METEORLAKE"] +  \
            CPUModels.CPU_GROUPS["SPR"] +         \
            CPUModels.CPU_GROUPS["RAPTORLAKE"] +  \
            CPUModels.CPU_GROUPS["ALDERLAKE"] +   \
            CPUModels.CPU_GROUPS["ROCKETLAKE"] +  \
            CPUModels.CPU_GROUPS["TIGERLAKE"] +   \
            CPUModels.CPU_GROUPS["ICELAKE"] +     \
            CPUModels.CPU_GROUPS["COMETLAKE"] +   \
            CPUModels.CPU_GROUPS["KABYLAKE"] +    \
            CPUModels.CPU_GROUPS["CANNONLAKE"] +  \
            CPUModels.CPU_GROUPS["SKYLAKE"] +     \
            CPUModels.CPU_GROUPS["BROADWELL"] +   \
            CPUModels.CPU_GROUPS["HASWELL"] +     \
            CPUModels.CPU_GROUPS["IVYBRIDGE"] +   \
            CPUModels.CPU_GROUPS["SANDYBRIDGE"] + \
            CPUModels.CPU_GROUPS["WESTMERE"] +    \
            CPUModels.CPU_GROUPS["TREMONT"] +     \
            CPUModels.CPU_GROUPS["GOLDMONT"] +    \
            CPUModels.CPU_GROUPS["PHI"]

# Description of CPU features controlled by the RAPL Power Unit MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "power_units": {
        "name": "Power units",
        "help": """Scaling factor for translating RAPL Power Units to Watts.""",
        "vfms": _RPU_VFMS,
        "sname": "package",
        "iosname": "package",
        "type": "float",
        "writable": False,
        "bits": (3, 0),
    },
    "energy_units": {
        "name": "Energy units",
        "help": """Scaling factor for translating RAPL Energy Units to Joules.""",
        "vfms": _RPU_VFMS,
        "sname": "package",
        "iosname": "package",
        "type": "float",
        "writable": False,
        "bits": (12, 8),
    },
    "time_units": {
        "name": "Time units",
        "help": """Scaling factor for translating RAPL Time Units to seconds.""",
        "vfms": _RPU_VFMS,
        "sname": "package",
        "iosname": "package",
        "type": "float",
        "writable": False,
        "bits": (19, 16),
    },
}

class RaplPowerUnit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x606 (RAPL_POWER_UNIT).
    """

    regaddr = RAPL_POWER_UNIT
    regname = "RAPL_POWER_UNIT"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname

    def _get_units(self, fname, cpus):
        """Helper routine to get and calculate given unit value."""

        finfo = self.features[fname]

        for cpu, val in self._msr.read_bits(self.regaddr, finfo["bits"], cpus):
            if fname == "energy_units" and \
               self._cpuinfo.info["vfm"] == CPUModels.MODELS["ATOM_SILVERMONT"]["vfm"]:
                val = pow(2, val) / 1000000
            else:
                val = 1 / pow(2, val)

            yield (cpu, val)

    def _get_power_units(self, cpus="all"):
        """Gets power units value in Watts."""

        return self._get_units("power_units", cpus)

    def _get_time_units(self, cpus="all"):
        """Gets time units value in Seconds."""

        return self._get_units("time_units", cpus)

    def _get_energy_units(self, cpus="all"):
        """Gets energy units value in Joules."""

        return self._get_units("energy_units", cpus)
