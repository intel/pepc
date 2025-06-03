# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide information about CPU topology and other CPU details.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import Iterable, Literal
from pepclibs import _CPUInfoBase
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
# pylint: disable-next=unused-import
from pepclibs._CPUInfoBase import SCOPE_NAMES, HYBRID_TYPE_INFO, NA, INVALID

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._CPUInfoBaseTypes import HybridCPUKeyType, ScopeNameType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUInfo(_CPUInfoBase.CPUInfoBase):
    """
    Provide information about CPU topology and other CPU details.

    Public methods overview.

    1. Get various CPU information.
        - 'get_topology()' - CPU topology.
    2. Get list of packages/cores/etc.
        - 'get_cpus()'
        - 'get_cores()'
        - 'get_modules()'
        - 'get_dies()'
        - 'get_nodes()'
        - 'get_packages()'
        - 'get_offline_cpus()'
        - 'get_tline_by_cpu()'
        - 'get_cpu_siblings()'
    3. Get list of packages/cores/etc for a subset of CPUs/cores/etc.
        - 'package_to_cpus()'
        - 'package_to_cores()'
        - 'package_to_modules()'
        - 'package_to_dies()'
        - 'package_to_nodes()'
        - 'cores_to_cpus()'
        - 'modules_to_cpus()'
        - 'dies_to_cpus()'
        - 'nodes_to_cpus()'
        - 'packages_to_cpus()'
    4. Get packages/core/etc counts.
        - 'get_cpus_count()'
        - 'get_cores_count()'
        - 'get_modules_count()'
        - 'get_dies_count()'
        - 'get_packages_count()'
        - 'get_offline_cpus_count()'
    5. Normalize a list of packages/cores/etc.
        A. Multiple packages/CPUs/etc numbers:
            - 'normalize_cpus()'
            - 'normalize_cores()'
            - 'normalize_modules()'
            - 'normalize_dies()'
            - 'normalize_packages()'
        B. Single package/CPU/etc.
            - 'normalize_cpu()'
            - 'normalize_core()'
            - 'normalize_die()'
            - 'normalize_package()'
    6. Select CPUs by sibling index.
        - 'select_core_siblings()'
        - 'select_module_siblings()'
    7. "Divide" list of CPUs.
        - 'cpus_div_cores()' - by cores.
        - 'cpus_div_dies()' - by dies.
        - 'cpus_div_packages()' - by packages.
    8. Miscellaneous.
        - 'dies_to_str()' - turn a die numbers dictionary into a string.
    """

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager is created.
        """

        super().__init__(pman=pman)

        # Scope name to its index number.
        self._sname2idx: dict[ScopeNameType, int]
        self._sname2idx = {sname: idx for idx, sname in enumerate(SCOPE_NAMES)}

    def _validate_sname(self, sname: ScopeNameType, name: str = "scope name"):
        """
        Check that the provided scope name is valid.

        Args:
            sname: The scope name to validate.
            name: The label to use in the error message.
        """

        if sname not in self._sname2idx:
            snames = ", ".join(SCOPE_NAMES)
            raise Error(f"Bad {name} name '{sname}', use: {snames}")

    def get_topology(self,
                     snames: Iterable[ScopeNameType] | None = None,
                     order: ScopeNameType = "CPU") -> list[dict[ScopeNameType, int ]]:
        """
        Return the CPU topology table sorted in the specified order, include the specified scopes.

        Args:
            scopes: Scope names to include to the topology table. All scopes by default.
            order: Topology table sorting order. Defaults to "CPU".

        The topology table is a list of dictionaries, one dictionary per CPU (plus dictionaries for
        I/O dies, which do not include CPUs).

        Each dictionary may contains the following keys (depending on the 'snames' argument):
            - CPU: Globally unique CPU number, or 'NA' for I/O dies.
            - core: Core number within the package, or 'NA' for I/O dies. Numbers are not globally
                    unique in older kernels (they are per-package), but globally unique in newer
                    kernels. May contain gaps in the numbers.
            - module: Globally unique module number, or 'NA' for I/O dies. Cores in a module share
                      the L2 cache.
            - die: Die number within the package, or 'NA' for I/O dies. Numbers may be per-package
                   or globally unique depending on the system.
            - node: Globally unique NUMA node number, or 'NA' for I/O dies.
            - package: Globally unique package number.

        Returns:
            The topology table.


        Examples:
            Consider the following hypothetical system:
                - 2 packages, numbers 0, 1.
                - 2 nodes, numbers 0, 1.
                - 1 die per package, numbers 0.
                - 3 modules, numbers 0, 4, 5.
                - 4 cores per package, numbers 0, 1, 5, 6.
                - 16 CPUs, numbers 0-16.

            Here is the topology table in package order. It is sorted by package and CPU.

            {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},

            The topology tables in node/die order will look the same (in this particular example).
            They are sorted by package number, then node/die number, then CPU number.

            Here is the topology table in core order. It'll be sorted by package number, and then
            core number, then CPU number.

            {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},

            Here is the topology table in CPU order.

            {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1},
            {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0},
            {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1},
        """

        if not snames:
            snames = SCOPE_NAMES
        else:
            for sname in snames:
                self._validate_sname(sname, name="topology scope name")

        self._validate_sname(order, name="order")
        topology = self._get_topology(snames, order=order)
        return copy.deepcopy(topology)

    def _get_scope_nums(self,
                        sname: ScopeNameType,
                        parent_sname: ScopeNameType,
                        nums: Iterable[int] | Literal["all"],
                        order: ScopeNameType | None = None) -> list[int]:
        """
        Return a list of "scope" numbers (e.g., CPU numbers or core numbers) for specified parent
        scope numbers (e.g., get a list of CPU numbers for specified cores, or get a list of core
        numbers for specified packages).

        Args:
            sname: Scope name to retrieve the numbers for (e.g., "CPU", "core", "die").
            parent_sname: Parent scope to retrieve to use for selecting scope numbers (e.g., "core",
                          "package").
            nums: Iterable of parent scope numbers for selecting scope numbers, or "all" to or all
                  parent scope numbers.
            order: Scope name to sort the result by. Defaults to 'sname'.

        Returns:
            List of scope numbers corresponding to the specified parent scope numbers.

        Examples:
            1. Get CPU numbers in cores 1 and 3.
               _get_scope_nums("CPU", "core", (1, 3))
            2. Get node numbers in package 1.
               _get_scope_nums("node", "package", (1,))
            3. Get all core numbers.
               _get_scope_nums("core", "package", "all")
               _get_scope_nums("core", "node", "all")
               _get_scope_nums("core", "core", "all")

            Assume a system with 2 packages, 1 die per package, 2 cores per package, and 2 CPUs per
            core:
                - Package 0 includes die 0.
                - Package 1 includes die 1.
                - Die 0 includes cores 0 and 1.
                - Die 1 includes cores 2 and 3.
                - Core 0 includes CPUs 0 and 4
                - Core 1 includes CPUs 1 and 5
                - Core 3 includes CPUs 2 and 6
                - Core 4 includes CPUs 3 and 7

                1. _get_scope_nums("CPU", "core", "all") returns:
                   [0, 1, 2, 3, 4, 5, 6, 7]
                2. _get_scope_nums("CPU", "core", "all", order="core") returns:
                   [0, 4, 1, 5, 2, 6, 3, 7]
                3. _get_scope_nums("CPU", "core", (1,3), order="core") returns:
                   [1, 5, 2, 6]
        """

        if order is None:
            order = sname

        self._validate_sname(sname)
        self._validate_sname(parent_sname)
        self._validate_sname(order, name="order")

        if self._sname2idx[parent_sname] < self._sname2idx[sname]:
            raise Error(f"Cannot get {sname}s for '{parent_sname}', {sname} is not a child of "
                        f"{parent_sname}")

        if nums != "all":
            # Convert 'nums' to a set. Any non-integer values will be validated later.
            nums_set = set(nums)
        else:
            nums_set = set()

        result: dict[int, None] = {}
        valid_nums: set[int] = set()

        for tline in self._get_topology((parent_sname, sname), order=order):
            if tline[parent_sname] == NA:
                continue
            valid_nums.add(tline[parent_sname])
            if tline[sname] == NA:
                continue
            if nums == "all" or tline[parent_sname] in nums_set:
                result[tline[sname]] = None

        if nums_set == "all":
            return list(result)

        # Validate the input numbers in 'nums'.
        if not nums_set.issubset(valid_nums):
            valid = Trivial.rangify(valid_nums)
            invalid = Trivial.rangify(nums_set - valid_nums)
            raise Error(f"{parent_sname} {invalid} do not exist{self._pman.hostmsg}, valid "
                        f"{parent_sname} numbers are: {valid}")

        return list(result)

    def get_cpus(self, order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of online CPU numbers in the specified order.

        Args:
            order: Sorting order for the returned CPU numbers. Defaults to "CPU".

        Returns:
            List of online CPU numbers, sorted in the specified order.

        Note:
            CPU numbers are unique across the system (contrast to die numbers, which are
            per-package).
        """

        if order == "CPU":
            return self._get_online_cpus()

        return self._get_scope_nums("CPU", "CPU", "all", order=order)

    def get_offline_cpus(self) -> list[int]:
        """
        Return a list of offline CPU numbers.

        Returns:
            List of offline CPU numbers sorted in ascending order.
        """

        cpus = self._get_all_cpus()
        online_cpus = self._get_online_cpus_set()
        return [cpu for cpu in cpus if cpu not in online_cpus]

    def get_cores(self, package: int = 0, order: ScopeNameType = "core") -> list[int]:
        """
        Return a list of core numbers within the specified package.

        Only cores containing at least one online CPU are included, as Linux does not provide
        topology information for offline CPUs. Depending on kernel version, core numbers may be
        relative to the package (e.g., core 0 may exist in both package 0 and package 1).

        Args:
            package: The package to retrieve core numbers from.
            order: The sorting order of the returned core numbers list. Defaults to "core"
                   (ascending core number order).

        Returns:
            A list of core numbers present in the specified package, sorted in the specified order.
        """

        return self._get_scope_nums("core", "package", (package,), order=order)

    def get_modules(self, order: ScopeNameType = "module") -> list[int]:
        """
        Return a list of module numbers, sorted in the specified order.

        Only modules containing at least one online CPU are included, because Linux does not provide
        topology information for offline CPUs. Module numbers are globally unique (unlike core
        numbers).

        Args:
            order: Sorting order for the returned module numbers list.

        Returns:
            A list of module numbers sorted in the specified order.
        """

        return self._get_scope_nums("module", "module", "all", order=order)

    def get_dies(self,
                 package: int = 0,
                 order: ScopeNameType = "die",
                 compute_dies: bool = True,
                 io_dies: bool = True) -> list[int]:
        """
        Return a list of die numbers in the specified package.

        Only dies containing at least one online CPU are included, as Linux does not provide
        topology information for offline CPUs. Die numbers may be globally unique or relative to the
        package, depending on the system.

        Args:
            package: The package number to return die numbers for.
            order: The sorting order for the resulting list of die numbers.
            compute_dies: Include compute dies (dies with CPUs) if True.
            io_dies: Include I/O dies (dies without CPUs) if True.

        Returns:
            A list of die numbers in the given package, filtered and sorted according to the
            provided arguments.
        """

        dies = self._get_scope_nums("die", "package", (package,), order=order)
        if compute_dies and io_dies:
            return dies

        if compute_dies:
            cdies: list[int] = []
            for die in dies:
                if die in self._compute_dies[package]:
                    cdies.append(die)
            return cdies

        iodies: list[int] = []
        for die in dies:
            if die in self._io_dies[package]:
                iodies.append(die)
        return iodies

    def get_nodes(self, order: ScopeNameType = "node") -> list[int]:
        """
        Return a list of NUMA node numbers.

        Only NUMA nodes with at least one online CPU are included, as Linux does not provide
        topology information for offline CPUs. Node numbers are globally unique.

        Args:
            order: Sorting order for the returned list of node numbers.

        Returns:
            List of NUMA node numbers sorted according to the specified order.
        """

        return self._get_scope_nums("node", "node", "all", order=order)

    def get_packages(self, order: ScopeNameType = "package") -> list[int]:
        """
        Return a list of package numbers.

        Only packages containing at least one online CPU are included, as Linux does not provide
        topology information for offline CPUs. Package numbers are globally unique.

        Args:
            order: Sorting order for the returned list of package numbers.

        Returns:
            List of package numbers present in the system, sorted as specified.
        """

        return self._get_scope_nums("package", "package", "all", order=order)

    def cpus_hotplugged(self):
        """
        Handle CPU hotplug events by updating internal state.

        Call this method whenever a CPU is brought online or taken offline. This ensures that the
        internal CPU information remains accurate after hotplug events.
        """

        self._cpus_hotplugged()

    def get_tline_by_cpu(self,
                         cpu: int,
                         snames: Iterable[ScopeNameType] | None = None) -> dict[ScopeNameType, int]:
        """
        Retrieve the topology line for a specific CPU.

        A topology line is an element of the topology table returned by 'get_topology()'. It is a
        dictionary with scope names as keys and their corresponding values for the specified CPU.

        Args:
            cpu: The CPU number to retrieve the topology line for.
            snames: Scope names to include in the resulting topology line dictionary. If not
                    provided, all available scope names are included.

        Returns:
            The topology line for the specified CPU.
        """

        cpu = Trivial.str_to_int(cpu, what="CPU number")
        if not snames:
            snames = SCOPE_NAMES

        tline = None
        # TODO: This for loop is an O(n) operation, which is not optimal. Consider optimizing it.
        for tline in self._get_topology(snames):
            if cpu == tline["CPU"]:
                break
        else:
            raise Error(f"CPU {cpu} is not available{self._pman.hostmsg}")

        result = {}
        for sname in snames:
            result[sname] = tline[sname]
        return result

    def get_cpu_siblings(self, cpu: int, sname: ScopeNameType | Literal["global"]) -> list[int]:
        """
        Return a list of sibling CPU number within a specified topology scope.

        Given a CPU number and a scope name, retrieve all CPUs that share the same
        topology scope (e.g., package, core, module) as the specified CPU. Special scope and
        "global" is also supported.

        For example, if 'sname' is "core", this method returns a list of CPU numbers that
        share the same core as CPU 'cpu'.

        Args:
            cpu: CPU number for which to find siblings.
            sname: Topology scope name to use for finding siblings. Supported values include all
                  'SCOPE_NAMES' plus "global".

        Returns:
            List of CPU numbers that are siblings of the specified CPU within the given scope.

        """

        if sname == "CPU":
            return [cpu]

        if sname == "global":
            return self.get_cpus()

        tline = self.get_tline_by_cpu(cpu, snames=(sname, "package"))
        if sname == "package":
            return self.package_to_cpus(tline[sname])
        if sname == "node":
            return self.nodes_to_cpus((tline[sname],))
        if sname == "die":
            return self.dies_to_cpus(dies=(tline[sname],), packages=(tline["package"],))
        if sname == "module":
            return self.modules_to_cpus((tline[sname],))
        if sname == "core":
            return self.cores_to_cpus(cores=(tline[sname],), packages=(tline["package"],))

        raise Error(f"Unsupported scope name \"{sname}\"")

    def package_to_cpus(self, package: int, order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers belonging to the specified package.

        Args:
            package: The package number to retrieve CPU numbers for.
            order: The sorting order of the returned CPU numbers list.

        Returns:
            List of CPU numbers within the given package, sorted according to the specified order.
        """

        return self._get_scope_nums("CPU", "package", (package,), order=order)

    def package_to_cores(self, package: int, order: ScopeNameType = "core") -> list[int]:
        """
        Return a list of core numbers within the specified package.

        Args:
            package: The package number for which to retrieve core numbers.
            order: The sorting order of the returned core numbers list.

        Returns:
            List of core numbers present in the given package, sorted according to the specified
            order.
        """

        return self._get_scope_nums("core", "package", (package,), order=order)

    def package_to_modules(self, package: int, order: ScopeNameType = "module") -> list[int]:
        """
        Return a list of module numbers within the specified package.

        Args:
            package: The package number for which to retrieve module numbers.
            order: The sorting order for the returned list of module numbers.

        Returns:
            List of module numbers present in the given package, sorted according to the specified
            order.
        """

        return self._get_scope_nums("module", "package", (package,), order=order)

    def package_to_dies(self, package: int, order: ScopeNameType = "die") -> list[int]:
        """
        Return a list of die numbers within the specified package.

        Args:
            package: The package number to retrieve die numbers from.
            order: Sorting order for the returned die numbers list.

        Returns:
            List of die numbers present in the given package.

        Note:
            Die numbers may be globally unique or relative to the package, depending on the system.
            For example, both package 0 and package 1 may have a die 0.
        """

        return self._get_scope_nums("die", "package", (package,), order=order)

    def package_to_nodes(self, package: int, order: ScopeNameType = "node") -> list[int]:
        """
        Return a list of NUMA node numbers within the specified package.

        Args:
            package: Package number to retrieve NUMA node numbers for.
            order: Sorting order for the returned list of node numbers.

        Returns:
            List of NUMA node numbers in the given package, sorted according to 'order'.
        """

        return self._get_scope_nums("node", "package", (package,), order=order)

    def cores_to_cpus(self,
                      cores: Iterable[int] | Literal["all"] = "all",
                      packages: Iterable[int] | Literal["all"] = "all",
                      order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers corresponding to specified cores and packages.

        Args:
            cores: Collection of core numbers within the specified packages to include. Use "all" to
                   select all cores.
            packages: Collection of package numbers to filter cores by. Use "all" to select all
                      packages.
            order: Sorting order for the returned CPU numbers list.

        Returns:
            List of CPU numbers matching the specified cores and packages, sorted as requested.

        Note:
            Core numbers may not be globally unique. Depending on the kernel version, they may be
            relative to the package (e.g., core 0 may exist in both package 0 and package 1).

        """

        by_core = self._get_scope_nums("CPU", "core", cores, order=order)
        by_package = set(self._get_scope_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_core:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def modules_to_cpus(self,
                        modules: Iterable[int] | Literal["all"] = "all",
                        order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers belonging to the specified modules.

        Args:
            modules: Collection of module numbers to retrieve CPU numbers for. Use "all" to include
                     all modules.
            order: Sorting order of the returned CPU numbers list.

        Returns:
            List of CPU numbers in the specified modules, sorted according to the given order.

        Note:
            Module numbers are globally unique.
        """

        return self._get_scope_nums("CPU", "module", modules, order=order)

    def dies_to_cpus(self,
                     dies: Iterable[int] | Literal["all"] = "all",
                     packages: Iterable[int] | Literal["all"] = "all",
                     order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers for specified dies and packages.

        Args:
            dies: Collection of die numbers within the specified packages to include, or "all" for
                  all dies.
            packages: Collection of package numbers to include, or "all" for all packages.
            order: Sorting order for the returned CPU numbers list.

        Returns:
            List of CPU numbers belonging to the specified dies and packages, sorted according to
            the specified order.

        Notes:
            Depending on the system, die numbers may be globally unique or unique only within a
            package. For example, both package 0 and package 1 may have a die 0.
        """

        by_die = self._get_scope_nums("CPU", "die", dies, order=order)
        by_package = set(self._get_scope_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_die:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def nodes_to_cpus(self,
                      nodes: Iterable[int] | Literal["all"] = "all",
                      order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers for specified NUMA nodes.

        Args:
            nodes: Collection of NUMA node numbers to retrieve CPU numbers for. Use "all" to include
                   all nodes.
            order: Sorting order for the returned CPU numbers list.

        Returns:
            List of CPU numbers present in the specified NUMA nodes, sorted in the given order.

        Note:
            NUMA node numbers are globally unique.
        """

        return self._get_scope_nums("CPU", "node", nodes, order=order)

    def packages_to_cpus(self,
                         packages: Iterable[int] | Literal["all"] = "all",
                         order: ScopeNameType = "CPU") -> list[int]:
        """
        Return a list of CPU numbers for specified packages.

        Args:
            packages: Collection of package numbers to retrieve CPU numbers for. Use "all" to
                      include all packages.
            order: Sorting order for the returned CPU numbers list.

        Returns:
            List of CPU numbers in the specified packages, sorted according to the given order.

        Note:
            Package numbers are globally unique.
        """

        return self._get_scope_nums("CPU", "package", packages, order=order)

    def get_cpus_count(self) -> int:
        """
        Return the number of online CPUs.

        Returns:
            Number of CPUs currently online.
        """

        return len(self._get_online_cpus())

    def get_offline_cpus_count(self) -> int:
        """
        Return the number of offline CPUs.

        Returns:
            Number of CPUs that are currently offline.
        """

        return len(self.get_offline_cpus())

    def get_cores_count(self, package: int = 0) -> int:
        """
        Return the number of cores in the specified package. Count only cores that have at least one
        online CPU.

        Args:
            package: Package number to query.

        Returns:
            Number of cores with at least one online CPU in the given package.
        """

        return len(self.get_cores(package=package))

    def get_modules_count(self) -> int:
        """
        Return the number of modules with at least one online CPU.

        Returns:
            Number of modules present in the system.
        """

        return len(self.get_modules())

    def get_dies_count(self,
                       package: int = 0,
                       compute_dies: bool = True,
                       io_dies: bool = True) -> int:
        """
        Return the number of dies in the specified package.

        Args:
            package: Package number to query.
            compute_dies: Include compute dies (dies with CPUs) if True.
            io_dies: Include I/O dies (dies without CPUs) if True.

        Returns:
            Number of dies in the package that contain at least one online CPU.

        Note:
            Only dies with at least one online CPU are counted.
        """

        return len(self.get_dies(package=package, compute_dies=compute_dies, io_dies=io_dies))

    def get_packages_count(self) -> int:
        """
        Return the number of CPU packages with at least one online CPU.

        Returns:
            Number of CPU packages present in the system that contain at least one online CPU.
        """

        return len(self.get_packages())

    def select_core_siblings(self, cpus: Iterable[int], indexes: Iterable[int]) -> list[int]:
        """
        Select core siblings from the provided list of CPUs based on sibling indexes.

        Given a list of CPU numbers, return a subset containing only those CPUs that are core
        siblings at the specified indexes. Core siblings are CPUs that share the same core (e.g.,
        hyperthreads).

        Args:
            cpus: List of CPU numbers to select core siblings from. The result is always a subset of
                  this list.
            indexes: List of sibling indexes to select. Each index corresponds to a sibling position
                     within a core.

        Returns:
            List of CPU numbers from 'cpus' that match the specified sibling indexes.

        Example:
            If the system has 4 cores with 2 CPUs each:
                - core 0: CPUs 0, 4
                - core 1: CPUs 1, 5
                - core 2: CPUs 2, 6
                - core 3: CPUs 3, 7

            For cpus = [1, 2, 4, 5]:
                - indexes = [0] returns [1, 2]
                - indexes = [1] returns [4, 5]
                - indexes = [0, 1] returns [1, 2, 4, 5]

        Note:
            Offline CPUs are ignored.
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)

        # CPU number -> core siblings index map.
        cpu2index: dict[int, int] = {}

        core = pkg = index = INVALID

        for tline in self._get_topology(("CPU", "core", "package"), order="core"):
            cpu = tline["CPU"]
            if tline["core"] != core or tline["package"] != pkg:
                core = tline["core"]
                pkg = tline["package"]
                index = 0
            cpu2index[cpu] = index
            index += 1

        result = []
        indexes = set(indexes)
        for cpu in cpus:
            if cpu in cpu2index and cpu2index[cpu] in indexes:
                result.append(cpu)

        return result

    def select_module_siblings(self, cpus: Iterable[int], indexes: Iterable[int]) -> list[int]:
        """
        Select CPUs from the input list that are module siblings at the specified indexes.

        Given a list of CPUs, return those that are module siblings at the provided indexes,
        considering only the modules present in the input list. Offline CPUs are ignored.

        Args:
            cpus: List of CPU numbers to select module siblings from. The result is always a
                  subset of CPU numbers from 'cpus'.
            indexes: List of sibling indexes to select.

        Returns:
            List of CPU numbers from 'cpus' that are module siblings at the specified indexes.

        Examples:
            Suppose the system has 4 modules, and each module has 4 CPUs.
                - module 0 includes CPUs 0, 1, 2, 3
                - module 1 includes CPUs 4, 5, 6, 7
                - module 2 includes CPUs 8, 9, 10, 11
                - module 4 includes CPUs 12, 13, 14, 15

            CPUs 0, 4, 8, and 12 are module siblings with index 0.
            CPUs 1, 5, 9, and 13 are module siblings with index 1.
            CPUs 2, 6, 10, and 14 are module siblings with index 2.
            CPUs 3, 7, 11, and 15 are module siblings with index 3.

            For cpus = [0, 1, 2, 3, 4, 5, 8]:
                - indexes = [0] returns [0, 4, 8]
                - indexes = [1] return [1, 5]
                - indexes = [0, 1] returns [0, 1, 4, 5, 8]

        Note:
            Offline CPUs are ignored.
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)

        # CPU number -> module siblings index map.
        cpu2index = {}
        module = pkg = index = INVALID

        for tline in self._get_topology(("CPU", "module", "package"), order="module"):
            cpu = tline["CPU"]
            if tline["module"] != module or tline["package"] != pkg:
                module = tline["module"]
                pkg = tline["package"]
                index = 0
            cpu2index[cpu] = index
            index += 1

        result = []
        indexes = set(indexes)
        for cpu in cpus:
            if cpu in cpu2index and cpu2index[cpu] in indexes:
                result.append(cpu)

        return result

    def cpus_div_cores(self, cpus: Iterable[int]) -> tuple[dict[int, list[int]], list[int]]:
        """
        Split a collection of CPU numbers into groups by core, inverse of 'cores_to_cpus()'.

        Args:
            cpus: Collection of CPU numbers to split by core.

        Returns:
            tuple:
                - Dictionary mapping package numbers to lists of core numbers.
                - List of remaining CPUs that could not be grouped by core.

        Example.
            Consider a system with 2 packages, 1 core per package, 2 CPUs per core.
                - package 0 includes core 0 and CPUs 0 and 1
                - package 1 includes core 0 and CPUs 2 and 3

            1. cpus_div_cores([0, 1, 2, 3]) returns ({0:[0], 1:[0]}, []).
            2. cpus_div_cores([2, 3])       returns ({1:[0]},        []).
            3. cpus_div_cores([0, 3])       returns ({},             [0,3]).

        Note:
            In older kernels, core numbers are relative to package numbers. In newer kernels,
            core numbers are globally unique.
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)
        cpus_set = set(cpus)

        cores: dict[int, list[int]] = {}
        rem_cpus: list[int] = []

        for pkg in self.get_packages():
            for core in self.package_to_cores(pkg):
                siblings_set = set(self.cores_to_cpus(cores=(core,), packages=(pkg,)))

                if siblings_set.issubset(cpus_set):
                    if pkg not in cores:
                        cores[pkg] = []
                    cores[pkg].append(core)
                    cpus_set -= siblings_set

        # Return the remaining CPUs in the order of the input 'cpus'.
        for cpu in cpus:
            if cpu in cpus_set:
                rem_cpus.append(cpu)

        return (cores, rem_cpus)

    def cpus_div_dies(self, cpus: Iterable[int]) -> tuple[dict[int, list[int]], list[int]]:
        """
        Split a collection of CPU numbers into groups by die, inverse of 'dies_to_cpus()'.

        Args:
            cpus: Collection of CPU numbers to group by die.

        Returns:
            tuple:
                - Dictionary mapping package numbers to lists of die numbers.
                - List of CPUs from 'cpus' that could not be grouped by die.

        Notes:
            - Die numbers may be relative to package numbers, depending on the system.
            - I/O dies (do not have CPUs) are skipped.
            - The order of rem_cpus matches the input order.

        Example:
            Consider a system with 2 packages, 2 dies per package, 1 core per die, 2 CPUs per core.
                - package 0 includes dies 0 and 1 and CPUs 0, 1, 2, and 3
                    - die 0 includes CPUs 0 and 1
                    - die 1 includes CPUs 2 and 3
                - package 1 includes dies 0 and 1 and CPUs 4, 5, 6, and 7
                    - die 0 includes CPUs 4 and 5
                    - die 1 includes CPUs 6 and 7

            1. cpus_div_dies([0, 1, 2, 3]) returns ({0:[0], 0:[1]}, []).
            2. cpus_div_dies([4,5,6])      returns ({1:[1]},        [6]).
            3. cpus_div_dies([0,3])        returns ({},             [0,3]).
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)
        cpus_set = set(cpus)

        dies: dict[int, list[int]] = {}
        rem_cpus: list[int] = []

        for pkg in self.get_packages():
            for die in self.package_to_dies(pkg):
                if die in self._io_dies[pkg]:
                    # Skip I/O dies, they have no CPUs.
                    continue

                siblings_set = set(self.dies_to_cpus(dies=(die,), packages=(pkg,)))

                if siblings_set.issubset(cpus_set):
                    if pkg not in dies:
                        dies[pkg] = []
                    dies[pkg].append(die)
                    cpus_set -= siblings_set

        # Return the remaining CPUs in the order of the input 'cpus'.
        for cpu in cpus:
            if cpu in cpus_set:
                rem_cpus.append(cpu)

        return (dies, rem_cpus)

    def cpus_div_packages(self, cpus, packages: Iterable[int] | Literal["all"] = "all"):
        """
        Split a collection of CPU numbers into groups by package, inverse of 'packages_to_cpus()'.

        Args:
            cpus: Collection of CPU numbers to group by package.
            packages: Package numbers to consider (default is all packages).

        Returns:
            tuple:
                - List of package numbers where all CPUs are present in 'cpus'.
                - List of remaining CPU numbers that do not form a complete package.

        Examples:
            Consider a system with 2 packages and 2 CPUs per package.
                - package 0 includes CPUs 0 and 1
                - package 1 includes CPUs 2 and 3

            1. cpus_div_packages([0,1,2,3]) returns ([0,1], []).
            2. cpus_div_packages([2,3])     returns ([1],   []).
            3. cpus_div_packages([0,3])     returns ([],    [0,3]).
        """

        pkgs = []
        rem_cpus = []

        cpus = self.normalize_cpus(cpus, offline_ok=True)
        cpus_set = set(cpus)

        for pkg in self.normalize_packages(packages):
            pkg_cpus_set = set(self.package_to_cpus(pkg))

            if pkg_cpus_set.issubset(cpus_set):
                pkgs.append(pkg)
                cpus_set -= pkg_cpus_set

        # Return the remaining CPUs in the order of the input 'cpus'.
        for cpu in cpus:
            if cpu in cpus_set:
                rem_cpus.append(cpu)

        return (pkgs, rem_cpus)

    def normalize_cpus(self,
                       cpus: Iterable[int] | Literal["all"],
                       offline_ok: bool = False) -> list[int]:
        """
        Validate and normalize a collection of CPU numbers.

        Args:
            cpus: Collection of CPU numbers to normalize, or the special value 'all' to select all
                  CPUs.
            offline_ok: If True, allow offline CPUs; otherwise, only online CPUs are considered
                        valid.

        Returns:
            List of validated and normalized CPU numbers.

        Note:
            Normalized CPU numbers are integers without duplicates, sorted in ascending order.
        """

        if offline_ok:
            allcpus = self._get_all_cpus_set()
        else:
            allcpus = self._get_online_cpus_set()

        if cpus == "all":
            return sorted(allcpus)

        cpus = Trivial.list_dedup(cpus)
        for cpu in cpus:
            # The reason for not using isinstance() here is to avoid bool to be treated as int.
            # Indeed, isinstance(True, int) is True.
            # pylint: disable-next=unidiomatic-typecheck
            if type(cpu) is not int:
                raise Error(f"'{cpu}' is not an integer, CPU numbers must be integers")

            if cpu not in allcpus:
                cpus_str = Trivial.rangify(allcpus)
                raise Error(f"CPU {cpu} is not available{self._pman.hostmsg}, available CPUs are: "
                            f"{cpus_str}")

        return cpus

    def normalize_cores(self, cores: Iterable[int] | Literal["all"], package: int = 0) -> list[int]:
        """
        Validate and normalize a collection of core numbers for a given package.

        Args:
            cores: Collection of core numbers to normalize, or the special value 'all' to select all
                   cores.
            package: Package number to validate the cores against.

        Returns:
            List of normalized core numbers for the specified package.

        Note:
            Normalized core numbers are integers without duplicates, sorted in ascending order.
        """

        pkg_cores = self.package_to_cores(package)

        if cores == "all":
            return pkg_cores

        pkg_cores_set = set(pkg_cores)
        cores = Trivial.list_dedup(cores)
        for core in cores:
            if type(core) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{core}' is not an integer, core numbers must be integers")

            if core not in pkg_cores_set:
                cores_str = Trivial.rangify(pkg_cores_set)
                raise Error(f"Core '{core}' is not available in package "
                            f"'{package}'{self._pman.hostmsg}, available cores are: {cores_str}")

        return cores

    def normalize_modules(self, modules: Iterable[int] | Literal["all"]) -> list[int]:
        """
        Validate and normalize a collection of module numbers.

        Args:
            modules: Collection of module numbers to normalize, or the special value 'all' to select
                     all modules.

        Returns:
            List of validated and normalized module numbers.

        Note:
            Normalized module numbers are integers without duplicates, sorted in ascending order.
        """

        all_modules = self.get_modules()

        if modules == "all":
            return all_modules

        all_modules_set = set(all_modules)
        modules = Trivial.list_dedup(modules)
        for mdl in modules:
            if type(mdl) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{mdl}' is not an integer, module numbers must be integers")

            if mdl not in all_modules_set:
                modules_str = Trivial.rangify(all_modules_set)
                raise Error(f"Module '{mdl}' is not available{self._pman.hostmsg}, available "
                            f"modules are: {modules_str}")

        return modules

    def normalize_dies(self, dies: Iterable[int] | Literal["all"], package: int = 0) -> list[int]:
        """
        Validate and normalize die numbers for a given package.

        Args:
            dies: Collection of die numbers to normalize, or the special value 'all' to select all
                  dies.
            package: Package number to validate dies against.

        Returns:
            List of normalized die numbers for the specified package.

        Note:
            Normalized die numbers are integers without duplicates, sorted in ascending order.
        """

        pkg_dies = self.package_to_dies(package)

        if dies == "all":
            return pkg_dies

        pkg_dies_set = set(pkg_dies)
        dies = Trivial.list_dedup(dies)
        for die in dies:
            if type(die) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{die}' is not an integer, die numbers must be integers")

            if die not in pkg_dies_set:
                dies_str = Trivial.rangify(pkg_dies_set)
                raise Error(f"Die '{die}' is not available in package "
                            f"'{package}'{self._pman.hostmsg}, available dies are: {dies_str}")

        return dies

    def normalize_packages(self, packages: Iterable[int] | Literal["all"]) -> list[int]:
        """
        Validate and normalize a collection of package numbers.

        Args:
            packages: Collection of package numbers to normalize, or the special value 'all' to
                      select all packages.

        Returns:
            List of normalized package numbers.

        Note:
            Normalized die package are integers without duplicates, sorted in ascending order.
        """

        allpkgs = self.get_packages()

        if packages == "all":
            return allpkgs

        allpkgs_set = set(allpkgs)
        packages = Trivial.list_dedup(packages)
        for pkg in packages:
            if type(pkg) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{pkg}' is not an integer, package numbers must be integers")

            if pkg not in allpkgs_set:
                pkgs_str = Trivial.rangify(allpkgs_set)
                raise Error(f"Package '{pkg}' is not available{self._pman.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return packages

    def normalize_cpu(self, cpu: int) -> int:
        """
        Validate single CPU number.

        Args:
            cpu: CPU number to validate.

        Returns:
            The validated CPU number.
        """

        return self.normalize_cpus((cpu,))[0]

    def normalize_core(self, core: int, package: int = 0) -> int:
        """
        Validate a core number for a given package.

        Args:
            core: Core number to validate.
            package: Package number the core belongs to (default is 0).

        Returns:
            The validated core number.
        """

        return self.normalize_cores((core,), package=package)[0]

    def normalize_die(self, die: int, package: int = 0) -> int:
        """
        Validate a die number for a given package.

        Args:
            die: Die number to validate.
            package: Package number the die belongs to (default is 0).

        Returns:
            The validated die number.
        """

        return self.normalize_dies((die,), package=package)[0]

    def normalize_package(self, package: int) -> int:
        """
        Validate a single package number.

        Args:
            package: Package number to validate.

        Returns:
            The validated package number.
        """

        return self.normalize_packages((package,))[0]

    def get_hybrid_cpus(self) -> dict[HybridCPUKeyType, list[int]]:
        """
        Return a dictionary with hybrid CPU information.

        Returns:
            HybridCPUsTypeDict: The dictionary may contain up to 2 keys:
                - "pcore": List of performance core CPU numbers.
                - "ecore": List of efficiency core CPU numbers.

        Note:
            In case of a non-hybrid system, only the "pcore" key is present.
        """

        if self.info["hybrid"] is False:
            return {"pcore": self.get_cpus()}

        return self._get_hybrid_cpus()

    @staticmethod
    def dies_to_str(dies: dict[int, list[int]]) -> str:
        """
        Convert a dictionary of package-to-die mappings into a human-readable string.

        Args:
            dies: Dictionary mapping package numbers to lists of die numbers.

        Returns:
            A string describing the dies for each package in a readable format.
        """

        dies_strs = []
        for package, pkg_dies in dies.items():
            if len(pkg_dies) > 1:
                dies_str = Trivial.rangify(pkg_dies)
                dies_strs.append(f"package {package} dies {dies_str}")
            else:
                dies_strs.append(f"package {package} die {pkg_dies[0]}")

        if len(dies_strs) > 1:
            dies_str = ", ".join(dies_strs[:-1])
            dies_str += ", and "
            dies_str += dies_strs[-1]
        else:
            dies_str = str(dies_strs[0])

        return dies_str
