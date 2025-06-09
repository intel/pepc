# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module provides API to MSR 0x0x54 (MSR_PM_LOGICAL_ID).
"""

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR
from pepclibs.msr ._FeaturedMSR import PartialFeatureTypedDict


# The PM Logical ID Model Specific Register.
MSR_PM_LOGICAL_ID = 0x54

# CPUs supporting the "PM Logical ID" MSR.
_PLI_VFMS = CPUModels.CPU_GROUPS["GNR"] + CPUModels.CPU_GROUPS["CRESTMONT"]

# Description of CPU features controlled by the PM Logical ID.
FEATURES: dict[str, PartialFeatureTypedDict] = {
    "domain_id": {
        "name": "Domain ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """Domain ID.""",
        "vfms": _PLI_VFMS,
        "type": "int",
        "bits": (15, 11),
        "writable": False,
    },
    "module_id": {
        "name": "Module ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """Module ID.""",
        "vfms": _PLI_VFMS,
        "type": "int",
        "bits": (10, 3),
        "writable": False,
    },
    "cpu_id": {
        "name": "CPU ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """CPU ID.""",
        "vfms": _PLI_VFMS,
        "type": "int",
        "bits": (2, 0),
        "writable": False,
    },
}

class PMLogicalId(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x54 (MSR_PM_LOGICAL_ID).
    """

    regaddr = MSR_PM_LOGICAL_ID
    regname = "MSR_PM_LOGICAL_ID"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
