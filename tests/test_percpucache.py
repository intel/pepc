#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Tests for the 'PerCPUCache' class."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common
from pepclibs import CPUInfo, _PerCPUCache
from pepclibs.helperlibs.Exceptions import ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Generator, cast
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
        """

        cpuinfo: CPUInfo.CPUInfo

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo

        yield params

def test_percpucache_scope(params: _TestParamsTypedDict):
    """
    Test that the 'PerCPUCache' class correctly caches values according to CPU scope.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()

    # Test with first CPU to ensure consistent, deterministic behavior across different topologies.
    test_cpu = cpus[0]
    pcache = _PerCPUCache.PerCPUCache(cpuinfo=cpuinfo)

    for sname in CPUInfo.SCOPE_NAMES:
        # Use unique objects to ensure each scope test is independent.
        val = object()
        key = (sname, "test_key")

        pcache.add(key, test_cpu, val, sname=sname)

        # Get CPUs that should have the cached value based on scope.
        siblings = cpuinfo.get_cpu_siblings(test_cpu, sname=sname)

        # Verify cache behavior for all CPUs.
        for cpu in cpus:
            if cpu in siblings:
                # CPUs in the same scope should have the cached value.
                assert pcache.is_cached(key, cpu), \
                    f"CPU {cpu} should be cached in scope '{sname}' for test CPU {test_cpu}"
                assert pcache.get(key, cpu) is val, \
                    f"CPU {cpu} should have same value in scope '{sname}'"
            else:
                # CPUs outside the scope should not have the value.
                assert not pcache.is_cached(key, cpu), \
                    f"CPU {cpu} should not be cached in scope '{sname}' for test CPU {test_cpu}"

def test_percpucache_remove(params: _TestParamsTypedDict):
    """
    Test that the 'PerCPUCache' class correctly removes cached values according to CPU scope.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()
    test_cpu = cpus[0]
    pcache = _PerCPUCache.PerCPUCache(cpuinfo=cpuinfo)

    for sname in CPUInfo.SCOPE_NAMES:
        val = object()
        key = (sname, "remove_test")

        # Add to cache.
        pcache.add(key, test_cpu, val, sname=sname)
        siblings = cpuinfo.get_cpu_siblings(test_cpu, sname=sname)

        # Verify it's cached.
        for cpu in siblings:
            assert pcache.is_cached(key, cpu), \
                f"CPU {cpu} should be cached before removal in scope '{sname}'"

        # Remove from cache.
        pcache.remove(key, test_cpu, sname=sname)

        # Verify it's removed for all CPUs in the scope.
        for cpu in cpus:
            assert not pcache.is_cached(key, cpu), \
                f"CPU {cpu} should not be cached after removal in scope '{sname}'"

def test_percpucache_disabled(params: _TestParamsTypedDict):
    """
    Test that the 'PerCPUCache' class works correctly when caching is disabled.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    test_cpu = cpuinfo.get_cpus()[0]
    pcache = _PerCPUCache.PerCPUCache(cpuinfo=cpuinfo, enable_cache=False)

    val = object()
    key = ("test", "disabled")

    # add() should return the value but not cache it.
    result = pcache.add(key, test_cpu, val, sname="package")
    assert result is val, "add() should return the value even when caching is disabled"

    # The value should not be cached.
    assert not pcache.is_cached(key, test_cpu), \
        "Value should not be cached when caching is disabled"

    # get() should raise ErrorNotFound.
    with pytest.raises(ErrorNotFound, match="Caching is disabled"):
        pcache.get(key, test_cpu)

def test_percpucache_scope_disabled(params: _TestParamsTypedDict):
    """
    Test that the 'PerCPUCache' class works correctly when scope optimization is disabled.

    Args:
        params: The test parameters.
    """

    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()

    # Skip test if there's only one CPU (can't test scope behavior).
    if len(cpus) < 2:
        pytest.skip("Need at least 2 CPUs to test scope disabled behavior")

    test_cpu = cpus[0]
    pcache = _PerCPUCache.PerCPUCache(cpuinfo=cpuinfo, enable_scope=False)

    val = object()
    key = ("test", "no_scope")

    # Add with a scope (e.g., "package") but scope is disabled.
    pcache.add(key, test_cpu, val, sname="package")

    # Only the specific CPU should have the value, not siblings.
    assert pcache.is_cached(key, test_cpu), "Test CPU should be cached"
    assert pcache.get(key, test_cpu) is val, "Test CPU should have the value"

    # Other CPUs in the same package should NOT have the value.
    package_siblings = cpuinfo.get_cpu_siblings(test_cpu, sname="package")
    for cpu in package_siblings:
        if cpu != test_cpu:
            assert not pcache.is_cached(key, cpu), \
                f"CPU {cpu} should not be cached when scope is disabled"
            break  # Found at least one sibling to test.
