# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Implement the 'pepc topology' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib

from pepclibs import CPUInfo, NonCompDies
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepctools._OpTarget import ErrorNoCPUTarget
from pepctools import _OpTarget

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict, Sequence, cast, Final
    from pepclibs.CPUInfoTypes import ScopeNameType, HybridCPUKeyType
    from pepclibs.NonCompDies import NonCompDieInfoTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc topology info' command.

        Attributes:
            yaml: Whether to output results in YAML format.
            order: The scope name to order the topology by.
            online_only: Whether to include only online CPUs.
            columns: Comma-separated list of column names to display.
            cpus: CPU numbers to operate on.
            cores: Core numbers to operate on.
            modules: Module numbers to operate on.
            dies: Die numbers to operate on.
            packages: Package numbers to operate on.
            core_siblings: Core sibling indices to operate on.
            module_siblings: Module sibling indices to operate on.
        """

        yaml: bool
        order: str
        online_only: bool
        columns: str
        cpus: str
        cores: str
        modules: str
        dies: str
        packages: str
        core_siblings: str
        module_siblings: str

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

COLNAMES: Final[tuple[str, ...]] = tuple(list(CPUInfo.SCOPE_NAMES) + ["hybrid", "dtype"])
HEADERS: Final[tuple[str, ...]] = tuple(
    [nm[0].upper() + nm[1:] for nm in COLNAMES if nm != "dtype"] + ["DieType"]
)
COLNAMES_HEADERS: Final[dict[str, str]] = dict(zip(COLNAMES, HEADERS))

OFFLINE_MARKER: Final[str] = "?"
NA_MARKER: Final[str] = "-"

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _CmdlineArgsTypedDict = {}

    cmdl["yaml"] = getattr(args, "yaml", False)
    cmdl["order"] = args.order
    cmdl["online_only"] = args.online_only
    cmdl["columns"] = args.columns
    cmdl["cpus"] = args.cpus
    cmdl["cores"] = args.cores
    cmdl["modules"] = args.modules
    cmdl["dies"] = args.dies
    cmdl["packages"] = args.packages
    cmdl["core_siblings"] = args.core_siblings
    cmdl["module_siblings"] = args.module_siblings

    return cmdl

def _get_default_colnames(cpuinfo: CPUInfo.CPUInfo,
                          noncomp_dies: dict[int, list[int]]) -> list[ScopeNameType]:
    """
    Get the default column names for the topology table.

    Returns all scope names from 'CPUInfo.SCOPE_NAMES' with the following optimizations:
      - If every module has exactly one core, exclude "module" column.
      - If every package has exactly one die, exclude "die" column.

    This simplifies the output by hiding redundant topology levels.

    Args:
        cpuinfo: CPUInfo object for retrieving topology information.
        noncomp_dies: Non-compute dies indexed by package number.

    Returns:
        List of scope names to display as columns in the topology table.
    """

    colnames = list(CPUInfo.SCOPE_NAMES)

    # Check if all modules have exactly one core. If so, the "module" column is redundant.
    module = -1
    for tline in cpuinfo.get_topology(snames=("core", "module", "package"), order="module"):
        if module != tline["module"]:
            module = tline["module"]
            core = tline["core"]
            package = tline["package"]
        elif core != tline["core"] or package != tline["package"]:
            break
    else:
        colnames.remove("module")

    if noncomp_dies:
        # There are non-compute dies, skip the "die" redundancy check.
        return colnames

    # Check if all packages have exactly one die. If so, the "die" column is redundant.
    package = -1
    for tline in cpuinfo.get_topology(snames=("die", "package"), order="package"):
        if package != tline["package"]:
            die = tline["die"]
            package = tline["package"]
        elif die != tline["die"]:
            break
    else:
        colnames.remove("die")

    return colnames

def _append_offline_cpus(cpus: set[int],
                         cpuinfo: CPUInfo.CPUInfo,
                         topology: list[dict[str, int | str]],
                         snames: Sequence[ScopeNameType]):
    """
    Append offline CPUs to the topology table.

    For offline CPUs, only the CPU number is known. All other topology information (core, die,
    package, etc.) is marked with 'OFFLINE_MARKER' as it cannot be determined for offline CPUs.

    Args:
        cpus: Set of CPU numbers that should be included in the topology.
        cpuinfo: CPUInfo object for retrieving offline CPU information.
        topology: Topology table to which offline CPUs should be added.
        snames: Scope names included in the topology table.
    """

    for cpu in cpuinfo.get_offline_cpus():
        if cpu in cpus:
            tline: dict[str, int | str] = {name: OFFLINE_MARKER for name in snames}
            tline["CPU"] = cpu
            topology.append(tline)

def _filter_cpus(cpus: set[int],
                 topology: list[dict[ScopeNameType, int]]) -> list[dict[ScopeNameType, int]]:
    """
    Filter the topology table to include only the specified CPUs.

    Args:
        cpus: Set of CPU numbers to include in the filtered topology.
        topology: Full topology table containing all CPUs and non-compute dies.

    Returns:
        Filtered topology table containing only the specified CPUs and all non-compute dies.
    """

    new_topology = []
    for tline in topology:
        if tline["CPU"] in cpus:
            new_topology.append(tline)
    return new_topology

def _insert_noncomp_dies_type(topology: list[dict[str, int | str]],
                              colnames: list[str]) -> list[dict[str, int | str]]:
    """
    Insert the "dtype" column into the topology table.

    Args:
        topology: Topology table to insert the "dtype" column into.
        colnames: Column names in the topology table.

    Returns:
        Updated topology table with the "dtype" column included.
    """

    new_topology: list[dict[str, int | str]] = []

    for tline in topology:
        new_tline: dict[str, int | str] = {}
        for colname in colnames:
            if colname != "dtype":
                new_tline[colname] = tline[colname]
            else:
                new_tline["dtype"] = "Compute"

        new_topology.append(new_tline)

    return new_topology

def _append_noncomp_dies(target_dies: dict[int, list[int]],
                         noncomp_dies: dict[int, list[int]],
                         noncomp_dies_info: dict[int, dict[int, NonCompDieInfoTypedDict]],
                         topology: list[dict[str, int | str]],
                         colnames: list[str]):
    """
    Append non-compute dies to the topology table.

    Args:
        target_dies: Dies to include in the topology table, indexed by package number.
        noncomp_dies: Non-compute dies to append to the topology table, indexed by package number.
        noncomp_dies_info: Detailed information about non-compute dies.
        topology: Topology table to add non-compute dies to.
        colnames: Column names in the topology table.
    """

    for package, pkg_noncomp_dies in noncomp_dies.items():
        if package not in target_dies:
            continue
        for noncomp_die in pkg_noncomp_dies:
            if noncomp_die not in target_dies[package]:
                continue

            tline: dict[str, int | str] = {name: NA_MARKER for name in colnames}
            tline["die"] = noncomp_die
            tline["package"] = package
            tline["dtype"] = noncomp_dies_info[package][noncomp_die]["title"]

            topology.append(tline)

def _insert_hybrid(cpuinfo: CPUInfo.CPUInfo,
                   colnames: list[str],
                   topology: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    """
    Insert hybrid CPU type information into the topology table.

    Args:
        cpuinfo: CPUInfo object for retrieving hybrid CPU information.
        colnames: Column names in the topology table.
        topology: Topology table to insert hybrid CPU type information into.

    Returns:
        Updated topology table with hybrid CPU type information included.
    """

    new_topology: list[dict[str, int | str]] = []

    cpu_type_lists = cpuinfo.get_hybrid_cpus()
    cpu_type_sets: dict[HybridCPUKeyType, set[int]] = {}
    for htype, cpus in cpu_type_lists.items():
        cpu_type_sets[htype] = set(cpus)

    for tline in topology:
        new_tline: dict[str, int | str] = {}
        for colname in colnames:
            if colname != "hybrid":
                new_tline[colname] = tline[colname]
            else:
                new_tline["hybrid"] = NA_MARKER

        cpu = tline["CPU"]
        if cpu == NA_MARKER:
            continue

        for htype, hcpus_set in cpu_type_sets.items():
            if cpu in hcpus_set:
                new_tline["hybrid"] = CPUInfo.HYBRID_TYPE_INFO[htype]["name"]
                break
        else:
            _LOG.warn_once(f"Hybrid CPU '{cpu}' not found in hybrid CPUs information "
                           f"dictionary")
            new_tline["hybrid"] = "Unknown"

        new_topology.append(new_tline)

    return new_topology

def topology_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'topology info' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    colnames: list[str] = []
    snames: list[ScopeNameType] = []

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        ncompd = NonCompDies.NonCompDies(pman=pman)
        stack.enter_context(ncompd)

        noncomp_dies = ncompd.get_dies()
        noncomp_dies_info = ncompd.get_dies_info()

        if not cmdl["columns"]:
            snames = _get_default_colnames(cpuinfo, noncomp_dies)
            colnames = list(snames)
            if cpuinfo.is_hybrid:
                colnames.append("hybrid")
            if noncomp_dies:
                colnames.append("dtype")
        else:
            for colname in Trivial.split_csv_line(cmdl["columns"]):
                for sname in CPUInfo.SCOPE_NAMES:
                    if colname.lower() == sname.lower():
                        snames.append(sname)
                        colnames.append(sname)
                        break
                else:
                    if colname.lower() == "hybrid":
                        colnames.append("hybrid")
                    elif colname.lower() == "dtype":
                        colnames.append("dtype")
                    else:
                        colnames_str = ", ".join(COLNAMES)
                        raise Error(f"Invalid column name '{colname}', use one of: {colnames_str}")

            # The 'hybrid' column does not make sense without the 'CPU' column. The 'dtype' column
            # does not make sense without the 'die' column.
            colnames_set = set(colnames)
            if "hybrid" in colnames_set and "CPU" not in colnames_set:
                raise Error("The 'hybrid' column requires the 'CPU' column to be specified")
            if "dtype" in colnames_set and "die" not in colnames_set:
                raise Error("The 'dtype' column requires the 'die' column to be specified")

        order = cmdl["order"]
        for sname in CPUInfo.SCOPE_NAMES:
            if order.lower() == sname.lower():
                order = sname
                break
        else:
            raise Error(f"Invalid order '{order}', use one of: {', '.join(CPUInfo.SCOPE_NAMES)}")

        offline_ok = not cmdl["online_only"]

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"], dies=cmdl["dies"],
                                   packages=cmdl["packages"], core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"], offline_ok=offline_ok)
        stack.enter_context(optar)

        try:
            cpus = set(optar.get_cpus())
        except ErrorNoCPUTarget:
            # Presumably if only non-compute dies are requested.
            cpus = set()

        colnames_set = set(colnames)

        _topology = cpuinfo.get_topology(snames=snames, order=order)
        _topology = _filter_cpus(cpus, _topology)

        if typing.TYPE_CHECKING:
            topology = cast(list[dict[str, int | str]], _topology)
        else:
            topology = _topology

        if offline_ok:
            _append_offline_cpus(cpus, cpuinfo, topology, snames)

        if ("package" in colnames_set or "die" in colnames_set) and "dtype" in colnames_set:
            # The 'hybrid' column has not yet been inserted, skip it.
            colnames_no_hybrid = [name for name in colnames if name != "hybrid"]
            topology = _insert_noncomp_dies_type(topology, colnames_no_hybrid)

            target_dies = optar.get_all_dies(strict=False)
            _append_noncomp_dies(target_dies, noncomp_dies, noncomp_dies_info,
                                 topology, colnames_no_hybrid)

        if "hybrid" in colnames:
            topology = _insert_hybrid(cpuinfo, colnames, topology)

    # Create format string, example: '%7s    %3s    %4s    %4s    %3s'.
    fmt = "    ".join([f"%{len(name)}s" for name in colnames])

    # Print the topology table, but avoid printing duplicate lines. This can happen, for example,
    # when only dies and packages are selected - all CPUs within the same die will have identical
    # die and package numbers, and hence identical lines in the output.
    printed_tlines: set[tuple[str, ...]] = set()

    headers = [COLNAMES_HEADERS[name] for name in colnames]
    _LOG.info(fmt, *headers)
    for tline in topology:
        tline_tuple = tuple(str(tline[name]) for name in colnames)
        if tline_tuple not in printed_tlines:
            _LOG.info(fmt, *tline_tuple)
        printed_tlines.add(tline_tuple)
