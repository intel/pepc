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

# CPU models supporting the "RAPL Power Unit" MSR.
_RPU_CPUS = CPUModels.MODEL_GROUPS["GNR"] +         \
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

# Description of CPU features controlled by the RAPL Power Unit MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "power_units": {
        "name": "Power units",
        "help": """Scaling factor for translating RAPL Power Units to Watts.""",
        "cpumodels": _RPU_CPUS,
        "sname": "package",
        "iosname": "package",
        "type": "float",
        "writable": False,
        "bits": (3, 0),
    },
    "energy_units": {
        "name": "Energy units",
        "help": """Scaling factor for translating RAPL Energy Units to Joules.""",
        "cpumodels": _RPU_CPUS,
        "sname": "package",
        "iosname": "package",
        "type": "float",
        "writable": False,
        "bits": (12, 8),
    },
    "time_units": {
        "name": "Time units",
        "help": """Scaling factor for translating RAPL Time Units to seconds.""",
        "cpumodels": _RPU_CPUS,
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
               self._cpuinfo.info["model"] == CPUModels.MODELS["ATOM_SILVERMONT"]["model"]:
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
