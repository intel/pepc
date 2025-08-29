# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'PMQoS' module. This file is separated to allow importing constants without
loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.PropsTypes import PropertyTypedDict

# This dictionary describes the CPU properties this module supports.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'PMQoS' objects. Use the full dictionary via
# 'PMQoS.props'.
#
# Some properties have scope name set to 'None' because the scope may be different for different
# systems. In such cases, the scope can be obtained via 'PMQoS.get_sname()'.
PROPS: Final[dict[str, PropertyTypedDict]] = {
    "latency_limit": {
        "name": "Linux per-CPU PM QoS latency limit",
        "unit": "s",
        "type": "float",
        "sname": "CPU",
        "mnames": ("sysfs",),
        "writable": True,
    },
    # In general, the global latency limit is writable, but the limit is active only as long as the
    # process keeps the character device open.
    "global_latency_limit": {
        "name": "Linux global PM QoS latency limit",
        "unit": "s",
        "type": "float",
        "sname": "global",
        "mnames": ("cdev",),
        "writable": False,
    },
}
