# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide information about CPU topology and other CPU details.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import TypedDict, Final

    class CPUModelTypedDict(TypedDict):
        """
        CPU model information.

        Attributes:
            vendor: The vendor of the CPU.
            family: The family of the CPU.
            model: The model number of the CPU.
            vfm: The VFM (Vendor, Family, Model) code of the CPU.
            codename: The codename of the CPU.
        """

        vendor: int
        family: int
        model: int
        vfm: int
        codename: str

X86_VENDOR_INTEL: Final[int] = 0
X86_VENDOR_AMD: Final[int] = 2

X86_CPU_VENDORS: Final[dict[str, int]] = {
    "GenuineIntel": X86_VENDOR_INTEL,
    "AuthenticAMD": X86_VENDOR_AMD,
}

def make_vfm(vendor: int | str, family: int, model: int) -> int:
    """
    Create and return the VFM (Vendor, Family, Model) code for an x86 CPU.

    Args:
        vendor: The vendor ID or vendor name of the CPU.
        family: The family of the CPU.
        model: The model number of the CPU.

    Returns:
        The VFM code of the CPU.
    """

    if isinstance(vendor, str):
        vendor_code = X86_CPU_VENDORS.get(vendor, -1)
        if vendor_code == -1:
            raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor}'")
    else:
        vendor_code = vendor

    return (vendor_code << 16) | (family << 8) | model

def make_intel_vfm(family: int, model: int) -> int:
    """
    Create and return the VFM (Vendor, Family, Model) code for an Intel CPU.

    Args:
        family: The family of the Intel CPU.
        model: The model number of the Intel CPU.

    Returns:
        The VFM code of the Intel CPU.
    """

    return make_vfm(X86_VENDOR_INTEL, family, model)

MODELS: Final[dict[str, CPUModelTypedDict]] = {
    # Xeons.
    "DIAMONDRAPIDS_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 19,
        "model": 0x1,
        "vfm": make_intel_vfm(19, 0x1),
        "codename": "Diamond Rapids Xeon",
    },
    "ATOM_DARKMONT_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xDD,
        "vfm": make_intel_vfm(6, 0xDD),
        "codename": "Clearwater Forest Xeon",
    },
    "ATOM_CRESTMONT_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xAF,
        "vfm": make_intel_vfm(6, 0xAF),
        "codename": "Sierra Forest Xeon",
    },
    "GRANITERAPIDS_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xAD,
        "vfm": make_intel_vfm(6, 0xAD),
        "codename": "Granite Rapids Xeon",
    },
    "GRANITERAPIDS_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xAE,
        "vfm": make_intel_vfm(6, 0xAE),
        "codename": "Granite Rapids Xeon D",
    },
    "EMERALDRAPIDS_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xCF,
        "vfm": make_intel_vfm(6, 0xCF),
        "codename": "Emerald Rapids Xeon",
    },
    "SAPPHIRERAPIDS_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x8F,
        "vfm": make_intel_vfm(6, 0x8F),
        "codename": "Sapphire Rapids Xeon",
    },
    "ICELAKE_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x6A,
        "vfm": make_intel_vfm(6, 0x6A),
        "codename": "Ice Lake Xeon",
    },
    "ICELAKE_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x6C,
        "vfm": make_intel_vfm(6, 0x6C),
        "codename": "Ice Lake Xeon D",
    },
    "SKYLAKE_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x55,
        "vfm": make_intel_vfm(6, 0x55),
        "codename": "Skylake, Cascade Lake, or Cooper Lake Xeon",
    },
    "BROADWELL_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x4F,
        "vfm": make_intel_vfm(6, 0x4F),
        "codename": "Broadwell Xeon",
    },
    "BROADWELL_G": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x47,
        "vfm": make_intel_vfm(6, 0x47),
        "codename": "Broadwell Xeon with Graphics",
    },
    "BROADWELL_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x56,
        "vfm": make_intel_vfm(6, 0x56),
        "codename": "Broadwell Xeon-D",
    },
    "HASWELL_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x3F,
        "vfm": make_intel_vfm(6, 0x3F),
        "codename": "Haswell Xeon",
    },
    "HASWELL_G": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x46,
        "vfm": make_intel_vfm(6, 0x46),
        "codename": "Haswell Xeon with Graphics",
    },
    "IVYBRIDGE_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x3E,
        "vfm": make_intel_vfm(6, 0x3E),
        "codename": "Ivy Town Xeon",
    },
    "SANDYBRIDGE_X": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x2D,
        "vfm": make_intel_vfm(6, 0x2D),
        "codename": "SandyBridge Xeon",
    },
    "WESTMERE_EP": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x2C,
        "vfm": make_intel_vfm(6, 0x2C),
        "codename": "Westmere 2S Xeon",
    },
    "WESTMERE_EX": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x2F,
        "vfm": make_intel_vfm(6, 0x2F),
        "codename": "Westmere 4S Xeon",
    },
    "NEHALEM_EP": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x1A,
        "vfm": make_intel_vfm(6, 0x1A),
        "codename": "Nehalem 2S Xeon",
    },
    "NEHALEM_EX": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x2E,
        "vfm": make_intel_vfm(6, 0x2E),
        "codename": "Nehalem 4S Xeon",
    },
    # Clients.
    "LUNARLAKE_M": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xBD,
        "vfm": make_intel_vfm(6, 0xBD),
        "codename": "Lunar Lake mobile",
    },
    "ARROWLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xC5,
        "vfm": make_intel_vfm(6, 0xC5),
        "codename": "Arrow Lake client",
    },
    "ARROWLAKE_H": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xC6,
        "vfm": make_intel_vfm(6, 0xC6),
        "codename": "Arrow Lake mobile",
    },
    "ARROWLAKE_U": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xB5,
        "vfm": make_intel_vfm(6, 0xB5),
        "codename": "Arrow Lake mobile",
    },
    "METEORLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xAC,
        "vfm": make_intel_vfm(6, 0xAC),
        "codename": "Meteor Lake client",
    },
    "METEORLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xAA,
        "vfm": make_intel_vfm(6, 0xAA),
        "codename": "Meteor Lake mobile",
    },
    "RAPTORLAKE_P": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xBA,
        "vfm": make_intel_vfm(6, 0xBA),
        "codename": "Raptor Lake mobile",
    },
    "RAPTORLAKE_S": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xBF,
        "vfm": make_intel_vfm(6, 0xBF),
        "codename": "Raptor Lake client",
    },
    "RAPTORLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xB7,
        "vfm": make_intel_vfm(6, 0xB7),
        "codename": "Raptor Lake client",
    },
    "ALDERLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x97,
        "vfm": make_intel_vfm(6, 0x97),
        "codename": "Alder Lake client",
    },
    "ALDERLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x9A,
        "vfm": make_intel_vfm(6, 0x9A),
        "codename": "Alder Lake mobile",
    },
    "ALDERLAKE_N": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xBE,
        "vfm": make_intel_vfm(6, 0xBE),
        "codename": "Alder Lake mobile",
    },
    "ROCKETLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xA7,
        "vfm": make_intel_vfm(6, 0xA7),
        "codename": "Rocket Lake client",
    },
    "TIGERLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x8D,
        "vfm": make_intel_vfm(6, 0x8D),
        "codename": "Tiger Lake client",
    },
    "TIGERLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x8C,
        "vfm": make_intel_vfm(6, 0x8C),
        "codename": "Tiger Lake mobile",
    },
    "LAKEFIELD": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x8A,
        "vfm": make_intel_vfm(6, 0x8A),
        "codename": "Lakefield client",
    },
    "COMETLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xA5,
        "vfm": make_intel_vfm(6, 0xA5),
        "codename": "Comet Lake client",
    },
    "COMETLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xA6,
        "vfm": make_intel_vfm(6, 0xA6),
        "codename": "Comet Lake mobile",
    },
    "KABYLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x9E,
        "vfm": make_intel_vfm(6, 0x9E),
        "codename": "Kaby Lake client",
    },
    "KABYLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x8E,
        "vfm": make_intel_vfm(6, 0x8E),
        "codename": "Kaby Lake mobile",
    },
    "ICELAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x7D,
        "vfm": make_intel_vfm(6, 0x7D),
        "codename": "IceLake client",
    },
    "ICELAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x7E,
        "vfm": make_intel_vfm(6, 0x7E),
        "codename": "Ice Lake mobile",
    },
    "CANNONLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x66,
        "vfm": make_intel_vfm(6, 0x66),
        "codename": "Cannonlake mobile",
    },
    "SKYLAKE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x5E,
        "vfm": make_intel_vfm(6, 0x5E),
        "codename": "Skylake client",
    },
    "SKYLAKE_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x4E,
        "vfm": make_intel_vfm(6, 0x4E),
        "codename": "Skylake mobile",
    },
    "BROADWELL": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x3D,
        "vfm": make_intel_vfm(6, 0x3D),
        "codename": "Broadwell client",
    },
    "HASWELL": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x3C,
        "vfm": make_intel_vfm(6, 0x3C),
        "codename": "Haswell client",
    },
    "HASWELL_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x45,
        "vfm": make_intel_vfm(6, 0x45),
        "codename": "Haswell mobile",
    },
    "IVYBRIDGE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x3A,
        "vfm": make_intel_vfm(6, 0x3A),
        "codename": "IvyBridge client",
    },
    "SANDYBRIDGE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x2A,
        "vfm": make_intel_vfm(6, 0x2A),
        "codename": "SandyBridge client",
    },
    "WESTMERE": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x25,
        "vfm": make_intel_vfm(6, 0x25),
        "codename": "Westmere client",
    },
    "NEHALEM_G": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x1F,
        "vfm": make_intel_vfm(6, 0x1F),
        "codename": "Nehalem client with graphics (Auburndale, Havendale)",
    },
    "NEHALEM": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x1E,
        "vfm": make_intel_vfm(6, 0x1E),
        "codename": "Nehalem client",
    },
    "CORE2_MEROM": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x0F,
        "vfm": make_intel_vfm(6, 0x0F),
        "codename": "Intel Core 2",
    },
    # Atoms.
    "ATOM_TREMONT": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x96,
        "vfm": make_intel_vfm(6, 0x96),
        "codename": "Elkhart Lake",
    },
    "ATOM_TREMONT_L": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x9C,
        "vfm": make_intel_vfm(6, 0x9C),
        "codename": "Jasper Lake",
    },
    "ATOM_GOLDMONT": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x5C,
        "vfm": make_intel_vfm(6, 0x5C),
        "codename": "Apollo Lake",
    },
    "ATOM_GOLDMONT_PLUS": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x7A,
        "vfm": make_intel_vfm(6, 0x7A),
        "codename": "Gemini Lake",
    },
    "ATOM_AIRMONT": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x4C,
        "vfm": make_intel_vfm(6, 0x4C),
        "codename": "Cherry Trail, Braswell",
    },
    "ATOM_SILVERMONT": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x37,
        "vfm": make_intel_vfm(6, 0x37),
        "codename": "Bay Trail, Valleyview",
    },
    "ATOM_SILVERMONT_MID": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x4A,
        "vfm": make_intel_vfm(6, 0x4A),
        "codename": "Merriefield",
    },
    "ATOM_SILVERMONT_MID1": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x5A,
        "vfm": make_intel_vfm(6, 0x5A),
        "codename": "Moorefield",
    },
    "ATOM_SALTWELL": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x36,
        "vfm": make_intel_vfm(6, 0x36),
        "codename": "Cedarview",
    },
    "ATOM_SALTWELL_MID": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x27,
        "vfm": make_intel_vfm(6, 0x27),
        "codename": "Penwell",
    },
    "ATOM_SALTWELL_TABLET": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x35,
        "vfm": make_intel_vfm(6, 0x35),
        "codename": "Cloverview",
    },
    "ATOM_BONNELL_MID": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x26,
        "vfm": make_intel_vfm(6, 0x26),
        "codename": "Silverthorne, Lincroft",
    },
    "ATOM_BONNELL": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x1C,
        "vfm": make_intel_vfm(6, 0x1C),
        "codename": "Diamondville, Pineview",
    },
    # Atom microservers.
    "ATOM_CRESTMONT": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0xB6,
        "vfm": make_intel_vfm(6, 0xB6),
        "codename": "Grand Ridge, Logansville",
    },
    "ATOM_TREMONT_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x86,
        "vfm": make_intel_vfm(6, 0x86),
        "codename": "Snow Ridge, Jacobsville",
    },
    "ATOM_GOLDMONT_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x5F,
        "vfm": make_intel_vfm(6, 0x5F),
        "codename": "Denverton, Harrisonville",
    },
    "ATOM_SILVERMONT_D": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x4D,
        "vfm": make_intel_vfm(6, 0x4D),
        "codename": "Avaton, Rangely",
    },
    # Other.
    "ICELAKE_NNPI": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x9D,
        "vfm": make_intel_vfm(6, 0x9D),
        "codename": "Ice Lake Neural Network Processor",
    },
    "XEON_PHI_KNM": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x85,
        "vfm": make_intel_vfm(6, 0x85),
        "codename": "Knights Mill",
    },
    "XEON_PHI_KNL": {
        "vendor": X86_VENDOR_INTEL,
        "family": 6,
        "model": 0x57,
        "vfm": make_intel_vfm(6, 0x57),
        "codename": "Knights Landing", },
}

#
# Various handy CPU groups.
#
CPU_GROUPS: Final[dict[str, tuple[int, ...]]] = {
    "DMR": (MODELS["DIAMONDRAPIDS_X"]["vfm"],),
    "LUNARLAKE": (MODELS["LUNARLAKE_M"]["vfm"],),
    "GNR": (MODELS["GRANITERAPIDS_X"]["vfm"],
            MODELS["GRANITERAPIDS_D"]["vfm"]),
    "EMR": (MODELS["EMERALDRAPIDS_X"]["vfm"],),
    "ARROWLAKE": (MODELS["ARROWLAKE"]["vfm"],
                  MODELS["ARROWLAKE_H"]["vfm"],
                  MODELS["ARROWLAKE_U"]["vfm"],),
    "METEORLAKE": (MODELS["METEORLAKE"]["vfm"],
                   MODELS["METEORLAKE_L"]["vfm"],),
    "SPR": (MODELS["SAPPHIRERAPIDS_X"]["vfm"],),
    "RAPTORLAKE": (MODELS["RAPTORLAKE"]["vfm"],
                   MODELS["RAPTORLAKE_P"]["vfm"],
                   MODELS["RAPTORLAKE_S"]["vfm"],),
    "ALDERLAKE": (MODELS["ALDERLAKE"]["vfm"],
                  MODELS["ALDERLAKE_L"]["vfm"],
                  MODELS["ALDERLAKE_N"]["vfm"],),
    "ROCKETLAKE": (MODELS["ROCKETLAKE"]["vfm"],),
    "TIGERLAKE": (MODELS["TIGERLAKE"]["vfm"],
                  MODELS["TIGERLAKE_L"]["vfm"],),
    "LAKEFIELD": (MODELS["LAKEFIELD"]["vfm"],),
    "ICELAKE": (MODELS["ICELAKE"]["vfm"],
                MODELS["ICELAKE_L"]["vfm"],
                MODELS["ICELAKE_D"]["vfm"],
                MODELS["ICELAKE_X"]["vfm"],),
    "ICL_CLIENT": (MODELS["ICELAKE"]["vfm"],
                   MODELS["ICELAKE_L"]["vfm"],),
    "ICX": (MODELS["ICELAKE_D"]["vfm"],
            MODELS["ICELAKE_X"]["vfm"],),
    "COMETLAKE": (MODELS["COMETLAKE"]["vfm"],
                  MODELS["COMETLAKE_L"]["vfm"],),
    "KABYLAKE": (MODELS["KABYLAKE"]["vfm"],
                 MODELS["KABYLAKE_L"]["vfm"],),
    "CANNONLAKE": (MODELS["CANNONLAKE_L"]["vfm"],),
    "SKYLAKE": (MODELS["SKYLAKE"]["vfm"],
                MODELS["SKYLAKE_L"]["vfm"],
                MODELS["SKYLAKE_X"]["vfm"],),
    "SKL_CLIENT": (MODELS["SKYLAKE"]["vfm"],
                   MODELS["SKYLAKE_L"]["vfm"]),
    "SKX": (MODELS["SKYLAKE_X"]["vfm"],),
    "BROADWELL": (MODELS["BROADWELL"]["vfm"],
                  MODELS["BROADWELL_G"]["vfm"],
                  MODELS["BROADWELL_D"]["vfm"],
                  MODELS["BROADWELL_X"]["vfm"],),
    "HASWELL": (MODELS["HASWELL"]["vfm"],
                MODELS["HASWELL_L"]["vfm"],
                MODELS["HASWELL_G"]["vfm"],
                MODELS["HASWELL_X"]["vfm"],),
    "IVYBRIDGE": (MODELS["IVYBRIDGE"]["vfm"],
                   MODELS["IVYBRIDGE_X"]["vfm"],),
    "SANDYBRIDGE": (MODELS["SANDYBRIDGE"]["vfm"],
                    MODELS["SANDYBRIDGE_X"]["vfm"],),
    "WESTMERE": (MODELS["WESTMERE"]["vfm"],
                 MODELS["WESTMERE_EP"]["vfm"],
                 MODELS["WESTMERE_EX"]["vfm"],),
    "NEHALEM": (MODELS["NEHALEM"]["vfm"],
                MODELS["NEHALEM_G"]["vfm"],
                MODELS["NEHALEM_EP"]["vfm"],
                MODELS["NEHALEM_EX"]["vfm"]),
    "DARKMONT": (MODELS["ATOM_DARKMONT_X"]["vfm"],),
    "CRESTMONT": (MODELS["ATOM_CRESTMONT"]["vfm"],
                  MODELS["ATOM_CRESTMONT_X"]["vfm"]),
    "TREMONT": (MODELS["ATOM_TREMONT"]["vfm"],
                MODELS["ATOM_TREMONT_L"]["vfm"],
                MODELS["ATOM_TREMONT_D"]["vfm"],),
    "GOLDMONT": (MODELS["ATOM_GOLDMONT"]["vfm"],
                 MODELS["ATOM_GOLDMONT_D"]["vfm"],
                 MODELS["ATOM_GOLDMONT_PLUS"]["vfm"],),
    "AIRMONT": (MODELS["ATOM_AIRMONT"]["vfm"],),
    "SILVERMONT": (MODELS["ATOM_SILVERMONT"]["vfm"],
                   MODELS["ATOM_SILVERMONT_MID"]["vfm"],
                   MODELS["ATOM_SILVERMONT_MID1"]["vfm"],
                   MODELS["ATOM_SILVERMONT_D"]["vfm"],),
    "PHI": (MODELS["XEON_PHI_KNL"]["vfm"],
            MODELS["XEON_PHI_KNM"]["vfm"],),
}

# CPU models that have dies but they are not enumerated via the CPUID instruction.
MODELS_WITH_HIDDEN_DIES: Final[tuple[int, ...]] = CPU_GROUPS["GNR"] + \
                                                  CPU_GROUPS["DARKMONT"] + \
                                                  CPU_GROUPS["CRESTMONT"]
