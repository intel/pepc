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
from pepclibs.helperlibs.Exceptions import Error # pylint: disable=unused-import
from pepclibs.helperlibs import ArgParse, Procs, Trivial

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

# The levels names have to be the same as "scope" names in 'CPUFreq', 'CPUIdle', etc.
LEVELS = ("package", "node", "core", "CPU")

class CPUInfo:
    """
    Provide information about the CPU of a local or remote host.
    """

    def _get_lscpu(self):
        """Return the 'lscpu' output."""

        if self._lscpu_cache:
            return self._lscpu_cache

        # Note, we could just walk sysfs, but 'lscpu' seems a bit more convenient.
        cmd = "lscpu --all -p=socket,node,core,cpu,online"
        lines, _ = self._proc.run_verify(cmd, join=False)

        self._lscpu_cache = []
        for line in lines:
            if line.startswith("#"):
                continue

            # Each line has comma-separated integers for socket, node, core and cpu. For example:
            # 1,1,9,61,Y. In case of offline CPU, the final element is going to be "N".
            line = line.strip().split(",")
            self._lscpu_cache.append(line)

        return self._lscpu_cache

    def _get_level(self, start, end, nums=None):
        """
        Returns list of level 'end' values belonging to level 'start' for each ID in 'nums'. Returns
        all values if 'nums' is None or "all". Offline CPUs are ignored.
        """

        if start not in LEVELS or end not in LEVELS:
            levels = ", ".join(LEVELS)
            raise Error(f"bad levels '{start}','{end}', use: {levels}")

        start_idx = LEVELS.index(start)
        end_idx = LEVELS.index(end)
        if start_idx > end_idx:
            raise Error(f"bad level order, cannot get {end}s from level '{start}'")

        items = {}
        for line in self._get_lscpu():
            if line[-1] != "Y":
                # Skip non-online CPUs.
                continue
            line = [int(val) for val in line[0:-1]]
            if line[start_idx] in items.keys():
                items[line[start_idx]].append(line[end_idx])
            else:
                items[line[start_idx]] = [line[end_idx]]

        # So now 'items' is a dictionary with keys being the 'start' level elements and values being
        # lists of the 'end' level elements.
        # For example, suppose we are looking for CPUs in packages, and the system has 2 packages,
        # each containing 8 CPUs. The 'items' dictionary will look like this:
        # items[0] = {0, 2, 4, 6, 8, 10, 12, 14}
        # items[1] = {1, 3, 6, 7, 9, 11, 13, 15}
        # In this example, package 0 includes CPUs with even numbers, and package 1 includes CPUs
        # with odd numbers.

        if nums is None or nums == "all":
            nums = list(items.keys())
        else:
            nums = ArgParse.parse_int_list(nums, ints=True, dedup=True, sort=True)

        result = []
        for num in nums:
            if num not in items:
                items_str = ", ".join(str(key) for key in items)
                raise Error(f"{start} {num} does not exist{self._proc.hostmsg}, use: {items_str}")
            result += items[num]

        return Trivial.list_dedup(result)

    def get_cpus(self):
        """Returns list of online CPU numbers."""
        return self._get_level("CPU", "CPU")

    def get_cores(self):
        """Returns list of core numbers, where at least one online CPU."""
        return self._get_level("core", "core")

    def get_packages(self):
        """Returns list of package numbers, where at least one online CPU."""
        return self._get_level("package", "package")

    def cores_to_cpus(self, cores=None):
        """
        Returns list of online CPU numbers belonging to cores 'cores'. The 'cores' argument is
        allowed to contain both integer and string type numbers. For example, both are OK: '(0, 2)'
        and '("0", "2")'. Returns all CPU numbers if 'cores' is None or "all".
        """
        return self._get_level("core", "CPU", nums=cores)

    def packages_to_cores(self, packages=None):
        """
        Returns list of cores with at least one online CPU belonging to packages 'packages'. The
        'packages' argument similar to 'cores' in 'cores_to_cpus()'.
        """
        return self._get_level("package", "core", nums=packages)

    def packages_to_cpus(self, packages=None):
        """
        Returns list of online CPU numbers belonging to packages 'packages'. The 'packages' argument
        is similar 'cores' in 'cores_to_cpus()'.
        """
        return self._get_level("package", "CPU", nums=packages)

    def normalize_cpus(self, cpus):
        """
        Validate CPU numbers 'cpus' and return a normalized list. The input numbers may be integers
        or strings containing integer numbers. The output will be list of integers, duplicate
        numbers will be removed.
        """

        allcpus = self.get_cpus()

        if cpus is None or cpus == "all":
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

    def normalize_packages(self, pkgs):
        """Same as 'normalize_cpus()', but for package numbers."""

        allpkgs = self.get_packages()

        if pkgs is None or pkgs == "all":
            return allpkgs

        allpkgs = set(allpkgs)
        pkgs = ArgParse.parse_int_list(pkgs, ints=True, dedup=True)
        for pkg in pkgs:
            if pkg not in allpkgs:
                pkgs_str = ", ".join([str(pkg) for pkg in sorted(allpkgs)])
                raise Error(f"package '{pkg}' not available{self._proc.hostmsg}, available "
                            f"packages are: {pkgs_str}")

        return pkgs

    def normalize_package(self, package):
        """Same as 'normalize_packages()', but for a single package number."""
        return self.normalize_packages([package])[0]

    def cpu_to_package(self, cpu):
        """Returns integer package number for CPU number 'cpu'."""

        for pkg in self.get_packages():
            if cpu in self.packages_to_cpus(packages=pkg):
                return pkg

        allcpus = self.get_cpus()
        cpus_str = ", ".join([str(cpu) for cpu in sorted(allcpus)])
        raise Error(f"CPU{cpu} is not available{self._proc.hostmsg}, available CPUs are:\n"
                    f"{cpus_str}")

    def cpu_to_core(self, cpu):
        """Returns integer core number for CPU number 'cpu'."""

        for core in self.get_cores():
            if cpu in self.cores_to_cpus(cores=core):
                return core

        allcpus = self.get_cpus()
        cpus_str = ", ".join([str(cpu) for cpu in sorted(allcpus)])
        raise Error(f"CPU{cpu} is not available{self._proc.hostmsg}, available CPUs are:\n"
                    f"{cpus_str}")

    def _add_nums(self, nums):
        """Add numbers from 'lscpu' to the CPU geometry dictionary."""

        item = self.cpugeom[LEVELS[0]]["nums"]
        for idx, lvl in enumerate(LEVELS[:-1]):
            last_level = False
            if idx == len(LEVELS) - 2:
                last_level = True

            num = int(nums[lvl])
            if num not in item:
                self.cpugeom[lvl]["cnt"] += 1
                if last_level:
                    item[num] = []
                else:
                    item[num] = {}

            if last_level:
                lvl = LEVELS[-1]
                item[num].append(int(nums[lvl]))
                self.cpugeom[lvl]["cnt"] += 1

            item = item[num]

    def _flatten_to_level(self, items, idx):
        """Flatten the multi-level 'items' dictionary down to level 'idx'."""

        if idx == 0:
            return items

        result = {}
        for item in items.values():
            add_items = self._flatten_to_level(item, idx - 1)
            if isinstance(add_items, list):
                if not result:
                    result = []
                result += add_items
            else:
                result.update(add_items)

        return result

    def get_cpu_geometry(self):
        """
        Get CPU geometry information. The returned geometry dictionary is returned and also saved in
        'self.cpugeom'. Note, if this method was already called before, it will just return
        'self.cpugeom'.

        The geometry dictionary structure.

        1. The top level geometry dictionary keys are the level names ("CPU", "core", etc). There
           are no other top level keys, so the top level structure is as follows.

           cpugeom = {
             "CPU"  : {<CPU level info>},
             "core" : {<core level info>},
             ... and so on for each level, see 'LEVELS' ...
             "package" : {<package level info>}
           }

        2. Every level info is a dictionary too. Each level info will contain the following keys.
           * cnt - count of elements (CPUs, cores, etc).
           * cnt_per_<level> - count of elements in upper levels.
           * nums - element numbers dictionary.

        3. There are some keys unique to the specific level. For example, the "CPU" level includes
           the 'offline_cnt' key, which provides the offline CPUs count.

        Here is an example cpugeom dictionary for a 2-core single socket system with 2 logical CPUs
        per core and one node per package, and no off-lined CPUs.

        { 'CPU':     {
                       'cnt': 4,
                       'cnt_per_core': 2,
                       'cnt_per_node': 4,
                       'cnt_per_package': 4,
                       'nums': [ 0, 2, 1, 3 ],
                       'offline_cnt': 0,
                       'offline_cpus': []
                     },
          'core':    {
                       'cnt': 2,
                       'cnt_per_node': 2,
                       'cnt_per_package': 2,
                       'nums': {
                                 0: [0, 2],
                                 1: [1, 3],
                               },
                     },
          'node':    {
                       'cnt': 1,
                       'cnt_per_package': 1,
                       'nums': {
                                 0: {
                                      0: [0, 2],
                                      1: [1, 3]
                                    },
                               },
                     },
          'package': {
                       'cnt': 1,
                       'nums': {
                                 0: {
                                      0: {
                                           0: [0, 2],
                                           1: [1, 3],
                                         },
                                    },
                                },
                     },

        In this examples, 'nums' in the 'node' info dictionary says that there is node number 0,
        which includes core number 0 and 1, which include CPUs numbers 0,2 and 1,3 respectively.
        """

        if self.cpugeom:
            return self.cpugeom

        self.cpugeom = cpugeom = {}
        for lvl in LEVELS:
            cpugeom[lvl] = {}
            cpugeom[lvl]["nums"] = {}
            cpugeom[lvl]["cnt"] = 0

        # List of offline CPUs. Note, Linux does not provide topology information for offline CPUs,
        # so we have the CPU numbers, but do not know to what core/package they belong to.
        cpugeom["CPU"]["offline_cpus"] = []
        # Offline CPUs count.
        cpugeom["CPU"]["offline_cnt"] = 0

        # Parse the 'lscpu' output.
        for line in self._get_lscpu():
            nums = {key : line[idx] for idx, key in enumerate(LEVELS)}
            if line[-1] != "Y":
                cpugeom["CPU"]["offline_cnt"] += 1
                cpugeom["CPU"]["offline_cpus"].append(int(nums["CPU"]))
                continue

            self._add_nums(nums)

        # Now we have the full hierarchy (in 'cpugeom["packages"]'). Create partial hierarchies
        # ('cpugeom["nodes"]', etc).
        #
        # Start with filling the 'nums'.
        for lvlidx, lvl in enumerate(LEVELS[1:]):
            cpugeom[lvl]["nums"] = self._flatten_to_level(cpugeom[LEVELS[0]]["nums"], lvlidx + 1)

        # Fill 'cnt_per_*' keys.
        for lvl1idx, lvl1 in enumerate(LEVELS[1:]):
            for lvl2idx, lvl2 in enumerate(LEVELS):
                # We need to iterate over all levels higher than 'lvl1'. Larger index corresponds to
                # lower level.
                if lvl2idx > lvl1idx:
                    continue
                key = f"cnt_per_{lvl2}"
                try:
                    cpugeom[lvl1][key] = int(cpugeom[lvl1]["cnt"] / cpugeom[lvl2]["cnt"])
                except ZeroDivisionError:
                    cpugeom[lvl1][key] = 0

        return cpugeom

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
        self._lscpu_cache = None

        self.info = None
        self.cpugeom = None
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
