# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'CStates' module. This file is separated to allow importing constants
without loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

# pylint: disable=unused-import
from pepclibs.CPUIdle import ReqCStateInfoTypedDict, ReqCStateInfoValuesType, ReqCStateInfoKeysType
from pepclibs._PropsClassBase import ErrorUsePerCPU, ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.CPUInfoTypes import AbsNumsType
    from pepclibs.PropsTypes import PropertyTypedDict

# This dictionary describes the C-state properties this module supports. Many of the properties are
# just features controlled by an MSR, such as "c1e_autopromote" from 'PowerCtl.FEATURES'.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'CStates' objects. Use the full dictionary via
# 'CStates.props'.
#
# Some properties have scope name set to 'None' because the scope may be different for different
# systems. In such cases, the scope can be obtained via 'CStates.get_sname()'.
PROPS: Final[dict[str, PropertyTypedDict]] = {
    "pkg_cstate_limit": {
        "name": "Package C-state limit",
        "type": "str",
        "sname": None,
        "mnames": ("msr",),
        "writable": True,
        "subprops": ("pkg_cstate_limit_lock", "pkg_cstate_limits"),
    },
    "pkg_cstate_limit_lock": {
        "name": "Package C-state limit lock",
        "type": "bool",
        "sname": None,
        "mnames": ("msr",),
        "writable": False,
    },
    "pkg_cstate_limits": {
        "name": "Available package C-state limits",
        "type": "list[str]",
        # Conceptually this is per-package, but in practice it is global on all current platforms.
        "sname": "global",
        "mnames": ("doc",),
        "writable": False,
    },
    "c1_demotion": {
        "name": "C1 demotion",
        "type": "bool",
        "sname": None,
        "mnames": ("msr",),
        "writable": True,
    },
    "c1_undemotion": {
        "name": "C1 undemotion",
        "type": "bool",
        "sname": None,
        "mnames": ("msr",),
        "writable": True,
    },
    "c1e_autopromote": {
        "name": "C1E autopromote",
        "type": "bool",
        "sname": None,
        "mnames": ("msr",),
        "writable": True,
    },
    "cstate_prewake": {
        "name": "C-state prewake",
        "type": "bool",
        "sname": None,
        "mnames": ("msr",),
        "writable": True,
    },
    "idle_driver": {
        "name": "Idle driver",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "governor": {
        "name": "Idle governor",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "governors": {
        "name": "Available idle governors",
        "type": "list[str]",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
}
