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

from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

# The Scalable Bus Speed Model Specific Register.
MSR_FSB_FREQ = 0xCD

# Core 2 clients.
_CORE2_FSB_CODES = {"codes": {100.0:  0b101, 133.33: 0b001,
                              166.67: 0b011, 200.0:  0b010,
                              266.67: 0b000, 333.33: 0b100,
                              400.0:  0b110},
                    "bits": (2, 0)}

# Pre-Silvermont Atoms.
_OLD_ATOM_FSB_CODES = {"codes": {83.0:   0b111, 100.0:  0b101,
                                 133.33: 0b001, 166.67: 0b011},
                       "bits": (2, 0)}

# Silvermont Atoms.
_SILVERMONT_FSB_CODES = {"codes": {80.0:  0b100, 83.3:  0b000,
                                   100.0: 0b001, 133.3: 0b010,
                                   116.7: 0b011},
                         "bits": (2, 0)}

# Airmont Atoms.
_AIRMONT_FSB_CODES = {"codes": {83.3:  0b0000, 100.0: 0b0001,
                                133.3: 0b0010, 116.7: 0b0011,
                                80.0:  0b0100, 93.3:  0b0101,
                                90.0:  0b0110, 88.9:  0b0111,
                                87.5:  0b1000},
                      "bits": (3, 0)}

# CPU ID -> FSB codes map.
_FSB_CODES = {
    CPUModels.MODELS["CORE2_MEROM"]["model"]:          _CORE2_FSB_CODES,
    CPUModels.MODELS["ATOM_BONNELL_MID"]["model"]:     _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_BONNELL"]["model"]:         _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL"]["model"]:        _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL_MID"]["model"]:    _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL_TABLET"]["model"]: _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT"]["model"]:      _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT_MID"]["model"]:  _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT_MID1"]["model"]: _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_AIRMONT"]["model"]:         _AIRMONT_FSB_CODES,
}

# MSR_FSB_FREQ features have core scope, except for the following CPU models.
_MODULE_SCOPE_CPUS = CPUModels.MODEL_GROUPS["SILVERMONT"] + CPUModels.MODEL_GROUPS["AIRMONT"]

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "fsb" : {
        "name": "Bus clock speed (megahertz)",
        "sname": None,
        "iosname": None,
        "help": "Platform bus clock speed (FSB) in megahertz",
        "cpumodels": tuple(_FSB_CODES.keys()),
        "type": "float",
        "writable": False,
    },
}

class FSBFreq(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0xCD (MSR_FSB_FREQ). This MSR provides bus clock speed
    information on some Intel platforms.
    """

    regaddr = MSR_FSB_FREQ
    regname = "MSR_FSB_FREQ"
    vendor = "GenuineIntel"

    def _init_features_dict_fsb(self):
        """Initialize the 'fsb' feature information in the 'self._features' dictionary."""

        if not self.is_feature_supported("fsb", cpus="all"):
            return

        cpumodel = self._cpuinfo.info["model"]
        cpumodel_info = _FSB_CODES[cpumodel]

        finfo = self._features["fsb"]
        finfo["bits"] = cpumodel_info["bits"]
        finfo["vals"] = cpumodel_info["codes"]

    def _init_features_dict(self):
        """Initialize the 'features' dictionary with platform-specific information."""

        self._init_supported_flag()
        self._init_features_dict_fsb()
        self._init_features_dict_defaults()

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        model = self._cpuinfo.info["model"]

        if model in _MODULE_SCOPE_CPUS:
            sname = "module"
        else:
            sname = "core"

        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname
