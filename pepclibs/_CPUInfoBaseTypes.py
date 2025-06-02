# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide types for '_CPUInfoBase' and 'CPUInfo' classes.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import TypedDict, Literal

ScopeNameType = Literal["CPU", "core", "module", "die", "node", "package"]

class CPUInfoTypedDict(TypedDict, total=False):
    """
    Type for the CPU information dictionary ('CPUInfo.info').

    Attributes:
        arch: The CPU architecture (e.g., "x86_64").
        vendor: The CPU vendor (e.g., "GenuineIntel").
        packages: The number of CPU packages.
        family: The CPU family number.
        model: The CPU model number.
        modelname: The full name of the CPU model.
        flags: A dictionary mapping CPU numbers to their flags.
        hybrid: Whether the CPU is a hybrid architecture (e.g., Intel's P-core/E-core).
        vfm: The vendor-family-model identifier for the CPU.
    """

    arch: str
    vendor: str
    family: int
    model: int
    modelname: str
    flags: dict[int, set[str]]
    hybrid: bool
    vfm: int

CPUInfoKeyType = Literal["arch", "vendor", "family", "model", "modelname", "flags", "hybrid", "vfm"]

class HybridCPUTypedDict(TypedDict, total=False):
    """
    Type for the hybrid CPUs dictionary.

    Attributes:
        pcore: List of P-core CPU numbers.
        ecore: List of E-core CPU numbers.
    """

    pcore: list[int]
    ecore: list[int]

HybridCPUKeyType = Literal["pcore", "ecore"]

class HybridCPUKeyInfoType(TypedDict, total=False):
    """
    Type for the hybrid CPUs key information dictionary.

    Attributes:
        name: The name of the hybrid CPU type (e.g., E-core, P-core).
        title: Longer title for the hybrid CPU type (e.g., "Efficient core", "Performance core").
    """

    name: str
    title: str
