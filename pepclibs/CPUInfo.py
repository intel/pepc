# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide information about CPU topology and other CPU details.
"""

import copy
import json
import logging
from pepclibs import _CPUInfoBase
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Trivial, Human
from pepclibs._CPUInfoBase import LEVELS, NA

_LOG = logging.getLogger()

class CPUInfo(_CPUInfoBase.CPUInfoBase):
    """
    Provide information about CPU topology and other CPU details.

    Public methods overview.

    1. Get various CPU information.
        * 'get_topology()' - CPU topology.
        * 'get_cache_info()' - CPU cache.
    2. Get list of packages/cores/etc.
        * 'get_cpus()'
        * 'get_cores()'
        * 'get_modules()'
        * 'get_dies()'
        * 'get_nodes()'
        * 'get_packages()'
        * 'get_offline_cpus()'
        * 'get_cpu_levels()'
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

    def _validate_level(self, lvl, name="level"):
        """Validate that 'lvl' is a valid level name."""

        if lvl not in self._lvl2idx:
            levels = ", ".join(LEVELS)
            raise Error(f"bad {name} name '{lvl}', use: {levels}")

    def get_topology(self, levels=None, order="CPU"):
        """
        Build and return copy of internal topology list. The topology includes dictionaries, one
        dictionary per CPU. By default each dictionary includes the following keys.
          * CPU     - CPU number.
                    - Globally unique.
          * core    - Core number.
                    - Per-package numbering, not globally unique.
                    - There can be gaps in the numbering.
          * module  - Module number.
                    - Shares same L2 cache.
                    - Globally unique.
          * die     - Die number.
                    - Per-package numbering, not globally unique.
          * node    - NUMA node number.
                    - Globally unique.
          * package - Package number.
                    - Globally unique.

        The 'levels' agreement can be used for limiting the levels this method initializes. Partial
        topology initialization is faster than full initialization. By default ('levels=None'), all
        levels are initialized.

        Example topology list for the following hypothetical system:
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

        The topology tables in node/die order will look the same (in this particular example). They
        are sorted by package number, then node/die number, then CPU number.

        Here is the topology table in core order. It'll be sorted by package number, and then core
        number, then CPU number.

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

        if not levels:
            levels = LEVELS
        else:
            for lvl in levels:
                self._validate_level(lvl, name="topology level")

        self._validate_level(order, name="order")
        topology = self._get_topology(levels=levels, order=order)
        return copy.deepcopy(topology)

    def _get_level_nums(self, sublvl, lvl, nums, order=None):
        """
        Return a list containing all sub-level 'sublvl' numbers in level 'lvl' elements with
        numbers 'nums'.

        Examples.

        1. Get CPU numbers in cores 1 and 3.
            _get_level_nums("CPU", "core", (1, 3))
        2. Get node numbers in package 1.
            _get_level_nums("node", "package", (1,))
        3. Get all core numbers.
            _get_level_nums("core", "package", "all")
            _get_level_nums("core", "node", "all")
            _get_level_nums("core", "core", "all")

        The 'order' argument defines the the order of the result (just ascending order by default).
        If 'order' contains a level name, the returned numbers will be sorted in order of that
        level.

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

        Examples.

        1. _get_level_nums("CPU", "core", "all") returns:
            * [0, 1, 2, 3, 4, 5, 6, 7]
        2. _get_level_nums("CPU", "core", "all", order="core") returns:
            * [0, 4, 1, 5, 2, 6, 3, 7]
        3. _get_level_nums("CPU", "core", (1,3), order="core") returns:
            * [1, 5, 2, 6]
        """

        if order is None:
            order = sublvl

        self._validate_level(sublvl)
        self._validate_level(lvl)
        self._validate_level(order, name="order")

        if self._lvl2idx[lvl] < self._lvl2idx[sublvl]:
            raise Error(f"bad level order, cannot get {sublvl}s from level '{lvl}'")

        if nums != "all":
            # Valid 'nums' should be an integer or a collection of integers. At this point, just
            # turn 'nums' into a set. Possible non-integers in the set will be detected later.
            try:
                nums = set(nums)
            except TypeError:
                nums = set([nums])

        result = {}
        valid_nums = set()

        for tline in self._get_topology(levels=(lvl, sublvl), order=order):
            if tline[lvl] == NA:
                continue
            valid_nums.add(tline[lvl])
            if tline[sublvl] == NA:
                continue
            if nums == "all" or tline[lvl] in nums:
                result[tline[sublvl]] = None

        # Validate the input numbers in 'nums'.
        if nums == "all":
            return list(result)

        if not nums.issubset(valid_nums):
            valid = Human.rangify(valid_nums)
            invalid = Human.rangify(nums - valid_nums)
            raise Error(f"{lvl} {invalid} do not exist{self._pman.hostmsg}, valid {lvl} numbers "
                        f"are: {valid}")

        return list(result)

    def get_cpus(self, order="CPU"):
        """Return list of online CPU numbers."""

        if order == "CPU":
            return sorted(self._read_online_cpus())

        return self._get_level_nums("CPU", "CPU", "all", order=order)

    def get_cores(self, package=0, order="core"):
        """
        Return list of core numbers in package 'package', only cores containing at least one online
        CPU will be included.
        """
        return self._get_level_nums("core", "package", package, order=order)

    def get_modules(self, order="module"):
        """
        Return list of module numbers, only modules containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("module", "module", "all", order=order)

    def get_dies(self, package=0, order="die", compute_dies=True, io_dies=True):
        """
        Return list of die numbers in package 'package'. The arguments are as follows.
          * package - package number to return the list of dies for.
          * order - the sorting order of the result.
          * compute_dies - include compute dies to the result if 'True', otherwise exclude them.
                           Compute dies are the dies that have CPUs.
          * io_dies - include I/O dies to the result if 'True', otherwise exclude them. I/O dies
                      are the dies that do not have any CPUs.

        Only dies containing at least one online CPU will be included to the result.
        """

        dies = self._get_level_nums("die", "package", package, order=order)
        if compute_dies and io_dies:
            return dies

        if compute_dies:
            compute_dies = []
            for die in dies:
                if die in self._compute_dies[package]:
                    compute_dies.append(die)
            return compute_dies

        io_dies = []
        for die in dies:
            if die in self._io_dies[package]:
                io_dies.append(die)
        return io_dies

    def get_nodes(self, order="node"):
        """
        Return list of node numbers, only nodes containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("node", "node", "all", order=order)

    def get_packages(self, order="package"):
        """
        Return list of package numbers, only packages containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("package", "package", "all", order=order)

    def _get_all_cpus(self):
        """Return set of online and offline CPU numbers."""

        if not self._all_cpus:
            self._all_cpus = set(self._read_range("/sys/devices/system/cpu/present"))
        return self._all_cpus

    def get_offline_cpus(self):
        """Return list of offline CPU numbers sorted in ascending order."""

        cpus = self._get_all_cpus()
        online_cpus = self._read_online_cpus()
        return list(cpu for cpu in cpus if cpu not in online_cpus)

    def cpus_hotplugged(self):
        """This method informs CPUInfo to update online/offline CPUs and topology lists."""

        self._cpus = None
        self._hybrid_cpus = None
        if self._topology:
            self._must_update_topology = True

    def get_cpu_levels(self, cpu, levels=None):
        """
        Return a dictionary of levels an online CPU 'cpu' belongs to. By default all levels are
        included.
        """

        cpu = Trivial.str_to_int(cpu, what="CPU number")
        if not levels:
            levels = LEVELS

        tline = None
        for tline in self._get_topology(levels=levels):
            if cpu == tline["CPU"]:
                break
        else:
            raise Error(f"CPU {cpu} is not available{self._pman.hostmsg}")

        result = {}
        for lvl in levels:
            result[lvl] = tline[lvl]
        return result

    def get_cpu_siblings(self, cpu, level):
        """
        Return a list of 'level' siblings. The arguments are as follows:
         * cpu - the CPU whose siblings to return.
         * level - the siblings level (e.g. "package", "core").

        For example, if 'level' is "package", this method returns a list of CPUs sharing the same
        package as CPU 'cpu'.
        """

        if level == "CPU":
            return self.normalize_cpus((cpu,))

        if level == "global":
            return self.get_cpus()

        levels = self.get_cpu_levels(cpu, levels=(level, "package"))
        if level == "package":
            return self.package_to_cpus(levels[level])
        if level == "node":
            return self.nodes_to_cpus(levels[level])
        if level == "die":
            return self.dies_to_cpus(dies=levels[level], packages=levels["package"])
        if level == "module":
            return self.modules_to_cpus(levels[level])
        if level == "core":
            return self.cores_to_cpus(cores=levels[level], packages=levels["package"])

        raise Error(f"unsupported scope name \"{level}\"")

    def package_to_cpus(self, package, order="CPU"):
        """Return list of cpu numbers belonging to package 'package', sorted by 'order'."""
        return self._get_level_nums("CPU", "package", (package,), order=order)

    def package_to_cores(self, package, order="core"):
        """Similar to 'package_to_cpus()', but for cores."""
        return self._get_level_nums("core", "package", (package,), order=order)

    def package_to_modules(self, package, order="module"):
        """Similar to 'package_to_cpus()', but for modules."""
        return self._get_level_nums("module", "package", (package,), order=order)

    def package_to_dies(self, package, order="die"):
        """Similar to 'package_to_cpus()', but for dies."""
        return self._get_level_nums("die", "package", (package,), order=order)

    def package_to_nodes(self, package, order="node"):
        """Similar to 'package_to_cpus()', but for nodes."""
        return self._get_level_nums("node", "package", (package,), order=order)

    def cores_to_cpus(self, cores="all", packages="all", order="CPU"):
        """
        Return list of online CPU numbers belonging to cores 'cores' in packages 'packages'.

        Note: core numbers are per-package.
        """

        by_core = self._get_level_nums("CPU", "core", cores, order=order)
        by_package = set(self._get_level_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_core:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def modules_to_cpus(self, modules="all", order="CPU"):
        """Return list of online CPU numbers belonging to modules 'modules'."""
        return self._get_level_nums("CPU", "module", modules, order=order)

    def dies_to_cpus(self, dies="all", packages="all", order="CPU"):
        """
        Return list of online CPU numbers belonging to dies 'dies' in packages 'packages'.
        Note: die numbers are per-package.
        """

        by_die = self._get_level_nums("CPU", "die", dies, order=order)
        by_package = set(self._get_level_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_die:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def nodes_to_cpus(self, nodes="all", order="CPU"):
        """Return list of online CPU numbers belonging to nodes 'nodes'."""
        return self._get_level_nums("CPU", "node", nodes, order=order)

    def packages_to_cpus(self, packages="all", order="CPU"):
        """Return list of online CPU numbers belonging to packages 'packages'."""
        return self._get_level_nums("CPU", "package", packages, order=order)

    def get_cpus_count(self):
        """Return count of online CPUs."""
        return len(self._read_online_cpus())

    def get_cores_count(self, package=0):
        """
        Return cores count in a package. The arguments are as follows.
          * package - package number to get cores count for.
        """
        return len(self.get_cores(package=package))

    def get_modules_count(self):
        """Return modules count."""
        return len(self.get_modules())

    def get_dies_count(self, package=0, compute_dies=True, io_dies=True):
        """
        Return dies count in a package. The arguments are as follows.
          * package - package number to get dies count for.
          * compute_dies - include compute dies to the result if 'True', otherwise exclude them.
                           Compute dies are the dies that have CPUs.
          * io_dies - include I/O dies to the result if 'True', otherwise exclude them. I/O dies
                      are the dies that do not have any CPUs.

        Only dies containing at least one online CPU will be counted.
        """

        return len(self.get_dies(package=package, compute_dies=compute_dies, io_dies=io_dies))

    def get_packages_count(self):
        """Return packages count."""
        return len(self.get_packages())

    def get_offline_cpus_count(self):
        """Return count of offline CPUs."""
        return len(self.get_offline_cpus())

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

        for tline in self._get_topology(levels=("CPU", "core", "package"), order="core"):
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

        for tline in self._get_topology(levels=("CPU", "module", "package"), order="module"):
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
        This method is similar to 'cpus_div_packages()', but it checks which CPU numbers in 'cpus'
        cover entire core(s). So it is inverse to the 'cores_to_cpus()' method. The arguments are as
        follows.
          * cpus - same as in 'normalize_cpus()'.

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
        This method is similar to 'cpus_div_packages()', but it checks which CPU numbers in 'cpus'
        cover entire die(s). So it is inverse to the 'dies_to_cpus()' method. The arguments are as
        follows.
          * cpus - same as in 'normalize_cpus()'.

        Return a tuple of ('dies', 'rem_cpus').
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers.
          * rem_cpus - list of remaining CPUs that cannot be converted to a die number.

        The return value is inconsistent with 'cpus_div_packages()' because die numbers are
        relative to package numbers.

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
        Check which CPU numbers in 'cpus' cover entire package(s). In other words, this method is
        inverse to 'packages_to_cpus()' and turns list of CPUs into a list of packages. The
        arguments are as follows.
          * cpus - same as in 'normalize_cpus()'.
          * packages - the packages to check for CPU numbers in.

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

    def normalize_cpus(self, cpus, offline_ok=False):
        """
        Validate CPU numbers in 'cpus' and return a normalized list. The arguments are as follows.
          * cpus - collection of integer CPU numbers to normalize. Special value 'all' means
                   "all CPUs".
          * offline_ok - by default, offline CPUs are considered as not available and are not
                         allowed to be in 'cpus' (will cause an exception). Use 'offline_ok=True'
                         to allow for offline CPUs.
        """

        if offline_ok:
            allcpus = self._get_all_cpus()
        else:
            allcpus = self._read_online_cpus()

        if cpus == "all":
            return sorted(allcpus)

        cpus = Trivial.list_dedup(cpus)
        for cpu in cpus:
            if type(cpu) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{cpu}' is not an integer, CPU numbers must be integers")

            if cpu not in allcpus:
                cpus_str = Human.rangify(allcpus)
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
                cores_str = Human.rangify(pkg_cores)
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
                modules_str = Human.rangify(all_modules)
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
                dies_str = Human.rangify(pkg_dies)
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
                pkgs_str = Human.rangify(allpkgs)
                raise Error(f"package '{pkg}' is not available{self._pman.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return packages

    def normalize_cpu(self, cpu):
        """Same as 'normalize_cpus()', but for a single CPU number."""
        return self.normalize_cpus((cpu,))[0]

    def normalize_core(self, core, package=0):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_cores((core,), package=package)[0]

    def normalize_die(self, die, package=0):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_dies((die,), package=package)[0]

    def normalize_package(self, package):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_packages((package,))[0]

    def get_hybrid_cpu_topology(self):
        """
        Return P-core/E-core information on hybrid in case of a hybrid Intel system (e.g., Alder
        Lake). The returned dictionary has the following format.

            {"ecore": <list of E-core CPU numbers>,
             "pcore": <list of P-core CPU numbers>}

        If the target system is not hybrid, return 'None'. Only online CPUs are included to the
        returned lists.
        """

        if self.info["hybrid"] is False:
            return None

        if not self._hybrid_cpus:
            self._hybrid_cpus = {}
            for arch, name in (("atom", "ecore"), ("core", "pcore")):
                self._hybrid_cpus[name] = self._read_range(f"/sys/devices/cpu_{arch}/cpus")

        return self._hybrid_cpus

    def get_cache_info(self):
        """
        Return a dictionary including CPU cache information. The dictionary keys and layout is
        similar to what the following command provides: 'lscpu --json --caches'.
        """

        if self._cacheinfo:
            return self._cacheinfo

        cmd = "lscpu --caches --json --bytes"
        stdout, _ = self._pman.run_verify(cmd)

        try:
            cacheinfo = json.loads(stdout)
        except Exception as err:
            msg = Error(err).indent(2)
            raise Error(f"failed parse output of '{cmd}' command{self._pman.hostmsg}:\n{msg}\n"
                        f"The output of the command was:\n{stdout}") from None

        self._cacheinfo = {}

        # Change dictionary structure from a list of dictionaries to a dictionary of dictionaries.
        for info in cacheinfo["caches"]:
            name = info["name"]
            if name in self._cacheinfo:
                raise Error(f"BUG: multiple caches with name '{name}'")

            self._cacheinfo[name] = {}
            # Turn size values from strings to integers amount bytes.
            for key, val in info.items():
                if Trivial.is_int(val):
                    self._cacheinfo[name][key] = int(val)
                else:
                    self._cacheinfo[name][key] = val

        return self._cacheinfo

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
                dies_str = Human.rangify(pkg_dies)
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

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        super().__init__(pman=pman)

        # Level name to its index number.
        self._lvl2idx = {lvl: idx for idx, lvl in enumerate(LEVELS)}

        # CPU cache information dictionary.
        self._cacheinfo = None
        # Set of online and offline CPUs.
        self._all_cpus = None
        # Dictionary of P-core/E-core CPUs.
        self._hybrid_cpus = None
