# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'PStates' module. This file is separated to allow importing constants
without loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.PropsTypes import PropertyTypedDict

# Special values for writable CPU frequency properties.
_SPECIAL_FREQ_VALS = {"min", "max", "base", "hfm", "P1", "Pm"}

# This properties dictionary defines the CPU properties supported by this module.
#
# Although this dictionary is user-visible and may be accessed directly, it is not recommended
# because it is incomplete. Prefer using 'PStates.props' instead.
#
# Some properties have their scope name set to 'None' because the scope may vary depending on the
# platform. In such cases, the scope can be determined using 'PStates.get_sname()'.
PROPS: Final[dict[str, PropertyTypedDict]] = {
    "turbo": {
        "name": "Turbo",
        "type": "bool",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "min_freq": {
        "name": "Min. CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
        "special_vals": _SPECIAL_FREQ_VALS,
    },
    "max_freq": {
        "name": "Max. CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
        "special_vals": _SPECIAL_FREQ_VALS,
    },
    "min_freq_limit": {
        "name": "Min. supported CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr", "cppc"),
        "writable": False,
    },
    "max_freq_limit": {
        "name": "Max. supported CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr", "cppc"),
        "writable": False,
    },
    "base_freq": {
        "name": "Base CPU frequency",
        "unit": "Hz",
        "type": "int",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": False,
    },
    "bus_clock": {
        "name": "Bus clock speed",
        "unit": "Hz",
        "type": "int",
        "sname": None,
        "mnames": ("msr", "doc"),
        "writable": False,
    },
    "frequencies": {
        "name": "Acceptable CPU frequencies",
        "unit": "Hz",
        "type": "list[int]",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "hwp": {
        "name": "Hardware power management",
        "type": "bool",
        "sname": "global",
        "mnames": ("msr",),
        "writable": False,
    },
    "epp": {
        "name": "EPP",
        "type": "str",
        "sname": "CPU",
        "mnames": ("sysfs", "msr"),
        "writable": True,
    },
    "epb": {
        "name": "EPB",
        "type": "int",
        "sname": None,
        "mnames": ("sysfs", "msr"),
        "writable": True,
    },
    "driver": {
        "name": "CPU frequency driver",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
    "intel_pstate_mode": {
        "name": "Mode of 'intel_pstate' driver",
        "type": "str",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "governor": {
        "name": "CPU frequency governor",
        "type": "str",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": True,
    },
    "governors": {
        "name": "Available CPU frequency governors",
        "type": "list[str]",
        "sname": "global",
        "mnames": ("sysfs",),
        "writable": False,
    },
}
