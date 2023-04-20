# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides an API to get CPU information.
"""

import re
import copy
from pathlib import Path
from contextlib import suppress
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ArgParse, LocalProcessManager, Trivial, ClassHelpers, Human

# CPU model numbers.
#
# Xeons.
INTEL_FAM6_SIERRAFOREST_X = 0xAF       # Sierra Forrest Xeon.
INTEL_FAM6_GRANITERAPIDS_X = 0xAD      # Granite Rapids Xeon.
INTEL_FAM6_GRANITERAPIDS_D = 0xAE      # Granite Rapids Xeon D.
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
INTEL_FAM6_GRANDRIDGE = 0xB6           # Grand Ridge, Logansville.
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
GNRS =         (INTEL_FAM6_GRANITERAPIDS_X,
                INTEL_FAM6_GRANITERAPIDS_D)
EMRS =         (INTEL_FAM6_EMERALDRAPIDS_X,)
METEORLAKES =  (INTEL_FAM6_METEORLAKE,
                INTEL_FAM6_METEORLAKE_L,)
SPRS =         (INTEL_FAM6_SAPPHIRERAPIDS_X,)
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
ICL_CLIENTS =  (INTEL_FAM6_ICELAKE,
                INTEL_FAM6_ICELAKE_L,)
ICXES       =  (INTEL_FAM6_ICELAKE_D,
                INTEL_FAM6_ICELAKE_X,)
COMETLAKES =   (INTEL_FAM6_COMETLAKE,
                INTEL_FAM6_COMETLAKE_L,)
KABYLAKES =    (INTEL_FAM6_KABYLAKE,
                INTEL_FAM6_KABYLAKE_L,)
CANNONLAKES =  (INTEL_FAM6_CANNONLAKE_L,)
SKYLAKES =     (INTEL_FAM6_SKYLAKE,
                INTEL_FAM6_SKYLAKE_L,
                INTEL_FAM6_SKYLAKE_X,)
SKL_CLIENTS =  (INTEL_FAM6_SKYLAKE,
                INTEL_FAM6_SKYLAKE_L)
SKXES =        (INTEL_FAM6_SKYLAKE_X,)
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

CRESTMONTS =    (INTEL_FAM6_GRANDRIDGE,
                 INTEL_FAM6_SIERRAFOREST_X)
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
_CPU_DESCR = {
              INTEL_FAM6_GRANITERAPIDS_X:  "Granite Rapids Xeon",
              INTEL_FAM6_GRANITERAPIDS_D:  "Granite Rapids Xeon D",
              INTEL_FAM6_EMERALDRAPIDS_X:  "Emerald Rapids Xeon",
              INTEL_FAM6_SAPPHIRERAPIDS_X: "Sapphire Rapids Xeon",
              INTEL_FAM6_ALDERLAKE:        "Alder Lake client",
              INTEL_FAM6_ALDERLAKE_L:      "Alder Lake mobile",
              INTEL_FAM6_ALDERLAKE_N:      "Alder Lake mobile",
              INTEL_FAM6_TREMONT_D:        "Tremont Atom (Snow Ridge)",
              INTEL_FAM6_SKYLAKE_X:        "Sky/Cascade/Cooper Lake"}

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
    6. Select CPUs by sibling index.
        * 'select_core_siblings()'
    7. "Divide" list of CPUs.
        * By cores: 'cpus_div_cores()'.
        * By dies: 'cpus_div_dies()'.
        * By packages: 'cpus_div_packages()'.
    """

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

    def _read_range(self, path, must_exist=True):
        """Read number range string from path 'path', and return it as a list of integers."""

        str_of_ranges = self._pman.read(path, must_exist=must_exist).strip()
        return ArgParse.parse_int_list(str_of_ranges, ints=True)

    def _sort_topology(self, topology, order):
        """Sorts and save the topology list by 'order' in sorting map"""

        skeys = self._sorting_map[order]
        self._topology[order] = sorted(topology, key=lambda tline: tuple(tline[s] for s in skeys))

    def _update_topology(self):
        """Update topology information with online/offline CPUs."""

        new_online_cpus = self._get_online_cpus()
        old_online_cpus = {tline["CPU"] for tline in self._topology["CPU"]}
        if new_online_cpus != old_online_cpus:
            onlined = list(new_online_cpus - old_online_cpus)

            tinfo = {cpu : {"CPU" : cpu} for cpu in onlined}
            for tline in self._topology["CPU"]:
                if tline["CPU"] in new_online_cpus:
                    tinfo[tline["CPU"]] = tline

            if "package" in self._initialized_levels or "core" in self._initialized_levels:
                self._add_core_and_package_numbers(tinfo, onlined)
            if "module" in self._initialized_levels:
                self._add_module_numbers(tinfo, onlined)
            if "die" in self._initialized_levels:
                self._add_die_numbers(tinfo, onlined)
            if "node" in self._initialized_levels:
                self._add_node_numbers(tinfo)

            topology = list(tinfo.values())
            for order in self._initialized_levels:
                self._sort_topology(topology, order)

        self._must_update_topology = False

    def _add_core_and_package_numbers(self, tinfo, cpus):
        """Adds core and package numbers for CPUs 'cpus' to 'tinfo'."""

        def _get_number(start, lines, index):
            """Check that line with index 'index' starts with 'start', and return its value."""

            try:
                line = lines[index]
            except IndexError:
                raise Error(f"there are to few lines in '/proc/cpuinfo' for CPU '{cpu}'") from None

            if not line.startswith(start):
                raise Error(f"line {index + 1} for CPU {cpu} in '/proc/cpuinfo' is not \"{start}\"")

            return Trivial.str_to_int(line.partition(":")[2], what=start)

        info = {}
        for data in self._pman.read("/proc/cpuinfo").strip().split("\n\n"):
            lines = data.split("\n")
            cpu = _get_number("processor", lines, 0)
            info[cpu] = lines

        for cpu in cpus:
            if cpu not in info:
                raise Error(f"CPU {cpu} is missing from '/proc/cpuinfo'")

            lines = info[cpu]
            tinfo[cpu]["package"] = _get_number("physical id", lines, 9)
            tinfo[cpu]["core"] = _get_number("core id", lines, 11)

    def _add_module_numbers(self, tinfo, cpus):
        """Adds module numbers for CPUs 'cpus' to 'tinfo'"""

        for cpu in cpus:
            if "module" in tinfo[cpu]:
                continue

            base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
            data = self._pman.read(base / "cache/index2/id")
            module = Trivial.str_to_int(data, "module number")
            siblings = self._read_range(base / "cache/index2/shared_cpu_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'shared_cpu_list' file included an offline CPU.
                with suppress(KeyError):
                    tinfo[sibling]["module"] = module

    def _add_die_numbers(self, tinfo, cpus):
        """Adds die numbers for CPUs 'cpus' to 'tinfo'"""

        for cpu in cpus:
            if "die" in tinfo[cpu]:
                continue

            base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
            data = self._pman.read(base / "topology/die_id")
            die = Trivial.str_to_int(data, "die number")
            siblings = self._read_range(base / "topology/die_cpus_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'die_cpus_list' file included an offline CPU.
                with suppress(KeyError):
                    tinfo[sibling]["die"] = die

    def _add_node_numbers(self, tinfo):
        """Adds NUMA node numbers to 'tinfo'."""

        nodes = self._read_range("/sys/devices/system/node/online")
        for node in nodes:
            cpus = self._read_range(f"/sys/devices/system/node/node{node}/cpulist")
            for cpu in cpus:
                # Suppress 'KeyError' in case the 'cpulist' file included an offline CPU.
                with suppress(KeyError):
                    tinfo[cpu]["node"] = node

    def _get_topology(self, levels, order="CPU"):
        """Build and return topology list, refer to 'get_topology()' for more information."""

        levels = set(levels)
        levels.update(set(self._sorting_map[order]))

        if self._must_update_topology:
            self._update_topology()

        levels -= self._initialized_levels
        if not levels:
            return self._topology[order]

        if not self._topology:
            tinfo = {cpu : {"CPU" : cpu} for cpu in self._get_online_cpus(update=True)}
        else:
            tinfo = {tline["CPU"] : tline for tline in self._topology["CPU"]}

        cpus = self._get_online_cpus()
        if "package" in levels or "core" in levels:
            self._add_core_and_package_numbers(tinfo, cpus)
            levels.update({"package", "core"})
        if "module" in levels:
            self._add_module_numbers(tinfo, cpus)
        if "die" in levels:
            self._add_die_numbers(tinfo, cpus)
        if "node" in levels:
            self._add_node_numbers(tinfo)

        topology = list(tinfo.values())
        self._initialized_levels.update(levels)
        for level in self._initialized_levels:
            if level not in self._topology:
                self._sort_topology(topology, level)

        return self._topology[order]

    def _validate_level(self, lvl, name="level"):
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
            valid_nums.add(tline[lvl])
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
        """Returns list of online CPU numbers."""

        if order == "CPU":
            return sorted(self._get_online_cpus())

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

    def _get_all_cpus(self):
        """Returns set of online and offline CPU numbers."""

        if not self._all_cpus:
            self._all_cpus = set(self._read_range("/sys/devices/system/cpu/present"))
        return self._all_cpus

    def _get_online_cpus(self, update=False):
        """Returns set of online CPU numbers."""

        if not self._cpus or update:
            self._cpus = set(self._read_range("/sys/devices/system/cpu/online"))
        return self._cpus

    def get_offline_cpus(self):
        """Returns list of offline CPU numbers sorted in ascending order."""

        cpus = self._get_all_cpus()
        online_cpus = self._get_online_cpus()
        return list(cpu for cpu in cpus if cpu not in online_cpus)

    def cpus_hotplugged(self):
        """This method informs CPUInfo to update online/offline CPUs and topology lists."""

        self._cpus = None
        if self._topology:
            self._must_update_topology = True

    def get_cpu_levels(self, cpu, levels=None):
        """
        Returns a dictionary of levels an online CPU 'cpu' belongs to. By default all levels are
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
        return len(self._get_online_cpus())

    def get_packages_count(self):
        """Returns packages count."""
        return len(self.get_packages())

    def select_core_siblings(self, cpus, indexes):
        """
        Select only core siblings from 'cpus' and return the result. The arguments are as follows.
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

        Suppose the input 'cpus' argument is '[1, 4, 5, 2]'. The following cores will be selected:
        1, 0 and 2.

        In order to select first core siblings from 'cpus', provide 'indexes=[0]'. The result will
        be: '[1, 2]'.

        In order to select second core siblings from 'cpus', provide 'indexes=[1]'. The result will
        be: '[4, 5]'.

        If 'indexes=[0,1]', the result will be the same as 'cpus': '[1, 4, 5, 2]'

        Note: the index of a CPU inside the core depends on the online status of all CPUs inside the
              core. For example, a core with 3 CPUs 0, 1 and 2, when each of the CPUs are online
              their CPU number corresponds to their index, but say we offline CPU 1, then CPU 2 will
              have index 1 instead of 2.
        """

        cpus = self.normalize_cpus(cpus, offlined_ok=True)

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
          * cpus - collection of integer CPU numbers to normalize. Special value 'all' means
                   "all CPUs".
          * offlined - by default, offlined CPUs are considered as not available and are not allowed
                       to be in 'cpus' (will cause an exception). Use 'offlined_ok=True' to allow
                       for offlined CPUs.
        """

        if offlined_ok:
            allcpus = self._get_all_cpus()
        else:
            allcpus = self._get_online_cpus()

        if cpus == "all":
            return sorted(allcpus)

        cpus = Trivial.list_dedup(cpus)
        for cpu in cpus:
            if type(cpu) is not int: # pylint: disable=unidiomatic-typecheck
                raise Error(f"'{cpu}' is not an integer, CPU numbers must be integers")

            if cpu not in allcpus:
                cpus_str = Human.rangify(allcpus)
                raise Error(f"CPU{cpu} is not available{self._pman.hostmsg}, available CPUs are: "
                            f"{cpus_str}")

        return cpus

    def normalize_dies(self, dies, package=0):
        """
        Validate die numbers in 'dies' for package 'package' and return the normalized list. The
        arguments are as follows.
          * dies - collection of integer die numbers to normalize. Special value 'all' means
                   "all diess".
          * package - package number to validate the 'dies' against: all numbers in 'dies' should be
                      valid die numbers in package number 'package'.

        Returns a list of integer die numbers.
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
            for cpu in self._get_online_cpus():
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
        # Stores all initialized topology levels.
        self._initialized_levels = set()
        # This flag notifies '_get_topology()' that some CPUs have been offlined/onlined.
        self._must_update_topology = False
        # We are going to sort topology by level, this map specifies how each is sorted. Note, core
        # and die numbers are per-package, therefore we always sort them by package first.
        self._sorting_map = {"CPU"     : ("CPU", ),
                             "core"    : ("package", "core", "CPU"),
                             "module"  : ("module", "CPU"),
                             "die"     : ("package", "die", "CPU"),
                             "node"    : ("node", "CPU"),
                             "package" : ("package", "CPU")}

        # Level name to its index number.
        self._lvl2idx = {lvl : idx for idx, lvl in enumerate(LEVELS)}

        # The CPU topology sysfs directory path pattern.
        self._topology_sysfs_base = "/sys/devices/system/cpu/cpu%d/topology/"

        # Set of online and offline CPUs.
        self._all_cpus = None
        # Set of online CPUs.
        self._cpus = None

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
