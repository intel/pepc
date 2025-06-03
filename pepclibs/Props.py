# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide types and common methods for users of property classes, such as 'PStates'.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import Union
from pepclibs import PStates, CStates

# pylint: disable=unused-import
from pepclibs._CPUInfoBaseTypes import NumsType, DieNumsType
from pepclibs._PropsClassBaseTypes import PropertyTypedDict, PropertyValueType, MechanismNameType
from pepclibs._PropsClassBaseTypes import ScopeNameType

PropsType = Union[PStates.PStates, CStates.CStates]
