# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API for accessing MSR 0xCD (MSR_FSB_FREQ), which reports the bus clock speed
on certain Intel platforms.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from pepclibs import CPUModels
from pepclibs.msr import _FeaturedMSR

if typing.TYPE_CHECKING:
    from typing import TypedDict, Final
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.CPUInfoTypes import ScopeNameType
    from pepclibs.msr._FeaturedMSR import PartialFeatureTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _FSBCodesTypedDict(TypedDict, total=False):
        """
        A dictionary that describes the FSB codes for a specific CPU model.

        Attributes:
            codes: A dictionary mapping bus clock speeds (in megahertz) to their corresponding
                   FSB codes.
            bits: A tuple containing the bit positions for the FSB code in the MSR register.
        """

        codes: dict[float, int]
        bits: tuple[int, int]

# The Scalable Bus Speed Model Specific Register.
MSR_FSB_FREQ: Final = 0xCD

# Core 2 clients.
_CORE2_FSB_CODES: Final[_FSBCodesTypedDict] = {
    "codes": {100.00: 0b101,
              133.33: 0b001,
              166.67: 0b011,
              200.00: 0b010,
              266.67: 0b000,
              333.33: 0b100,
              400.00: 0b110},
    "bits": (2, 0)
}

# Pre-Silvermont Atoms.
_OLD_ATOM_FSB_CODES: Final[_FSBCodesTypedDict] = {
    "codes": {083.00: 0b111,
              100.00: 0b101,
              133.33: 0b001,
              166.67: 0b011},
    "bits": (2, 0)
}

# Silvermont Atoms.
_SILVERMONT_FSB_CODES: Final[_FSBCodesTypedDict] = {
    "codes": {080.0: 0b100,
              083.3: 0b000,
              100.0: 0b001,
              133.3: 0b010,
              116.7: 0b011},
    "bits": (2, 0)
}

# Airmont Atoms.
_AIRMONT_FSB_CODES: Final[_FSBCodesTypedDict] = {
    "codes": {083.3: 0b0000,
              100.0: 0b0001,
              133.3: 0b0010,
              116.7: 0b0011,
              080.0: 0b0100,
              093.3: 0b0101,
              090.0: 0b0110,
              088.9:  0b0111,
              087.5:  0b1000},
    "bits": (3, 0)
}

# CPU ID -> FSB codes map.
_FSB_CODES: Final[dict[int, _FSBCodesTypedDict]] = {
    CPUModels.MODELS["CORE2_MEROM"]["vfm"]:          _CORE2_FSB_CODES,
    CPUModels.MODELS["ATOM_BONNELL_MID"]["vfm"]:     _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_BONNELL"]["vfm"]:         _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL"]["vfm"]:        _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL_MID"]["vfm"]:    _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SALTWELL_TABLET"]["vfm"]: _OLD_ATOM_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT"]["vfm"]:      _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT_MID"]["vfm"]:  _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_SILVERMONT_MID1"]["vfm"]: _SILVERMONT_FSB_CODES,
    CPUModels.MODELS["ATOM_AIRMONT"]["vfm"]:         _AIRMONT_FSB_CODES,
}

# MSR_FSB_FREQ features have core scope, except for the following CPUs.
_MODULE_SCOPE_VFMS: Final = CPUModels.CPU_GROUPS["SILVERMONT"] + CPUModels.CPU_GROUPS["AIRMONT"]

# Description of CPU features controlled by the the Power Control MSR.
FEATURES: Final[dict[str, PartialFeatureTypedDict]] = {
    "fsb" : {
        "name": "Bus clock speed (megahertz)",
        "sname": None,
        "iosname": None,
        "help": "Platform bus clock speed (FSB) in megahertz",
        "vfms": set(_FSB_CODES),
        "type": "float",
        "writable": False,
    },
}

class FSBFreq(_FeaturedMSR.FeaturedMSR):
    """
    Provide API for accessing MSR 0xCD (MSR_FSB_FREQ), which reports the bus clock speed on certain
    Intel platforms.
    """

    regaddr = MSR_FSB_FREQ
    regname = "MSR_FSB_FREQ"
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
        vfm = cpuinfo.proc_cpuinfo["vfm"]

        sname: ScopeNameType
        if vfm in _MODULE_SCOPE_VFMS:
            sname = "module"
        else:
            sname = "core"

        for finfo in self._partial_features.values():
            finfo["sname"] = finfo["iosname"] = sname

        super().__init__(cpuinfo, pman=pman, msr=msr)

    def _init_features_dict_fsb(self):
        """Initialize the 'fsb' feature information in the 'self._features' dictionary."""

        vfm = self._cpuinfo.proc_cpuinfo["vfm"]
        if vfm not in _FSB_CODES:
            return

        fsb_codes = _FSB_CODES[vfm]

        finfo = self._features["fsb"]
        finfo["bits"] = fsb_codes["bits"]
        finfo["vals"] = fsb_codes["codes"]

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        self._init_features_dict_fsb()

        super()._init_features_dict()
