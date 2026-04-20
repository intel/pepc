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

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from typing import TypedDict, Final

    class _EDConfMSRTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'msr' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the MSR data file.
            filename: The MSR data file name.
        """

        dirname: str
        filename: str

    class _EDConfSysfsRcopyTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'sysfs.rcopy' section of the emulation data configuration file.

        Attributes:
            paths: List of sub-paths (relative to the sysfs sub-directory) to recursively copy.
            rw_patterns: Optional list of Python regex patterns. A file whose path matches any of
                         these patterns is registered is read-write. All other files default to
                         read-only.
        """

        paths: list[Path]
        rw_patterns: list[str]

    class _EDConfSysfsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'sysfs' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the sysfs data file.
            inlinefiles: The sysfs inline data file name.
            rcopy: Recursive-copy configuration: paths to copy and optional R/W path patterns.
        """

        dirname: str
        inlinefiles: str
        rcopy: _EDConfSysfsRcopyTypedDict

    class _EDConfProcfsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'procfs' section of the emulation data configuration file.

        Attributes:
            dirname: Name of the sub-directory containing the procfs data files.
            rw_patterns: Optional list of Python regex patterns. A procfs file whose path matches
                         any of these patterns is read-write. All other files default to read-only.
        """

        dirname: str
        rw_patterns: list[str]

    class _EDConfMetadataGeneratedByTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'metadata.generated_by' section of the emulation data
        configuration.

        Attributes:
            tool: Name of the tool that generated the emulation data.
            version: Version of the tool.
            date: Date when the emulation data was generated.
        """

        tool: str
        version: str
        date: str

    class _EDConfMetadataTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the 'metadata' section of the emulation data configuration file.

        Attributes:
            generated_by: Information about the tool that generated the emulation data.
        """

        generated_by: _EDConfMetadataGeneratedByTypedDict

    class _EDConfTypedDict(TypedDict, total=False):
        """
        Typed dictionary describing the complete YAML emulation data configuration file.

        Attributes:
            metadata: Metadata about the emulation data (version, generation date, etc).
            msr: MSR register configuration.
            sysfs: Sysfs files configuration.
            procfs: Procfs files configuration.
        """

        metadata: _EDConfMetadataTypedDict
        msr: _EDConfMSRTypedDict
        sysfs: _EDConfSysfsTypedDict
        procfs: _EDConfProcfsTypedDict

# The name of the main configuration file in each emulation dataset directory.
EMUL_CONFIG_FNAME: Final[str] = "config.yml"
