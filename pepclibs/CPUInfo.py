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

# TODO: modernize this module
from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import Iterable, Literal
from pepclibs import _CPUInfoBase
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs._CPUInfoBase import SCOPE_NAMES, NA

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._CPUInfoBaseTypes import ScopeNameType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUInfo(_CPUInfoBase.CPUInfoBase):
    """
    Provide information about CPU topology and other CPU details.

    Public methods overview.

    1. Get various CPU information.
        * 'get_topology()' - CPU topology.
    2. Get list of packages/cores/etc.
        * 'get_cpus()'
        * 'get_cores()'
        * 'get_modules()'
        * 'get_dies()'
        * 'get_nodes()'
        * 'get_packages()'
        * 'get_offline_cpus()'
        * 'get_tline_by_cpu()'
        * 'get_cpu_siblings()'
    3. Get list of packages/cores/etc for a subset of CPUs/cores/etc.
        * 'package_to_cpus()'
        * 'package_to_cores()'
        * 'package_to_modules()'
        * 'package_to_dies()'
        * 'package_to_nodes()'
        * 'cores_to_cpus()'
        * 'modules_to_cpus()'
        * 'dies_to_cpus()'
        * 'nodes_to_cpus()'
        * 'packages_to_cpus()'
    4. Get packages/core/etc counts.
        * 'get_cpus_count()'
        * 'get_cores_count()'
        * 'get_modules_count()'
        * 'get_dies_count()'
        * 'get_packages_count()'
        * 'get_offline_cpus_count()'
    5. Normalize a list of packages/cores/etc.
        A. Multiple packages/CPUs/etc numbers:
            * 'normalize_cpus()'
            * 'normalize_cores()'
            * 'normalize_modules()'
            * 'normalize_dies()'
            * 'normalize_packages()'
        B. Single package/CPU/etc.
            * 'normalize_cpu()'
            * 'normalize_core()'
            * 'normalize_die()'
            * 'normalize_package()'
    6. Select CPUs by sibling index.
        * 'select_core_siblings()'
        * 'select_module_siblings()'
    7. "Divide" list of CPUs.
        * 'cpus_div_cores()' - by cores.
        * 'cpus_div_dies()' - by dies.
        * 'cpus_div_packages()' - by packages.
    8. Miscellaneous.
        * 'dies_to_str()' - turn a die numbers dictionary into a string.
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
            - die: Die number within the package, or 'NA' for I/O dies. Numbers are per-package, but
                   not globally unique.
            - node: Globally unique NUMA node number, or 'NA' for I/O dies.
            - package: Globally unique package number.

        Returns:
            The topology table.


        Examples:
            Consider the following hypothetical system:
            * 2 packages, numbers 0, 1.
            * 2 nodes, numbers 0, 1.
            * 1 die per package, numbers 0.
            * 3 modules, numbers 0, 4, 5.
            * 4 cores per package, numbers 0, 1, 5, 6.
            * 16 CPUs, numbers 0-16.

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
                * Package 0 includes die 0.
                * Package 1 includes die 1.
                * Die 0 includes cores 0 and 1.
                * Die 1 includes cores 2 and 3.
                * Core 0 includes CPUs 0 and 4
                * Core 1 includes CPUs 1 and 5
                * Core 3 includes CPUs 2 and 6
                * Core 4 includes CPUs 3 and 7

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
            return sorted(self._get_online_cpus_set())

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
            return self.normalize_cpus((cpu,))

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

    def package_to_cpus(self, package, order="CPU"):
        """
        Return list of CPU numbers in package 'package'. The arguments are as follows.
          * package - package number to return CPU numbers for.
          * order - the sorting order of the returned CPU numbers list.
        """

        return self._get_scope_nums("CPU", "package", (package,), order=order)

    def package_to_cores(self, package, order="core"):
        """
        Return list of core numbers in package 'package'. The arguments are as follows.
          * package - package number to return core numbers for.
          * order - the sorting order of the returned core numbers list.
        """

        return self._get_scope_nums("core", "package", (package,), order=order)

    def package_to_modules(self, package, order="module"):
        """
        Return list of module numbers in package 'package'. The arguments are as follows.
          * package - package number to return module numbers for.
          * order - the sorting order of the returned module numbers list.
        """

        return self._get_scope_nums("module", "package", (package,), order=order)

    def package_to_dies(self, package, order="die"):
        """
        Return list of dies numbers in package 'package'. The arguments are as follows.
          * package - package number to return dies numbers for.
          * order - the sorting order of the returned dies numbers list.

        Note, die numbers are not globally unique. They are per-package. E.g., there may be die 0 in
        packages 0 and 1.
        """

        return self._get_scope_nums("die", "package", (package,), order=order)

    def package_to_nodes(self, package, order="node"):
        """
        Return list of NUMA node numbers in package 'package'. The arguments are as follows.
          * package - package number to return node numbers for.
          * order - the sorting order of the returned node numbers list.
        """

        return self._get_scope_nums("node", "package", (package,), order=order)

    def cores_to_cpus(self, cores="all", packages="all", order="CPU"):
        """
        Return list of CPU numbers in cores 'cores' of package 'package'. The arguments are as
        follows.
          * cores - a collection of core numbers in package 'package' to return CPU numbers for.
          * packages - a collection of integer package number core numbers in 'cores' belong to.
          * order - the sorting order of the returned CPU numbers list.

        Note, core numbers are not globally unique. They are per-package. E.g., there may be core 0
        in packages 0 and 1.
        """

        by_core = self._get_scope_nums("CPU", "core", cores, order=order)
        by_package = set(self._get_scope_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_core:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def modules_to_cpus(self, modules="all", order="CPU"):
        """
        Return list of CPU numbers in modules 'modules'. The arguments are as follows.
          * modules - a collection of module numbers to return CPU numbers for.
          * order - the sorting order of the returned CPU numbers list.

        Note, module numbers are globally unique (unlike, for example, core numbers).
        """

        return self._get_scope_nums("CPU", "module", modules, order=order)

    def dies_to_cpus(self, dies="all", packages="all", order="CPU"):
        """
        Return list of CPU numbers in dies 'dies' of package 'package'. The arguments are as
        follows.
          * dies - a collection of die numbers in package 'package' to return CPU numbers for.
          * packages - a collection of integer package number die numbers in 'dies' belong to.
          * order - the sorting order of the returned CPU numbers list.

        Note, die numbers are not globally unique. They are per-package. E.g., there may be die 0
        in packages 0 and 1.
        """

        by_die = self._get_scope_nums("CPU", "die", dies, order=order)
        by_package = set(self._get_scope_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_die:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def nodes_to_cpus(self, nodes="all", order="CPU"):
        """
        Return list of CPU numbers in NUMA nodes 'nodes'. The arguments are as follows.
          * nodes - a collection of node numbers to return CPU numbers for.
          * order - the sorting order of the returned CPU numbers list.

        Note, NUMA node numbers are globally unique (unlike, for example, core numbers).
        """

        return self._get_scope_nums("CPU", "node", nodes, order=order)

    def packages_to_cpus(self, packages="all", order="CPU"):
        """
        Return list of CPU numbers in packages 'packages'. The arguments are as follows.
          * packages - a collection of package numbers to return CPU numbers for.
          * order - the sorting order of the returned CPU numbers list.

        Note, package numbers are globally unique (unlike, for example, core numbers).
        """

        return self._get_scope_nums("CPU", "package", packages, order=order)

    def get_cpus_count(self):
        """Return count of online CPUs."""

        return len(self._get_online_cpus_set())

    def get_offline_cpus_count(self):
        """Return count of offline CPUs."""

        return len(self.get_offline_cpus())

    def get_cores_count(self, package=0):
        """
        Return cores count in package 'package'. The arguments are as follows.
          * package - package number to get cores count for.

        Only core numbers containing at least one online CPU will be counted.
        """
        return len(self.get_cores(package=package))

    def get_modules_count(self):
        """
        Return modules count. Only module numbers containing at least one online CPU will be
        counted.
        """

        return len(self.get_modules())

    def get_dies_count(self, package=0, compute_dies=True, io_dies=True):
        """
        Return dies count in package 'package'. The arguments are as follows.
          * package - package number to get dies count for.
          * compute_dies - include compute dies to the result if 'True', otherwise exclude them.
                           Compute dies are the dies that have CPUs.
          * io_dies - include I/O dies to the result if 'True', otherwise exclude them. I/O dies
                      are the dies that do not have any CPUs.

        Only dies numbers containing at least one online CPU will be counted.
        """

        return len(self.get_dies(package=package, compute_dies=compute_dies, io_dies=io_dies))

    def get_packages_count(self):
        """
        Return packages count. Only package numbers containing at least one online CPU will be
        counted.
        """

        return len(self.get_packages())

    def select_core_siblings(self, cpus, indexes):
        """
        Select core siblings described by 'indexes' from 'cpus' and return the result. The arguments
        are as follows.
        * cpus - list of CPU numbers to select core siblings from. The returned result is always a
                 subset of CPU numbers from 'cpus'.
        * indexes - "indexes" of core siblings to select.

        Example.

        Suppose the system has 4 cores, and each core has 2 CPUs.
        * core 0 includes CPUs 0, 4
        * core 1 includes CPUs 1, 5
        * core 2 includes CPUs 2, 6
        * core 4 includes CPUs 3, 7

        CPUs 0 and 4, 1 and 5, 2 and 6, 3 and 7 are core siblings.
        CPUs 0, 1, 2, and 3 are core siblings with index 0.
        CPUs 4, 5, 6, and 7 are core siblings with index 1.

        Suppose the 'cpus' input argument is '[1, 2, 4, 5]'. This means that the following cores
        will participate in the selection: 0, 1, and 2.

        In order to select first core siblings from 'cpus', provide 'indexes=[0]'. The result will
        be: '[1, 2]'.

        In order to select second core siblings from 'cpus', provide 'indexes=[1]'. The result will
        be: '[4, 5]'.

        If 'indexes=[0,1]', the result will be the same as 'cpus': '[1, 2, 4, 5]'

        Note: this method ignores offline CPUs.
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)

        cpu2index = {} # CPU number -> core siblings index map.
        core = pkg = index = None

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

    def select_module_siblings(self, cpus, indexes):
        """
        Select module siblings described by 'indexes' from 'cpus' and return the result. The
        arguments are as follows.
        * cpus - list of CPU numbers to select module siblings from. The returned result is always a
                 subset of CPU numbers from 'cpus'.
        * indexes - "indexes" of module siblings to select.

        Example.

        Suppose the system has 4 modules, and each module has 4 CPUs.
        * module 0 includes CPUs 0, 1, 2, 3
        * module 1 includes CPUs 4, 5, 6, 7
        * module 2 includes CPUs 8, 9, 10, 11
        * module 4 includes CPUs 12, 13, 14, 15

        CPUs 0, 4, 8, and 12 are module siblings with index 0.
        CPUs 1, 5, 9, and 13 are module siblings with index 1.
        CPUs 2, 6, 10, and 14 are module siblings with index 2.
        CPUs 3, 7, 11, and 15 are module siblings with index 3.

        Suppose the 'cpus' input argument is '[0, 1, 2, 3, 4, 5, 8]'. This means that the following
        modules will participate in selection: 0, 1, 2.

        In order to select first module siblings from 'cpus', provide 'indexes=[0]'. The result will
        be: '[0, 4, 8]'.

        In order to select second module siblings from 'cpus', provide 'indexes=[1]'. The result
        will be: '[1, 5]'.

        If 'indexes=[0,1]', the result will be '[0, 1, 4, 5, 8]'

        Note: this method ignores offline CPUs.
        """

        cpus = self.normalize_cpus(cpus, offline_ok=True)

        cpu2index = {} # CPU number -> module siblings index map.
        module = pkg = index = None

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

    def cpus_div_cores(self, cpus):
        """
        Split CPU numbers in 'cpus' into by-core groups (an operation inverse to 'cores_to_cpus()').
        The arguments are as follows.
          * cpus - a collection of integer CPU numbers to split by core numbers.

        Return a tuple of ('cores', 'rem_cpus').
          * cores - a dictionary indexed by the package numbers with values being lists of core
                    numbers.
          * rem_cpus - list of remaining CPUs that cannot be converted to a core number.

        The return value is inconsistent with 'cpus_div_packages()' because core numbers are
        relative to package numbers.

        Consider an example of a system with 2 packages, 1 core per package, 2 CPUs per core.
          * package 0 includes core 0 and CPUs 0 and 1
          * package 1 includes core 0 and CPUs 2 and 3

        1. cpus_div_cores("0-3") would return ({0:[0], 1:[0]}, []).
        2. cpus_div_cores("2,3") would return ({1:[0]},        []).
        3. cpus_div_cores("0,3") would return ({},             [0,3]).
        """

        cores = {}
        rem_cpus = []

        cpus = self.normalize_cpus(cpus, offline_ok=True)
        cpus_set = set(cpus)

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

    def cpus_div_dies(self, cpus):
        """
        Split CPU numbers in 'cpus' into by-die groups (an operation inverse to 'dies_to_cpus()').
        The arguments are as follows.
          * cpus - a collection of integer CPU numbers to split by die numbers.

        Return a tuple of ('dies', 'rem_cpus').
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers.
          * rem_cpus - list of remaining CPUs that cannot be converted to a die number.

        The return value is inconsistent with 'cpus_div_packages()' because die numbers may be
        relative to package numbers on some systems.

        Consider an example of a system with 2 packages, 2 dies per package, 1 core per die, 2 CPUs
        per core.
          * package 0 includes dies 0 and 1 and CPUs 0, 1, 2, and 3
            - die 0 includes CPUs 0 and 1
            - die 1 includes CPUs 2 and 3
          * package 1 includes dies 0 and 1 and CPUs 4, 5, 6, and 7
            - die 0 includes CPUs 4 and 5
            - die 1 includes CPUs 6 and 7

        1. cpus_div_dies("0-3") would return   ({0:[0], 0:[1]}, []).
        2. cpus_div_dies("4,5,6") would return ({1:[1]},        [6]).
        3. cpus_div_dies("0,3") would return   ({},             [0,3]).
        """

        dies = {}
        rem_cpus = []

        cpus = self.normalize_cpus(cpus, offline_ok=True)
        cpus_set = set(cpus)

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

    def cpus_div_packages(self, cpus, packages="all"):
        """
        Split CPU numbers in 'cpus' into by-package groups (an operation inverse to
        'packages_to_cpus()'). The arguments are as follows.
          * cpus - a collection of integer CPU numbers to split by package numbers.
          * packages - package numbers to check for CPU numbers in (all packages by default).

        Return a tuple of two lists: ('packages', 'rem_cpus').
          * packages - list of packages with all CPUs present in 'cpus'.
          * rem_cpus - list of remaining CPUs that cannot be converted to a package number.

        Consider an example of a system with 2 packages and 2 CPUs per package.
          * package 0 includes CPUs 0 and 1
          * package 1 includes CPUs 2 and 3

        1. cpus_div_packages("0-3") would return ([0,1], []).
        2. cpus_div_packages("2,3") would return ([1],   []).
        3. cpus_div_packages("0,3") would return ([],    [0,3]).
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

    def normalize_cpus(self, cpus, offline_ok=False) -> list[int]:
        """
        Validate CPU numbers in 'cpus' and return a normalized list. The arguments are as follows.
          * cpus - collection of integer CPU numbers to normalize. Special value 'all' means
                   "all CPUs".
          * offline_ok - by default, offline CPUs are considered as not available and are not
                         allowed to be in 'cpus' (will cause an exception). Use 'offline_ok=True'
                         to allow for offline CPUs.
        """

        if offline_ok:
            allcpus = self._get_all_cpus_set()
        else:
            allcpus = self._get_online_cpus_set()

        if cpus == "all":
            return sorted(allcpus)

        cpus = Trivial.list_dedup(cpus)
        for cpu in cpus:
            if type(cpu) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{cpu}' is not an integer, CPU numbers must be integers")

            if cpu not in allcpus:
                cpus_str = Trivial.rangify(allcpus)
                raise Error(f"CPU {cpu} is not available{self._pman.hostmsg}, available CPUs are: "
                            f"{cpus_str}")

        return cpus

    def normalize_cores(self, cores, package=0):
        """
        Validate core numbers in 'cores' for package 'package' and return the normalized list. The
        arguments are as follows.
          * cores - collection of integer core numbers to normalize. Special value 'all' means
                    "all coress".
          * package - package number to validate the 'cores' against: all numbers in 'cores' should
                      be valid core numbers in package number 'package'.

        Return a list of integer core numbers.
        """

        pkg_cores = self.package_to_cores(package)

        if cores == "all":
            return pkg_cores

        pkg_cores = set(pkg_cores)
        cores = Trivial.list_dedup(cores)
        for core in cores:
            if type(core) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{core}' is not an integer, core numbers must be integers")

            if core not in pkg_cores:
                cores_str = Trivial.rangify(pkg_cores)
                raise Error(f"core '{core}' is not available in package "
                            f"'{package}'{self._pman.hostmsg}, available cores are: {cores_str}")

        return cores

    def normalize_modules(self, modules):
        """
        Validate module numbers in 'modules' and return the normalized list. The arguments are
        as follows.
          * modules - collection of integer module numbers to normalize. Special value 'all' means
                      "all modules".
        """

        all_modules = self.get_modules()

        if modules == "all":
            return all_modules

        all_modules = set(all_modules)
        modules = Trivial.list_dedup(modules)
        for mdl in modules:
            if type(mdl) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{mdl}' is not an integer, module numbers must be integers")

            if mdl not in all_modules:
                modules_str = Trivial.rangify(all_modules)
                raise Error(f"module '{mdl}' is not available{self._pman.hostmsg}, available "
                            f"modules are: {modules_str}")

        return modules

    def normalize_dies(self, dies, package=0):
        """
        Validate die numbers in 'dies' for package 'package' and return the normalized list. The
        arguments are as follows.
          * dies - collection of integer die numbers to normalize. Special value 'all' means
                   "all dies".
          * package - package number to validate the 'dies' against: all numbers in 'dies' should be
                      valid die numbers in package number 'package'.

        Return a list of integer die numbers.
        """

        pkg_dies = self.package_to_dies(package)

        if dies == "all":
            return pkg_dies

        pkg_dies = set(pkg_dies)
        dies = Trivial.list_dedup(dies)
        for die in dies:
            if type(die) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{die}' is not an integer, die numbers must be integers")

            if die not in pkg_dies:
                dies_str = Trivial.rangify(pkg_dies)
                raise Error(f"die '{die}' is not available in package "
                            f"'{package}'{self._pman.hostmsg}, available dies are: {dies_str}")

        return dies

    def normalize_packages(self, packages):
        """
        Validate package numbers in 'packages' and return the normalized list. The arguments are
        as follows.
          * packages - collection of integer package numbers to normalize. Special value 'all' means
                       "all packages".
        """

        allpkgs = self.get_packages()

        if packages == "all":
            return allpkgs

        allpkgs = set(allpkgs)
        packages = Trivial.list_dedup(packages)
        for pkg in packages:
            if type(pkg) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{pkg}' is not an integer, package numbers must be integers")

            if pkg not in allpkgs:
                pkgs_str = Trivial.rangify(allpkgs)
                raise Error(f"package '{pkg}' is not available{self._pman.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return packages

    def normalize_cpu(self, cpu):
        """
        Validate CPU number 'cpu'. The arguments are as follows.
          * cpu - an integer CPU number to validate.

        Return 'cpu' if it is valid, raise an 'Error' exception otherwise.
        """

        return self.normalize_cpus((cpu,))[0]

    def normalize_core(self, core, package=0):
        """
        Validate core number 'core'. The arguments are as follows.
          * core - an integer core number to validate.
          * package - package number the core belongs to.

        Return 'core' if it is valid, raise an 'Error' exception otherwise.
        """

        return self.normalize_cores((core,), package=package)[0]

    def normalize_die(self, die, package=0):
        """
        Validate die number 'die'. The arguments are as follows.
          * die - an integer die number to validate.
          * package - package number the die belongs to.

        Return 'die' if it is valid, raise an 'Error' exception otherwise.
        """

        return self.normalize_dies((die,), package=package)[0]

    def normalize_package(self, package):
        """
        Validate package number 'package'. The arguments are as follows.
          * package - an integer package number to validate.

        Return 'package' if it is valid, raise an 'Error' exception otherwise.
        """

        return self.normalize_packages((package,))[0]

    def get_hybrid_cpus(self):
        """
        Return a tuple with E-core and P-core CPU lists:
        '(<list of E-core CPU numbers>, <list of P-core CPU numbers>)'.

        Only online CPUs are included to the returned lists. If the target system is not hybrid,
        raise 'ErrorNotSupported'.
        """

        if self.info["hybrid"] is False:
            raise ErrorNotSupported(f"can't get E-core/P-core CPU information{self._pman.hostmsg}: "
                                    f"{self.cpudescr} is not a hybrid processor")

        hybrid_cpus = self._get_hybrid_cpus()
        return (list(hybrid_cpus["ecores"]), list(hybrid_cpus["pcores"]))

    @staticmethod
    def dies_to_str(dies):
        """
        Turn the die numbers dictionary into a user-readable string and return the result. The
        arguments are as follows.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers.
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
