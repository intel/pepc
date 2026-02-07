# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Implement per-CPU data caching, indexed by data element key and CPU number. The cache accounts for
CPU scope (e.g., global, package, core) and uses a write-through policy to ensure consistency.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Any
    from collections.abc import Hashable
    from pepclibs import CPUInfo
    from pepclibs.CPUInfoTypes import ScopeNameType

class PerCPUCache:
    """
    Implement per-CPU data caching, indexed by data element key and CPU number. The cache accounts
    for CPU scope (e.g., global, package, core) and uses a write-through policy to ensure
    consistency.
    """

    def __init__(self, cpuinfo: CPUInfo.CPUInfo, enable_cache: bool = True,
                 enable_scope: bool = True):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object.
            enable_cache: Set to False to disable caching.
            enable_scope: Set to False to disable the CPU scope optimization.
        """

        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache
        self._enable_scope = enable_scope

        self._cache: dict[Hashable, dict[int, Any]] = {}

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, unref_attrs=("_cpuinfo",))

    def get(self, key: Hashable, cpu: int) -> Any:
        """
        Retrieve the cached entry for the specified key and CPU.

        Args:
            key: The key of the cache entry to retrieve.
            cpu: The CPU number of the cache entry to retrieve.

        Returns:
            The retrieved cache entry.

        Raises:
            ErrorNotFound: If caching is disabled or the item is not found in the cache.
        """

        if not self._enable_cache:
            raise ErrorNotFound("Caching is disabled")

        try:
            return self._cache[key][cpu]
        except KeyError:
            raise ErrorNotFound(f"'{key}' is not cached for CPU {cpu}") from None

    def is_cached(self, key: Hashable, cpu: int):
        """
        Check if the cache contains an entry for the given key and CPU.

        Args:
            key: The key of the cache entry to check.
            cpu: The CPU number of the cache entry to check.

        Returns:
            bool: True if the entry is present in the cache, False otherwise.
        """

        if key not in self._cache or cpu not in self._cache[key]:
            return False
        return True

    def remove(self, key: Hashable, cpu: int, sname: ScopeNameType = "CPU"):
        """
        Remove the specified key and CPU entry, along with all items sharing the same scope.

        Args:
            key: The key of the cache entry to remove.
            cpu: The CPU number of the cache entry to remove.
            sname: The scope of the cache entry.
        """

        if not self._enable_cache:
            return

        if not self._enable_scope:
            if key in self._cache and cpu in self._cache[key]:
                del self._cache[key][cpu]
            return

        if sname == "global":
            del self._cache[key]
            return

        cpus = self._cpuinfo.get_cpu_siblings(cpu, sname)
        for rmcpu in cpus:
            if key in self._cache and rmcpu in self._cache[key]:
                del self._cache[key][rmcpu]

    def add(self, key: Hashable, cpu: int, entry: Any, sname: ScopeNameType = "CPU") -> Any:
        """
        Add an entry to the cache for a specific key and CPU, and propagate it to all CPUs sharing
        the same scope.

        Args:
            key: The key of the cache entry to add.
            cpu: The CPU number of the cache entry to add.
            entry: The entry to add to the cache.
            sname: The scope of the cache entry.

        Returns:
            The entry that was cached.

        Notes:
            - If caching is disabled, return the entry without modifying the cache.
            - The entry is stored for the specified CPU and all CPUs that share the same scope as
              determined by 'sname'.
        """

        if not self._enable_cache:
            return entry

        if self._enable_scope:
            cpus = self._cpuinfo.get_cpu_siblings(cpu, sname)
        else:
            cpus = [cpu]

        if key not in self._cache:
            self._cache[key] = {}
        for addcpu in cpus:
            self._cache[key][addcpu] = entry

        return entry
