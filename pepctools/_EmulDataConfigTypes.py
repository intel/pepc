# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Type definitions for emulation data configuration files.
"""
import typing

if typing.TYPE_CHECKING:
    from typing import TypedDict

    class _EmulDataConfigMSRTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'msr' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the MSR data file.
            filename: The MSR data file name.
        """

        dirname: str
        filename: str

    class _EmulDataConfigSysfsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'sysfs' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the sysfs data file.
            filename: The sysfs data file name.
        """

        dirname: str
        filename: str
