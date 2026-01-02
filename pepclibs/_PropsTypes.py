# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Types for property modules (e.g., 'PStates'). Includes only API types. Internal types are in
'_PropsClassBase'. However, this module is not supposed to be imported directly by property module
users.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import TypedDict, Literal, Union
from pepclibs.CPUInfoTypes import ScopeNameType

class MechanismTypedDict(TypedDict):
    """
    Type for the mechanism description dictionary.

    Attributes:
        short: A short name or identifier for the mechanism.
        long: A more descriptive name for the mechanism (but still a one-liner).
        writable: Whether the mechanism property is writable.
    """

    short: str
    long: str
    writable: bool

MechanismNameType = Literal["sysfs", "tpmi", "cdev", "msr", "cppc", "doc"]

PropertyTypeType = Literal["int", "float", "bool", "str", "list[str]", "list[int]"]

class PropertyTypedDict(TypedDict, total=False):
    """
    Type for the property description dictionary.

    Attributes:
        name: The name of the property.
        unit: The unit of the property value (e.g., "Hz", "W").
        type: The type of the property value (e.g., "int", "float", "bool").
        sname: The scope name of the property (e.g., "CPU", "core", "package").
        iosname: The I/O scope name of the property.
        mnames: A tuple of mechanism names supported by the property.
        writable: Whether the property is writable.
        special_vals: A set of special values for the property.
        subprops: A tuple of sub-properties related to this property.
    """

    name: str
    unit: str
    type: PropertyTypeType
    sname: ScopeNameType | None
    mnames: tuple[MechanismNameType, ...]
    writable: bool
    special_vals: set[str]
    subprops: tuple[str, ...]

PropertyValueType = Union[int, float, bool, str, list[str], list[int]]

class PVInfoTypedDict(TypedDict, total=False):
    """
    Type for the property value dictionary (pvinfo).

    Attributes:
        cpu: The CPU number.
        die: The die number.
        package: The package number.
        pname: The name of the property.
        val: The value of the property.
        mname: The name of the mechanism used to retrieve the property.
    """

    cpu: int
    die: int
    package: int
    pname: str
    val: PropertyValueType
    mname: MechanismNameType
