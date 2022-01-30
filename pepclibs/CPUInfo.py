# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides an API to get CPU information.
"""

import re
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from pepclibs.helperlibs import ArgParse, Procs, Trivial, FSHelpers

# CPU model numbers.
#
# Xeons.
INTEL_FAM6_SAPPHIRERAPIDS_X = 0x8F     # Sapphire Rapids Xeon.
INTEL_FAM6_ICELAKE_X = 0x6A            # Ice Lake Xeon.
INTEL_FAM6_ICELAKE_D = 0x6C            # Ice Lake Xeon D.
INTEL_FAM6_SKYLAKE_X = 0x55            # Skylake, Cascade Lake, and Cooper Lake Xeon.
INTEL_FAM6_BROADWELL_X = 0x4F          # Broadwell Xeon.
INTEL_FAM6_BROADWELL_G = 0x47          # Broadwell Xeon with Graphics.
INTEL_FAM6_BROADWELL_D = 0x56          # Broadwell Xeon-D.
INTEL_FAM6_HASWELL_X = 0x3F            # Haswell Xeon.
INTEL_FAM6_HASWELL_G = 0x46            # Haswell Xeon with Graphics.
INTEL_FAM6_IVYBRIDGE_X = 0x3E          # Ivy Town Xeon.
INTEL_FAM6_SANDYBRIDGE_X = 0x2D        # SandyBridge Xeon.
INTEL_FAM6_WESTMERE_EP = 0x2C          # Westmere 2S Xeon.
INTEL_FAM6_WESTMERE_EX = 0x2F          # Westmere 4S Xeon.
INTEL_FAM6_NEHALEM_EP = 0x1A           # Nehalem 2S Xeon.
INTEL_FAM6_NEHALEM_EX = 0x2E           # Nehalem 4S Xeon.

# Clients.
INTEL_FAM6_ROCKETLAKE = 0xA7           # Rocket lake client.
INTEL_FAM6_ALDERLAKE = 0x97            # Alder Lake client.
INTEL_FAM6_ALDERLAKE_L = 0x9A          # Alder Lake mobile.
INTEL_FAM6_TIGERLAKE = 0x8D            # Tiger Lake client.
INTEL_FAM6_TIGERLAKE_L = 0x8C          # Tiger Lake mobile.
INTEL_FAM6_LAKEFIELD = 0x8A            # Lakefield client.
INTEL_FAM6_ICELAKE = 0x7D              # IceLake client.
INTEL_FAM6_ICELAKE_L = 0x7E            # Ice Lake mobile.
INTEL_FAM6_COMETLAKE = 0xA5            # Comet Lake client.
INTEL_FAM6_COMETLAKE_L = 0xA6          # Comet Lake mobile.
INTEL_FAM6_KABYLAKE = 0x9E             # Kaby Lake client.
INTEL_FAM6_KABYLAKE_L = 0x8E           # Kaby Lake mobile.
INTEL_FAM6_CANNONLAKE_L = 0x66         # Cannonlake mobile.
INTEL_FAM6_SKYLAKE = 0x5E              # Skylake client.
INTEL_FAM6_SKYLAKE_L = 0x4E            # Skylake mobile.
INTEL_FAM6_BROADWELL = 0x3D            # Broadwell client.
INTEL_FAM6_HASWELL = 0x3C              # Haswell client.
INTEL_FAM6_HASWELL_L = 0x45            # Haswell mobile.
INTEL_FAM6_IVYBRIDGE = 0x3A            # IvyBridge client.
INTEL_FAM6_SANDYBRIDGE = 0x2A          # SandyBridge client.
INTEL_FAM6_WESTMERE = 0x25             # Westmere client.
INTEL_FAM6_NEHALEM_G = 0x1F            # Nehalem client with graphics (Auburndale, Havendale).
INTEL_FAM6_NEHALEM = 0x1E              # Nehalem client.
INTEL_FAM6_CORE2_MEROM = 0x0F          # Intel Core 2.

# Atoms.
INTEL_FAM6_ATOM_TREMONT = 0x96         # Elkhart Lake.
INTEL_FAM6_ATOM_TREMONT_L = 0x9C       # Jasper Lake.
INTEL_FAM6_ATOM_GOLDMONT = 0x5C        # Apollo Lake.
INTEL_FAM6_ATOM_GOLDMONT_PLUS = 0x7A   # Gemini Lake.
INTEL_FAM6_ATOM_AIRMONT = 0x4C         # Cherry Trail, Braswell.
INTEL_FAM6_ATOM_SILVERMONT = 0x37      # Bay Trail, Valleyview.
INTEL_FAM6_ATOM_SILVERMONT_MID = 0x4A  # Merriefield.
INTEL_FAM6_ATOM_SILVERMONT_MID1 = 0x5A # Moorefield.
INTEL_FAM6_ATOM_SALTWELL = 0x36        # Cedarview.
INTEL_FAM6_ATOM_SALTWELL_MID = 0x27    # Penwell.
INTEL_FAM6_ATOM_SALTWELL_TABLET = 0x35 # Cloverview.
INTEL_FAM6_ATOM_BONNELL_MID = 0x26     # Silverthorne, Lincroft.
INTEL_FAM6_ATOM_BONNELL = 0x1C         # Diamondville, Pineview.

# Atom microservers.
INTEL_FAM6_TREMONT_D = 0x86            # Snow Ridge, Jacobsville.
INTEL_FAM6_GOLDMONT_D = 0x5F           # Denverton, Harrisonville.
INTEL_FAM6_ATOM_SILVERMONT_D = 0x4D    # Avaton, Rangely.

# Other.
INTEL_FAM6_ICELAKE_NNPI = 0x9D         # Ice Lake Neural Network Processor.
INTEL_FAM6_XEON_PHI_KNM = 0x85         # Knights Mill.
INTEL_FAM6_XEON_PHI_KNL = 0x57         # Knights Landing.

#
# Various handy combinations of CPU models.
#
SPRS =         (INTEL_FAM6_SAPPHIRERAPIDS_X,)
ROCKETLAKES =  (INTEL_FAM6_ROCKETLAKE,)
ALDERLAKES =   (INTEL_FAM6_ALDERLAKE,
                INTEL_FAM6_ALDERLAKE_L,)
TIGERLAKES =   (INTEL_FAM6_TIGERLAKE,
                INTEL_FAM6_TIGERLAKE_L,)
LAKEFIELDS =   (INTEL_FAM6_LAKEFIELD,)
ICELAKES =     (INTEL_FAM6_ICELAKE,
                INTEL_FAM6_ICELAKE_L,
                INTEL_FAM6_ICELAKE_D,
                INTEL_FAM6_ICELAKE_X,)
COMETLAKES =   (INTEL_FAM6_COMETLAKE,
                INTEL_FAM6_COMETLAKE_L,)
KABYLAKES =    (INTEL_FAM6_KABYLAKE,
                INTEL_FAM6_KABYLAKE_L,)
CANNONLAKES =  (INTEL_FAM6_CANNONLAKE_L,)
SKYLAKES =     (INTEL_FAM6_SKYLAKE,
                INTEL_FAM6_SKYLAKE_L,
                INTEL_FAM6_SKYLAKE_X,)
BROADWELLS =   (INTEL_FAM6_BROADWELL,
                INTEL_FAM6_BROADWELL_G,
                INTEL_FAM6_BROADWELL_D,
                INTEL_FAM6_BROADWELL_X,)
HASWELLS =     (INTEL_FAM6_HASWELL,
                INTEL_FAM6_HASWELL_L,
                INTEL_FAM6_HASWELL_G,
                INTEL_FAM6_HASWELL_X,)
IVYBRIDGES =   (INTEL_FAM6_IVYBRIDGE,
                INTEL_FAM6_IVYBRIDGE_X,)
SANDYBRIDGES = (INTEL_FAM6_SANDYBRIDGE,
                INTEL_FAM6_SANDYBRIDGE_X,)
WESTMERES =    (INTEL_FAM6_WESTMERE,
                INTEL_FAM6_WESTMERE_EP,
                INTEL_FAM6_WESTMERE_EX,)
NEHALEMS =     (INTEL_FAM6_NEHALEM,
                INTEL_FAM6_NEHALEM_G,
                INTEL_FAM6_NEHALEM_EP,
                INTEL_FAM6_NEHALEM_EX)

TREMONTS =     (INTEL_FAM6_ATOM_TREMONT,
                INTEL_FAM6_ATOM_TREMONT_L,
                INTEL_FAM6_TREMONT_D,)
GOLDMONTS =    (INTEL_FAM6_ATOM_GOLDMONT,
                INTEL_FAM6_GOLDMONT_D,
                INTEL_FAM6_ATOM_GOLDMONT_PLUS,)
AIRMONTS =     (INTEL_FAM6_ATOM_AIRMONT,)
SILVERMONTS =  (INTEL_FAM6_ATOM_SILVERMONT,
                INTEL_FAM6_ATOM_SILVERMONT_MID,
                INTEL_FAM6_ATOM_SILVERMONT_MID1,
                INTEL_FAM6_ATOM_SILVERMONT_D,)

PHIS =         (INTEL_FAM6_XEON_PHI_KNL,
                INTEL_FAM6_XEON_PHI_KNM,)

# CPU model description. Note, we keep only relatively new CPUs here, because for released CPUs
# model name is available from the OS.
_CPU_DESCR = {INTEL_FAM6_SAPPHIRERAPIDS_X: "Sapphire Rapids Xeon",
              INTEL_FAM6_ALDERLAKE:        "Alder Lake client",
              INTEL_FAM6_ALDERLAKE_L:      "Alder Lake mobile",
              INTEL_FAM6_TREMONT_D:        "Tremont Atom (Snow Ridge)"}

# The levels names have to be the same as "scope" names in 'PStates', 'CStates', etc.
LEVELS = ("package", "die", "node", "core", "CPU")

class CPUInfo:
    """
    Provide information about the CPU of a local or remote host.

    Public methods overview.

    1. Get list of packages/cores/etc.
        * 'get_packages()'
        * 'get_cpus()'
        * 'get_offline_cpus()'
        * 'get_cpu_siblings()'
    2. Get list of packages/cores/etc for a subset of CPUs/cores/etc.
        * 'packages_to_cpus()'
        * 'package_to_dies()'
        * 'package_to_nodes()'
        * 'package_to_cores()'
        * 'cores_to_cpus()'
    3. Get packages/core/etc counts.
        * 'get_packages_count()'
        * 'get_cpus_count()'
        * 'get_offline_cpus_count()'
    4. Normalize a list of packages/cores/etc.
        A. Multiple packages/CPUs/etc numbers:
            * 'normalize_packages()'
            * 'normalize_cpus()'
        B. Single package/CPU/etc.
            * 'normalize_package()'
            * 'normalize_cpu()'
    """

    def _get_cpu_die(self, cpu):
        """Returns the die number for CPU number in 'cpu'."""

        if self._no_die_info:
            # Just assume there is one die per package.
            return 0

        if cpu in self._die_cache:
            return self._die_cache[cpu]

        sysfs_base = Path(self._topology_sysfs_base % cpu)

        # Get the CPU die number.
        die_id_path = sysfs_base / "die_id"
        try:
            die = FSHelpers.read(die_id_path, proc=self._proc)
        except ErrorNotFound:
            # The file does not exist.
            self._no_die_info = True
            return 0

        die = int(die)

        # Get the list of CPUs belonging to the same die.
        cpus = FSHelpers.read(sysfs_base / "die_cpus_list", proc=self._proc)
        cpus = ArgParse.parse_int_list(cpus, ints=True)

        # Save the list of CPUs in the case.
        for cpunum in cpus:
            self._die_cache[cpunum] = die

        return die

    def _get_topology(self, order="CPU"):
        """
        Build and return the topology list. Here is an example topology list for the following
        hypothetical system:
          * 2 packages, numbers 0, 1 (global numbering).
          * 1 die, numbers 0, 1 (global numbering).
          * 1 node per package, numbers 0, 1 (global numbering)
          * 4 cores per package, numbers 0, 1, 5, 6 (cores 2, 3, 4 do not exist). Non-global
          *   numbering.
          * 2 CPUs per core. Total 16 CPUs, numbers 0-16 (global numbering).

        Here is the topology table in package order. It is sorted by package and CPU.

		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 0,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 2,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 4,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 6,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 8,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 10, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 12, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 14, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 1,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 3,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 5,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 7,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 9,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 11, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 13, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 15, 'online': True},

        The topology tables in node/die order will look the same (in this particular example). They
        are sorted by package number, then node/die number, then CPU number.

        Here is the topology table in core order. It'll be sorted by package number, and then core
        number, then CPU number.

		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 0,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 8,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 4,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 12, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 6,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 14, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 2,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 10, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 1,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 9,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 5,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 13, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 7,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 15, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 3,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 11, 'online': True},

        Here is the topology table in CPU order. It'll be sorted by CPU number and then package
        number.

		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 0,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 1,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 2,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 3,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 4,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 5,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 6,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 7,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 0, 'CPU': 8,  'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 0, 'CPU': 9,  'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 6, 'CPU': 10, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 6, 'CPU': 11, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 1, 'CPU': 12, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 1, 'CPU': 13, 'online': True},
		  {'package': 0, 'die': 0, 'node': 0, 'core': 5, 'CPU': 14, 'online': True},
		  {'package': 1, 'die': 1, 'node': 1, 'core': 5, 'CPU': 15, 'online': True},
        """

        if self._topology:
            return self._topology[order]

        # Note, we could just walk sysfs, but 'lscpu' is faster.
        cmd = "lscpu --physical --all -p=socket,node,core,cpu,online"
        lines, _ = self._proc.run_verify(cmd, join=False)

        # Prepare the list of levels excluding the "die" level for parsing 'lscpu' output, which
        # does not include die information.
        levels = [lvl for lvl in LEVELS if lvl != "die"]

        topology = []
        for line in lines:
            if line.startswith("#"):
                continue

            # Each line has comma-separated integers for socket, node, core and CPU. For example:
            # 1,1,9,61,Y. In case of offline CPU, the final element is going to be "N", for example:
            # ,-,,61,N. Note, only the "CPU" level is known for offline CPUs.
            vals = line.strip().split(",")

            tline = {lvl : None for lvl in LEVELS}
            tline["online"] = vals[-1] == "Y"

            for key, val in zip(levels, vals):
                # For offline CPUs all levels except for the "CPU" level will be 'None'.
                if key == "CPU" or tline["online"]:
                    tline[key] = int(val)

            tline["die"] = self._get_cpu_die(tline["CPU"])

            topology.append(tline)

        # We are going to store 4 versions of the table, sorted in different order. The package and
        # CPU orders are obvious. Package and CPU numbers are global, so this is the easy case.
        # Note and core numbers are not necessarily global, therefore we always first sort by
        # package.
        sorting_map = {"package" : ("package", "CPU"),
                       "node"    : ("package", "node", "CPU"),
                       "die"     : ("package", "die", "CPU"),
                       "core"    : ("package", "core", "CPU"),
                       "CPU"     : ("CPU", "package")}

        def sort_func(tline):
            """
            The sorting function. It receives a topology line and returns the sorting key for
            'sorted()'. The returned key is a tuple with numbers, and 'sorted()' method will sort by
            the these returned tuples.

            The first element of the returned tuples is a bit tricky. For online CPUs, it'll be
            'True', and for offline CPUs it'll be 'False'. This will make sure that topology lines
            corresponding to offline CPUs will always go last.
            """

            vals = (tline[skey] for skey in skeys) # pylint: disable=undefined-loop-variable
            return (not tline["online"], *vals)

        for lvl, skeys in sorting_map.items():
            self._topology[lvl] = sorted(topology, key=sort_func)

        return self._topology[order]

    def _check_level(self, lvl, name="level"):
        """Validate that 'lvl' is a valid level name."""

        if lvl not in self._lvl2idx:
            levels = ", ".join(LEVELS)
            raise Error(f"bad {name} name '{lvl}', use: {levels}")

    def _get_level_nums(self, sublvl, lvl, nums, order=None):
        """
        Returns a list containing all sub-level 'sublvl' numbers in level 'lvl' elements with
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

        Assume a system with 2 packages, 1 die perpackage, 2 cores per package, and 2 CPUs per core:
            * Package 0 includes die 0.
            * Package 1 includes die 1.
            * Package 0 includes cores 1 and 2.
            * Package 1 includes cores 2 and 3.
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

        self._check_level(sublvl)
        self._check_level(lvl)
        self._check_level(order, name="order")

        if self._lvl2idx[lvl] > self._lvl2idx[sublvl]:
            raise Error(f"bad level order, cannot get {sublvl}s from level '{lvl}'")

        if nums != "all":
            nums = set(ArgParse.parse_int_list(nums, ints=True, dedup=True, sort=True))

        result = {}
        valid_nums = set()

        for tline in self._get_topology(order=order):
            if not tline["online"]:
                continue

            valid_nums.add(tline[lvl])
            if nums == "all" or tline[lvl] in nums:
                result[tline[sublvl]] = None

        # Validate the input numbers in 'nums'.
        if nums == "all":
            return list(result)

        for num in nums:
            if num not in valid_nums:
                valid_nums_str = ", ".join([str(num) for num in valid_nums])
                raise Error(f"{lvl} {num} does not exist{self._proc.hostmsg}.\n"
                            f"Valid {lvl} numbers are:: {valid_nums_str}")

        return list(result)

    def get_packages(self, order="package"):
        """
        Returns list of package numbers sorted in ascending order. The 'order' argument must always
        be "package". It exists only for consistency with 'get_cpus()'.

        Important: if a package has all CPUs offline, the package number will not be included in the
        returned list.
        """

        return self._get_level_nums("package", "package", "all", order=order)

    def get_dies(self, package=0, order="die"):
        """
        Returns list of dies numbers in package 'package'. The returned list is sorted in ascending
        order. The 'order' argument must always be "dies". It exists only for consistency with
        'get_cpus()'.

        Important: if a 'die' has all CPUs offline, the die number will not be included in the
        returned list.
        """

        return self._get_level_nums("die", "package", package, order=order)

    def get_cpus(self, order="CPU"):
        """
        Returns list of online CPU numbers. The numbers are sored in ascending order by default. The
        'order' argument can be one of:
          * "package" - sort in ascending package order.
          * "node" - sort in ascending node order.
          * "core" - sort in ascending core order.
          * "CPU" - sort in ascending CPU order (same as default).
        """

        return self._get_level_nums("CPU", "CPU", "all", order=order)

    def get_offline_cpus(self):
        """Returns list of offline CPU numbers sorted in ascending order."""

        cpus = []
        for tline in self._get_topology(order="CPU"):
            if not tline["online"]:
                cpus.append(tline["CPU"])

        return sorted(cpus)

    def get_cpu_siblings(self, cpu):
        """
        Returns list of online CPUs belonging to the same core as CPU 'cpu' (including CPU 'cpu').
        The list is sorted in ascending order.
        """

        cpu = self.normalize_cpu(cpu)

        tline = None
        for tline in self._get_topology(order="CPU"):
            if not tline["online"]:
                continue
            if cpu == tline["CPU"]:
                break
        else:
            raise Error("CPU {cpu} is not available{self._proc.hostmsg}")

        siblings = []
        for tline1 in self._get_topology(order="CPU"):
            if not tline1["online"]:
                continue

            if tline["package"] == tline1["package"] and tline["core"] == tline1["core"]:
                siblings.append(tline1["CPU"])

        return siblings

    def packages_to_cpus(self, packages="all", order="CPU"):
        """
        Returns list of online CPU numbers belonging to packages 'packages'. The 'packages' argument
        is similar to the one in 'normalize_packages()'. The 'order' argument is the same as in
        'get_cpus()'. By default, the result sorted in ascending order.
        """
        return self._get_level_nums("CPU", "package", packages, order=order)

    def cores_to_cpus(self, cores="all", packages="all", order="CPU"):
        """
        Returns list of online CPU numbers belonging to cores 'cores' in packages 'packages'. The
        'cores' and 'packages' arguments are similar to the 'packages' argument in
        'normalize_packages()'. The 'order' argument is the same as in 'get_cpus()'. By default, the
        result sorted in ascending order.
        """

        by_core = self._get_level_nums("CPU", "core", cores, order=order)
        by_package = set(self._get_level_nums("CPU", "package", packages))

        cpus = []
        for cpu in by_core:
            if cpu in by_package:
                cpus.append(cpu)

        return cpus

    def package_to_dies(self, package, order="die"):
        """
        Returns list of die numbers belonging to package 'package'. The 'order' argument can
        only be "die", and it exists only for compatibility with other methods, such as
        'package_to_cores()'.
        """
        return self._get_level_nums("die", "package", (package,), order=order)

    def package_to_nodes(self, package, order="node"):
        """
        Returns list of NUMA node numbers belonging to package 'package'. The 'order' argument can
        only be "node", and it exists only for compatibility with other methods, such as
        'package_to_cores()'.
        """
        return self._get_level_nums("node", "package", (package,), order=order)

    def package_to_cores(self, package, order="core"):
        """
        Returns list of cores numbers belonging to package 'package'. The 'order' argument can be
        one of:
           * "node" - sort in ascending node order.
           * "core" - sort in ascending core order (same as default).
        """
        return self._get_level_nums("core", "package", (package,), order=order)

    def get_packages_count(self):
        """Returns packages count."""
        return len(self.get_packages())

    def get_cpus_count(self):
        """Returns count of online CPUs."""
        return len(self.get_cpus())

    def get_offline_cpus_count(self):
        """Returns count of offline CPUs."""
        return len(self.get_offline_cpus())

    def normalize_packages(self, packages):
        """
        Validate package numbers in 'packages' and return the normalized list. The input package
        numbers may be integers or strings containing integer numbers. It may also be a string with
        comma-separated package numbers and ranges. This is similar to the 'cpus' argument in
        'normalize_cpus()'.

        Returns a list of integer package numbers.
        """

        allpkgs = self.get_packages()

        if packages == "all":
            return allpkgs

        allpkgs = set(allpkgs)
        packages = ArgParse.parse_int_list(packages, ints=True, dedup=True)
        for pkg in packages:
            if pkg not in allpkgs:
                pkgs_str = ", ".join([str(pkg) for pkg in sorted(allpkgs)])
                raise Error(f"package '{pkg}' not available{self._proc.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return packages

    def normalize_package(self, package):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_packages([package])[0]

    def normalize_dies(self, dies, package=0):
        """
        Validate die numbers in 'dies' for package 'package' and return the normalized list. The
        arguments are as follows.
          * dies - similar to 'packages' in 'normalize_packages()', but contains die numbers.
          * package - package number to validate the 'dies' against: all numbers in 'dies' should be
            valid die numbers in package number 'package'.

        Returns a list of integer die numbers.
        """

        pkg_dies = self.package_to_dies(package)

        if dies == "all":
            return pkg_dies

        pkg_dies = set(pkg_dies)
        dies = ArgParse.parse_int_list(dies, ints=True, dedup=True)
        for die in dies:
            if die not in pkg_dies:
                dies_str = ", ".join([str(pkg) for pkg in sorted(pkg_dies)])
                raise Error(f"die '{die}' is not available in package "
                            f"'{package}'{self._proc.hostmsg}, available dies are: {dies_str}")

        return dies

    def normalize_cpus(self, cpus, offlined_ok=False):
        """
        Validate CPU numbers in 'cpus' and return a normalized list. The arguments are as follows.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs".
          * offlined - by default, offlined CPUs are considered as not available and are not allowed
                       to be in 'cpus' (will cause an exception). Use 'offlined_ok=True' to allow
                       for offlined CPUs.
        """

        allcpus = self.get_cpus()
        if offlined_ok:
            allcpus += self.get_offline_cpus()

        if cpus == "all":
            return allcpus

        allcpus = set(allcpus)
        cpus = ArgParse.parse_int_list(cpus, ints=True, dedup=True, sort=False)
        for cpu in cpus:
            if cpu not in allcpus:
                cpus_str = ", ".join([str(cpu) for cpu in sorted(allcpus)])
                raise Error(f"CPU{cpu} is not available{self._proc.hostmsg}, available CPUs are: "
                            f"{cpus_str}")

        return cpus

    def normalize_cpu(self, cpu):
        """Same as 'normalize_cpus()', but for a single CPU number."""
        return  self.normalize_cpus([cpu])[0]

    def _get_cpu_info(self):
        """Get general CPU information (model, architecture, etc)."""

        if self.info:
            return self.info

        self.info = cpuinfo = {}
        lscpu, _ = self._proc.run_verify("lscpu", join=False)

        # Parse misc. information about the CPU.
        patterns = ((r"^Architecture:\s*(.*)$", "arch"),
                    (r"^Byte Order:\s*(.*)$", "byteorder"),
                    (r"^Vendor ID:\s*(.*)$", "vendor"),
                    (r"^Socket\(s\):\s*(.*)$", "packages"),
                    (r"^CPU family:\s*(.*)$", "family"),
                    (r"^Model:\s*(.*)$", "model"),
                    (r"^Model name:\s*(.*)$", "modelname"),
                    (r"^Model name:.*@\s*(.*)GHz$", "basefreq"),
                    (r"^Stepping:\s*(.*)$", "stepping"),
                    (r"^L1d cache:\s*(.*)$", "l1d"),
                    (r"^L1i cache:\s*(.*)$", "l1i"),
                    (r"^L2 cache:\s*(.*)$", "l2"),
                    (r"^L3 cache:\s*(.*)$", "l3"),
                    (r"^Flags:\s*(.*)$", "flags"))

        for line in lscpu:
            for pattern, key in patterns:
                match = re.match(pattern, line.strip())
                if not match:
                    continue

                val = match.group(1)
                if Trivial.is_int(val):
                    cpuinfo[key] = int(val)
                else:
                    cpuinfo[key] = val

        if cpuinfo.get("flags"):
            cpuinfo["flags"] = cpuinfo["flags"].split()

        return cpuinfo

    def __init__(self, proc=None):
        """
        The class constructor. The 'proc' argument is a 'Proc' or 'SSH' object that defines the
        host to create a class instance for (default is the local host). This object will keep a
        'proc' reference and use it in various methods.
        """

        self._proc = proc
        self._close_proc = proc is None

        # The topology dictionary. See '_get_topology()' for more information.
        self._topology = {}

        # Level name to its index number.
        self._lvl2idx = {lvl : idx for idx, lvl in enumerate(LEVELS)}
        # Level index number to its name.
        self._idx2lvl = dict(enumerate(LEVELS))

        # The CPU topology sysfs directory path pattern.
        self._topology_sysfs_base = "/sys/devices/system/cpu/cpu%d/topology/"
        # A CPU number -> die number cache. Used only when building the topology dictionary, helps
        # reading less sysfs files.
        self._die_cache = {}
        # Will be 'True' if the system does not provide die information (e.g., the kernel is old).
        self._no_die_info = False

        # General CPU information.
        self.info = None
        # A short CPU description string.
        self.cpudescr = None

        if not self._proc:
            self._proc = Procs.Proc()

        self.info = self._get_cpu_info()

        if "Genuine Intel" in self.info["modelname"]:
            modelname = _CPU_DESCR.get(self.info["model"], self.info["modelname"])
        else:
            modelname = self.info["modelname"]
        self.cpudescr = f"{modelname} (model {self.info['model']:#x})"

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_proc", None):
            if getattr(self, "_close_proc", False):
                self._proc.close()
            self._proc = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
