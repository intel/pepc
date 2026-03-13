# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Tests for the 'KernelVersion' module.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from pepclibs.helperlibs import KernelVersion

def test_split_kver():
    """Test the 'split_kver()' function."""

    result = KernelVersion.split_kver("4.18.1")
    assert result['major'] == 4
    assert result['minor'] == 18
    assert result['stable'] == 1
    assert result['rc'] == 0
    assert result['localver'] == ""

    # Version with just 0 stable version.
    result = KernelVersion.split_kver("5.15.0")
    assert result['major'] == 5
    assert result['minor'] == 15
    assert result['stable'] == 0
    assert result['rc'] == 0
    assert result['localver'] == ""

    # No stable version, should default to 0.
    result = KernelVersion.split_kver("5.0")
    assert result['major'] == 5
    assert result['minor'] == 0
    assert result['stable'] == 0
    assert result['rc'] == 0
    assert result['localver'] == ""

    # RC without stable version.
    result = KernelVersion.split_kver("5.0-rc2")
    assert result['major'] == 5
    assert result['minor'] == 0
    assert result['stable'] == 0
    assert result['rc'] == 2
    assert result['localver'] == ""

    # RC with stable version.
    result = KernelVersion.split_kver("6.1.0-rc10")
    assert result['major'] == 6
    assert result['minor'] == 1
    assert result['stable'] == 0
    assert result['rc'] == 10
    assert result['localver'] == ""

    # Local version without RC.
    result = KernelVersion.split_kver("4.18.1-build0")
    assert result['major'] == 4
    assert result['minor'] == 18
    assert result['stable'] == 1
    assert result['rc'] == 0
    assert result['localver'] == "-build0"

    # Local version with a dash.
    result = KernelVersion.split_kver("5.10.0-arch1-1")
    assert result['major'] == 5
    assert result['minor'] == 10
    assert result['stable'] == 0
    assert result['rc'] == 0
    assert result['localver'] == "-arch1-1"

    # RC with local version.
    result = KernelVersion.split_kver("6.1-rc1-next-20221201")
    assert result['major'] == 6
    assert result['minor'] == 1
    assert result['stable'] == 0
    assert result['rc'] == 1
    assert result['localver'] == "-next-20221201"

def test_split_kver_type():
    """Test that split_kver returns the correct type."""

    result = KernelVersion.split_kver("5.10.1")

    assert isinstance(result, dict)
    assert isinstance(result['major'], int)
    assert isinstance(result['minor'], int)
    assert isinstance(result['stable'], int)
    assert isinstance(result['rc'], int)
    assert isinstance(result['localver'], str)

def test_kver_lt():
    """Test the 'kver_lt()' function."""

    # Major version comparisons.
    assert KernelVersion.kver_lt("4.18.1", "5.0.0") is True
    assert KernelVersion.kver_lt("5.0.0", "4.18.1") is False
    assert KernelVersion.kver_lt("5.0.0", "5.0.0") is False

    # Minor version comparisons.
    assert KernelVersion.kver_lt("5.10.0", "5.15.0") is True
    assert KernelVersion.kver_lt("5.15.0", "5.10.0") is False
    assert KernelVersion.kver_lt("5.10.0", "5.10.0") is False

    # Stable version comparisons.
    assert KernelVersion.kver_lt("5.10.1", "5.10.2") is True
    assert KernelVersion.kver_lt("5.10.2", "5.10.1") is False
    assert KernelVersion.kver_lt("5.10.0", "5.10") is False

    # RC comparisons - RC is older than final release.
    assert KernelVersion.kver_lt("5.10-rc1", "5.10.0") is True
    assert KernelVersion.kver_lt("5.10.0", "5.10-rc1") is False

    # RC comparisons - lower RC is older than higher RC.
    assert KernelVersion.kver_lt("5.10-rc1", "5.10-rc2") is True
    assert KernelVersion.kver_lt("5.10-rc2", "5.10-rc1") is False

    # RC comparisons - both final releases.
    assert KernelVersion.kver_lt("5.10.0", "5.10.0") is False
    assert KernelVersion.kver_lt("5.10", "5.10.0") is False

    # Local version comparisons.
    assert KernelVersion.kver_lt("5.10.0-arch1", "5.10.0-arch2") is True
    assert KernelVersion.kver_lt("5.10.0-arch2", "5.10.0-arch1") is False
    assert KernelVersion.kver_lt("5.10.0", "5.10.0-arch1") is True

    # Cases with RC and local version.
    assert KernelVersion.kver_lt("5.10-rc1-custom", "5.10-rc2-custom") is True
    assert KernelVersion.kver_lt("5.10-rc1-custom", "5.10.0") is True

    # Edge cases.
    assert KernelVersion.kver_lt("5.0", "5.0.1") is True
    assert KernelVersion.kver_lt("5.0.1", "5.0") is False
