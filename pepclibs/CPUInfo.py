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

import re
import copy
import json
import logging
from pathlib import Path
from contextlib import suppress
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import ArgParse, LocalProcessManager, Trivial, ClassHelpers, Human
from pepclibs.helperlibs import KernelVersion

_LOG = logging.getLogger()

CPUS = {
    # Xeons.
    "SIERRAFOREST_X" : {
        "model"    : 0xAF,
        "codename" : "Sierra Forest Xeon",
    },
    "GRANITERAPIDS_X" : {
        "model"    : 0xAD,
        "codename" : "Granite Rapids Xeon",
    },
    "GRANITERAPIDS_D" : {
        "model"    : 0xAE,
        "codename" : "Granite Rapids Xeon D",
    },
    "EMERALDRAPIDS_X" : {
        "model"    : 0xCF,
        "codename" : "Emerald Rapids Xeon",
    },
    "SAPPHIRERAPIDS_X" : {
        "model"    : 0x8F,
        "codename" : "Sapphire Rapids Xeon",
    },
    "ICELAKE_X" : {
        "model"    : 0x6A,
        "codename" : "Ice Lake Xeon",
    },
    "ICELAKE_D" : {
        "model"    : 0x6C,
        "codename" : "Ice Lake Xeon D",
    },
    "SKYLAKE_X" : {
        "model"    : 0x55,
        "codename" : "Skylake, Cascade Lake, or Cooper Lake Xeon",
    },
    "BROADWELL_X" : {
        "model"    : 0x4F,
        "codename" : "Broadwell Xeon",
    },
    "BROADWELL_G" : {
        "model"    : 0x47,
        "codename" : "Broadwell Xeon with Graphics",
    },
    "BROADWELL_D" : {
        "model"    : 0x56,
        "codename" : "Broadwell Xeon-D",
    },
    "HASWELL_X" : {
        "model"    : 0x3F,
        "codename" : "Haswell Xeon",
    },
    "HASWELL_G" : {
        "model"    : 0x46,
        "codename" : "Haswell Xeon with Graphics",
    },
    "IVYBRIDGE_X" : {
        "model"    : 0x3E,
        "codename" : "Ivy Town Xeon",
    },
    "SANDYBRIDGE_X" : {
        "model"    : 0x2D,
        "codename" : "SandyBridge Xeon",
    },
    "WESTMERE_EP" : {
        "model"    : 0x2C,
        "codename" : "Westmere 2S Xeon",
    },
    "WESTMERE_EX" : {
        "model"    : 0x2F,
        "codename" : "Westmere 4S Xeon",
    },
    "NEHALEM_EP" : {
        "model"    : 0x1A,
        "codename" : "Nehalem 2S Xeon",
    },
    "NEHALEM_EX" : {
        "model"    : 0x2E,
        "codename" : "Nehalem 4S Xeon",
    },
    # Clients.
    "METEORLAKE" : {
        "model"    : 0xAC,
        "codename" : "Meteor Lake client",
    },
    "METEORLAKE_L" : {
        "model"    : 0xAA,
        "codename" : "Meteor Lake mobile",
    },
    "RAPTORLAKE_P" : {
        "model"    : 0xBA,
        "codename" : "Raptor Lake mobile",
    },
    "RAPTORLAKE_S" : {
        "model"    : 0xBF,
        "codename" : "Raptor Lake client",
    },
    "RAPTORLAKE" : {
        "model"    : 0xB7,
        "codename" : "Raptor Lake client",
    },
    "ALDERLAKE" : {
        "model"    : 0x97,
        "codename" : "Alder Lake client",
    },
    "ALDERLAKE_L" : {
        "model"    : 0x9A,
        "codename" : "Alder Lake mobile",
    },
    "ALDERLAKE_N" : {
        "model"    : 0xBE,
        "codename" : "Alder Lake mobile",
    },
    "ROCKETLAKE" : {
        "model"    : 0xA7,
        "codename" : "Rocket Lake client",
    },
    "TIGERLAKE" : {
        "model"    : 0x8D,
        "codename" : "Tiger Lake client",
    },
    "TIGERLAKE_L" : {
        "model"    : 0x8C,
        "codename" : "Tiger Lake mobile",
    },
    "LAKEFIELD" : {
        "model"    : 0x8A,
        "codename" : "Lakefield client",
    },
    "COMETLAKE" : {
        "model"    : 0xA5,
        "codename" : "Comet Lake client",
    },
    "COMETLAKE_L" : {
        "model"    : 0xA6,
        "codename" : "Comet Lake mobile",
    },
    "KABYLAKE" : {
        "model"    : 0x9E,
        "codename" : "Kaby Lake client",
    },
    "KABYLAKE_L" : {
        "model"    : 0x8E,
        "codename" : "Kaby Lake mobile",
    },
    "ICELAKE" : {
        "model"    : 0x7D,
        "codename" : "IceLake client",
    },
    "ICELAKE_L" : {
        "model"    : 0x7E,
        "codename" : "Ice Lake mobile",
    },
    "CANNONLAKE_L" : {
        "model"    : 0x66,
        "codename" : "Cannonlake mobile",
    },
    "SKYLAKE" : {
        "model"    : 0x5E,
        "codename" : "Skylake client",
    },
    "SKYLAKE_L" : {
        "model"    : 0x4E,
        "codename" : "Skylake mobile",
    },
    "BROADWELL" : {
        "model"    : 0x3D,
        "codename" : "Broadwell client",
    },
    "HASWELL" : {
        "model"    : 0x3C,
        "codename" : "Haswell client",
    },
    "HASWELL_L" : {
        "model"    : 0x45,
        "codename" : "Haswell mobile",
    },
    "IVYBRIDGE" : {
        "model"    : 0x3A,
        "codename" : "IvyBridge client",
    },
    "SANDYBRIDGE" : {
        "model"    : 0x2A,
        "codename" : "SandyBridge client",
    },
    "WESTMERE" : {
        "model"    : 0x25,
        "codename" : "Westmere client",
    },
    "NEHALEM_G" : {
        "model"    : 0x1F,
        "codename" : "Nehalem client with graphics (Auburndale, Havendale)",
    },
    "NEHALEM" : {
        "model"    : 0x1E,
        "codename" : "Nehalem client",
    },
    "CORE2_MEROM" : {
        "model"    : 0x0F,
        "codename" : "Intel Core 2",
    },
    # Atoms.
    "ATOM_TREMONT" : {
        "model"    : 0x96,
        "codename" : "Elkhart Lake",
    },
    "ATOM_TREMONT_L" : {
        "model"    : 0x9C,
        "codename" : "Jasper Lake",
    },
    "ATOM_GOLDMONT" : {
        "model"    : 0x5C,
        "codename" : "Apollo Lake",
    },
    "ATOM_GOLDMONT_PLUS" : {
        "model"    : 0x7A,
        "codename" : "Gemini Lake",
    },
    "ATOM_AIRMONT" : {
        "model"    : 0x4C,
        "codename" : "Cherry Trail, Braswell",
    },
    "ATOM_SILVERMONT" : {
        "model"    : 0x37,
        "codename" : "Bay Trail, Valleyview",
    },
    "ATOM_SILVERMONT_MID" : {
        "model"    : 0x4A,
        "codename" : "Merriefield",
    },
    "ATOM_SILVERMONT_MID1" : {
        "model"    : 0x5A,
        "codename" : "Moorefield",
    },
    "ATOM_SALTWELL" : {
        "model"    : 0x36,
        "codename" : "Cedarview",
    },
    "ATOM_SALTWELL_MID" : {
        "model"    : 0x27,
        "codename" : "Penwell",
    },
    "ATOM_SALTWELL_TABLET" : {
        "model"    : 0x35,
        "codename" : "Cloverview",
    },
    "ATOM_BONNELL_MID" : {
        "model"    : 0x26,
        "codename" : "Silverthorne, Lincroft",
    },
    "ATOM_BONNELL" : {
        "model"    : 0x1C,
        "codename" : "Diamondville, Pineview",
    },
    # Atom microservers.
    "GRANDRIDGE" : {
        "model"    : 0xB6,
        "codename" : "Grand Ridge, Logansville",
    },
    "TREMONT_D" : {
        "model"    : 0x86,
        "codename" : "Snow Ridge, Jacobsville",
    },
    "GOLDMONT_D" : {
        "model"    : 0x5F,
        "codename" : "Denverton, Harrisonville",
    },
    "ATOM_SILVERMONT_D" : {
        "model"    : 0x4D,
        "codename" : "Avaton, Rangely",
    },
    # Other.
    "ICELAKE_NNPI" : {
        "model"    : 0x9D,
        "codename" : "Ice Lake Neural Network Processor",
    },
    "XEON_PHI_KNM" : {
        "model"    : 0x85,
        "codename" : "Knights Mill",
    },
    "XEON_PHI_KNL" : {
        "model"    : 0x57,
        "codename" : "Knights Landing", },
}

#
# Various handy combinations of CPU models.
#
CPU_GROUPS = {
    "GNR":        (CPUS["GRANITERAPIDS_X"]["model"],
                   CPUS["GRANITERAPIDS_D"]["model"]),
    "EMR":        (CPUS["EMERALDRAPIDS_X"]["model"],),
    "METEORLAKE": (CPUS["METEORLAKE"]["model"],
                   CPUS["METEORLAKE_L"]["model"],),
    "SPR":        (CPUS["SAPPHIRERAPIDS_X"]["model"],),
    "RAPTORLAKE": (CPUS["RAPTORLAKE"]["model"],
                   CPUS["RAPTORLAKE_P"]["model"],
                   CPUS["RAPTORLAKE_S"]["model"],),
    "ALDERLAKE":  (CPUS["ALDERLAKE"]["model"],
                   CPUS["ALDERLAKE_L"]["model"],
                   CPUS["ALDERLAKE_N"]["model"],),
    "ROCKETLAKE": (CPUS["ROCKETLAKE"]["model"],),
    "TIGERLAKE":  (CPUS["TIGERLAKE"]["model"],
                   CPUS["TIGERLAKE_L"]["model"],),
    "LAKEFIELD":  (CPUS["LAKEFIELD"]["model"],),
    "ICELAKE":    (CPUS["ICELAKE"]["model"],
                   CPUS["ICELAKE_L"]["model"],
                   CPUS["ICELAKE_D"]["model"],
                   CPUS["ICELAKE_X"]["model"],),
    "ICL_CLIENT": (CPUS["ICELAKE"]["model"],
                   CPUS["ICELAKE_L"]["model"],),
    "ICX":        (CPUS["ICELAKE_D"]["model"],
                   CPUS["ICELAKE_X"]["model"],),
    "COMETLAKE":  (CPUS["COMETLAKE"]["model"],
                   CPUS["COMETLAKE_L"]["model"],),
    "KABYLAKE":   (CPUS["KABYLAKE"]["model"],
                   CPUS["KABYLAKE_L"]["model"],),
    "CANNONLAKE": (CPUS["CANNONLAKE_L"]["model"],),
    "SKYLAKE":    (CPUS["SKYLAKE"]["model"],
                   CPUS["SKYLAKE_L"]["model"],
                   CPUS["SKYLAKE_X"]["model"],),
    "SKL_CLIENT": (CPUS["SKYLAKE"]["model"],
                   CPUS["SKYLAKE_L"]["model"]),
    "SKX":        (CPUS["SKYLAKE_X"]["model"],),
    "BROADWELL":  (CPUS["BROADWELL"]["model"],
                   CPUS["BROADWELL_G"]["model"],
                   CPUS["BROADWELL_D"]["model"],
                   CPUS["BROADWELL_X"]["model"],),
    "HASWELL":    (CPUS["HASWELL"]["model"],
                   CPUS["HASWELL_L"]["model"],
                   CPUS["HASWELL_G"]["model"],
                   CPUS["HASWELL_X"]["model"],),
    "IVYBRIDGE":  (CPUS["IVYBRIDGE"]["model"],
                   CPUS["IVYBRIDGE_X"]["model"],),
    "SANDYBRIDGE":(CPUS["SANDYBRIDGE"]["model"],
                   CPUS["SANDYBRIDGE_X"]["model"],),
    "WESTMERE":   (CPUS["WESTMERE"]["model"],
                   CPUS["WESTMERE_EP"]["model"],
                   CPUS["WESTMERE_EX"]["model"],),
    "NEHALEM":    (CPUS["NEHALEM"]["model"],
                   CPUS["NEHALEM_G"]["model"],
                   CPUS["NEHALEM_EP"]["model"],
                   CPUS["NEHALEM_EX"]["model"]),
    "CRESTMONT":  (CPUS["GRANDRIDGE"]["model"],
                   CPUS["SIERRAFOREST_X"]["model"]),
    "TREMONT":    (CPUS["ATOM_TREMONT"]["model"],
                   CPUS["ATOM_TREMONT_L"]["model"],
                   CPUS["TREMONT_D"]["model"],),
    "GOLDMONT":   (CPUS["ATOM_GOLDMONT"]["model"],
                   CPUS["GOLDMONT_D"]["model"],
                   CPUS["ATOM_GOLDMONT_PLUS"]["model"],),
    "AIRMONT":    (CPUS["ATOM_AIRMONT"]["model"],),
    "SILVERMONT": (CPUS["ATOM_SILVERMONT"]["model"],
                   CPUS["ATOM_SILVERMONT_MID"]["model"],
                   CPUS["ATOM_SILVERMONT_MID1"]["model"],
                   CPUS["ATOM_SILVERMONT_D"]["model"],),
    "PHI":        (CPUS["XEON_PHI_KNL"]["model"],
                   CPUS["XEON_PHI_KNM"]["model"],),
}

# The levels names have to be the same as 'sname' names in 'PStates', 'CStates', etc.
LEVELS = ("CPU", "core", "module", "die", "node", "package")

# 'NA' is used for the CPU/core/module number for I/O dies, which do not include CPUs, cores, or
# modules. Use a very large number to make sure the the 'NA' numbers go last when sorting.
NA = 0xFFFFFFFF

class CPUInfo(ClassHelpers.SimpleCloseContext):
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
            online = list(new_online_cpus - old_online_cpus)

            tinfo = {cpu: {"CPU": cpu} for cpu in online}
            for tline in self._topology["CPU"]:
                if tline["CPU"] in new_online_cpus:
                    tinfo[tline["CPU"]] = tline

            if "package" in self._initialized_levels or "core" in self._initialized_levels:
                self._add_cores_and_packages(tinfo, online)
            if "module" in self._initialized_levels:
                self._add_modules(tinfo, online)
            if "die" in self._initialized_levels:
                self._add_compute_dies(tinfo, online)
            if "node" in self._initialized_levels:
                self._add_nodes(tinfo)

            topology = list(tinfo.values())

            if "die" in self._initialized_levels:
                self._add_io_dies(topology)
            elif "die" in self._initialized_levels:
                self._add_io_dies_from_cache(topology)

            for order in self._initialized_levels:
                self._sort_topology(topology, order)

        self._must_update_topology = False

    def _add_cores_and_packages(self, tinfo, cpus):
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

    def _add_modules(self, tinfo, cpus):
        """Adds module numbers for CPUs 'cpus' to 'tinfo'"""

        no_cache_info = False
        for cpu in cpus:
            if "module" in tinfo[cpu]:
                continue

            if no_cache_info:
                tinfo[cpu]["module"] = tinfo[cpu]["core"]
                continue

            base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
            try:
                data = self._pman.read(base / "cache/index2/id")
            except ErrorNotFound as err:
                if not no_cache_info:
                    _LOG.debug("no CPU cache topology info found%s:\n%s.",
                               self._pman.hostmsg, err.indent(2))
                    no_cache_info = True
                    tinfo[cpu]["module"] = tinfo[cpu]["core"]
                    continue

            module = Trivial.str_to_int(data, "module number")
            siblings = self._read_range(base / "cache/index2/shared_cpu_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'shared_cpu_list' file included an offline CPU.
                with suppress(KeyError):
                    tinfo[sibling]["module"] = module

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            # Disable caching because it does not add value - the MSR should be read only once for
            # every online CPU, and also to exclude usage of the 'cpuinfo' object by the 'MSR'
            # module, which happens when 'MSR' module uses 'PerCPUCache'.
            self._msr = MSR.MSR(self._pman, cpuinfo=self, enable_cache=False)

        return self._msr

    def _get_pliobj(self):
        """Returns a 'PMLogicalId.PMLogicalID()' object."""

        if not self._pliobj:
            if not self._pli_msr_supported:
                return None

            from pepclibs.msr import PMLogicalId # pylint: disable=import-outside-toplevel

            msr = self._get_msr()

            try:
                self._pliobj = PMLogicalId.PMLogicalId(pman=self._pman, cpuinfo=self, msr=msr)
            except ErrorNotSupported:
                self._pli_msr_supported = False

        return self._pliobj

    def _get_uncfreq_obj(self):
        """Return an '_UncoreFreq' object."""

        if not self._uncfreq_supported:
            return None

        if not self._uncfreq_obj:
            from pepclibs import _UncoreFreq # pylint: disable=import-outside-toplevel

            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreq(self, pman=self._pman)
            except ErrorNotSupported:
                self._uncfreq_supported = False

        return self._uncfreq_obj

    def _add_io_dies(self, topology):
        """Add I/O dies to the 'topology' topology table (list of dictionaries)."""

        uncfreq_obj = self._get_uncfreq_obj()
        if not uncfreq_obj:
            return

        # The 'UncoreFreq' class is I/O dies-aware.
        dies_info = uncfreq_obj.get_dies_info()

        for package, pkg_dies in dies_info.items():
            for die in pkg_dies:
                if die in self._compute_dies[package]:
                    continue

                tline = {}
                for key in LEVELS:
                    # At this point the topology table lines may not even include some levels (e.g.,
                    # "numa" may not be there). But they may be added later. Add them for the I/O
                    # die topology table lines now, so that later the lines would not need # to be
                    # updated.
                    tline[key] = NA
                tline["package"] = package
                tline["die"] = die
                topology.append(tline)

                # Cache the I/O die number.
                self._io_dies[package].add(die)

    def _add_io_dies_from_cache(self, topology):
        """Append the cached I/O dies to the 'topology' topology table (list of dictionaries)."""

        for package, pkg_dies in self._io_dies.items():
            for die in pkg_dies:
                tline = {}
                for key in LEVELS:
                    # At this point the topology table lines may not even include some levels (e.g.,
                    # "numa" may not be there). But they may be added later. Add them for the I/O
                    # die topology table lines now, so that later the lines would not need # to be
                    # updated.
                    tline[key] = NA
                tline["package"] = package
                tline["die"] = die
                topology.append(tline)

    def _add_compute_dies(self, tinfo, cpus):
        """Adds die numbers for CPUs 'cpus' to 'tinfo'"""

        def _add_compute_die(tinfo, cpu, die):
            """Add compute die number 'die'."""

            tinfo[cpu]["die"] = die
            package = tinfo[cpu]["package"]
            if package not in self._compute_dies:
                self._compute_dies[package] = set()
                # Initialize the I/O dies cache at the same time.
                self._io_dies[package] = set()
            self._compute_dies[package].add(die)

        pli_obj = self._get_pliobj()

        for cpu in cpus:
            if "die" in tinfo[cpu]:
                continue

            if pli_obj:
                # Domain IDs match the die numbers.
                die = pli_obj.read_cpu_feature("domain_id", cpu)
                _add_compute_die(tinfo, cpu, die)
                continue

            base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
            data = self._pman.read(base / "topology/die_id")
            die = Trivial.str_to_int(data, "die number")
            siblings = self._read_range(base / "topology/die_cpus_list")
            for _ in siblings:
                # Suppress 'KeyError' in case the 'die_cpus_list' file included an offline CPU.
                with suppress(KeyError):
                    _add_compute_die(tinfo, cpu, die)

    def _add_nodes(self, tinfo):
        """Adds NUMA node numbers to 'tinfo'."""

        nodes = self._read_range("/sys/devices/system/node/online")
        for node in nodes:
            cpus = self._read_range(f"/sys/devices/system/node/node{node}/cpulist")
            for cpu in cpus:
                # Suppress 'KeyError' in case the 'cpulist' file included an offline CPU.
                with suppress(KeyError):
                    tinfo[cpu]["node"] = node

    def _get_topology(self, levels, order="CPU"):
        """
        Build and return topology list, refer to 'get_topology()' for more information. For
        optimization purposes, try to build only the necessary parts of the topology - only the
        levels in 'levels'.
        """

        if self._must_update_topology:
            self._update_topology()

        levels = set(levels)
        levels.update(set(self._sorting_map[order]))
        levels -= self._initialized_levels

        if not levels:
            # The topology for the necessary levels has already been built, just return it.
            return self._topology[order]

        if not self._topology:
            tinfo = {cpu: {"CPU": cpu} for cpu in self._get_online_cpus()}
        else:
            tinfo = {tline["CPU"]: tline for tline in self._topology["CPU"] if tline["CPU"] != NA}

        cpus = self._get_online_cpus()
        self._add_cores_and_packages(tinfo, cpus)
        levels.update({"package", "core"})

        if "module" in levels:
            self._add_modules(tinfo, cpus)
        if "die" in levels:
            self._add_compute_dies(tinfo, cpus)
        if "node" in levels:
            self._add_nodes(tinfo)

        topology = list(tinfo.values())

        if "die" in levels:
            self._add_io_dies(topology)
        elif "die" in self._initialized_levels:
            self._add_io_dies_from_cache(topology)

        self._initialized_levels.update(levels)
        for level in self._initialized_levels:
            self._sort_topology(topology, level)

        return self._topology[order]

    def _validate_level(self, lvl, name="level"):
        """Validate that 'lvl' is a valid level name."""

        if lvl not in self._lvl2idx:
            levels = ", ".join(LEVELS)
            raise Error(f"bad {name} name '{lvl}', use: {levels}")

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
            return sorted(self._get_online_cpus())

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

    def _get_online_cpus(self):
        """Return set of online CPU numbers."""

        if not self._cpus:
            self._cpus = set(self._read_range("/sys/devices/system/cpu/online"))
        return self._cpus

    def get_offline_cpus(self):
        """Return list of offline CPU numbers sorted in ascending order."""

        cpus = self._get_all_cpus()
        online_cpus = self._get_online_cpus()
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
        return len(self._get_online_cpus())

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
            allcpus = self._get_online_cpus()

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

        if self._pman.exists("/sys/devices/cpu_atom/cpus"):
            cpuinfo["hybrid"] = True
        else:
            cpuinfo["hybrid"] = False
            with suppress(Error):
                kver = KernelVersion.get_kver(pman=self._pman)
                if KernelVersion.kver_lt(kver, "5.13"):
                    _LOG.debug("kernel v%s does not support hybrid CPU topology. The minimum "
                               "required kernel version is v5.13.", kver)

        return cpuinfo

    def _get_cpu_description(self):
        """Build and return a string identifying and describing the processor."""

        if "Genuine Intel" in self.info["modelname"]:
            # Pre-release firmware on Intel CPU describes them as "Genuine Intel", which is not very
            # helpful.
            cpudescr = f"Intel processor model {self.info['model']:#x}"

            for info in CPUS.values():
                if info["model"] == self.info["model"]:
                    cpudescr += f" (codename: {info['codename']})"
                    break
        else:
            cpudescr = self.info["modelname"]

        return cpudescr

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        self._pman = pman
        self._close_pman = pman is None

        self._msr = None
        self._pliobj = None
        # 'True' if 'MSR_PM_LOGICAL_ID' is supported by the system, otherwise 'False'. When this MSR
        # is supported, it provides the die IDs enumeration.
        self._pli_msr_supported = True
        self._uncfreq_obj = None
        self._uncfreq_supported = True

        # The topology dictionary. See 'get_topology()' for more information.
        self._topology = {}
        # Stores all initialized topology levels.
        self._initialized_levels = set()
        # This flag notifies '_get_topology()' that some CPUs have been offline/online.
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
        self._lvl2idx = {lvl: idx for idx, lvl in enumerate(LEVELS)}

        # Set of online and offline CPUs.
        self._all_cpus = None
        # Set of online CPUs.
        self._cpus = None
        # Dictionary of P-core/E-core CPUs.
        self._hybrid_cpus = None
        # Per-package compute die numbers (dies which have CPUs) and I/O die numbers (dies which do
        # not have CPUs). Dictionaries with package numbers as key and set of die numbers as values.
        self._compute_dies = {}
        self._io_dies = {}

        # General CPU information.
        self.info = None
        # A short CPU description string.
        self.cpudescr = None

        # CPU cache information dictionary.
        self._cacheinfo = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        self.info = self._get_cpu_info()
        self.cpudescr = self._get_cpu_description()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman", "_msr", "_pliobj", "_uncfreq_obj"))
