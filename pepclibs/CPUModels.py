# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide information about CPU models and their identification.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorBadFormat

if typing.TYPE_CHECKING:
    from typing import TypedDict, Final

    class CPUModelTypedDict(TypedDict):
        """
        CPU model information.

        Attributes:
            vendor: The vendor of the CPU.
            vendor_name: Name of the CPU vendor.
            family: The family of the CPU.
            model: The model number of the CPU.
            vfm: The VFM (Vendor, Family, Model) code of the CPU.
            codename: The codename of the CPU.
        """

        vendor: int
        vendor_name: str
        family: int
        model: int
        vfm: int
        codename: str

VENDOR_INTEL: Final[int] = 0
VENDOR_AMD: Final[int] = 2

_VENDOR_NAMES: Final[dict[str, int]] = {
    "GenuineIntel": VENDOR_INTEL,
    "AuthenticAMD": VENDOR_AMD,
}

def _make_intel_vfm(family: int, model: int) -> int:
    """
    Create and return the VFM (Vendor, Family, Model) code for an Intel CPU.

    Args:
        family: The family of the Intel CPU.
        model: The model number of the Intel CPU.

    Returns:
        The VFM code of the Intel CPU.
    """

    return (VENDOR_INTEL << 16) | (family << 8) | model

MODELS: Final[dict[str, CPUModelTypedDict]] = {
    # Xeons.
    "DIAMONDRAPIDS_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 19,
        "model": 0x1,
        "vfm": _make_intel_vfm(19, 0x1),
        "codename": "Diamond Rapids Xeon",
    },
    "ATOM_DARKMONT_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xDD,
        "vfm": _make_intel_vfm(6, 0xDD),
        "codename": "Clearwater Forest Xeon",
    },
    "ATOM_CRESTMONT_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xAF,
        "vfm": _make_intel_vfm(6, 0xAF),
        "codename": "Sierra Forest Xeon",
    },
    "GRANITERAPIDS_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xAD,
        "vfm": _make_intel_vfm(6, 0xAD),
        "codename": "Granite Rapids Xeon",
    },
    "GRANITERAPIDS_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xAE,
        "vfm": _make_intel_vfm(6, 0xAE),
        "codename": "Granite Rapids Xeon D",
    },
    "EMERALDRAPIDS_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xCF,
        "vfm": _make_intel_vfm(6, 0xCF),
        "codename": "Emerald Rapids Xeon",
    },
    "SAPPHIRERAPIDS_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x8F,
        "vfm": _make_intel_vfm(6, 0x8F),
        "codename": "Sapphire Rapids Xeon",
    },
    "ICELAKE_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x6A,
        "vfm": _make_intel_vfm(6, 0x6A),
        "codename": "Ice Lake Xeon",
    },
    "ICELAKE_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x6C,
        "vfm": _make_intel_vfm(6, 0x6C),
        "codename": "Ice Lake Xeon D",
    },
    "SKYLAKE_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x55,
        "vfm": _make_intel_vfm(6, 0x55),
        "codename": "Skylake, Cascade Lake, or Cooper Lake Xeon",
    },
    "BROADWELL_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x4F,
        "vfm": _make_intel_vfm(6, 0x4F),
        "codename": "Broadwell Xeon",
    },
    "BROADWELL_G": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x47,
        "vfm": _make_intel_vfm(6, 0x47),
        "codename": "Broadwell Xeon with Graphics",
    },
    "BROADWELL_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x56,
        "vfm": _make_intel_vfm(6, 0x56),
        "codename": "Broadwell Xeon-D",
    },
    "HASWELL_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x3F,
        "vfm": _make_intel_vfm(6, 0x3F),
        "codename": "Haswell Xeon",
    },
    "HASWELL_G": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x46,
        "vfm": _make_intel_vfm(6, 0x46),
        "codename": "Haswell Xeon with Graphics",
    },
    "IVYBRIDGE_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x3E,
        "vfm": _make_intel_vfm(6, 0x3E),
        "codename": "Ivy Town Xeon",
    },
    "SANDYBRIDGE_X": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x2D,
        "vfm": _make_intel_vfm(6, 0x2D),
        "codename": "SandyBridge Xeon",
    },
    "WESTMERE_EP": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x2C,
        "vfm": _make_intel_vfm(6, 0x2C),
        "codename": "Westmere 2S Xeon",
    },
    "WESTMERE_EX": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x2F,
        "vfm": _make_intel_vfm(6, 0x2F),
        "codename": "Westmere 4S Xeon",
    },
    "NEHALEM_EP": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x1A,
        "vfm": _make_intel_vfm(6, 0x1A),
        "codename": "Nehalem 2S Xeon",
    },
    "NEHALEM_EX": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x2E,
        "vfm": _make_intel_vfm(6, 0x2E),
        "codename": "Nehalem 4S Xeon",
    },
    # Clients.
    "PANTHERLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xCC,
        "vfm": _make_intel_vfm(6, 0xCC),
        "codename": "Panther Lake mobile",
    },
    "LUNARLAKE_M": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xBD,
        "vfm": _make_intel_vfm(6, 0xBD),
        "codename": "Lunar Lake mobile",
    },
    "ARROWLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xC5,
        "vfm": _make_intel_vfm(6, 0xC5),
        "codename": "Arrow Lake client",
    },
    "ARROWLAKE_H": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xC6,
        "vfm": _make_intel_vfm(6, 0xC6),
        "codename": "Arrow Lake mobile",
    },
    "ARROWLAKE_U": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xB5,
        "vfm": _make_intel_vfm(6, 0xB5),
        "codename": "Arrow Lake mobile",
    },
    "METEORLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xAC,
        "vfm": _make_intel_vfm(6, 0xAC),
        "codename": "Meteor Lake client",
    },
    "METEORLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xAA,
        "vfm": _make_intel_vfm(6, 0xAA),
        "codename": "Meteor Lake mobile",
    },
    "RAPTORLAKE_P": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xBA,
        "vfm": _make_intel_vfm(6, 0xBA),
        "codename": "Raptor Lake mobile",
    },
    "RAPTORLAKE_S": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xBF,
        "vfm": _make_intel_vfm(6, 0xBF),
        "codename": "Raptor Lake client",
    },
    "RAPTORLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xB7,
        "vfm": _make_intel_vfm(6, 0xB7),
        "codename": "Raptor Lake client",
    },
    "ALDERLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x97,
        "vfm": _make_intel_vfm(6, 0x97),
        "codename": "Alder Lake client",
    },
    "ALDERLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x9A,
        "vfm": _make_intel_vfm(6, 0x9A),
        "codename": "Alder Lake mobile",
    },
    "ALDERLAKE_N": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xBE,
        "vfm": _make_intel_vfm(6, 0xBE),
        "codename": "Alder Lake mobile",
    },
    "ROCKETLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xA7,
        "vfm": _make_intel_vfm(6, 0xA7),
        "codename": "Rocket Lake client",
    },
    "TIGERLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x8D,
        "vfm": _make_intel_vfm(6, 0x8D),
        "codename": "Tiger Lake client",
    },
    "TIGERLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x8C,
        "vfm": _make_intel_vfm(6, 0x8C),
        "codename": "Tiger Lake mobile",
    },
    "LAKEFIELD": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x8A,
        "vfm": _make_intel_vfm(6, 0x8A),
        "codename": "Lakefield client",
    },
    "COMETLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xA5,
        "vfm": _make_intel_vfm(6, 0xA5),
        "codename": "Comet Lake client",
    },
    "COMETLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xA6,
        "vfm": _make_intel_vfm(6, 0xA6),
        "codename": "Comet Lake mobile",
    },
    "KABYLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x9E,
        "vfm": _make_intel_vfm(6, 0x9E),
        "codename": "Kaby Lake client",
    },
    "KABYLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x8E,
        "vfm": _make_intel_vfm(6, 0x8E),
        "codename": "Kaby Lake mobile",
    },
    "ICELAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x7D,
        "vfm": _make_intel_vfm(6, 0x7D),
        "codename": "IceLake client",
    },
    "ICELAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x7E,
        "vfm": _make_intel_vfm(6, 0x7E),
        "codename": "Ice Lake mobile",
    },
    "CANNONLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x66,
        "vfm": _make_intel_vfm(6, 0x66),
        "codename": "Cannonlake mobile",
    },
    "SKYLAKE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x5E,
        "vfm": _make_intel_vfm(6, 0x5E),
        "codename": "Skylake client",
    },
    "SKYLAKE_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x4E,
        "vfm": _make_intel_vfm(6, 0x4E),
        "codename": "Skylake mobile",
    },
    "BROADWELL": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x3D,
        "vfm": _make_intel_vfm(6, 0x3D),
        "codename": "Broadwell client",
    },
    "HASWELL": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x3C,
        "vfm": _make_intel_vfm(6, 0x3C),
        "codename": "Haswell client",
    },
    "HASWELL_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x45,
        "vfm": _make_intel_vfm(6, 0x45),
        "codename": "Haswell mobile",
    },
    "IVYBRIDGE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x3A,
        "vfm": _make_intel_vfm(6, 0x3A),
        "codename": "IvyBridge client",
    },
    "SANDYBRIDGE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x2A,
        "vfm": _make_intel_vfm(6, 0x2A),
        "codename": "SandyBridge client",
    },
    "WESTMERE": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x25,
        "vfm": _make_intel_vfm(6, 0x25),
        "codename": "Westmere client",
    },
    "NEHALEM_G": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x1F,
        "vfm": _make_intel_vfm(6, 0x1F),
        "codename": "Nehalem client with graphics (Auburndale, Havendale)",
    },
    "NEHALEM": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x1E,
        "vfm": _make_intel_vfm(6, 0x1E),
        "codename": "Nehalem client",
    },
    "CORE2_MEROM": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x0F,
        "vfm": _make_intel_vfm(6, 0x0F),
        "codename": "Intel Core 2",
    },
    # Atoms.
    "ATOM_TREMONT": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x96,
        "vfm": _make_intel_vfm(6, 0x96),
        "codename": "Elkhart Lake",
    },
    "ATOM_TREMONT_L": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x9C,
        "vfm": _make_intel_vfm(6, 0x9C),
        "codename": "Jasper Lake",
    },
    "ATOM_GOLDMONT": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x5C,
        "vfm": _make_intel_vfm(6, 0x5C),
        "codename": "Apollo Lake",
    },
    "ATOM_GOLDMONT_PLUS": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x7A,
        "vfm": _make_intel_vfm(6, 0x7A),
        "codename": "Gemini Lake",
    },
    "ATOM_AIRMONT": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x4C,
        "vfm": _make_intel_vfm(6, 0x4C),
        "codename": "Cherry Trail, Braswell",
    },
    "ATOM_SILVERMONT": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x37,
        "vfm": _make_intel_vfm(6, 0x37),
        "codename": "Bay Trail, Valleyview",
    },
    "ATOM_SILVERMONT_MID": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x4A,
        "vfm": _make_intel_vfm(6, 0x4A),
        "codename": "Merriefield",
    },
    "ATOM_SILVERMONT_MID1": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x5A,
        "vfm": _make_intel_vfm(6, 0x5A),
        "codename": "Moorefield",
    },
    "ATOM_SALTWELL": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x36,
        "vfm": _make_intel_vfm(6, 0x36),
        "codename": "Cedarview",
    },
    "ATOM_SALTWELL_MID": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x27,
        "vfm": _make_intel_vfm(6, 0x27),
        "codename": "Penwell",
    },
    "ATOM_SALTWELL_TABLET": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x35,
        "vfm": _make_intel_vfm(6, 0x35),
        "codename": "Cloverview",
    },
    "ATOM_BONNELL_MID": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x26,
        "vfm": _make_intel_vfm(6, 0x26),
        "codename": "Silverthorne, Lincroft",
    },
    "ATOM_BONNELL": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x1C,
        "vfm": _make_intel_vfm(6, 0x1C),
        "codename": "Diamondville, Pineview",
    },
    # Atom microservers.
    "ATOM_CRESTMONT": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0xB6,
        "vfm": _make_intel_vfm(6, 0xB6),
        "codename": "Grand Ridge, Logansville",
    },
    "ATOM_TREMONT_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x86,
        "vfm": _make_intel_vfm(6, 0x86),
        "codename": "Snow Ridge, Jacobsville",
    },
    "ATOM_GOLDMONT_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x5F,
        "vfm": _make_intel_vfm(6, 0x5F),
        "codename": "Denverton, Harrisonville",
    },
    "ATOM_SILVERMONT_D": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x4D,
        "vfm": _make_intel_vfm(6, 0x4D),
        "codename": "Avaton, Rangely",
    },
    # Other.
    "ICELAKE_NNPI": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x9D,
        "vfm": _make_intel_vfm(6, 0x9D),
        "codename": "Ice Lake Neural Network Processor",
    },
    "XEON_PHI_KNM": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x85,
        "vfm": _make_intel_vfm(6, 0x85),
        "codename": "Knights Mill",
    },
    "XEON_PHI_KNL": {
        "vendor": VENDOR_INTEL,
        "vendor_name": "GenuineIntel",
        "family": 6,
        "model": 0x57,
        "vfm": _make_intel_vfm(6, 0x57),
        "codename": "Knights Landing", },
}

#
# Various handy CPU groups.
#
CPU_GROUPS: Final[dict[str, tuple[int, ...]]] = {
    "DMR": (MODELS["DIAMONDRAPIDS_X"]["vfm"],),
    "PANTHERLAKE": (MODELS["PANTHERLAKE_L"]["vfm"],),
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

#
# CPU models that have dies but they are not enumerated via the CPUID instruction.
#
MODELS_WITH_HIDDEN_DIES: Final[tuple[int, ...]] = CPU_GROUPS["GNR"] + \
                                                  CPU_GROUPS["DARKMONT"] + \
                                                  CPU_GROUPS["CRESTMONT"]

def vendor_name_to_id(vendor_name: str) -> int:
    """
    Convert the CPU vendor name to its ID.

    Args:
        vendor_name: The CPU vendor name (e.g., "GenuineIntel").

    Returns:
        The CPU vendor ID.

    Raises:
        ErrorNotSupported: If the CPU vendor is not supported.
    """

    vendor_id = _VENDOR_NAMES.get(vendor_name, -1)
    if vendor_id == -1:
        supported = ", ".join(_VENDOR_NAMES.keys())
        raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor_name}', supported vendors are:\n"
                                f"{supported}")

    return vendor_id

def vendor_id_to_name(vendor_id: int) -> str:
    """
    Convert the CPU vendor ID to its name.

    Args:
        vendor_id: The CPU vendor ID.

    Returns:
        The CPU vendor name.

    Raises:
        ErrorNotSupported: If the CPU vendor ID is not supported.
    """

    for vename, vid in _VENDOR_NAMES.items():
        if vid == vendor_id:
            return vename

    supported = ", ".join(str(vid) for vid in _VENDOR_NAMES.values())
    raise ErrorNotSupported(f"Unsupported CPU vendor ID '{vendor_id}', supported vendor IDs are:\n"
                            f"{supported}")

def is_intel(vendor: int | str) -> bool:
    """
    Check if a CPU vendor ID or name corresponds to Intel.

    Args:
        vendor: The CPU vendor ID or name.
    Returns:
        True if the vendor is Intel, False otherwise.
    """

    if isinstance(vendor, str):
        vendor_id = vendor_name_to_id(vendor)
    else:
        vendor_id = vendor

    return vendor_id == VENDOR_INTEL

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
        vendor_id = vendor_name_to_id(vendor)
    else:
        vendor_id = vendor

    return (vendor_id << 16) | (family << 8) | model

def make_intel_vfm(family: int, model: int) -> int:
    """
    Create and return the VFM (Vendor, Family, Model) code for an Intel CPU.

    Args:
        family: The family of the Intel CPU.
        model: The model number of the Intel CPU.

    Returns:
        The VFM code of the Intel CPU.
    """

    return _make_intel_vfm(family, model)

def split_vfm(vfm: int) -> tuple[int, int, int]:
    """
    Split the VFM (Vendor, Family, Model) code into its components.

    Args:
        vfm: The VFM code to split.

    Returns:
        A tuple of (vendor, family, model).
    """

    vendor = (vfm >> 16) & 0xFFFF
    family = (vfm >> 8) & 0xFF
    model = vfm & 0xFF

    return (vendor, family, model)

def get_model_dict_by_vfm(vfm: int) -> CPUModelTypedDict:
    """
    Get the CPU model dictionary by its VFM code.

    Args:
        vfm: The VFM code of the CPU.

    Returns:
        The CPU model dictionary.
    """

    for mdict in MODELS.values():
        if mdict["vfm"] == vfm:
            return mdict

    raise ErrorNotSupported(f"Unsupported CPU VFM '{vfm:#x}'")

def parse_user_vfm(user_vfm: str) -> CPUModelTypedDict:
    """
    Parse a user-provided CPU model specification and return the corresponding CPU model dictionary.

    Args:
        user_vfm: The user-provided CPU model specification. It can be either and integer VFM code
                  or a string in the format '[<Vendor>]:<Family>:<Model>'.

    Returns:
        The CPU model dictionary.

    Raises:
        ErrorBadFormat: If the user-provided string is not in the correct format.
        ErrorNotSupported: If the specified CPU model is not supported.
    """

    if Trivial.is_int(user_vfm):
        # Assume this is already a VFM integer.
        return get_model_dict_by_vfm(int(user_vfm))

    # Assume that this is a CPU model in '[<Vendor>]:<Family>:<Model>' format.
    split = user_vfm.split(":")
    if len(split) > 3 or len(split) < 2:
        raise ErrorBadFormat(f"Bad CPU model '{user_vfm}': should be in the form of "
                             f"'[<Vendor>]:<Family>:<Model>'.")

    if len(split) == 3:
        # Vendor is specified. It can be either name or ID.
        if Trivial.is_int(split[0]):
            vendor = int(split[0])
            vendor_name = vendor_id_to_name(vendor)
        else:
            vendor_name = split[0]
            vendor = vendor_name_to_id(vendor_name)

        family_str = split[1]
        model_str = split[2]
    else:
        vendor_name = "GenuineIntel"
        vendor = VENDOR_INTEL

        family_str = split[0]
        model_str = split[1]

    family = Trivial.str_to_int(family_str, what="CPU family")
    model = Trivial.str_to_int(model_str, what="CPU model")

    vfm = make_vfm(vendor, family, model)

    return get_model_dict_by_vfm(vfm)
