# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide the base class for the 'CPUInfo.CPUInfo' class.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pathlib import Path
from pepclibs import CPUModels, ProcCpuinfo
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Iterable
    from pepclibs import _DieInfo
    from pepclibs.ProcCpuinfo import ProcCpuinfoTypedDict, ProcCpuinfoPerCPUTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import (ScopeNameType, AbsNumsType, HybridCPUKeyType,
                                       HybridCPUKeyInfoType)

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUInfoBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for 'CPUInfo.CPUInfo'. Provides low-level functionality, while 'CPUInfo' implements
    the public API.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 dieinfo: _DieInfo.DieInfo | None = None):
        """
        Initialize a class instance.

        Args:
            pman: Process manager object that defines the target host. If not provided, a local
                  process manager is created.
            dieinfo: An instance of the '_DieInfo' class. If not provided, a new instance is
                     created.
        """

        _LOG.debug("Initializing the '%s' class object", self.__class__.__name__)

        # A short CPU description string.
        self.cpudescr = ""

        self._close_pman = pman is None
        self._close_dieinfo = dieinfo is None

        # Online CPU numbers sorted in ascending order.
        self._cpus: list[int] = []
        # Set of online CPU numbers.
        self._cpus_set: set[int] = set()
        # List of online and offline CPUs sorted in ascending order.
        self._all_cpus: list[int] = []
        # Set of online and offline CPUs.
        self._all_cpus_set: set[int] = set()
        # Dictionary of P-core/E-core CPUs.
        self._hybrid_cpus: dict[HybridCPUKeyType, list[int]] = {}

        self._dieinfo = dieinfo
        self._dieinfo_errmsg = ""

        # The topology dictionary.
        self._topology: dict[ScopeNameType, list[dict[ScopeNameType, int]]] = {}

        # Topology scopes that have been already initialized.
        self._initialized_snames: set[ScopeNameType] = set()

        # CPU to topology line cache for O(1) lookups.
        self._cpu_to_tline: dict[int, dict[ScopeNameType, int]] = {}

        # Sibling index caches: CPU -> sibling index within core/module.
        self._cpu_to_core_index: dict[int, int] = {}
        self._cpu_to_module_index: dict[int, int] = {}

        # Core and die to CPU numbers caches: package -> core/die -> frozenset of CPU numbers.
        # Core and die numbers are not globally unique, they are per-package.
        self._core_to_cpus: dict[int, dict[int, frozenset[int]]] = {}
        self._die_to_cpus: dict[int, dict[int, frozenset[int]]] = {}

        # Module, node, and package to CPU numbers caches: module/node/package -> frozenset of
        # CPU numbers. Module, node, and package numbers are globally unique.
        self._module_to_cpus: dict[int, frozenset[int]] = {}
        self._node_to_cpus: dict[int, frozenset[int]] = {}
        self._package_to_cpus: dict[int, frozenset[int]] = {}

        # The topology dictionary is a dictionary of lists where keys are scope names. The values
        # are lists of topology lines (tlines) sorted in the key order (or more precisely, in the
        # order specified by the sorting map).
        #
        # Note, core and die numbers are relative to the package. For this reason, the die and core
        # topology lines are sorted by package first, then by die/core.
        self._sorting_map: dict[ScopeNameType, tuple[ScopeNameType, ...]] = \
            {"CPU":     ("CPU",),
             "core":    ("package", "core", "CPU"),
             "module":  ("module", "CPU"),
             "die":     ("package", "die", "CPU"),
             "node":    ("node", "CPU"),
             "package": ("package", "CPU")}

        self._cpu_sysfs_base = Path("/sys/devices/system/cpu")

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        self._proc_cpuinfo: ProcCpuinfoTypedDict = {}
        self._proc_percpuinfo: ProcCpuinfoPerCPUTypedDict = {}

        # TODO: make 'cpudescr' and 'is_hybrid' lazy.
        self.cpudescr = self._get_cpu_description()

        if self._pman.exists("/sys/devices/cpu_atom/cpus"):
            self.is_hybrid = True
        else:
            self.is_hybrid = False

    def close(self):
        """Uninitialize the class instance."""

        _LOG.debug("Closing the '%s' class object", self.__class__.__name__)

        ClassHelpers.close(self, close_attrs=("_dieinfo", "_pman"))

    def get_proc_cpuinfo(self) -> ProcCpuinfoTypedDict:
        """
        Return the general '/proc/cpuinfo' information dictionary.

        Returns:
            The general '/proc/cpuinfo' information dictionary.
        """

        if not self._proc_cpuinfo:
            self._proc_cpuinfo = ProcCpuinfo.get_proc_cpuinfo(self._pman)
        return self._proc_cpuinfo

    def get_proc_percpuinfo(self) -> ProcCpuinfoPerCPUTypedDict:
        """
        Return the per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The per-CPU '/proc/cpuinfo' topology information dictionary.
        """

        if not self._proc_percpuinfo:
            self._proc_percpuinfo = ProcCpuinfo.get_proc_percpuinfo(self._pman)
        return self._proc_percpuinfo

    def get_dieinfo(self) -> _DieInfo.DieInfo:
        """
        Return or create an instance of '_DieInfo.DieInfo' object.

        Returns:
            An instance of '_DieInfo.DieInfo' object.
        """

        if self._dieinfo:
            return self._dieinfo

        if self._dieinfo_errmsg:
            raise ErrorNotSupported(self._dieinfo_errmsg)

        _LOG.debug("Creating an instance of '_DieInfo.DieInfo'")

        # pylint: disable-next=import-outside-toplevel
        from pepclibs import _DieInfo

        proc_cpuinfo = self.get_proc_cpuinfo()

        try:
            self._dieinfo = _DieInfo.DieInfo(pman=self._pman, proc_cpuinfo=proc_cpuinfo)
        except Exception as err:
            self._dieinfo_errmsg = str(err)
            _LOG.debug(self._dieinfo_errmsg)
            raise

        return self._dieinfo

    def _add_cores_and_packages(self,
                                cpu_tdict: dict[int, dict[ScopeNameType, int]],
                                cpus: AbsNumsType):
        """
        Add core and package numbers for the specified CPUs to the CPU topology dictionary.

        Args:
            cpu_tdict: CPU topology dictionary to update with core and package information.
            cpus: CPU numbers for which to add core and package numbers.
        """

        cpus_set = set(cpus)

        proc_percpuinfo = self.get_proc_percpuinfo()
        for package, pkg_cores in proc_percpuinfo["topology"].items():
            for core, core_cpus in pkg_cores.items():
                for cpu in core_cpus:
                    if cpu in cpus_set:
                        cpu_tdict[cpu]["package"] = package
                        cpu_tdict[cpu]["core"] = core

    def _add_modules(self, cpu_tdict: dict[int, dict[ScopeNameType, int]], cpus: AbsNumsType):
        """
        Add module numbers for the specified CPUs to the CPU topology dictionary.

        Args:
            cpu_tdict: CPU topology dictionary to update with module information.
            cpus: CPU numbers for which to add module numbers.

        Notes:
            - Module numbers are read from the sysfs files under
              '/sys/devices/system/cpu/cpu<cpu>/cache/index2/'.
        """

        _LOG.debug("Reading CPU module information from sysfs")

        # Whether the L2 cache topology information is available in sysfs.
        cache_info_available = False

        for cpu in cpus:
            if "module" in cpu_tdict[cpu]:
                continue

            base = Path(f"{self._cpu_sysfs_base}/cpu{cpu}")
            try:
                data = self._pman.read_file(base / "cache/index2/id")
            except ErrorNotFound as err:
                if cache_info_available:
                    raise Error(f"CPU cache topology info is inconsistent{self._pman.hostmsg}: "
                                f"found for some CPUs but not for CPU {cpu}") from err

                # First CPU failure: cache topology info not available system-wide.
                _LOG.debug("No CPU cache topology info found%s:\n%s.",
                           self._pman.hostmsg, err.indent(2))

                for cpu in cpus:
                    cpu_tdict[cpu]["module"] = cpu_tdict[cpu]["core"]
                break

            cache_info_available = True
            module = Trivial.str_to_int(data, what="module number")
            siblings = self._read_range(base / "cache/index2/shared_cpu_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'shared_cpu_list' file included an offline CPU.
                with contextlib.suppress(KeyError):
                    cpu_tdict[sibling]["module"] = module

    def _add_compute_dies(self, cpu_tdict: dict[int, dict[ScopeNameType, int]]):
        """
        Add compute die numbers for the CPUs in the CPU topology dictionary.

        Args:
            cpu_tdict: CPU topology dictionary to update with compute die information.
        """

        dieinfo = self.get_dieinfo()
        proc_percpuinfo = self.get_proc_percpuinfo()
        compute_dies_cpus = dieinfo.get_compute_dies_cpus(proc_percpuinfo)

        for pkg_dies in compute_dies_cpus.values():
            for die, die_cpus in pkg_dies.items():
                for cpu in die_cpus:
                    cpu_tdict.setdefault(cpu, {})
                    cpu_tdict[cpu]["die"] = die

    def _add_nodes(self, cpu_tdict: dict[int, dict[ScopeNameType, int]]):
        """
        Add NUMA node numbers for CPUs in the CPU topology dictionary.

        Args:
            cpu_tdict: CPU topology dictionary to update with NUMA node information.

        Notes:
            - NUMA node numbers are read from the sysfs files under
              '/sys/devices/system/node/node<node>/cpulist'.
        """

        _LOG.debug("Reading NUMA node information from sysfs")

        try:
            nodes = self._read_range("/sys/devices/system/node/online")
        except ErrorNotFound:
            # No NUMA information in sysfs, assume a single NUMA node.
            for cpu in cpu_tdict:
                cpu_tdict[cpu]["node"] = 0
        else:
            for node in nodes:
                cpus = self._read_range(f"/sys/devices/system/node/node{node}/cpulist")
                for cpu in cpus:
                    # Suppress 'KeyError' in case the 'cpulist' file included an offline CPU.
                    with contextlib.suppress(KeyError):
                        cpu_tdict[cpu]["node"] = node

    def _sort_topology(self, tlines: list[dict[ScopeNameType, int]], order: ScopeNameType):
        """Sort and save the topology list by 'order' in sorting map."""

        skeys = self._sorting_map[order]
        self._topology[order] = sorted(tlines, key=lambda tline: tuple(tline[s] for s in skeys))

    def _get_topology(self,
                      snames: Iterable[ScopeNameType],
                      order: ScopeNameType = "CPU") -> list[dict[ScopeNameType, int]]:
        """
        Build and return the topology table for the specified scopes, sorted in the specified order.

        Args:
            snames: Scope names to include in the topology table.
            order: Topology table sorting order. Defaults to "CPU".

        Returns:
            The topology table for the specified scopes and order.

        Notes:
            - The topology table is a list of topology lines.
            - Each topology line is a dictionary where keys are scope names and values are the
              corresponding scope numbers (e.g., CPU numbers, core numbers, etc.).
        """

        snames_set = set(snames)
        snames_set.update(set(self._sorting_map[order]))
        snames_set -= self._initialized_snames

        if not snames_set:
            # The topology for the necessary scopes has already been built, just return it.
            return self._topology[order]

        _LOG.debug("Building CPU topology for scopes %s, order '%s'", ", ".join(snames), order)

        # A preliminary CPU topology dictionary. The keys are CPU numbers, and the values are the
        # topology lines.
        cpu_tdict: dict[int, dict[ScopeNameType, int]]

        cpus = self._get_online_cpus()

        if not self._topology:
            cpu_tdict = {cpu: {"CPU": cpu} for cpu in cpus}
        else:
            cpu_tdict = {}
            for tline in self._topology["CPU"]:
                cpu_tdict[tline["CPU"]] = tline

        tlines = list(cpu_tdict.values())

        if "CPU" not in self._initialized_snames or "core" not in self._initialized_snames or \
           "package" not in self._initialized_snames:
            self._add_cores_and_packages(cpu_tdict, cpus)
            snames_set.update({"CPU", "core", "package"})

        if "module" in snames_set:
            self._add_modules(cpu_tdict, cpus)
        if "die" in snames_set:
            self._add_compute_dies(cpu_tdict)
        if "node" in snames_set:
            self._add_nodes(cpu_tdict)

        self._initialized_snames.update(snames_set)
        for level in self._initialized_snames:
            self._sort_topology(tlines, level)

        return self._topology[order]

    def _get_cpu_to_core_index_cache(self) -> dict[int, int]:
        """
        Get or build the CPU-to-core-sibling-index cache.

        Returns:
            Dictionary mapping CPU numbers to their core sibling index.
        """

        if self._cpu_to_core_index:
            return self._cpu_to_core_index

        self._get_topology(("CPU", "core", "package"), order="core")

        core = pkg = index = -1

        for tline in self._topology["core"]:
            cpu = tline["CPU"]
            if tline["core"] != core or tline["package"] != pkg:
                core = tline["core"]
                pkg = tline["package"]
                index = 0
            self._cpu_to_core_index[cpu] = index
            index += 1

        return self._cpu_to_core_index

    def _get_cpu_to_module_index_cache(self) -> dict[int, int]:
        """
        Get or build the CPU-to-module-sibling-index cache.

        Returns:
            Dictionary mapping CPU numbers to their module sibling index.
        """

        if self._cpu_to_module_index:
            return self._cpu_to_module_index

        self._get_topology(("CPU", "module", "package"), order="module")

        module = pkg = index = -1

        for tline in self._topology["module"]:
            cpu = tline["CPU"]
            if tline["module"] != module or tline["package"] != pkg:
                module = tline["module"]
                pkg = tline["package"]
                index = 0
            self._cpu_to_module_index[cpu] = index
            index += 1

        return self._cpu_to_module_index

    def _get_core_to_cpus_cache(self) -> dict[int, dict[int, frozenset[int]]]:
        """
        Get or build the core-to-CPU-numbers cache.

        Returns:
            Dictionary mapping package numbers to dictionaries that map core numbers to
            frozensets of CPU numbers.
        """

        if self._core_to_cpus:
            return self._core_to_cpus

        self._get_topology(("CPU", "core", "package"), order="core")

        for tline in self._topology["core"]:
            pkg = tline["package"]
            core = tline["core"]
            if pkg not in self._core_to_cpus:
                self._core_to_cpus[pkg] = {}
            if core not in self._core_to_cpus[pkg]:
                self._core_to_cpus[pkg][core] = frozenset()
            self._core_to_cpus[pkg][core] |= {tline["CPU"]}

        return self._core_to_cpus

    def _get_die_to_cpus_cache(self) -> dict[int, dict[int, frozenset[int]]]:
        """
        Get or build the die-to-CPU-numbers cache.

        Returns:
            Dictionary mapping package numbers to dictionaries that map die numbers to
            frozensets of CPU numbers.
        """

        if self._die_to_cpus:
            return self._die_to_cpus

        self._get_topology(("CPU", "die", "package"), order="die")

        for tline in self._topology["die"]:
            pkg = tline["package"]
            die = tline["die"]
            if pkg not in self._die_to_cpus:
                self._die_to_cpus[pkg] = {}
            if die not in self._die_to_cpus[pkg]:
                self._die_to_cpus[pkg][die] = frozenset()
            self._die_to_cpus[pkg][die] |= {tline["CPU"]}

        return self._die_to_cpus

    def _get_module_to_cpus_cache(self) -> dict[int, frozenset[int]]:
        """
        Get or build the module-to-CPU-numbers cache.

        Returns:
            Dictionary mapping module numbers to frozensets of CPU numbers.
        """

        if self._module_to_cpus:
            return self._module_to_cpus

        self._get_topology(("CPU", "module"), order="module")

        for tline in self._topology["module"]:
            module = tline["module"]
            if module not in self._module_to_cpus:
                self._module_to_cpus[module] = frozenset()
            self._module_to_cpus[module] |= {tline["CPU"]}

        return self._module_to_cpus

    def _get_node_to_cpus_cache(self) -> dict[int, frozenset[int]]:
        """
        Get or build the node-to-CPU-numbers cache.

        Returns:
            Dictionary mapping node numbers to frozensets of CPU numbers.
        """

        if self._node_to_cpus:
            return self._node_to_cpus

        self._get_topology(("CPU", "node"), order="node")

        for tline in self._topology["node"]:
            node = tline["node"]
            if node not in self._node_to_cpus:
                self._node_to_cpus[node] = frozenset()
            self._node_to_cpus[node] |= {tline["CPU"]}

        return self._node_to_cpus

    def _get_package_to_cpus_cache(self) -> dict[int, frozenset[int]]:
        """
        Get or build the package-to-CPU-numbers cache.

        Returns:
            Dictionary mapping package numbers to frozensets of CPU numbers.
        """

        if self._package_to_cpus:
            return self._package_to_cpus

        self._get_topology(("CPU", "package"), order="package")

        for tline in self._topology["package"]:
            package = tline["package"]
            if package not in self._package_to_cpus:
                self._package_to_cpus[package] = frozenset()
            self._package_to_cpus[package] |= {tline["CPU"]}

        return self._package_to_cpus

    def _read_range(self, path: Path | str) -> list[int]:
        """
        Read a file containing a comma-separated list of integers or integer ranges, and return a
        list of integers.

        Args:
            path: Path to the file to read.

        Returns:
            A list of integers parsed from the file.
        """

        str_of_ranges = self._pman.read_file(path).strip()

        _LOG.debug("Read CPU numbers from '%s'%s: %s", path, self._pman.hostmsg, str_of_ranges)

        what = f"contents of file at '{path}'{self._pman.hostmsg}"
        return Trivial.split_csv_line_int(str_of_ranges, what=what)

    def _get_online_cpus(self) -> list[int]:
        """
        Return a list of online CPU numbers.

        Returns:
            A list containing the online CPU numbers sorted in ascending order.
        """

        if not self._cpus:
            self._cpus = self._read_range(f"{self._cpu_sysfs_base}/online")

        return self._cpus

    def _get_online_cpus_set(self) -> set[int]:
        """
        Return a set of online CPU numbers.

        Returns:
            A set containing the online CPU numbers.
        """

        if not self._cpus_set:
            self._cpus_set = set(self._get_online_cpus())

        return self._cpus_set

    def _get_all_cpus(self) -> list[int]:
        """
        Return a list of all CPU numbers, including both online and offline CPUs.

        Returns:
            A list containing all CPU numbers present in the system, sorted in ascending order.
        """

        if not self._all_cpus:
            self._all_cpus = self._read_range(f"{self._cpu_sysfs_base}/present")

        return self._all_cpus

    def _get_all_cpus_set(self) -> set[int]:
        """
        Return a set of all CPU numbers, including both online and offline CPUs.

        Returns:
            A set containing all CPU numbers present in the system.
        """

        if not self._all_cpus_set:
            self._all_cpus_set = set(self._get_all_cpus())

        return self._all_cpus_set

    def _get_cpu_description(self) -> str:
        """
        Build and return a human-readable string describing the processor.

        Returns:
            A string describing the processor.

        Notes:
            - For supported Intel CPUs, includes the codename.
        """

        # Some pre-release Intel CPUs are labeled as "GENUINE INTEL", hence 'lower()' is used.
        proc_cpuinfo = self.get_proc_cpuinfo()
        vendor, _, _ = CPUModels.split_vfm(proc_cpuinfo["vfm"])
        if vendor == CPUModels.VENDOR_INTEL:
            cpudescr = f"Intel processor model {proc_cpuinfo['model']:#x}"
            for info in CPUModels.MODELS.values():
                if info["vfm"] == proc_cpuinfo["vfm"]:
                    cpudescr += f" (codename: {info['codename']})"
                    break
        else:
            cpudescr = proc_cpuinfo["modelname"]
        return cpudescr

    def _probe_lpe_cores_l3(self):
        """
        Look for LPE (Low Power Efficiency) cores on a hybrid system.

        Notes:
            - LPE cores are not necessarily enumerated in the sysfs.
            - They are identified by the fact that they do not have the L3 cache.
        """

        cpus = self._get_online_cpus_set()

        has_l3: set[int] = set()
        no_l3: set[int] = set()

        for cpu in cpus:
            base = Path(f"{self._cpu_sysfs_base}/cpu{cpu}")

            try:
                l3_cpus = self._read_range(base / "cache/index3/shared_cpu_list")
            except ErrorNotFound:
                no_l3.add(cpu)
            else:
                has_l3.update(l3_cpus)

            if cpus == has_l3 | no_l3:
                # All online CPUs have been checked, no need to continue.
                break

        if not no_l3 or not has_l3:
            return

        self._hybrid_cpus["lpecore"] = sorted(list(no_l3))

        if "ecore" not in self._hybrid_cpus:
            return

        # Make sure LPE cores are not in the E-core list.
        ecores = [cpu for cpu in self._hybrid_cpus["ecore"] if cpu not in no_l3]
        self._hybrid_cpus["ecore"] = ecores

    def _get_hybrid_cpus(self) -> dict[HybridCPUKeyType, list[int]]:
        """
        Build and return a dictionary mapping hybrid CPU types to their corresponding CPU numbers.

        Returns:
            A dictionary mapping hybrid CPU types to CPU numbers.

        Notes:
            - Dictionary keys are hybrid CPU types (such as 'ecore' and 'pcore').
            - Dictionary values are the corresponding CPU numbers.
        """

        if self._hybrid_cpus:
            return self._hybrid_cpus

        _LOG.debug("Reading hybrid CPUs information from sysfs")

        iterator: dict[HybridCPUKeyType, str] = {"ecore": "atom", "pcore": "core",
                                                 "lpecore": "lowpower"}
        for hybrid_type, arch in iterator.items():
            with contextlib.suppress(ErrorNotFound):
                self._hybrid_cpus[hybrid_type] = self._read_range(f"/sys/devices/cpu_{arch}/cpus")

        if "lpecore" not in self._hybrid_cpus:
            self._probe_lpe_cores_l3()

        return self._hybrid_cpus

    def cpus_hotplugged(self):
        """
        Handle CPU hotplug events by updating internal state.

        Call this method whenever a CPU is brought online or taken offline. This ensures that the
        internal CPU information remains accurate after hotplug events.

        Notes:
            This is a coarse-grained implementation that clears all cached information. Ideally,
            only the affected parts should be updated.
        """

        _LOG.debug("Clearing cached CPU information")
        self._cpus = []
        self._cpus_set = set()
        self._hybrid_cpus = {}
        self._initialized_snames = set()
        self._topology = {}
        self._cpu_to_tline = {}
        self._cpu_to_core_index = {}
        self._cpu_to_module_index = {}
        self._core_to_cpus = {}
        self._die_to_cpus = {}
        self._module_to_cpus = {}
        self._node_to_cpus = {}
        self._package_to_cpus = {}
        self._proc_percpuinfo = {}

        if self._dieinfo:
            self._dieinfo.cpus_hotplugged()
