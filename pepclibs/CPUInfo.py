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
from pepclibs.helperlibs import ArgParse, LocalProcessManager, Trivial, ClassHelpers

# CPU model numbers.
#
# Xeons.
INTEL_FAM6_EMERALDRAPIDS_X = 0xCF      # Emerald Rapids Xeon.
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
INTEL_FAM6_METEORLAKE = 0xAC           # Meteor Lake client.
INTEL_FAM6_METEORLAKE_L = 0xAA         # Meteor Lake mobile.
INTEL_FAM6_RAPTORLAKE_P = 0xBA         # Raptor Lake mobile.
INTEL_FAM6_RAPTORLAKE_S = 0xBF         # Raptor Lake client.
INTEL_FAM6_RAPTORLAKE = 0xB7           # Raptor Lake client.
INTEL_FAM6_ALDERLAKE = 0x97            # Alder Lake client.
INTEL_FAM6_ALDERLAKE_L = 0x9A          # Alder Lake mobile.
INTEL_FAM6_ALDERLAKE_N = 0xBE          # Alder Lake mobile.
INTEL_FAM6_ROCKETLAKE = 0xA7           # Rocket Lake client.
INTEL_FAM6_TIGERLAKE = 0x8D            # Tiger Lake client.
INTEL_FAM6_TIGERLAKE_L = 0x8C          # Tiger Lake mobile.
INTEL_FAM6_LAKEFIELD = 0x8A            # Lakefield client.
INTEL_FAM6_COMETLAKE = 0xA5            # Comet Lake client.
INTEL_FAM6_COMETLAKE_L = 0xA6          # Comet Lake mobile.
INTEL_FAM6_KABYLAKE = 0x9E             # Kaby Lake client.
INTEL_FAM6_KABYLAKE_L = 0x8E           # Kaby Lake mobile.
INTEL_FAM6_ICELAKE = 0x7D              # IceLake client.
INTEL_FAM6_ICELAKE_L = 0x7E            # Ice Lake mobile.
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
INTEL_FAM6_GRANDRIDGE = 0xB6           # Grand Ridge, Logansville.
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
EMRS =         (INTEL_FAM6_EMERALDRAPIDS_X,)
SPRS =         (INTEL_FAM6_SAPPHIRERAPIDS_X,)
METEORLAKES =  (INTEL_FAM6_METEORLAKE,
                INTEL_FAM6_METEORLAKE_L,)
RAPTORLAKES =  (INTEL_FAM6_RAPTORLAKE,
                INTEL_FAM6_RAPTORLAKE_P,
                INTEL_FAM6_RAPTORLAKE_S,)
ALDERLAKES =   (INTEL_FAM6_ALDERLAKE,
                INTEL_FAM6_ALDERLAKE_L,
                INTEL_FAM6_ALDERLAKE_N,)
ROCKETLAKES =  (INTEL_FAM6_ROCKETLAKE,)
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

CRESMONTS =    (INTEL_FAM6_GRANDRIDGE,)
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
_CPU_DESCR = {INTEL_FAM6_EMERALDRAPIDS_X:  "Emerald Rapids Xeon",
              INTEL_FAM6_SAPPHIRERAPIDS_X: "Sapphire Rapids Xeon",
              INTEL_FAM6_ALDERLAKE:        "Alder Lake client",
              INTEL_FAM6_ALDERLAKE_L:      "Alder Lake mobile",
              INTEL_FAM6_ALDERLAKE_N:      "Alder Lake mobile",
              INTEL_FAM6_TREMONT_D:        "Tremont Atom (Snow Ridge)"}

# The levels names have to be the same as 'sname' names in 'PStates', 'CStates', etc.
LEVELS = ("CPU", "core", "module", "die", "node", "package")

class CPUInfo(ClassHelpers.SimpleCloseContext):
    """
    Provide information about the CPU of a local or remote host.

    Public methods overview.

    1. Get CPU topology information.
        * 'get_topology()'
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
        * 'get_packages_count()'
        * 'get_offline_cpus_count()'
    5. Normalize a list of packages/cores/etc.
        A. Multiple packages/CPUs/etc numbers:
            * 'normalize_cpus()'
            * 'normalize_dies()'
            * 'normalize_packages()'
        B. Single package/CPU/etc.
            * 'normalize_cpu()'
            * 'normalize_package()'
    6. "Divide" list of CPUs.
        A. By cores: 'cpus_div_cores()'.
        B. By dies: 'cpus_div_dies()'.
        C. By packages: 'cpus_div_packages()'.
    7. Mark CPUs online/offline.
        * 'mark_cpus_online()'
        * 'mark_cpus_offline()'
    """

    def _get_cpu_module(self, cpu):
        """
        Returns the module number for CPU number in 'cpu'. If number can't be resolved returns
        'None'.
        """

        if cpu in self._module_cache:
            return self._module_cache[cpu]

        sysfs_base = Path(f"/sys/devices/system/cpu/cpu{cpu}/cache/index2/")

        # All CPUs in a module share the same L2 cache, so we use L2 cache ID for the module number.
        module_id_path = sysfs_base / "id"
        try:
            module = self._pman.read(module_id_path)
        except ErrorNotFound:
            return None

        module = int(module)

        # Get the list of CPUs belonging to the same module.
        cpus = self._pman.read(sysfs_base / "shared_cpu_list")
        cpus = ArgParse.parse_int_list(cpus, ints=True)

        for cpunum in cpus:
            self._module_cache[cpunum] = module

        return module

    def _get_cpu_die(self, cpu):
        """
        Returns the die number for CPU number in 'cpu'. If number can't be resolved returns 'None'.
        """

        if cpu in self._die_cache:
            return self._die_cache[cpu]

        sysfs_base = Path(self._topology_sysfs_base % cpu)

        # Get the CPU die number.
        die_id_path = sysfs_base / "die_id"
        try:
            die = self._pman.read(die_id_path)
        except ErrorNotFound:
            return None

        die = int(die)

        # Get the list of CPUs belonging to the same die.
        cpus = self._pman.read(sysfs_base / "die_cpus_list")
        cpus = ArgParse.parse_int_list(cpus, ints=True)

        # Save the list of CPUs in the case.
        for cpunum in cpus:
            self._die_cache[cpunum] = die

        return die

    def _sort_topology(self, topology):
        """Sorts the topology list."""

        # We are going to store 5 versions of the table, sorted in different order. Note, core and
        # die numbers are per-package, therefore we always sort them by package first.
        sorting_map = {"CPU"     : ("CPU", ),
                       "core"    : ("package", "core", "CPU"),
                       "module"  : ("module", "CPU"),
                       "die"     : ("package", "die", "CPU"),
                       "node"    : ("node", "CPU"),
                       "package" : ("package", "CPU")}

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

    def get_topology(self, order="CPU"):
        """
        Build and return the topology list. The topology includes dictionaries, one dictionary per
        CPU. Each dictionary includes the following keys.
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
          * online  - CPU online status.
                    - 'True' if the CPU is online, 'False' when the CPU is offline.

        Note, when a CPU is offline, its core, die, node and package numbers are 'None'.

        Example topology list for the following hypothetical system:
          * 2 packages, numbers 0, 1.
          * 2 nodes, numbers 0, 1.
          * 1 die per package, numbers 0.
          * 3 modules, numbers 0, 4, 5.
          * 4 cores per package, numbers 0, 1, 5, 6.
          * 16 CPUs, numbers 0-16.

        Here is the topology table in package order. It is sorted by package and CPU.

		  {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},

        The topology tables in node/die order will look the same (in this particular example). They
        are sorted by package number, then node/die number, then CPU number.

        Here is the topology table in core order. It'll be sorted by package number, and then core
        number, then CPU number.

		  {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},

        Here is the topology table in CPU order.

		  {'CPU': 0,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 1,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 2,  'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 3,  'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 4,  'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 5,  'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 6,  'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 7,  'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 8,  'core': 0, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 9,  'core': 0, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 10, 'core': 6, 'module': 5, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 11, 'core': 6, 'module': 5, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 12, 'core': 1, 'module': 0, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 13, 'core': 1, 'module': 0, 'die': 0, 'node': 1, 'package': 1, 'online': True},
		  {'CPU': 14, 'core': 5, 'module': 4, 'die': 0, 'node': 0, 'package': 0, 'online': True},
		  {'CPU': 15, 'core': 5, 'module': 4, 'die': 0, 'node': 1, 'package': 1, 'online': True},
        """

        self._check_level(order, name="order")

        if self._topology:
            return self._topology[order]

        # Note, we could just walk sysfs, but 'lscpu' is faster.
        cmd = "lscpu --physical --all -p=socket,node,core,cpu,online"
        lines, _ = self._pman.run_verify(cmd, join=False)

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
            tline["CPU"] = int(vals[3])

            if tline["online"]:
                tline["core"] = int(vals[2])
                tline["module"] = self._get_cpu_module(tline["CPU"])
                tline["die"] = self._get_cpu_die(tline["CPU"])
                tline["node"] = int(vals[1])
                tline["package"] = int(vals[0])

            topology.append(tline)

        self._sort_topology(topology)
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

        self._check_level(sublvl)
        self._check_level(lvl)
        self._check_level(order, name="order")

        if self._lvl2idx[lvl] < self._lvl2idx[sublvl]:
            raise Error(f"bad level order, cannot get {sublvl}s from level '{lvl}'")

        if nums != "all":
            nums = set(ArgParse.parse_int_list(nums, ints=True, dedup=True, sort=True))

        result = {}
        valid_nums = set()

        for tline in self.get_topology(order=order):
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
                raise Error(f"{lvl} {num} does not exist{self._pman.hostmsg}.\n"
                            f"Valid {lvl} numbers are: {valid_nums_str}")

        return list(result)

    def _toggle_cpus_online(self, cpus, online):
        """Mark CPUs 'cpus' online status to 'online' in internal topology dictionary."""

        cpus = self.normalize_cpus(cpus, offlined_ok=True)
        topology = self.get_topology(order="CPU")
        for cpu in cpus:
            topology[cpu]["online"] = online

        self._sort_topology(topology)
        return self._topology["CPU"]

    def mark_cpus_online(self, cpus):
        """Mark CPUs 'cpus' as online in internal topology dictionary."""
        self._toggle_cpus_online(cpus, True)

    def mark_cpus_offline(self, cpus):
        """Same as 'mark_cpus_online()' but mark CPUs as offline."""
        self._toggle_cpus_online(cpus, False)

    def get_cpus(self, order="CPU"):
        """Returns list of online CPU numbers."""
        return self._get_level_nums("CPU", "CPU", "all", order=order)

    def get_cores(self, package=0, order="core"):
        """
        Returns list of core numbers in package 'package', only cores containing at least one online
        CPU will be included.
        """
        return self._get_level_nums("core", "package", package, order=order)

    def get_modules(self, order="module"):
        """
        Returns list of module numbers, only modules containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("module", "module", "all", order=order)

    def get_dies(self, package=0, order="die"):
        """
        Returns list of die numbers in package 'package', only dies containing at least one online
        CPU will be included.
        """
        return self._get_level_nums("die", "package", package, order=order)

    def get_nodes(self, order="node"):
        """
        Returns list of node numbers, only nodes containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("node", "node", "all", order=order)

    def get_packages(self, order="package"):
        """
        Returns list of package numbers, only packages containing at least one online CPU will be
        included.
        """
        return self._get_level_nums("package", "package", "all", order=order)

    def get_offline_cpus(self):
        """Returns list of offline CPU numbers sorted in ascending order."""

        cpus = []
        for tline in self.get_topology(order="CPU"):
            if not tline["online"]:
                cpus.append(tline["CPU"])

        return cpus

    def get_cpu_levels(self, cpu):
        """
        Returns a dictionary of levels an online CPU 'cpu' belongs to. Example for CPU 16:
            {"package": 0, "die": 1, "node": 1, "core" : 5, "CPU": 16}
        """

        cpu = self.normalize_cpu(cpu)

        tline = None
        for tline in self.get_topology(order="CPU"):
            if cpu == tline["CPU"]:
                break
        else:
            raise Error(f"CPU {cpu} is not available{self._pman.hostmsg}")

        if not tline["online"]:
            raise Error(f"CPU {cpu} is offline{self._pman.hostmsg}, cannot get its topology")

        result = {}
        for lvl in LEVELS:
            result[lvl] = tline[lvl]
        return result

    def get_cpu_siblings(self, cpu, level):
        """
        Returns a list of 'level' siblings. The arguments are as follows:
         * cpu - the CPU whose siblings to return.
         * level - the siblings level (e.g. "package", "core").

        For example, if 'level' is "package", this method returns a list of CPUs sharing the same
        package as CPU 'cpu'.
        """

        if level == "CPU":
            return self.normalize_cpus((cpu, ))

        if level == "global":
            return self.get_cpus()

        levels = self.get_cpu_levels(cpu)
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
        Returns list of online CPU numbers belonging to cores 'cores' in packages 'packages'.

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
        """Returns list of online CPU numbers belonging to modules 'modules'."""
        return self._get_level_nums("CPU", "module", modules, order=order)

    def dies_to_cpus(self, dies="all", packages="all", order="CPU"):
        """
        Returns list of online CPU numbers belonging to dies 'dies' in packages 'packages'.

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
        """Returns list of online CPU numbers belonging to nodes 'nodes'."""
        return self._get_level_nums("CPU", "node", nodes, order=order)

    def packages_to_cpus(self, packages="all", order="CPU"):
        """Returns list of online CPU numbers belonging to packages 'packages'."""
        return self._get_level_nums("CPU", "package", packages, order=order)

    def get_offline_cpus_count(self):
        """Returns count of offline CPUs."""
        return len(self.get_offline_cpus())

    def get_cpus_count(self):
        """Returns count of online CPUs."""
        return len(self.get_cpus())

    def get_packages_count(self):
        """Returns packages count."""
        return len(self.get_packages())

    def cpus_div_cores(self, cpus):
        """
        This method is similar to 'cpus_div_packages()', but it checks which CPU numbers in 'cpus'
        cover entire core(s). So it is inverse to the 'cores_to_cpus()' method. The arguments are as
        follows.
          * cpus - same as in 'normalize_cpus()'.

        Returns a tuple of two lists: ('cores', 'rem_cpus').
          * cores - list of ('core', 'package') tuples with all CPUs present in 'cpus'.
              o core - core number.
              o package - package number 'core' belongs to
          * rem_cpus - list of remaining CPUs that cannot be converted to a core number.

        The return value is inconsistent with 'cpus_div_packages()' because cores numbers are not
        global, so they must go with package numbers.

        Consider an example of a system with 2 packages, 1 core per package, 2 CPUs per core.
          * package 0 includes core 0 and CPUs 0 and 1
          * package 1 includes core 0 and CPUs 2 and 3

        1. cpus_div_cores("0-3") would return ([(0,0), (0,1)], []).
        2. cpus_div_cores("2,3") would return ([(0,1)],        []).
        3. cpus_div_cores("0,3") would return ([],             [0,3]).
        """

        cores = []
        rem_cpus = []

        cpus = self.normalize_cpus(cpus)
        cpus_set = set(cpus)

        for pkg in self.get_packages():
            for core in self.package_to_cores(pkg):
                siblings_set = set(self.cores_to_cpus(cores=(core,), packages=(pkg,)))

                if siblings_set.issubset(cpus_set):
                    cores.append((core, pkg))
                    cpus_set -= siblings_set

        # Return the remaining CPUs in the order of the input 'cpus'.
        for cpu in cpus:
            if cpu in cpus_set:
                rem_cpus.append(cpu)

        return (cores, rem_cpus)

    def cpus_div_dies(self, cpus):
        """
        This method is similar to 'cpus_div_packages()', but it checks which CPU numbers in 'cpus'
        cover entire dies(s). The arguments are as follows.
          * cpus - same as in 'normalize_cpus()'.

        Returns a tuple of two lists: ('dies', 'rem_cpus').
          * dies - list of ('die', 'package') tuples with all CPUs present in 'cpus'.
              o die - die number.
              o package - package number 'die' belongs to
          * rem_cpus - list of remaining CPUs that cannot be converted to a die number.

        The return value is inconsistent with 'cpus_div_packages()' because die numbers are not
        global, so they must go with package numbers.

        Consider an example of a system with 2 packages, 2 dies per package, 1 core per die, 2 CPUs
        per core.
          * package 0 includes dies 0 and 1, cores 0 and 1, and CPUs 0, 1, 2, and 3
            - die 0 includes CPUs 0 and 1
            - die 1 includes CPUs 2 and 3
          * package 1 includes dies 0 and 1, cores 0 and 1, and CPUs 4, 5, 6, and 7
            - die 0 includes CPUs 4 and 5
            - die 1 includes CPUs 6 and 7

        1. cpus_div_dies("0-3") would return   ([(0,0), (1,0)], []).
        2. cpus_div_dies("4,5,6") would return ([(1,1)],        [6]).
        3. cpus_div_dies("0,3") would return   ([],             [0,3]).
        """

        dies = []
        rem_cpus = []

        cpus = self.normalize_cpus(cpus)
        cpus_set = set(cpus)

        for pkg in self.get_packages():
            for die in self.package_to_dies(pkg):
                siblings_set = set(self.dies_to_cpus(dies=(die,), packages=(pkg,)))

                if siblings_set.issubset(cpus_set):
                    dies.append((die, pkg))
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

        Returns a tuple of two lists: ('packages', 'rem_cpus').
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

        cpus = self.normalize_cpus(cpus)
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
                raise Error(f"CPU{cpu} is not available{self._pman.hostmsg}, available CPUs are: "
                            f"{cpus_str}")

        return cpus

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
                            f"'{package}'{self._pman.hostmsg}, available dies are: {dies_str}")

        return dies

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
                raise Error(f"package '{pkg}' not available{self._pman.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return packages

    def normalize_cpu(self, cpu):
        """Same as 'normalize_cpus()', but for a single CPU number."""
        return  self.normalize_cpus([cpu])[0]

    def normalize_package(self, package):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_packages([package])[0]

    def _get_cpu_info(self):
        """Get general CPU information (model, architecture, etc)."""

        if self.info:
            return self.info

        self.info = cpuinfo = {}
        lscpu, _ = self._pman.run_verify("lscpu", join=False)

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
            cpuflags = set(cpuinfo["flags"].split())
            cpuinfo["flags"] = {}
            # In current implementation we assume all CPUs have the same flags. But ideally, we
            # should read the flags for each CPU from '/proc/cpuinfo', instead of using 'lscpu'.
            for cpu in self.get_cpus():
                cpuinfo["flags"][cpu] = cpuflags

        return cpuinfo

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        self._pman = pman
        self._close_pman = pman is None

        # The topology dictionary. See 'get_topology()' for more information.
        self._topology = {}

        # Level name to its index number.
        self._lvl2idx = {lvl : idx for idx, lvl in enumerate(LEVELS)}

        # The CPU topology sysfs directory path pattern.
        self._topology_sysfs_base = "/sys/devices/system/cpu/cpu%d/topology/"
        # A CPU number -> die/module number cache. Used only when building the topology dictionary,
        # helps reading less sysfs files.
        self._die_cache = {}
        self._module_cache = {}

        # General CPU information.
        self.info = None
        # A short CPU description string.
        self.cpudescr = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        self.info = self._get_cpu_info()

        if "Genuine Intel" in self.info["modelname"]:
            modelname = _CPU_DESCR.get(self.info["model"], self.info["modelname"])
        else:
            modelname = self.info["modelname"]

        self.cpudescr = f"{modelname} (model {self.info['model']:#x})"

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
