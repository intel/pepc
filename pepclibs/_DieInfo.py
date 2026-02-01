# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide information about compute and non-compute dies.

Compute dies are dies with CPUs. The CPU typically enumerates them via the CPUID instruction, and
Linux exposes die IDs via '/sys/devices/system/cpu/cpu<cpu>/topology/die_id' files. However, on
certain platforms such as Granite Rapids Xeon, compute dies are not exposed via CPUID. On these
platforms, compute dies are enumerated via MSR 0x54 (MSR_PM_LOGICAL_ID), and pepc uses the
'domain ID' field from this MSR as the die ID.

When compute dies are enumerated via CPUID, die IDs are globally unique within the system. When
compute dies are enumerated via MSR 0x54, die IDs are unique only within a package. In other words,
multiple packages may have dies with the same die ID.

Non-compute dies are dies without CPUs. They are not enumerated via CPUID and cannot be enumerated
via MSRs. pepc discovers non-compute dies via TPMI (Intel's Topology and Power Management Interface)
and assigns them unique die IDs.

A non-compute die is not a physical die - it is a logical entity representing an uncore frequency
scaling unit that does not have CPUs. Non-compute dies are enumerated via TPMI UFS (Uncore Frequency
Scaling) - each UFS cluster without a "core" agent is considered a non-compute die.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path

from pepclibs import CPUModels
from pepclibs.helperlibs import Logging, ClassHelpers, LocalProcessManager, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import TypedDict, Literal, Final
    from pepclibs import TPMI
    from pepclibs.ProcCpuinfo import ProcCpuinfoTypedDict, ProcCpuinfoPerCPUTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    # TPMI "agent types" for a die. Non-compute dies never have "core" agent type, but it is
    # included here for completeness.
    AgentTypes = Literal["core", "cache", "io", "memory"]

    class DieInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary representing information about a die.

        Attributes:
            title: A short description of the die.
            agent_types: A set of agent types present on the die.
            addr: The TPMI PCI device address.
            instance: The TPMI instance number.
            cluster: The TPMI cluster number.
        """

        title: str
        agent_types: set[AgentTypes]
        addr: str
        instance: int
        cluster: int

AGENT_TYPES: Final[tuple[AgentTypes, ...]] = ("core", "cache", "io", "memory")

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class DieInfo(ClassHelpers.SimpleCloseContext):
    """
    Provide information about compute and non-compute dies.

    Compute dies are discovered via sysfs or MSR 0x54, while non-compute dies are discovered via
    TPMI. This class provides unified access to both types of dies.

    Public methods overview:
        - get_tpmi() - return or create an instance of the TPMI object.
        - get_compute_dies_cpus() - return compute dies with their CPU lists.
        - get_compute_dies() - return compute dies indexed by package number.
        - get_compute_dies_info() - return detailed information about compute dies.
        - get_noncomp_dies() - return non-compute dies indexed by package number.
        - get_noncomp_dies_info() - return detailed information about non-compute dies.
        - get_all_dies() - return all dies (compute and non-compute).
        - get_all_dies_info() - return detailed information about all dies.
        - cpus_hotplugged() - handle CPU hotplug events.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 tpmi: TPMI.TPMI | None = None,
                 proc_cpuinfo: ProcCpuinfoTypedDict | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager is created.
            tpmi: An instance of the 'TPMI' class. If not provided, a new instance is created.
            proc_cpuinfo: The general '/proc/cpuinfo' information dictionary containing
                          CPU model, vendor, etc. If not provided, it is obtained via
                          'ProcCpuinfo.get_proc_cpuinfo()'.
        """

        self._close_pman = pman is None
        self._close_tpmi = tpmi is None

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        self._tpmi = tpmi
        self._tpmi_errmsg = ""

        self._proc_cpuinfo = proc_cpuinfo

        self._compute_discovered = False
        # {package: [die1, die2, ...]}.
        self._compute_dies: dict[int, list[int]] = {}
        # {package: {die: [cpu1, cpu2, ...]}}.
        self._compute_dies_cpus: dict[int, dict[int, list[int]]] = {}
        # {package: {die: DieInfoTypedDict, ...}}.
        self._compute_dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}

        self._noncomp_discovered = False
        # {package: [die1, die2, ...]}.
        self._noncomp_dies: dict[int, list[int]] = {}
        # {package: {die: DieInfoTypedDict, ...}}.
        self._noncomp_dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}

        # {package: [die1, die2, ...]}.
        self._all_dies: dict[int, list[int]] = {}
        # {package: {die: DieInfoTypedDict, ...}}.
        self._all_dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}

        # Whether die IDs correspond to domain IDs.
        self._die_ids_are_domain_ids: bool | None = None

    def close(self):
        """Uninitialize the class object."""

        _LOG.debug("Closing the '%s' class object", self.__class__.__name__)
        ClassHelpers.close(self, close_attrs=("_tpmi", "_pman"), unref_attrs=("_proc_cpuinfo",))

    def _get_proc_cpuinfo(self) -> ProcCpuinfoTypedDict:
        """
        Return the general '/proc/cpuinfo' information dictionary.

        Returns:
            The general '/proc/cpuinfo' information dictionary containing CPU model, vendor, etc.
        """

        if not self._proc_cpuinfo:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import ProcCpuinfo

            self._proc_cpuinfo = ProcCpuinfo.get_proc_cpuinfo(pman=self._pman)

        return self._proc_cpuinfo

    def get_tpmi(self) -> TPMI.TPMI:
        """
        Return or create a 'TPMI.TPMI' object instance.

        Returns:
            The 'TPMI.TPMI' object.

        Raises:
            ErrorNotSupported: if TPMI is not supported on the target system.
        """

        if self._tpmi:
            return self._tpmi

        if self._tpmi_errmsg:
            raise ErrorNotSupported(self._tpmi_errmsg)

        _LOG.debug("Creating an instance of 'TPMI.TPMI'")

        # pylint: disable-next=import-outside-toplevel
        from pepclibs import TPMI

        proc_cpuinfo = self._get_proc_cpuinfo()

        try:
            self._tpmi = TPMI.TPMI(pman=self._pman, vfm=proc_cpuinfo["vfm"])
        except Exception as err:
            self._tpmi_errmsg = str(err)
            _LOG.debug(self._tpmi_errmsg)
            raise

        return self._tpmi

    def _use_domain_ids_for_compute_dies(self) -> bool:
        """
        Determine whether to use domain IDs as compute die IDs.

        Returns:
            'True' if domain IDs should be used as compute die IDs, 'False' otherwise.
        """

        if self._die_ids_are_domain_ids is not None:
            return self._die_ids_are_domain_ids

        proc_cpuinfo = self._get_proc_cpuinfo()
        self._die_ids_are_domain_ids = proc_cpuinfo["vfm"] in CPUModels.MODELS_WITH_HIDDEN_DIES
        return self._die_ids_are_domain_ids

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

    @staticmethod
    def _format_die_title(agent_types: set[AgentTypes]) -> str:
        """
        Format and return a die title based on its agent types.

        Args:
            agent_types: A set of agent types present on the die.

        Returns:
            A formatted die title string.
        """

        # Format the description to have one of these forms:
        # - x: if there is only one agent.
        # - x and y: if there are two agents.
        # - x, y, and z: if there are three or more agents.
        # Use "I/O" instead of "io".
        agents = []
        for agent_type in AGENT_TYPES:
            if agent_type not in agent_types:
                continue
            if agent_type == "io":
                agents.append("I/O")
            else:
                agents.append(agent_type)

        if "core" in agent_types:
            title = "compute"
        elif len(agents) == 1:
            title = f"{agents[0]}"
        elif len(agents) == 2:
            title = f"{agents[0]} and {agents[1]}"
        elif len(agents) > 2:
            title = ", ".join(agents[:-1]) + f", and {agents[-1]}"
        else:
            title = "unknown"

        return title[0].upper() + title[1:]

    def _format_dmr_die_titles(self):
        """
        Format Diamond Rapids Xeon-specific non-compute die titles by adding IMH (Integrated
        Memory Hub) prefixes.
        """

        # Diamond Rapids Xeon has 2 IMHs per package. Each IMH is represented by one TPMI device
        # (address) and has one I/O die and one memory die. This code relies on dies being ordered
        # such that lower die numbers map to IMH0, then IMH1. The TPMI addresses are iterated in
        # order, ensuring correct IMH numbering.
        for pkg, dies_info in self._noncomp_dies_info.items():
            # Map TPMI addresses to IMH numbers.
            addr2imh: dict[str, int] = {}
            imh_number = 0

            # First pass: assign IMH numbers to addresses in iteration order.
            for die_info in dies_info.values():
                addr = die_info["addr"]
                if addr not in addr2imh:
                    addr2imh[addr] = imh_number
                    imh_number += 1

            # Verify that there are 2 IMHs per package.
            if len(addr2imh) != 2:
                raise Error(f"Expected 2 TPMI devices (IMHs) for Diamond Rapids package {pkg}, "
                            f"but found {len(addr2imh)}")

            # Verify that each IMH has both I/O and memory dies.
            addr2agents: dict[str, set[str]] = {}
            for die_info in dies_info.values():
                addr = die_info["addr"]
                addr2agents.setdefault(addr, set()).update(die_info["agent_types"])

            for addr, agents in addr2agents.items():
                if "io" not in agents or "memory" not in agents:
                    raise Error(f"Expected both I/O and memory dies for Diamond Rapids TPMI "
                                f"device {addr} in package {pkg}, but found agents: {agents}")

            # Second pass: format titles using the IMH number for each address.
            for die_info in dies_info.values():
                addr = die_info["addr"]
                imh_num = addr2imh[addr]
                if "io" in die_info["agent_types"]:
                    die_info["title"] = f"IMH{imh_num} I/O"
                elif "memory" in die_info["agent_types"]:
                    die_info["title"] = f"IMH{imh_num} Mem"

    @staticmethod
    def _print_dies_info(dies_info: dict[int, dict[int, DieInfoTypedDict]], loglevel: int):
        """
        Print a dies information dictionary.

        Args:
            dies_info: The dies information dictionary to print.
            loglevel: The logging level to use for printing.
        """

        for pkg, pkg_dies in dies_info.items():
            _LOG.log(loglevel, "- Package %d:", pkg)
            for die, die_info in pkg_dies.items():
                _LOG.log(loglevel, "  - Die %d:", die)
                _LOG.log(loglevel, "    Title: %s", die_info["title"])
                if not die_info["addr"]:
                    continue
                _LOG.log(loglevel, "    Agent type(s): %s",
                        ", ".join(die_info["agent_types"]))
                _LOG.log(loglevel, "    Address: %s", die_info["addr"])
                _LOG.log(loglevel, "    Instance: %d", die_info["instance"])
                _LOG.log(loglevel, "    Cluster: %d", die_info["cluster"])

    @staticmethod
    def _print_dies_cpus(dies_info: dict[int, dict[int, list[int]]], loglevel: int):
        """
        Print a dies dictionary with their CPU lists.

        Args:
            dies_info: The dies dictionary to print.
            loglevel: The logging level to use for printing.
        """

        for pkg, pkg_dies in dies_info.items():
            _LOG.log(loglevel, "- Package %d:", pkg)
            for die, cpus in pkg_dies.items():
                _LOG.log(loglevel, "  - Die %d:", die)
                _LOG.log(loglevel, "    CPUs: %s", Trivial.rangify(cpus))

    def _verify_compute_dies_match(self):
        """
        Verify that compute dies discovered via MSR match those discovered via TPMI.
        """

        # The compute dies info was already built via TPMI, verify that die IDs match.
        for package, dies_info in self._compute_dies_info.items():
            if package not in self._compute_dies:
                raise Error(f"BUG: Discovered compute dies via MSR do not match TPMI results: "
                            f"package {package} is missing in MSR results")
            dies_from_info = list(dies_info)
            dies_from_msr = self._compute_dies[package]
            if dies_from_info != dies_from_msr:
                raise Error(f"BUG: Discovered compute dies via MSR do not match TPMI results: "
                            f"package {package} dies from TPMI: {dies_from_info}, dies from "
                            f"MSR: {dies_from_msr}")

    def _init_die_info_tpmi(self):
        """
        Initialize compute and non-compute die information from TPMI.

        Notes:
            - The compute dies must have already been discovered via sysfs or MSR prior to calling
              this method.
            - If all CPUs from a compute die are offline, the die ID cannot be determined via MSR.
              The die will be absent from 'self._compute_dies' and other compute die data
              structures.
            - UFS TPMI walk will see the compute dies with all CPUs offline, and this situation is
              handled by ignoring such compute dies here.
            - This method relies on the fact that TPMI UFS walk yields entries in a sorted order,
              first compute dies with lower die IDs are seen, then compute dies with higher die IDs.
              This allows for matching TPMI-discovered compute dies to those discovered via sysfs or
              MSR.
            - This method assigns unique die IDs to non-compute dies, ensuring that they do not
              overlap with compute die IDs. This is why it is important to detect existing compute
              dies, even those absent from data structures due to all CPUs being offline. Otherwise,
              there is a risk of assigning a non-compute die an ID that collides with a compute die
              ID when the CPUs of that compute die go online.
            - This method deals with 2 situations: compute die IDs enumerated via sysfs (globally
              unique IDs) and compute die IDs enumerated via MSR (unique within a package). This
              adds some complexity to the code.
        """

        compute_dies_sets: dict[int, set[int]] = {}
        for pkg, dies in self._compute_dies.items():
            compute_dies_sets[pkg] = set(dies)

        # The global compute die index. Increments for each compute die found during the TPMI UFS
        # walk.
        index_global = -1
        # The per-package compute die index. Increments for each compute die found during the TPMI
        # UFS walk, but resets on each new package.
        index_package: dict[int, int] = {}
        # Package ID of the previous TPMI UFS entry. The assumption is that during the walk package
        # IDs are only increasing.
        prev_pkg = -1

        # Temporary structure for the dies information discovered during the TPMI UFS walk:
        # [package, die, DieInfoTypedDict].
        prelim_dies_info: list[tuple[int, int, DieInfoTypedDict]] = []

        tpmi = self.get_tpmi()

        _LOG.debug("Walk TPMI UFS")

        # The goal of the first walk is to discover all dies and build the 'DieInfoTypedDict'
        # dictionaries. Do not assign die IDs at this stage yet.
        for package, addr, instance, cluster in tpmi.iter_ufs_feature():
            ufs_status = tpmi.read_ufs_register(addr, instance, cluster, "UFS_STATUS")
            agent_types = set()
            for agent_type in AGENT_TYPES:
                if tpmi.get_bitfield(ufs_status, "ufs", "UFS_STATUS",
                                     f"AGENT_TYPE_{agent_type.upper()}"):
                    agent_types.add(agent_type)

            die_info: DieInfoTypedDict = {}
            die_info["title"] = self._format_die_title(agent_types)
            die_info["agent_types"] = agent_types
            die_info["addr"] = addr
            die_info["instance"] = instance
            die_info["cluster"] = cluster

            if "core" not in agent_types:
                # A non-compute die. Die ID will be assigned later.
                prelim_dies_info.append((package, -1, die_info))
                continue

            if package != prev_pkg:
                index_package.setdefault(package, -1)
                prev_pkg = package

            index_global += 1
            index_package[package] += 1

            # In case of sysfs-enumerated compute dies, die IDs are globally unique numbers starting
            # from 0, and index_global corresponds to the die ID. In case of MSR-enumerated compute
            # dies, die IDs are unique only within a package, and index_package corresponds to the
            # die ID.
            if self._use_domain_ids_for_compute_dies():
                compute_die_id = index_package[package]
            else:
                compute_die_id = index_global

            if compute_die_id in compute_dies_sets.get(package, set()):
                prelim_dies_info.append((package, compute_die_id, die_info))
            else:
                _LOG.debug("Skipping compute die %d in package %d (all CPUs offline)",
                           compute_die_id, package)

        if index_global == -1:
            raise Error(f"BUG: No compute dies found via TPMI UFS{self._pman.hostmsg}")

        # Assign non-compute die IDs and build the internal data structures.
        for package, die, die_info in prelim_dies_info:
            if "core" in die_info["agent_types"]:
                dies_info = self._compute_dies_info
            else:
                dies_info = self._noncomp_dies_info
                if self._use_domain_ids_for_compute_dies():
                    die = index_package[package] + 1
                    index_package[package] += 1
                else:
                    die = index_global + 1
                    index_global += 1

            dies_info.setdefault(package, {}).setdefault(die, die_info)

        self._verify_compute_dies_match()

        proc_cpuinfo = self._get_proc_cpuinfo()
        if proc_cpuinfo["vfm"] in CPUModels.CPU_GROUPS["DMR"]:
            self._format_dmr_die_titles()

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            _LOG.debug("Built compute dies info via TPMI:")
            self._print_dies_info(self._compute_dies_info, Logging.DEBUG)
            _LOG.debug("Built non-compute dies info via TPMI:")
            self._print_dies_info(self._noncomp_dies_info, Logging.DEBUG)

    def _build_compute_dies_info_no_tpmi(self):
        """
        Build compute die information on a platform that does not support TPMI.

        Returns:
            A dictionary mapping package numbers to dictionaries that map die numbers to
            'DieInfoTypedDict' dictionaries: {package: {die: DieInfoTypedDict, ...}}.
        """

        compute_dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}

        for package, dies in self._compute_dies.items():
            compute_dies_info.setdefault(package, {})
            for die in dies:
                die_info: DieInfoTypedDict = {
                    "title": "Compute",
                    "agent_types": {"core"},
                    "addr": "",
                    "instance": -1,
                    "cluster": -1,
                }
                compute_dies_info[package][die] = die_info

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            _LOG.debug("Built compute dies info without TPMI:")
            self._print_dies_info(compute_dies_info, Logging.DEBUG)

        return compute_dies_info

    def _discover_compute_dies_sysfs(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies via sysfs and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Notes:
            If all CPUs from a die are offline, the die ID cannot be determined via sysfs.
        """

        _LOG.debug("Discovering compute dies via sysfs")

        cpu2die: dict[int, int] = {}
        compute_dies_sets: dict[int, set[int]] = {}
        compute_dies_cpus_sets: dict[int, dict[int, set[int]]] = {}

        for package, cores in proc_percpuinfo["topology"].items():
            compute_dies_cpus_sets.setdefault(package, {})
            for cpus in cores.values():
                for cpu in cpus:
                    if cpu in cpu2die:
                        continue

                    base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
                    die_str = self._pman.read_file(base / "topology/die_id")
                    die = Trivial.str_to_int(die_str, what="compute die ID")
                    cpu_siblings = self._read_range(base / "topology/die_cpus_list")
                    for cpu_sibling in cpu_siblings:
                        cpu2die[cpu_sibling] = die
                        compute_dies_sets.setdefault(package, set()).add(die)
                        compute_dies_cpus_sets[package].setdefault(die, set()).add(cpu_sibling)

        # Note, dies and CPUs in 'compute_dies_sets' and 'compute_dies_cpus_sets' are not
        # necessarily sorted, so sort them here.
        self._compute_dies = {pkg: sorted(dies) for pkg, dies in compute_dies_sets.items()}
        for pkg, pkg_dies in compute_dies_cpus_sets.items():
            self._compute_dies_cpus.setdefault(pkg, {})
            for die in sorted(pkg_dies):
                self._compute_dies_cpus[pkg][die] = sorted(pkg_dies[die])

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            _LOG.debug("Discovered compute dies via sysfs:")
            self._print_dies_cpus(self._compute_dies_cpus, Logging.DEBUG)

    def _discover_compute_dies_msr(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies via MSR 0x54 and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Notes:
            If all CPUs from a die are offline, the die ID cannot be determined via the MSR.
        """

        _LOG.debug("Discovering compute dies via 'MSR_PM_LOGICAL_ID'")

        # pylint: disable=import-outside-toplevel
        from pepclibs.msr import _SimpleMSR

        try:
            msr = _SimpleMSR.SimpleMSR(pman=self._pman)
        except Error as err:
            _LOG.warning("Failed to initialize MSR access for 'MSR_PM_LOGICAL_ID'%s:\n%s",
                         self._pman.hostmsg, err.indent(2))
            _LOG.warning("Die information will not be available")
            self._compute_dies = {}
            return

        cpu2package: dict[int, int] = {}
        for package, cores in proc_percpuinfo["topology"].items():
            for cpus in cores.values():
                for cpu in cpus:
                    cpu2package[cpu] = package

        regaddr = 0x54
        # {package: {die: set(cpu1, cpu2, ...)}}
        compute_dies_cpus_sets: dict[int, dict[int, set[int]]] = {}
        cpus = sorted(cpu2package)
        for cpu, regval in msr.cpus_read(regaddr, cpus):
            die = (regval >> 11) & 0x3F
            package = cpu2package[cpu]
            compute_dies_cpus_sets.setdefault(package, {})
            compute_dies_cpus_sets[package].setdefault(die, set()).add(cpu)

        for package, compute_dies_set in compute_dies_cpus_sets.items():
            self._compute_dies[package] = sorted(compute_dies_set)
            self._compute_dies_cpus[package] = {}
            for die, die_cpus_set in compute_dies_set.items():
                self._compute_dies_cpus[package][die] = sorted(die_cpus_set)

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            _LOG.debug("Discovered compute dies via MSR:")
            self._print_dies_cpus(self._compute_dies_cpus, Logging.DEBUG)

    def _discover_compute_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.
        """

        self._compute_discovered = True

        if self._use_domain_ids_for_compute_dies():
            self._discover_compute_dies_msr(proc_percpuinfo)
        else:
            self._discover_compute_dies_sysfs(proc_percpuinfo)

        try:
            self.get_tpmi()
        except ErrorNotSupported:
            _LOG.debug("TPMI is not supported, using basic compute die information")
            self._compute_dies_info = self._build_compute_dies_info_no_tpmi()
            return

        _LOG.debug("Building compute dies info via TPMI")
        if not self._compute_dies_info:
            self._init_die_info_tpmi()

    def _discover_noncomp_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover non-compute dies and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.
        """

        self._noncomp_discovered = True

        try:
            self.get_tpmi()
        except ErrorNotSupported:
            _LOG.debug("TPMI is not supported on the target system, cannot discover "
                       "non-compute dies")
            return

        # Discover compute dies first in order to avoid non-compute die IDs overlapping with compute
        # die IDs.
        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)

        if not self._noncomp_dies_info:
            self._init_die_info_tpmi()
        if not self._noncomp_dies:
            for pkg, dies in self._noncomp_dies_info.items():
                self._noncomp_dies.setdefault(pkg, []).extend(sorted(dies))

        # Self-check: verify that non-compute die IDs do not overlap with compute die IDs.
        for package, pkg_dies in self._noncomp_dies.items():
            if package not in self._compute_dies:
                # All packages must have compute dies.
                raise Error(f"BUG: Package {package} has non-compute dies but no compute dies")
            compute_dies_set = set(self._compute_dies[package])
            for die in pkg_dies:
                if die in compute_dies_set:
                    raise Error(f"BUG: Non-compute die ID {die} in package {package} overlaps "
                                f"with a compute die ID")

    def get_compute_dies_cpus(self,
                              proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> \
                                                                dict[int, dict[int, list[int]]]:
        """
        Return a dictionary mapping package numbers to dictionaries that map compute die numbers to
        lists of CPU numbers.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The compute dies CPUs dictionary: {package: {die: [cpu1, cpu2, ...]}}. Packages, dies,
            and CPUs are sorted in ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)

        return self._compute_dies_cpus

    def get_compute_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> dict[int, list[int]]:
        """
        Return a dictionary mapping package numbers to lists of compute die numbers.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The compute dies dictionary: {package: [die1, die2, ...]}. Packages and dies are sorted
            in ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)

        return self._compute_dies

    def get_noncomp_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> dict[int, list[int]]:
        """
        Return a dictionary mapping package numbers to lists of non-compute die numbers.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary

        Returns:
            The non-compute dies dictionary: {package: [die1, die2, ...]}. Packages and dies are
            sorted in ascending order.
        """

        if not self._noncomp_discovered:
            self._discover_noncomp_dies(proc_percpuinfo)

        return self._noncomp_dies

    def get_all_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> dict[int, list[int]]:
        """
        Return a dictionary mapping package numbers to lists of all die numbers (compute and
        non-compute).

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The all dies dictionary: {package: [die1, die2, ...]}. Packages and dies are sorted in
            ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)
        if not self._noncomp_discovered:
            self._discover_noncomp_dies(proc_percpuinfo)

        if self._all_dies:
            return self._all_dies

        all_dies_sets: dict[int, set[int]] = {}
        for pkg, dies in self._compute_dies.items():
            all_dies_sets.setdefault(pkg, set()).update(dies)
        for pkg, dies in self._noncomp_dies.items():
            all_dies_sets.setdefault(pkg, set()).update(dies)

        self._all_dies = {pkg: sorted(dies) for pkg, dies in all_dies_sets.items()}
        return self._all_dies

    def get_compute_dies_info(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> \
                                                        dict[int, dict[int, DieInfoTypedDict]]:
        """
        Return detailed information about compute dies.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The compute dies information dictionary: {package: {die: DieInfoTypedDict, ...}}.
            Packages and dies are sorted in ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)

        return self._compute_dies_info

    def get_noncomp_dies_info(self,
                              proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> \
                                                            dict[int, dict[int, DieInfoTypedDict]]:
        """
        Return detailed information about non-compute dies.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The non-compute dies information dictionary: {package: {die: DieInfoTypedDict, ...}}.
            Packages and dies are sorted in ascending order.
        """

        if not self._noncomp_discovered:
            self._discover_noncomp_dies(proc_percpuinfo)

        return self._noncomp_dies_info

    def get_all_dies_info(self,
                          proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> \
                                                        dict[int, dict[int, DieInfoTypedDict]]:
        """
        Return information about all dies (compute and non-compute).

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The all dies information dictionary: {package: {die: DieInfoTypedDict, ...}}.
            Packages and dies are sorted in ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)
        if not self._noncomp_discovered:
            self._discover_noncomp_dies(proc_percpuinfo)

        if self._all_dies_info:
            return self._all_dies_info

        for pkg, dies_info in self._compute_dies_info.items():
            self._all_dies_info.setdefault(pkg, {}).update(dies_info)
        for pkg, dies_info in self._noncomp_dies_info.items():
            self._all_dies_info.setdefault(pkg, {}).update(dies_info)

        return self._all_dies_info

    def cpus_hotplugged(self):
        """
        Handle CPU hotplug events by resetting cached die information.

        Notes:
            This is a coarse-grained implementation that clears all cached die information.
            Ideally, only the affected parts should be updated.
        """

        _LOG.debug("Clearing cached die information")

        self._compute_discovered = False
        self._compute_dies = {}
        self._compute_dies_cpus = {}
        self._compute_dies_info = {}
        self._noncomp_discovered = False
        self._noncomp_dies = {}
        self._noncomp_dies_info = {}
        self._all_dies = {}
        self._all_dies_info = {}
