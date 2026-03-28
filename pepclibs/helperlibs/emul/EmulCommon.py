# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Shared constants and type definitions for emulation data configuration.

This module contains shared definitions used by both the emulation data generator
(_EmulDataGen.py) and the emulation process manager (EmulProcessManager.py).
"""
import typing
from pathlib import Path
from typing import Final

# The name of the main configuration file in each emulation dataset directory.
EMUL_CONFIG_FNAME: Final[str] = "config.yml"

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

    class _EmulDataConfigSysfsRcopyTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'sysfs.rcopy' section of the emulation data configuration file.

        Attributes:
            paths: List of sub-paths (relative to the sysfs sub-directory) to recursively copy.
            rw_patterns: Optional list of Python regex patterns. A copied file whose absolute
                         virtual sysfs path matches any pattern is registered as read-write.
                         All other files default to read-only.
        """

        paths: list[Path]
        rw_patterns: list[str]

    class _EmulDataConfigSysfsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'sysfs' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the sysfs data file.
            inlinefiles: The sysfs inline data file name.
            rcopy: Recursive-copy configuration: paths to copy and optional R/W path patterns.
        """

        dirname: str
        inlinefiles: str
        rcopy: _EmulDataConfigSysfsRcopyTypedDict

    class _EmulDataConfigProcfsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'procfs' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the procfs data files.
            rw_patterns: Optional list of Python regex patterns. A procfs file whose absolute path
                         matches any pattern is registered as read-write. All other files default
                         to read-only.
        """

        dirname: str
        rw_patterns: list[str]
