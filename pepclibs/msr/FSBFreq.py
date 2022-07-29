# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0xCD (MSR_FSB_FREQ). This MSR provides bus clock speed information
on some Intel platforms.
"""

import logging
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

_LOG = logging.getLogger()

# The Scalable Bus Speed Model Specific Register.
MSR_FSB_FREQ = 0xCD

# Core 2 clients.
_CORE2_FSB_CODES = {"codes" : {100    : 0b101, 133.33 : 0b001,
                               166.67 : 0b011, 200    : 0b010,
                               266.67 : 0b000, 333.33 : 0b100,
                               400    : 0b110},
                    "bits": (2, 0)}

# Core 2 clients.
_CORE2_FSB_CODES = {"codes" : {"100"    : 0b101, "133.33" : 0b001,
                               "166.67" : 0b011, "200"    : 0b010,
                               "266.67" : 0b000, "333.33" : 0b100,
                               "400"    : 0b110},
                    "bits": (2, 0)}

# Pre-Silvermont Atoms.
_OLD_ATOM_FSB_CODES = {"codes" : {"83"     : 0b111, "100"    : 0b101,
                                  "133.33" : 0b001, "166.67" : 0b011},
                       "bits": (2, 0)}

# Silvermont Atoms.
_SILVERMONT_FSB_CODES = {"codes" : {"80"    : 0b100, "83.3"  : 0b000,
                                    "100.0" : 0b001, "133.3" : 0b010,
                                    "116.7" : 0b011},
                         "bits": (2, 0)}

# Airmont Atoms.
_AIRMONT_FSB_CODES = {"codes" : {"83.3"  : 0b0000, "100.0" : 0b0001,
                                 "133.3" : 0b0010, "116.7" : 0b0011,
                                 "80"    : 0b0100, "93.3"  : 0b0101,
                                 "90"    : 0b0110, "88.9"  : 0b0111,
                                 "87.5"  : 0b1000},
                      "bits": (3, 0)}

# CPU ID -> FSB codes map.
_FSB_CODES = {
    CPUInfo.INTEL_FAM6_CORE2_MEROM:          _CORE2_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_BONNELL_MID:     _OLD_ATOM_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_BONNELL:         _OLD_ATOM_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SALTWELL:        _OLD_ATOM_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SALTWELL_MID:    _OLD_ATOM_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SALTWELL_TABLET: _OLD_ATOM_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SILVERMONT:      _SILVERMONT_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SILVERMONT_MID:  _SILVERMONT_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_SILVERMONT_MID1: _SILVERMONT_FSB_CODES,
    CPUInfo.INTEL_FAM6_ATOM_AIRMONT:         _AIRMONT_FSB_CODES,
}

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the # notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "fsb" : {
        "name" : "Bus clock speed (megahertz)",
        "scope": "package",
        "help" : f"""Platform bus clock speed (FSB) in megahertz, as inidcated by MSR
                     {MSR_FSB_FREQ:#x} (MSR_FSB_FREQ).""",
        "cpumodels" : tuple(_FSB_CODES.keys()),
        "type"      : "float",
        "writable"  : False,
    },
}

class FSBFreq(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xCD (MSR_FSB_FREQ). This MSR provides bus clock speed
    information on some Intel platforms.
    """

    def _init_features_dict_fsb(self):
        """Initialize the 'fsb' feature information in the 'self._features' dictionary."""

        if not self._features["fsb"]["supported"]:
            return

        cpumodel = self._cpuinfo.info["model"]
        cpumodel_info = _FSB_CODES[cpumodel]

        finfo = self._features["fsb"]
        finfo["bits"] = cpumodel_info["bits"]
        finfo["vals"] = cpumodel_info["codes"]

    def _init_features_dict(self):
        """Intitialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_fsb()
        self._init_features_dict_defaults()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self._features = FEATURES
        self.regaddr = MSR_FSB_FREQ
        self.regname = "MSR_FSB_FREQ"

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
