# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'Uncore' module. This file is separated to allow importing constants
without loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.PropsTypes import PropertyTypedDict

# Special values for writable uncore frequency properties.
_SPECIAL_UNCORE_FREQ_VALS = {"min", "max", "mdl"}

# This properties dictionary defines the CPU properties supported by this module.
#
# Although this dictionary is user-visible and may be accessed directly, it is not recommended
# because it is incomplete. Prefer using 'Uncore.props' instead.
#
# Some properties have their scope name set to 'None' because the scope may vary depending on the
# platform. In such cases, the scope can be determined using 'Uncore.get_sname()'.
PROPS: Final[dict[str, PropertyTypedDict]] = {
    "min_freq": {
        "name": "Min. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "max_freq": {
        "name": "Max. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "min_freq_limit": {
        "name": "Min. supported uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "max_freq_limit": {
        "name": "Max. supported uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "elc_low_zone_min_freq": {
        "name": "ELC low zone min. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "elc_mid_zone_min_freq": {
        "name": "ELC middle zone min. uncore frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "die",
        # Not a typo, not available via the sysfs.
        "mnames": ("tpmi",),
        "writable": True,
        "special_vals": _SPECIAL_UNCORE_FREQ_VALS,
    },
    "elc_low_threshold": {
        "name": "ELC low threshold",
        "unit": "%",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
    },
    "elc_high_threshold": {
        "name": "ELC high threshold",
        "unit": "%",
        "type": "int",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
    },
    "elc_high_threshold_status": {
        "name": "ELC high threshold status",
        "type": "bool",
        "sname": "die",
        "mnames": ("sysfs", "tpmi"),
        "writable": True,
    },
}
