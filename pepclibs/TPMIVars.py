# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Global variables for the 'TPMI' module. This file is separated to allow importing constants without
loading the entire module, improving import efficiency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUModels

if typing.TYPE_CHECKING:
    from typing import Final

# The default VFM to use when the user does not provide one.
DEFAULT_VFM: Final[int] = CPUModels.MODELS["GRANITERAPIDS_X"]["vfm"]
DEFAULT_PLATFORM_NAME: Final[str] = CPUModels.MODELS["GRANITERAPIDS_X"]["codename"]

# UFS header register names. These registers are per-instance rather than per-cluster. All other
# registers are "control registers" and are per-cluster.
UFS_HEADER_REGNAMES: Final[set[str]] = {
    "UFS_HEADER",
    "UFS_FABRIC_CLUSTER_OFFSET",
}
