# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'CPUInfo' module. This file is separated to allow importing constants
without loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from pepclibs.CPUInfoTypes import ScopeNameType, HybridCPUKeyType, HybridCPUKeyInfoType

# Must be in the order from the smallest to the largest scope.
SCOPE_NAMES: tuple[ScopeNameType, ...] = ("CPU", "core", "module", "die", "node", "package")

# 'NA' is used as the CPU/core/module number for non-compute dies, which lack CPUs, cores, or
# modules.
NA = 0xFFFFFFFF
# A helpful CPU/core/etc (all scopes) number that is guaranteed to never be used.
INVALID = NA - 1

# The hybrid CPU information dictionary.
HYBRID_TYPE_INFO: dict[HybridCPUKeyType, HybridCPUKeyInfoType] = {
        "pcore":   {"name": "P-core", "title": "Performance core"},
        "ecore":   {"name": "E-core", "title": "Efficiency core"},
        "lpecore": {"name": "LPE-core", "title": "Low Power Efficiency core"},
}
