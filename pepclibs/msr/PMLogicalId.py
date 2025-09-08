# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide an API for MSR 0x0x54 (MSR_PM_LOGICAL_ID), a model-specific register present on many Intel
platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs import CPUModels, CPUInfo
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The PM Logical ID Model Specific Register.
MSR_PM_LOGICAL_ID: Final = 0x54

# CPUs supporting the "PM Logical ID" MSR.
_PLI_VFMS: Final = CPUModels.CPU_GROUPS["GNR"] + \
                   CPUModels.CPU_GROUPS["DARKMONT"] + \
                   CPUModels.CPU_GROUPS["CRESTMONT"]

# Description of CPU features controlled by the PM Logical ID.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "domain_id": {
        "name": "Domain ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """Domain ID.""",
        "vfms": set(_PLI_VFMS),
        "type": "int",
        "bits": (15, 11),
        "writable": False,
    },
    "module_id": {
        "name": "Module ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """Module ID.""",
        "vfms": set(_PLI_VFMS),
        "type": "int",
        "bits": (10, 3),
        "writable": False,
    },
    "cpu_id": {
        "name": "CPU ID",
        "sname": "CPU",
        "iosname": "CPU",
        "help": """CPU ID.""",
        "vfms": set(_PLI_VFMS),
        "type": "int",
        "bits": (2, 0),
        "writable": False,
    },
}

class PMLogicalId(_FeaturedMSR.FeaturedMSR):
    """
    Provide an API for MSR 0x0x54 (MSR_PM_LOGICAL_ID), a model-specific register present on many
    Intel platforms.
    """

    regaddr = MSR_PM_LOGICAL_ID
    regname = "MSR_PM_LOGICAL_ID"
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
