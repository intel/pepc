# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides API for getting CPU information.
"""

import re
import copy
import json
import logging
from pathlib import Path
from contextlib import suppress
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
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
GNRS =         (CPUS["GRANITERAPIDS_X"]["model"],
                CPUS["GRANITERAPIDS_D"]["model"])
EMRS =         (CPUS["EMERALDRAPIDS_X"]["model"],)
METEORLAKES =  (CPUS["METEORLAKE"]["model"],
                CPUS["METEORLAKE_L"]["model"],)
SPRS =         (CPUS["SAPPHIRERAPIDS_X"]["model"],)
RAPTORLAKES =  (CPUS["RAPTORLAKE"]["model"],
                CPUS["RAPTORLAKE_P"]["model"],
                CPUS["RAPTORLAKE_S"]["model"],)
ALDERLAKES =   (CPUS["ALDERLAKE"]["model"],
                CPUS["ALDERLAKE_L"]["model"],
                CPUS["ALDERLAKE_N"]["model"],)
ROCKETLAKES =  (CPUS["ROCKETLAKE"]["model"],)
TIGERLAKES =   (CPUS["TIGERLAKE"]["model"],
                CPUS["TIGERLAKE_L"]["model"],)
LAKEFIELDS =   (CPUS["LAKEFIELD"]["model"],)
ICELAKES =     (CPUS["ICELAKE"]["model"],
                CPUS["ICELAKE_L"]["model"],
                CPUS["ICELAKE_D"]["model"],
                CPUS["ICELAKE_X"]["model"],)
ICL_CLIENTS =  (CPUS["ICELAKE"]["model"],
                CPUS["ICELAKE_L"]["model"],)
ICXES       =  (CPUS["ICELAKE_D"]["model"],
                CPUS["ICELAKE_X"]["model"],)
COMETLAKES =   (CPUS["COMETLAKE"]["model"],
                CPUS["COMETLAKE_L"]["model"],)
KABYLAKES =    (CPUS["KABYLAKE"]["model"],
                CPUS["KABYLAKE_L"]["model"],)
CANNONLAKES =  (CPUS["CANNONLAKE_L"]["model"],)
SKYLAKES =     (CPUS["SKYLAKE"]["model"],
                CPUS["SKYLAKE_L"]["model"],
                CPUS["SKYLAKE_X"]["model"],)
SKL_CLIENTS =  (CPUS["SKYLAKE"]["model"],
                CPUS["SKYLAKE_L"]["model"])
SKXES =        (CPUS["SKYLAKE_X"]["model"],)
BROADWELLS =   (CPUS["BROADWELL"]["model"],
                CPUS["BROADWELL_G"]["model"],
                CPUS["BROADWELL_D"]["model"],
                CPUS["BROADWELL_X"]["model"],)
HASWELLS =     (CPUS["HASWELL"]["model"],
                CPUS["HASWELL_L"]["model"],
                CPUS["HASWELL_G"]["model"],
                CPUS["HASWELL_X"]["model"],)
IVYBRIDGES =   (CPUS["IVYBRIDGE"]["model"],
                CPUS["IVYBRIDGE_X"]["model"],)
SANDYBRIDGES = (CPUS["SANDYBRIDGE"]["model"],
                CPUS["SANDYBRIDGE_X"]["model"],)
WESTMERES =    (CPUS["WESTMERE"]["model"],
                CPUS["WESTMERE_EP"]["model"],
                CPUS["WESTMERE_EX"]["model"],)
NEHALEMS =     (CPUS["NEHALEM"]["model"],
                CPUS["NEHALEM_G"]["model"],
                CPUS["NEHALEM_EP"]["model"],
                CPUS["NEHALEM_EX"]["model"])

CRESTMONTS =   (CPUS["GRANDRIDGE"]["model"],
                CPUS["SIERRAFOREST_X"]["model"])
TREMONTS =     (CPUS["ATOM_TREMONT"]["model"],
                CPUS["ATOM_TREMONT_L"]["model"],
                CPUS["TREMONT_D"]["model"],)
GOLDMONTS =    (CPUS["ATOM_GOLDMONT"]["model"],
                CPUS["GOLDMONT_D"]["model"],
                CPUS["ATOM_GOLDMONT_PLUS"]["model"],)
AIRMONTS =     (CPUS["ATOM_AIRMONT"]["model"],)
SILVERMONTS =  (CPUS["ATOM_SILVERMONT"]["model"],
                CPUS["ATOM_SILVERMONT_MID"]["model"],
                CPUS["ATOM_SILVERMONT_MID1"]["model"],
                CPUS["ATOM_SILVERMONT_D"]["model"],)

PHIS =         (CPUS["XEON_PHI_KNL"]["model"],
                CPUS["XEON_PHI_KNM"]["model"],)

# The levels names have to be the same as 'sname' names in 'PStates', 'CStates', etc.
LEVELS = ("CPU", "core", "module", "die", "node", "package")

class CPUInfo(ClassHelpers.SimpleCloseContext):
    """
    Provide information about the CPU of a local or remote host.

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
        * 'get_packages_count()'
        * 'get_offline_cpus_count()'
    5. Normalize a list of packages/cores/etc.
        A. Multiple packages/CPUs/etc numbers:
            * 'normalize_cpus()'
            * 'normalize_dies()'
            * 'normalize_packages()'
        B. Single package/CPU/etc.
            * 'normalize_cpu()'
            * 'normalize_die()'
            * 'normalize_package()'
    6. Select CPUs by sibling index.
        * 'select_core_siblings()'
        * 'select_module_siblings()'
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
            online = list(new_online_cpus - old_online_cpus)

            tinfo = {cpu : {"CPU" : cpu} for cpu in online}
            for tline in self._topology["CPU"]:
                if tline["CPU"] in new_online_cpus:
                    tinfo[tline["CPU"]] = tline

            if "package" in self._initialized_levels or "core" in self._initialized_levels:
                self._add_core_and_package_numbers(tinfo, online)
            if "module" in self._initialized_levels:
                self._add_module_numbers(tinfo, online)
            if "die" in self._initialized_levels:
                self._add_die_numbers(tinfo, online)
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
                    _LOG.debug("no CPU cache topology info found%s:\n%s",
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

    def get_dies(self, package=0, order="die"):
        """
        Return list of die numbers in package 'package', only dies containing at least one online
        CPU will be included.
        """
        return self._get_level_nums("die", "package", package, order=order)

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

    def _get_online_cpus(self, update=False):
        """Return set of online CPU numbers."""

        if not self._cpus or update:
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

    def get_offline_cpus_count(self):
        """Return count of offline CPUs."""
        return len(self.get_offline_cpus())

    def get_cpus_count(self):
        """Return count of online CPUs."""
        return len(self._get_online_cpus())

    def get_packages_count(self):
        """Return packages count."""
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

        Return a tuple of two lists: ('cores', 'rem_cpus').
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

        Return a tuple of two lists: ('dies', 'rem_cpus').
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

    def normalize_dies(self, dies, package=0):
        """
        Validate die numbers in 'dies' for package 'package' and return the normalized list. The
        arguments are as follows.
          * dies - collection of integer die numbers to normalize. Special value 'all' means
                   "all diess".
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
        return  self.normalize_cpus((cpu,))[0]

    def normalize_die(self, die, package=0):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_dies((die,), package=package)[0]

    def normalize_package(self, package):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_packages((package,))[0]

    def get_hybrid_cpu_topology(self):
        """
        Return P-core/E-core CPU list on hybrid CPUs, otherwise return 'None'.
        If the kernel does not support hybrid CPU topology, this function will return 'None'
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
        Return a dictionary including CPU cache infomration. The dictionary keys and layout is
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
        self._lvl2idx = {lvl : idx for idx, lvl in enumerate(LEVELS)}

        # The CPU topology sysfs directory path pattern.
        self._topology_sysfs_base = "/sys/devices/system/cpu/cpu%d/topology/"

        # Set of online and offline CPUs.
        self._all_cpus = None
        # Set of online CPUs.
        self._cpus = None
        # Dictionary of P-core/E-core CPUs.
        self._hybrid_cpus = None

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
        ClassHelpers.close(self, close_attrs=("_pman",))
