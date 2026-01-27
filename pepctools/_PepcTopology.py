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

from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo
from pepctools import _OpTarget

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict, Sequence, cast
    from pepclibs.CPUInfoTypes import ScopeNameType
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

def _get_default_colnames(cpuinfo: CPUInfo.CPUInfo) -> list[ScopeNameType]:
    """
    Get the default column names for the topology table.

    Returns all scope names from 'CPUInfo.SCOPE_NAMES' with the following optimizations:
      - If every module has exactly one core, exclude "module" column.
      - If every package has exactly one die, exclude "die" column.

    This simplifies the output by hiding redundant topology levels.

    Args:
        cpuinfo: CPUInfo object for retrieving topology information.

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

def _add_offline_cpus(cpus: set[int],
                      cpuinfo: CPUInfo.CPUInfo,
                      topology: list[dict[ScopeNameType, int]],
                      colnames: Sequence[ScopeNameType]) -> list[dict[ScopeNameType, int]]:
    """
    Add offline CPUs to the topology table.

    For offline CPUs, only the CPU number is known. All other topology information (core, die,
    package, etc.) is marked with -1 as it cannot be determined for offline CPUs.

    Args:
        cpus: Set of CPU numbers that should be included in the topology.
        cpuinfo: CPUInfo object for retrieving offline CPU information.
        topology: Topology table to which offline CPUs should be added.
        colnames: Column names to include in the topology table entries.

    Returns:
        The updated topology table with offline CPUs added.
    """

    for cpu in cpuinfo.get_offline_cpus():
        if cpu in cpus:
            tline = {name: -1 for name in colnames}
            tline["CPU"] = cpu
            topology.append(tline)

    return topology

def _filter_cpus(cpus: set[int],
                 topology: list[dict[ScopeNameType, int]]) -> list[dict[ScopeNameType, int]]:
    """
    Filter the topology table to include only the specified CPUs.

    The topology table includes all CPUs in the system. Filter out the CPUs not specified in the
    'cpus' set. Non-compute dies (with NA CPU values) are always included as they will be filtered
    separately.

    Args:
        cpus: Set of CPU numbers to include in the filtered topology.
        topology: Full topology table containing all CPUs and non-compute dies.

    Returns:
        Filtered topology table containing only the specified CPUs and all non-compute dies.
    """

    new_topology = []
    for tline in topology:
        # Always include non-compute dies (NA CPUs), they will be filtered separately.
        if tline["CPU"] == CPUInfo.NA or tline["CPU"] in cpus:
            new_topology.append(tline)
    return new_topology

def _exclude_noncomp_dies(optar: _OpTarget.OpTarget,
                          topology: list[dict[ScopeNameType, int]],
                          colnames: Sequence[ScopeNameType]) -> list[dict[ScopeNameType, int]]:
    """
    Exclude non-compute dies from the topology table based on the operation target.

    Args:
        optar: Operation target object specifying which dies should be included.
        topology: Topology table containing both compute and non-compute dies.
        colnames: Sequence of column names to be displayed.

    Returns:
        A topology table with non-compute dies excluded if they are not in the operation target's
        die selection.
    """

    dies: dict[int, list[int]] = {}
    if "die" in colnames:
        dies = optar.get_dies(strict=False)

    new_topology = []
    for tline in topology:
        # Always include compute dies (lines with actual CPUs).
        if tline["CPU"] != CPUInfo.NA:
            new_topology.append(tline)
            continue

        if tline["package"] not in dies:
            continue
        if tline["die"] not in dies[tline["package"]]:
            continue

        new_topology.append(tline)

    return new_topology

def topology_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'topology info' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    snames: list[ScopeNameType]
    show_hybrid = False

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if not cmdl["columns"]:
            snames = list(_get_default_colnames(cpuinfo))
            if cpuinfo.is_hybrid:
                show_hybrid = True
        else:
            snames = []
            for colname in Trivial.split_csv_line(cmdl["columns"]):
                for key in CPUInfo.SCOPE_NAMES:
                    if colname.lower() == key.lower():
                        snames.append(key)
                        break
                else:
                    if colname.lower() == "hybrid":
                        show_hybrid = True
                    else:
                        columns = list(CPUInfo.SCOPE_NAMES) + ["hybrid"]
                        columns_str = ", ".join(columns)
                        raise Error(f"Invalid column name '{colname}', use one of: {columns_str}")

        order = cmdl["order"]
        for sname in CPUInfo.SCOPE_NAMES:
            if order.lower() == sname.lower():
                order = sname
                break
        else:
            raise Error(f"Invalid order '{order}', use one of: {', '.join(CPUInfo.SCOPE_NAMES)}")

        offline_ok = not cmdl["online_only"]

        # Create format string, example: '%7s    %3s    %4s    %4s    %3s'.
        fmt = "    ".join([f"%{len(name)}s" for name in snames])

        # Create list of scope names with the first letter capitalized. Example:
        # ["CPU", "Core", "Node", "Die", "Package"]
        headers = [name[0].upper() + name[1:] for name in snames]

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"], dies=cmdl["dies"],
                                   packages=cmdl["packages"], core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"], offline_ok=offline_ok)
        stack.enter_context(optar)

        cpus = set(optar.get_cpus())

        _topology = cpuinfo.get_topology(snames=snames, order=order)
        _topology = _filter_cpus(cpus, _topology)
        _topology = _exclude_noncomp_dies(optar, _topology, snames)
        if offline_ok:
            _topology = _add_offline_cpus(cpus, cpuinfo, _topology, snames)

        if typing.TYPE_CHECKING:
            topology = cast(list[dict[str, int | str]], _topology)
        else:
            topology = _topology

        colnames: list[str] = list(snames)
        if show_hybrid:
            colnames.append("hybrid")
            headers.append("Hybrid")
            fmt += "    %6s"

            hybrid_cpus = cpuinfo.get_hybrid_cpus()

            hybrid_cpu_sets = {}
            for htype, hcpus in hybrid_cpus.items():
                hybrid_cpu_sets[htype] = set(hcpus)

            for tline in topology:
                cpu = tline["CPU"]
                for htype, hcpus_set in hybrid_cpu_sets.items():
                    if cpu in hcpus_set:
                        tline["hybrid"] = CPUInfo.HYBRID_TYPE_INFO[htype]["name"]
                        break
                else:
                    _LOG.warn_once(f"Hybrid CPU '{cpu}' not found in hybrid CPUs information "
                                   f"dictionary")
                    tline["hybrid"] = "Unknown"

    printed_tlines = set()
    _LOG.info(fmt, *headers)
    for tline in topology:
        for lvl, val in tline.items():
            if val == CPUInfo.NA:
                tline[lvl] = "-"
            elif val == -1:
                tline[lvl] = "?"

        tline_str = fmt % tuple(str(tline[name]) for name in colnames)
        if tline_str in printed_tlines:
            continue

        _LOG.info(tline_str)
        printed_tlines.add(tline_str)
