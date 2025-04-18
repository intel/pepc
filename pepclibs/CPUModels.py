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

from typing import TypedDict

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

X86_VENDOR_INTEL = 0

def make_vfm(vendor: int, family: int, model: int) -> int:
    """
    Create and return the VFM (Vendor, Family, Model) code for an Intel CPU.

    Args:
        vendor: The vendor of the CPU.
        family: The family of the CPU.
        model: The model number of the CPU.

    Returns:
        The VFM code of the CPU.
    """

    return (vendor << 16) | (family << 8) | model

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

MODELS: dict[str, CPUModelTypedDict] = {
    # Xeons.
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
# Various handy combinations of CPU models.
#
MODEL_GROUPS: dict[str, tuple[int, ...]] = {
    "LUNARLAKE": (MODELS["LUNARLAKE_M"]["model"],),
    "GNR": (MODELS["GRANITERAPIDS_X"]["model"],
            MODELS["GRANITERAPIDS_D"]["model"]),
    "EMR": (MODELS["EMERALDRAPIDS_X"]["model"],),
    "METEORLAKE": (MODELS["METEORLAKE"]["model"],
                   MODELS["METEORLAKE_L"]["model"],),
    "SPR": (MODELS["SAPPHIRERAPIDS_X"]["model"],),
    "RAPTORLAKE": (MODELS["RAPTORLAKE"]["model"],
                   MODELS["RAPTORLAKE_P"]["model"],
                   MODELS["RAPTORLAKE_S"]["model"],),
    "ALDERLAKE": (MODELS["ALDERLAKE"]["model"],
                  MODELS["ALDERLAKE_L"]["model"],
                  MODELS["ALDERLAKE_N"]["model"],),
    "ROCKETLAKE": (MODELS["ROCKETLAKE"]["model"],),
    "TIGERLAKE": (MODELS["TIGERLAKE"]["model"],
                  MODELS["TIGERLAKE_L"]["model"],),
    "LAKEFIELD": (MODELS["LAKEFIELD"]["model"],),
    "ICELAKE": (MODELS["ICELAKE"]["model"],
                MODELS["ICELAKE_L"]["model"],
                MODELS["ICELAKE_D"]["model"],
                MODELS["ICELAKE_X"]["model"],),
    "ICL_CLIENT": (MODELS["ICELAKE"]["model"],
                   MODELS["ICELAKE_L"]["model"],),
    "ICX": (MODELS["ICELAKE_D"]["model"],
            MODELS["ICELAKE_X"]["model"],),
    "COMETLAKE": (MODELS["COMETLAKE"]["model"],
                  MODELS["COMETLAKE_L"]["model"],),
    "KABYLAKE": (MODELS["KABYLAKE"]["model"],
                 MODELS["KABYLAKE_L"]["model"],),
    "CANNONLAKE": (MODELS["CANNONLAKE_L"]["model"],),
    "SKYLAKE": (MODELS["SKYLAKE"]["model"],
                MODELS["SKYLAKE_L"]["model"],
                MODELS["SKYLAKE_X"]["model"],),
    "SKL_CLIENT": (MODELS["SKYLAKE"]["model"],
                   MODELS["SKYLAKE_L"]["model"]),
    "SKX": (MODELS["SKYLAKE_X"]["model"],),
    "BROADWELL": (MODELS["BROADWELL"]["model"],
                  MODELS["BROADWELL_G"]["model"],
                  MODELS["BROADWELL_D"]["model"],
                  MODELS["BROADWELL_X"]["model"],),
    "HASWELL": (MODELS["HASWELL"]["model"],
                   MODELS["HASWELL_L"]["model"],
                   MODELS["HASWELL_G"]["model"],
                   MODELS["HASWELL_X"]["model"],),
    "IVYBRIDGE": (MODELS["IVYBRIDGE"]["model"],
                   MODELS["IVYBRIDGE_X"]["model"],),
    "SANDYBRIDGE":(MODELS["SANDYBRIDGE"]["model"],
                   MODELS["SANDYBRIDGE_X"]["model"],),
    "WESTMERE": (MODELS["WESTMERE"]["model"],
                   MODELS["WESTMERE_EP"]["model"],
                   MODELS["WESTMERE_EX"]["model"],),
    "NEHALEM": (MODELS["NEHALEM"]["model"],
                MODELS["NEHALEM_G"]["model"],
                MODELS["NEHALEM_EP"]["model"],
                MODELS["NEHALEM_EX"]["model"]),
    "DARKMONT": (MODELS["ATOM_DARKMONT_X"]["model"],),
    "CRESTMONT": (MODELS["ATOM_CRESTMONT"]["model"],
                  MODELS["ATOM_CRESTMONT_X"]["model"]),
    "TREMONT": (MODELS["ATOM_TREMONT"]["model"],
                MODELS["ATOM_TREMONT_L"]["model"],
                MODELS["ATOM_TREMONT_D"]["model"],),
    "GOLDMONT": (MODELS["ATOM_GOLDMONT"]["model"],
                 MODELS["ATOM_GOLDMONT_D"]["model"],
                 MODELS["ATOM_GOLDMONT_PLUS"]["model"],),
    "AIRMONT": (MODELS["ATOM_AIRMONT"]["model"],),
    "SILVERMONT": (MODELS["ATOM_SILVERMONT"]["model"],
                   MODELS["ATOM_SILVERMONT_MID"]["model"],
                   MODELS["ATOM_SILVERMONT_MID1"]["model"],
                   MODELS["ATOM_SILVERMONT_D"]["model"],),
    "PHI": (MODELS["XEON_PHI_KNL"]["model"],
            MODELS["XEON_PHI_KNM"]["model"],),
}
