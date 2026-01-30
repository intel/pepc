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
Linux exposes die IDs via '/sys/devices/system/cpu/cpu<cpu>/topology/die_id' files. However, certain
platforms, such as Granite Rapids Xeon, do not expose compute dies via CPUID. On such platforms,
compute dies are enumerated via MSR 0x54 (MSR_PM_LOGICAL_ID), and 'pepc' uses the 'domain ID' field
of this MSR as die IDs.

When compute dies are enumerated via CPUID, die IDs are globally unique within the system. When
compute dies are enumerated via MSR 0x54, die IDs are unique only within a package. In other words,
multiple packages may have dies with the same die ID.

Non-compute dies are dies without CPUs. They are not enumerated via CPUID and cannot be enumerated
via MSRs. Pepc discovers non-compute dies via TPMI (Intel's Topology and Power Management
Interface) and assigns them a unique die ID.

A non-compute die is not a physical die - it is a logical entity representing an uncore frequency
scaling unit that does not have CPUs. Non-compute dies are enumerated via TPMI UFS (Uncore Frequency
Scaling) - every UFS cluster that does not have a "core" agent is considered a non-compute die.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path

from pepclibs import CPUModels
from pepclibs.helperlibs import Logging, ClassHelpers, LocalProcessManager, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import TypedDict, Literal
    from pepclibs import TPMI
    from pepclibs.ProcCpuinfo import ProcCpuinfoTypedDict, ProcCpuinfoPerCPUTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    # TPMI "agent types" for a die. Non-compute dies never have "core" agent type. But it is
    # included here for completeness.
    AgentTypes = Literal["core", "cache", "io", "memory"]

    class DieInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary representing information about a die.

        Attributes:
            title: A short description of the die.
            package: The package number the die belongs to.
            die: The die number.
            agent_types: A set of agent types present on the die.
            addr: The TPMI PCI device address.
            instance: The TPMI instance number.
            cluster: The TPMI cluster number.
        """

        title: str
        package: int
        die: int
        agent_types: set[AgentTypes]
        addr: str
        instance: int
        cluster: int

AGENT_TYPES: list[AgentTypes] = ["core", "cache", "io", "memory"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class DieInfo(ClassHelpers.SimpleCloseContext):
    """
    Provide information about compute and non-compute dies.

    Compute dies are discovered via sysfs or MSR 0x54, while non-compute dies are discovered via
    TPMI. This class provides unified access to both types of dies.

    Public methods overview.
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
        Return or create an instance of 'TPMI.TPMI' object.

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

    def _build_die_info_tpmi(self, compute: bool = True) -> \
                                tuple[dict[int, list[int]], dict[int, dict[int, DieInfoTypedDict]]]:
        """
        Build and return compute or non-compute die information from TPMI.

        Args:
            compute: If 'True', build compute die information, otherwise build non-compute die
                     information.

        Returns:
            A tuple containing:
                - A dictionary mapping package numbers to lists of die numbers:
                  {package: [die1, die2, ...]}.
                - A dictionary mapping package numbers to dictionaries that map die numbers to
                  'DieInfoTypedDict' dictionaries: {package: {die: DieInfoTypedDict, ...}}.
        """

        tpmi = self.get_tpmi()

        dies: dict[int, list[int]] = {}
        dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}

        for package, addr, instance, cluster in tpmi.iter_ufs_feature():
            regval = tpmi.read_ufs_register(addr, instance, cluster, "UFS_STATUS")

            is_compute = tpmi.get_bitfield(regval, "ufs", "UFS_STATUS", "AGENT_TYPE_CORE")
            if not compute and is_compute:
                _LOG.debug("Skipping a compute die at package %d, addr %s, instance %d, cluster %d",
                           package, addr, instance, cluster)
                continue
            if compute and not is_compute:
                _LOG.debug("Skipping a non-compute die at package %d, addr %s, instance %d, "
                           "cluster %d", package, addr, instance, cluster)
                continue

            die = instance + cluster
            dies.setdefault(package, []).append(die)

            agent_types = set()
            for agent_type in AGENT_TYPES:
                if tpmi.get_bitfield(regval, "ufs", "UFS_STATUS",
                                     f"AGENT_TYPE_{agent_type.upper()}"):
                    agent_types.add(agent_type)

            # Format the description so that it would have a form of:
            # - x: if there is only one agent.
            # - x and y: if there are two agents.
            # - x, y, and z: if there are three or more agents.
            # Also, use "I/O" instead of "io".
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

            pkg_info = dies_info.setdefault(package, {})
            die_info = pkg_info.setdefault(die, {})
            die_info["package"] = package
            die_info["die"] = die
            die_info["agent_types"] = agent_types
            die_info["title"] = title[0].upper() + title[1:]
            die_info["addr"] = addr
            die_info["instance"] = instance
            die_info["cluster"] = cluster

        return dies, dies_info

    def _build_compute_dies_info_no_tpmi(self):
        """
        Build compute die information when TPMI is not available.

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
                    "package": package,
                    "die": die,
                    "agent_types": {"core"},
                    "addr": "",
                    "instance": -1,
                    "cluster": -1,
                }
                compute_dies_info[package][die] = die_info

        return compute_dies_info

    def _discover_compute_dies_sysfs(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies via sysfs and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.
        """

        _LOG.debug("Discovering compute dies via sysfs")

        cpu2die: dict[int, int] = {}
        compute_dies_sets: dict[int, set[int]] = {}

        for package, cores in proc_percpuinfo["topology"].items():
            self._compute_dies_cpus.setdefault(package, {})
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
                        self._compute_dies_cpus[package].setdefault(die, []).append(cpu_sibling)

        self._compute_dies = {pkg: sorted(dies) for pkg, dies in compute_dies_sets.items()}
        for pkg, die_cpus in self._compute_dies_cpus.items():
            for die, cpus in die_cpus.items():
                die_cpus[die] = sorted(cpus)

    def _discover_compute_dies_msr(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies via MSR 0x54 and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.
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
        cpus = list(cpu2package)
        for cpu, regval in msr.cpus_read(regaddr, cpus):
            die = (regval >> 11) & 0x3F
            package = cpu2package[cpu]
            compute_dies_cpus_sets.setdefault(package, {})
            compute_dies_cpus_sets[package].setdefault(die, set()).add(cpu)

        for package, dies in compute_dies_cpus_sets.items():
            self._compute_dies[package] = sorted(dies)
            self._compute_dies_cpus[package] = {}
            for die, die_cpus_set in dies.items():
                self._compute_dies_cpus[package][die] = sorted(die_cpus_set)

    def _discover_compute_dies(self, proc_percpuinfo: ProcCpuinfoPerCPUTypedDict):
        """
        Discover compute dies and build the internal data structures.

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.
        """

        self._compute_discovered = True

        proc_cpuinfo = self._get_proc_cpuinfo()
        if proc_cpuinfo["vfm"] in CPUModels.MODELS_WITH_HIDDEN_DIES:
            self._discover_compute_dies_msr(proc_percpuinfo)
        else:
            self._discover_compute_dies_sysfs(proc_percpuinfo)

        try:
            self.get_tpmi()
        except ErrorNotSupported:
            _LOG.debug("TPMI is not supported, using basic compute die information")
            self._compute_dies_info = self._build_compute_dies_info_no_tpmi()
        else:
            _, self._compute_dies_info = self._build_die_info_tpmi(compute=True)

    def _discover_noncomp_dies(self):
        """Discover non-compute dies and build the internal data structures."""

        self._noncomp_discovered = True

        try:
            self.get_tpmi()
        except ErrorNotSupported:
            _LOG.debug("TPMI is not supported on the target system, cannot discover "
                       "non-compute dies")
            return

        _LOG.debug("Discovering non-compute dies via TPMI")

        self._noncomp_dies, self._noncomp_dies_info = self._build_die_info_tpmi(compute=False)

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

    def get_noncomp_dies(self) -> dict[int, list[int]]:
        """
        Return a dictionary mapping package numbers to lists of non-compute die numbers.

        Returns:
            The non-compute dies dictionary: {package: [die1, die2, ...]}. Packages and dies are
            sorted in ascending order.
        """

        if not self._noncomp_discovered:
            self._discover_noncomp_dies()

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
            self._discover_noncomp_dies()

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

    def get_noncomp_dies_info(self) -> dict[int, dict[int, DieInfoTypedDict]]:
        """
        Return detailed information about non-compute dies.

        Returns:
            The non-compute dies information dictionary: {package: {die: DieInfoTypedDict, ...}}.
            Packages and dies are sorted in ascending order.
        """

        if not self._noncomp_discovered:
            self._discover_noncomp_dies()

        return self._noncomp_dies_info

    def get_all_dies_info(self,
                          proc_percpuinfo: ProcCpuinfoPerCPUTypedDict) -> \
                                                        dict[int, dict[int, DieInfoTypedDict]]:
        """
        Return detailed information about all dies (compute and non-compute).

        Args:
            proc_percpuinfo: The per-CPU '/proc/cpuinfo' topology information dictionary.

        Returns:
            The all dies information dictionary: {package: {die: DieInfoTypedDict, ...}}.
            Packages and dies are sorted in ascending order.
        """

        if not self._compute_discovered:
            self._discover_compute_dies(proc_percpuinfo)
        if not self._noncomp_discovered:
            self._discover_noncomp_dies()

        all_dies_info: dict[int, dict[int, DieInfoTypedDict]] = {}
        for pkg, dies_info in self._compute_dies_info.items():
            all_dies_info.setdefault(pkg, {}).update(dies_info)
        for pkg, dies_info in self._noncomp_dies_info.items():
            all_dies_info.setdefault(pkg, {}).update(dies_info)

        return all_dies_info

    def cpus_hotplugged(self):
        """
        Handle CPU hotplug events by resetting cached compute die information.

        Notes:
            This is a coarse-grained implementation that clears all cached compute die information.
            Ideally, only the affected parts should be updated.
        """

        _LOG.debug("Clearing cached compute die information")
        self._compute_discovered = False
        self._compute_dies = {}
        self._compute_dies_cpus = {}
        self._all_dies = {}
