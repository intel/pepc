# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Types for users of property modules (e.g., 'PStates') for property module users.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import Union

# pylint: disable=wildcard-import,unused-wildcard-import
from pepclibs._PropsTypes import *  # noqa: F403

from pepclibs import CStates, PStates, Uncore, PMQoS

PropsClassType = Union[CStates.CStates, PStates.PStates, Uncore.Uncore, PMQoS.PMQoS]
