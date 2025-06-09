# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide the base class for the 'CPUInfo.CPUInfo' class.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
from typing import Iterable
import contextlib
from pathlib import Path
from pepclibs import _UncoreFreq, CPUModels
from pepclibs.msr import MSR, PMLogicalId
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial, KernelVersion
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound

from pepclibs._CPUInfoBaseTypes import CPUInfoTypedDict
if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._CPUInfoBaseTypes import CPUInfoKeyType, ScopeNameType, AbsNumsType
    from pepclibs._CPUInfoBaseTypes import HybridCPUKeyType, HybridCPUKeyInfoType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

SCOPE_NAMES: tuple[ScopeNameType, ...] = ("CPU", "core", "module", "die", "node", "package")

# 'NA' is used as the CPU/core/module number for I/O dies, which lack CPUs, cores, or modules.
NA = 0xFFFFFFFF
# A helpful CPU/code/etc (all scopes) number that is guaranteed to never be used.
INVALID = NA - 1

# Thy hybrid CPU information dictionary.
HYBRID_TYPE_INFO: dict[HybridCPUKeyType, HybridCPUKeyInfoType] = {
        "pcore":   {"name": "P-core", "title": "Performance core"},
        "ecore":   {"name": "E-core", "title": "Efficiency core"},
        "lpecore": {"name": "LPE-core", "title": "Low Power Efficiency core"},
}

class CPUInfoBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for 'CPUInfo.CPUInfo'. Provides low-level functionality, while 'CPUInfo' implements
    the public API.
    """

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager is created.
        """

        _LOG.debug("Initializing the '%s' class object", self.__class__.__name__)

        # A short CPU description string.
        self.cpudescr = None

        self._close_pman = pman is None

        self._msr: MSR.MSR | None = None
        self._pliobj: PMLogicalId.PMLogicalId | None = None
        self._uncfreq_obj: _UncoreFreq.UncoreFreqSysfs | None = None

        # 'True' if the target supports 'MSR_PM_LOGICAL_ID', which provides die ID enumeration.
        self._pli_msr_supported = True
        # 'True' if the target supports uncore frequency scaling.
        self._uncfreq_supported = True

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

        # Per-package compute die numbers (dies with CPUs) and I/O die numbers (dies without CPUs).
        self._compute_dies: dict[int, set[int]] = {}
        self._io_dies: dict[int, set[int]] = {}

        # The topology dictionary.
        self._topology: dict[ScopeNameType, list[dict[ScopeNameType, int]]] = {}

        # Topology scopes that have been already initialized.
        self._initialized_snames: set[str] = set()

        # The topology dictionary is a dictionary of lists where keys are scope names. The values
        # are lists of topology lines (tlines) sorted in the key order (or more precisely, in the
        # order specified by the sorting map).
        #
        # Note, die numbers are relative to the package, and core numbers are relative to the
        # package in older kernels. For this reason, the die and core topology lines are sorted by
        # package first, then by die/core.
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

        self.info = self._get_cpu_info()
        self.cpudescr = self._get_cpu_description()

    def close(self):
        """Uninitialize the class object."""

        _LOG.debug("Closing the '%s' class object", self.__class__.__name__)

        ClassHelpers.close(self, close_attrs=("_uncfreq_obj", "_pliobj", "_msr", "_pman"))

    def _get_msr(self) -> MSR.MSR:
        """
        Return an instance of the 'MSR.MSR' object for interacting with Model-Specific Registers
        (MSRs).

        Returns:
            An instance of the 'MSR.MSR' object.
        """

        if not self._msr:
            # Disable caching to exclude usage of the 'cpuinfo' object by the 'MSR' module, which
            # happens when 'MSR' module uses 'PerCPUCache'.
            _LOG.debug("Creating an instance of 'MSR.MSR' with cache disabled")
            self._msr = MSR.MSR(self, pman=self._pman, enable_cache=False)

        return self._msr

    def _get_pliobj(self) -> PMLogicalId.PMLogicalId | None:
        """
        Return a 'PMLogicalId.PMLogicalId' object if MSR_PM_LOGICAL_ID is supported by the target
        platform, otherwise return None.

        Returns:
            The 'PMLogicalId.PMLogicalId' object or None.
        """

        if not self._pliobj:
            if not self._pli_msr_supported:
                return None

            msr = self._get_msr()

            _LOG.debug("Creating an instance of 'PMLogicalId.PMLogicalId'")

            try:
                self._pliobj = PMLogicalId.PMLogicalId(pman=self._pman, cpuinfo=self, msr=msr)
            except ErrorNotSupported:
                self._pli_msr_supported = False

        return self._pliobj

    def _get_uncfreq_obj(self) -> _UncoreFreq.UncoreFreqSysfs | None:
        """
        Return an instance of '_UncoreFreq.UncoreFreqSysfs' if uncore frequency is supported.

        Returns:
            The '_UncoreFreq.UncoreFreqSysfs' object or None.
        """

        if not self._uncfreq_supported:
            return None

        if not self._uncfreq_obj:
            _LOG.debug("Creating an instance of '_UncoreFreq.UncoreFreqSysfs'")

            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreqSysfs(self, pman=self._pman)
            except ErrorNotSupported:
                self._uncfreq_supported = False

        return self._uncfreq_obj

    def _add_cores_and_packages(self,
                                cpu_tdict: dict[int, dict[ScopeNameType, int]],
                                cpus: AbsNumsType):
        """
        Add core and package numbers for the specified CPUs to the provided CPU topology dictionary.

        Exctract the core and package numbers from the '/proc/cpuinfo'.

        Args:
            cpu_tdict: The CPU topology dictionary to update with core and package information.
            cpus: CPU numbers for which to add core and package numbers.
        """

        def _get_number(start: str, lines: list[str], index: int) -> int:
            """
            Validate that a '/proc/cpuinfo' line at the specified index starts with the given
            prefix, extract and return its integer value.

            Args:
                start: The expected prefix at the beginning of the line.
                lines: The list of lines to search through.
                index: The index of the line to check.

            Returns:
                The integer value found after the ':' character in the specified line.
            """

            try:
                line = lines[index]
            except IndexError:
                lines_count = len(lines)
                lines_str = "\n".join(lines)
                lines_str = Error(lines_str).indent(2)
                raise Error(f"There are to few lines in '/proc/cpuinfo' for CPU '{cpu}'.\n"
                            f"Expected at least {index + 1} lines, got {lines_count}.\n"
                            f"The lines:\n{lines_str}") from None

            if not line.startswith(start):
                raise Error(f"Expected line {index + 1} for CPU {cpu} in '/proc/cpuinfo' to start "
                            f"with \"{start}\", got:\n{line!r}.")

            return Trivial.str_to_int(line.partition(":")[2],
                                      what=f"value of '{start}' from '/proc/cpuinfo'")

        _LOG.debug("Reading CPU topology information from '/proc/cpuinfo'")

        info: dict[int, list[str]] = {}
        for data in self._pman.read_file("/proc/cpuinfo").strip().split("\n\n"):
            lines = data.split("\n")
            cpu = _get_number("processor", lines, 0)
            info[cpu] = lines

        for cpu in cpus:
            if cpu not in info:
                raise Error(f"CPU {cpu} is missing from '/proc/cpuinfo'")

            lines = info[cpu]
            cpu_tdict[cpu]["package"] = _get_number("physical id", lines, 9)
            cpu_tdict[cpu]["core"] = _get_number("core id", lines, 11)

    def _add_modules(self, cpu_tdict: dict[int, dict[ScopeNameType, int]], cpus: AbsNumsType):
        """
        Add module numbers for the specified CPUs to the CPU topology dictionary.

        Module numbers are read from the sysfs files under
        '/sys/devices/system/cpu/cpu<cpu>/cache/index2/'.

        Args:
            cpu_tdict: The CPU topology dictionary to update with module information.
            cpus: CPU numbers for which to add module numbers.
        """

        _LOG.debug("Reading CPU module information from sysfs")

        no_cache_info = False
        for cpu in cpus:
            if "module" in cpu_tdict[cpu]:
                continue

            if no_cache_info:
                cpu_tdict[cpu]["module"] = cpu_tdict[cpu]["core"]
                continue

            base = Path(f"{self._cpu_sysfs_base}/cpu{cpu}")
            try:
                data = self._pman.read_file(base / "cache/index2/id")
            except ErrorNotFound as err:
                if not no_cache_info:
                    _LOG.debug("No CPU cache topology info found%s:\n%s.",
                               self._pman.hostmsg, err.indent(2))
                    no_cache_info = True
                    cpu_tdict[cpu]["module"] = cpu_tdict[cpu]["core"]
                    continue

            module = Trivial.str_to_int(data, what="module number")
            siblings = self._read_range(base / "cache/index2/shared_cpu_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'shared_cpu_list' file included an offline CPU.
                with contextlib.suppress(KeyError):
                    cpu_tdict[sibling]["module"] = module

    def _add_compute_dies(self,
                          cpu_tdict: dict[int, dict[ScopeNameType, int]],
                          cpus: AbsNumsType):
        """
        Add compute die numbers for the specified CPUs to the CPU topology dictionary.

        Compute die numbers are read from either 'MSR_PM_LOGICAL_ID' MSR or from the sysfs
        files under '/sys/devices/system/cpu/cpu<cpu>/topology/'.

        Args:
            cpu_tdict: The CPU topology dictionary to update with compute die information.
            cpus: CPU numbers for which to add compute die numbers.
        """

        def _add_compute_die(cpu_tdict: dict[int, dict[ScopeNameType, int]], cpu: int, die: int):
            """
            Add a compute die number to the CPU topology dictionary.

            Args:
                cpu_tdict: The CPU topology dictionary to update.
                cpu: The CPU number to which the die number should be added.
                die: The compute die number to add.
            """

            cpu_tdict[cpu]["die"] = die
            package = cpu_tdict[cpu]["package"]
            if package not in self._compute_dies:
                self._compute_dies[package] = set()
                # Initialize the I/O dies cache at the same time.
                self._io_dies[package] = set()
            self._compute_dies[package].add(die)

        if self.info["vfm"] in CPUModels.MODELS_WITH_HIDDEN_DIES:
            pli_obj = self._get_pliobj()
            if pli_obj:
                _LOG.debug("Reading compute die information from 'MSR_PM_LOGICAL_ID'")
                for cpu, die in pli_obj.read_feature("domain_id", cpus=cpus):
                    _add_compute_die(cpu_tdict, cpu, die)
                return

        _LOG.debug("Reading compute die information from sysfs")
        for cpu in cpus:
            if "die" in cpu_tdict[cpu]:
                continue

            base = Path(f"{self._cpu_sysfs_base}/cpu{cpu}")
            data = self._pman.read_file(base / "topology/die_id")
            die = Trivial.str_to_int(data, what="die number")
            siblings = self._read_range(base / "topology/die_cpus_list")
            for _ in siblings:
                # Suppress 'KeyError' in case the 'die_cpus_list' file included an offline CPU.
                with contextlib.suppress(KeyError):
                    _add_compute_die(cpu_tdict, cpu, die)

    def _add_nodes(self, cpu_tdict: dict[int, dict[ScopeNameType, int]]):
        """
        Assign NUMA node numbers for specified CPUs in the CPU topology dictionary.

        NUMA node numbers are read from the sysfs files under
        '/sys/devices/system/node/node<node>/cpulist'.

        Args:
            cpu_tdict: Dictionary mapping CPU identifiers to their attributes.
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

    def _add_io_dies(self, tlines: list[dict[ScopeNameType, int]]):
        """
        Add I/O dies to the topology table.

        I/O dies information is obtained from the uncore frequency driver. However, a better
        solution would be to read it from TPMI.

        Args:
            tlines: The topology table (list of dictionaries) to which I/O dies should be added.
        """

        uncfreq_obj = self._get_uncfreq_obj()
        if not uncfreq_obj:
            return

        _LOG.debug("Reading I/O dies information from uncore frequency driver")

        # The 'UncoreFreqSysfs' class is I/O dies-aware.
        dies_info = uncfreq_obj.get_dies_info()

        for package, pkg_dies in dies_info.items():
            # This must be a package that has all CPUs offline.
            if package not in self._compute_dies:
                continue
            for die in pkg_dies:
                if die in self._compute_dies[package]:
                    continue

                tline = {}
                for key in SCOPE_NAMES:
                    # At this point the topology table lines may not even include some levels (e.g.,
                    # "numa" may not be there). But they may be added later. Add them for the I/O
                    # die topology table lines now, so that later the lines would not need # to be
                    # updated.
                    tline[key] = NA
                tline["package"] = package
                tline["die"] = die
                tlines.append(tline)

                # Cache the I/O die number.
                self._io_dies[package].add(die)

    def _sort_topology(self, tlines, order):
        """Sorts and save the topology list by 'order' in sorting map"""

        skeys = self._sorting_map[order]
        self._topology[order] = sorted(tlines, key=lambda tline: tuple(tline[s] for s in skeys))

    def _get_topology(self, snames: Iterable[ScopeNameType], order: ScopeNameType = "CPU"):
        """
        Build and return the topology table for the specified scopes and sorted in the specified
        order.

        Args:
            scopes: Scope names to include to the topology table.
            order: Topology table sorting order. Defaults to "CPU".

        Returns:
            The topology table for the specified scopes and order. The topology table is a
            a list of topology lines, which are dictionaries where keys are scope names and
            values are the corresponding scope numbers (e.g., CPU numbers, core numbers, etc.).
        """

        snames_set = set(snames)
        snames_set.update(set(self._sorting_map[order]))
        snames_set -= self._initialized_snames

        if not snames_set:
            # The topology for the necessary scopes has already been built, just return it.
            return self._topology[order]

        _LOG.debug("Building CPU topology for scopes %s, order '%s'",
                   ", ".join(snames), order)

        # A prelimitary CPU topology dictionary. They keys are CPU numbers, and the values are the
        # topology lines.
        cpu_tdict: dict[int, dict[ScopeNameType, int]]

        cpus = self._get_online_cpus()

        tlines_no_cpu: list[dict[ScopeNameType, int]] = []
        if not self._topology:
            cpu_tdict = {cpu: {"CPU": cpu} for cpu in cpus}
        else:
            cpu_tdict = {}
            for tline in self._topology["CPU"]:
                if tline["CPU"] != NA:
                    # If the topology table already has some CPU lines, use them as a base.
                    cpu_tdict[tline["CPU"]] = tline
                else:
                    tlines_no_cpu.append(tline)

        if "CPU" not in self._initialized_snames or "core" not in self._initialized_snames or \
           "package" not in self._initialized_snames:
            self._add_cores_and_packages(cpu_tdict, cpus)
            snames_set.update({"CPU", "core", "package"})

        if "module" in snames_set:
            self._add_modules(cpu_tdict, cpus)
        if "die" in snames_set:
            self._add_compute_dies(cpu_tdict, cpus)
        if "node" in snames_set:
            self._add_nodes(cpu_tdict)

        # I/O dies do not have CPUs, so 'cpu_tdict' is not a suitable data structure for them. Use a
        # list of topology lines (tlines) instead.
        tlines = list(cpu_tdict.values()) + tlines_no_cpu

        if "die" in snames_set:
            self._add_io_dies(tlines)

        self._initialized_snames.update(snames_set)
        for level in self._initialized_snames:
            self._sort_topology(tlines, level)

        return self._topology[order]

    def _read_range(self, path: Path | str) -> list[int]:
        """
        Read a file containing a comma-separated list of integers or integer ranges, and return a
        list of integers.

        Args:
            path: Path to the file to read.

        Returns:
            List of integers parsed from the file.
        """

        str_of_ranges = self._pman.read_file(path).strip()

        _LOG.debug("Read CPU numbers from '%s'%s: %s", path, self._pman.hostmsg, str_of_ranges)

        what = f"contents of file at '{path}'{self._pman.hostmsg}"
        return Trivial.split_csv_line_int(str_of_ranges, what=what)

    def _get_online_cpus(self) -> list[int]:
        """
        Return a list of online CPU numbers.

        Returns:
            A cst ontaining the online CPU numbers sorted in ascending order.
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

    def _get_cpu_info(self) -> CPUInfoTypedDict:
        """
        Collect and return general CPU information such as model, and architecture.

        Returns:
            CPUInfoTypeDict: The CPU information dictionary.
        """

        _LOG.debug("Building CPU information")

        cpuinfo: CPUInfoTypedDict = {}

        lscpu, _ = self._pman.run_verify("lscpu", join=False)

        # Parse misc. information about the CPU.
        patterns: tuple[tuple[str, CPUInfoKeyType], ...] = \
                    ((r"^Architecture:\s*(.*)$", "arch"),
                     (r"^Vendor ID:\s*(.*)$", "vendor"),
                     (r"^CPU family:\s*(.*)$", "family"),
                     (r"^Model:\s*(.*)$", "model"),
                     (r"^Model name:\s*(.*)$", "modelname"),
                     (r"^Flags:\s*(.*)$", "flags"))

        key_types = typing.get_type_hints(CPUInfoTypedDict)
        for line in lscpu:
            for pattern, key in patterns:
                match = re.match(pattern, line.strip())
                if not match:
                    continue

                val = match.group(1)
                if key_types[key] is int:
                    what=f"'{key}' value from 'lscpu' output"
                    cpuinfo[key] = Trivial.str_to_int(val, what=what)
                elif key_types[key] is str:
                    cpuinfo[key] = val
                elif key == "flags":
                    cpuflags = set(val.split())
                    cpuinfo["flags"] = {}
                    # Assume that all CPUs share the same flags, this is the case for current CPUs.
                    # But generally, the flags could be different for different CPUs, in which case
                    # they would be read from '/proc/cpuinfo'.
                    for cpu in self._get_online_cpus():
                        cpuinfo["flags"][cpu] = cpuflags
                else:
                    raise Error(f"Unexpected type for '{key}', expected "
                                f"{key_types[key]}, got {type(val)}")

        if self._pman.exists("/sys/devices/cpu_atom/cpus"):
            cpuinfo["hybrid"] = True
        else:
            cpuinfo["hybrid"] = False
            with contextlib.suppress(Error):
                kver = KernelVersion.get_kver(pman=self._pman)
                if KernelVersion.kver_lt(kver, "5.13"):
                    _LOG.warn_once("Kernel v%s does not support hybrid CPU topology. The minimum "
                                   "required kernel version is v5.13.", kver)

        cpuinfo["vfm"] = CPUModels.make_vfm(cpuinfo["vendor"], cpuinfo["family"], cpuinfo["model"])
        return cpuinfo

    def _get_cpu_description(self) -> str:
        """
        Build and return a human-readable string describing the processor.

        Returns:
            A string describing the processor, including codename for supported Intel CPUs.
        """

        # Some pre-release Intel CPUs are labeled as "GENUINE INTEL", hence 'lower()' is used.
        if "genuine intel" in self.info["modelname"].lower():
            cpudescr = f"Intel processor model {self.info['model']:#x}"

            for info in CPUModels.MODELS.values():
                if info["vfm"] == self.info["vfm"]:
                    cpudescr += f" (codename: {info['codename']})"
                    break
        else:
            cpudescr = self.info["modelname"]

        return cpudescr

    def _probe_lpe_cores_l3(self):
        """
        Look for LPE (Low Power Efficiency) cores on a hybrid system.

        LPE cores are not necessarily enumerated in the sysfs. Find them using the fact that they do
        not have the L3 cache.
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
            A dictionary where keys are hybrid CPU types (such as 'ecores' and 'pcores') and values
            are the corresponding CPU numbers.
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

    def _cpus_hotplugged(self):
        """
        Handle CPU hotplug events by resetting cached CPU and topology information.
        """

        _LOG.debug("Clearing cashed CPU information")

        self._cpus = []
        self._cpus_set = set()
        self._hybrid_cpus = {}
        self._initialized_snames = set()
        self._topology = {}
