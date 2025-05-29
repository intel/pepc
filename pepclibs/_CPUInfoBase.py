# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide the base class for the 'CPUInfo.CPUInfo' class.
"""

# TODO: modernize this module
from __future__ import annotations # Remove when switching to Python 3.10+.

import re
from typing import Literal
import contextlib
from pathlib import Path
from pepclibs import _UncoreFreq, CPUModels
from pepclibs.msr import MSR, PMLogicalId
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial, KernelVersion
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

LevelNameType = Literal["CPU", "core", "module", "die", "node", "package"]

# The levels names have to be the same as 'sname' names in 'PStates', 'CStates', etc.
LEVELS: tuple[LevelNameType, ...] = ("CPU", "core", "module", "die", "node", "package")

# 'NA' is used for the CPU/core/module number for I/O dies, which do not include CPUs, cores, or
# modules. Use a very large number to make sure the the 'NA' numbers go last when sorting.
NA = 0xFFFFFFFF

class CPUInfoBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for the 'CPUInfo.CPUInfo' class. Implements low-level "plumbing", while the 'CPUInfo'
    class implements the API methods.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            # Disable caching to exclude usage of the 'cpuinfo' object by the 'MSR' module, which
            # happens when 'MSR' module uses 'PerCPUCache'.
            self._msr = MSR.MSR(self, pman=self._pman, enable_cache=False)

        return self._msr

    def _get_pliobj(self):
        """Returns a 'PMLogicalId.PMLogicalID()' object."""

        if not self._pliobj:
            if not self._pli_msr_supported:
                return None

            msr = self._get_msr()

            try:
                self._pliobj = PMLogicalId.PMLogicalId(pman=self._pman, cpuinfo=self, msr=msr)
            except ErrorNotSupported:
                self._pli_msr_supported = False

        return self._pliobj

    def _get_uncfreq_obj(self):
        """Return an '_UncoreFreqSysfs' object."""

        if not self._uncfreq_supported:
            return None

        if not self._uncfreq_obj:
            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreqSysfs(self, pman=self._pman)
            except ErrorNotSupported:
                self._uncfreq_supported = False

        return self._uncfreq_obj

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
        for data in self._pman.read_file("/proc/cpuinfo").strip().split("\n\n"):
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
                data = self._pman.read_file(base / "cache/index2/id")
            except ErrorNotFound as err:
                if not no_cache_info:
                    _LOG.debug("no CPU cache topology info found%s:\n%s.",
                               self._pman.hostmsg, err.indent(2))
                    no_cache_info = True
                    tinfo[cpu]["module"] = tinfo[cpu]["core"]
                    continue

            module = Trivial.str_to_int(data, what="module number")
            siblings = self._read_range(base / "cache/index2/shared_cpu_list")
            for sibling in siblings:
                # Suppress 'KeyError' in case the 'shared_cpu_list' file included an offline CPU.
                with contextlib.suppress(KeyError):
                    tinfo[sibling]["module"] = module

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
        if pli_obj:
            for cpu, die in pli_obj.read_feature("domain_id", cpus=cpus):
                _add_compute_die(tinfo, cpu, die)
        else:
            for cpu in cpus:
                if "die" in tinfo[cpu]:
                    continue

                base = Path(f"/sys/devices/system/cpu/cpu{cpu}")
                data = self._pman.read_file(base / "topology/die_id")
                die = Trivial.str_to_int(data, what="die number")
                siblings = self._read_range(base / "topology/die_cpus_list")
                for _ in siblings:
                    # Suppress 'KeyError' in case the 'die_cpus_list' file included an offline CPU.
                    with contextlib.suppress(KeyError):
                        _add_compute_die(tinfo, cpu, die)

    def _add_nodes(self, tinfo):
        """Adds NUMA node numbers to 'tinfo'."""

        nodes = self._read_range("/sys/devices/system/node/online")
        for node in nodes:
            cpus = self._read_range(f"/sys/devices/system/node/node{node}/cpulist")
            for cpu in cpus:
                # Suppress 'KeyError' in case the 'cpulist' file included an offline CPU.
                with contextlib.suppress(KeyError):
                    tinfo[cpu]["node"] = node

    def _add_io_dies(self, topology):
        """Add I/O dies to the 'topology' topology table (list of dictionaries)."""

        uncfreq_obj = self._get_uncfreq_obj()
        if not uncfreq_obj:
            return

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

    def _sort_topology(self, topology, order):
        """Sorts and save the topology list by 'order' in sorting map"""

        skeys = self._sorting_map[order]
        self._topology[order] = sorted(topology, key=lambda tline: tuple(tline[s] for s in skeys))

    def _update_topology(self):
        """Update topology information with online/offline CPUs."""

        new_online_cpus = self._get_online_cpus_set()
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
            tinfo = {cpu: {"CPU": cpu} for cpu in self._get_online_cpus_set()}
        else:
            tinfo = {tline["CPU"]: tline for tline in self._topology["CPU"] if tline["CPU"] != NA}

        cpus = self._get_online_cpus_set()
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

    def _read_range(self, path):
        """
        Read a file that is expected to contain a comma separated list of integer numbers or
        integer number rangees. Parse the contents of the file and return it as a list of integers.
        """

        str_of_ranges = self._pman.read_file(path)

        what = f"contents of file at '{path}'{self._pman.hostmsg}"
        return Trivial.split_csv_line_int(str_of_ranges.strip(), what=what)

    def _get_online_cpus_set(self):
        """Return online CPU numbers as a set."""

        if not self._cpus:
            self._cpus = set(self._read_range("/sys/devices/system/cpu/online"))
        return self._cpus

    def _get_all_cpus_set(self):
        """Return online and offline CPU numbers as a set."""

        if not self._all_cpus:
            self._all_cpus = set(self._read_range("/sys/devices/system/cpu/present"))
        return self._all_cpus

    def _get_cpu_info(self):
        """Get general CPU information (model, architecture, etc)."""

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
            for cpu in self._get_online_cpus_set():
                cpuinfo["flags"][cpu] = cpuflags

        if self._pman.exists("/sys/devices/cpu_atom/cpus"):
            cpuinfo["hybrid"] = True
        else:
            cpuinfo["hybrid"] = False
            with contextlib.suppress(Error):
                kver = KernelVersion.get_kver(pman=self._pman)
                if KernelVersion.kver_lt(kver, "5.13"):
                    _LOG.warn_once("kernel v%s does not support hybrid CPU topology. The minimum "
                                   "required kernel version is v5.13.", kver)

        cpuinfo["vfm"] = CPUModels.make_vfm(cpuinfo["vendor"], cpuinfo["family"], cpuinfo["model"])
        return cpuinfo

    def _get_cpu_description(self):
        """Build and return a string identifying and describing the processor."""

        if "genuine intel" in self.info["modelname"].lower():
            # Pre-release firmware on Intel CPU describes them as "Genuine Intel" (sometimes in
            # upper case), which is not very helpful.
            cpudescr = f"Intel processor model {self.info['model']:#x}"

            for info in CPUModels.MODELS.values():
                if info["vfm"] == self.info["vfm"]:
                    cpudescr += f" (codename: {info['codename']})"
                    break
        else:
            cpudescr = self.info["modelname"]

        return cpudescr

    def _get_hybrid_cpus(self):
        """Build and return the hybrid CPUs dictionary."""

        self._hybrid_cpus = {}
        for arch, name in (("atom", "ecore_cpus"), ("core", "pcore_cpus")):
            self._hybrid_cpus[name] = self._read_range(f"/sys/devices/cpu_{arch}/cpus")
        return self._hybrid_cpus

    def _cpus_hotplugged(self):
        """
        Must be called when a CPU goes online or offline. Drop cached numbers and force re-reading
        topology-related sysfs files.
        """

        self._cpus = None
        self._hybrid_cpus = None
        if self._topology:
            self._must_update_topology = True

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        # A dictionary including the general CPU information.
        self.info = None
        # A short CPU description string.
        self.cpudescr = None

        self._pman = pman
        self._close_pman = pman is None

        self._msr = None
        self._pliobj = None
        self._uncfreq_obj = None

        # 'True' if 'MSR_PM_LOGICAL_ID' is supported by the target host, otherwise 'False'. When
        # this MSR is supported, it provides the die IDs enumeration.
        self._pli_msr_supported = True
        # 'True' if the target host supports uncore frequency scaling.
        self._uncfreq_supported = True

        # Online CPU numbers.
        self._cpus = set()
        # Set of online and offline CPUs.
        self._all_cpus = None
        # Dictionary of P-core/E-core CPUs.
        self._hybrid_cpus = None

        # Per-package compute die numbers (dies which have CPUs) and I/O die numbers (dies which do
        # not have CPUs). Dictionaries with package numbers as key and set of die numbers as values.
        self._compute_dies = {}
        self._io_dies = {}

        # The topology dictionary. See 'get_topology()' for more information.
        self._topology = {}
        # Some CPUs have been brought online or offline, the topology data structures should be
        # updated.
        self._must_update_topology = False
        # Stores all initialized topology levels.
        self._initialized_levels = set()

        # We are going to sort topology by level, this map specifies how each is sorted. Note, core
        # and die numbers are per-package, therefore we always sort them by package first.
        self._sorting_map = {"CPU":     ("CPU",),
                             "core":    ("package", "core", "CPU"),
                             "module":  ("module", "CPU"),
                             "die":     ("package", "die", "CPU"),
                             "node":    ("node", "CPU"),
                             "package": ("package", "CPU")}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        self.info = self._get_cpu_info()
        self.cpudescr = self._get_cpu_description()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_uncfreq_obj", "_pliobj", "_msr", "_pman"))
