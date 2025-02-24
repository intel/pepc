# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>

"""
Implement the 'pepc topology' command.
"""

from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo
from pepctool import _OpTarget

_LOG = Logging.getLogger(f"pepc.{__name__}")

def _get_default_colnames(cpuinfo):
    """
    Return 'CPUInfo.LEVELS' with the following exceptions:
     * If there is one die per package, exclude "die".
     * If there is one core per module, exclude "module".
    """

    colnames = list(CPUInfo.LEVELS)

    module = None
    for tline in cpuinfo.get_topology(levels=("core", "module", "package"), order="module"):
        if module != tline["module"]:
            module = tline["module"]
            core = tline["core"]
            package = tline["package"]
        elif core != tline["core"] or package != tline["package"]:
            break
    else:
        colnames.remove("module")

    package = None
    for tline in cpuinfo.get_topology(levels=("die", "package"), order="package"):
        if package != tline["package"]:
            die = tline["die"]
            package = tline["package"]
        elif die != tline["die"]:
            break
    else:
        colnames.remove("die")

    return colnames

def _add_offline_cpus(cpus, cpuinfo, topology, colnames):
    """
    Add offline CPUs to the topology table. Only the CPU numbers are known for offline CPUs,
    everything else is marked with '?' symbol.

    Return the updated topology table.
    """

    for cpu in cpuinfo.get_offline_cpus():
        if cpu in cpus:
            tline = {name: "?" for name in colnames}
            tline["CPU"] = cpu
            topology.append(tline)

    return topology

def _filter_cpus(cpus, topology):
    """
    The 'topology' topology table includes all CPUs. Filter out CPUs that are not in the 'cpus' set.
    """

    new_topology = []
    for tline in topology:
        # Do not filter out 'NA' CPUs, they will be handled separately.
        if tline["CPU"] == CPUInfo.NA or tline["CPU"] in cpus:
            new_topology.append(tline)
    return new_topology

def _filter_io_dies(optar, topology, colnames):
    """
    If the system has I/O dies (dies withot CPUs), they will be present in the 'topology' topology
    table. Exclude them if they should not be printed.
    """

    dies = {}
    if "die" in colnames:
        dies = optar.get_dies(strict=False)

    new_topology = []
    for tline in topology:
        if tline["CPU"] != CPUInfo.NA:
            new_topology.append(tline)
            continue

        if tline["package"] not in dies:
            continue
        if tline["die"] not in dies[tline["package"]]:
            continue
        new_topology.append(tline)

    return new_topology

def topology_info_command(args, pman):
    """
    Implement the 'topology info' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

    show_hybrid = None
    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        if args.columns is None:
            colnames = _get_default_colnames(cpuinfo)
        else:
            colnames = []
            for colname in Trivial.split_csv_line(args.columns):
                for key in CPUInfo.LEVELS:
                    if colname.lower() == key.lower():
                        colnames.append(key)
                        break
                else:
                    if colname == "hybrid":
                        show_hybrid = True
                    else:
                        columns = list(CPUInfo.LEVELS) + ["hybrid"]
                        columns = ", ".join(columns)
                        raise Error(f"invalid column name '{colname}', use one of: {columns}")

        if show_hybrid and not cpuinfo.info["hybrid"]:
            raise Error(f"no hybrid CPU found{pman.hostmsg}, found {cpuinfo.cpudescr}")
        order = args.order
        for lvl in CPUInfo.LEVELS:
            if order.lower() == lvl.lower():
                order = lvl
                break
        else:
            raise Error(f"invalid order '{order}', use one of: {', '.join(CPUInfo.LEVELS)}")

        offline_ok = not args.online_only

        # Create format string, example: '%7s    %3s    %4s    %4s    %3s'.
        fmt = "    ".join([f"%{len(name)}s" for name in colnames])

        # Create list of level names with the first letter capitalized. Example:
        # ["CPU", "Core", "Node", "Die", "Package"]
        headers = [name[0].upper() + name[1:] for name in colnames]

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings, offline_ok=offline_ok)

        # Note, if there are I/O dies, the topology will include them. They will be filtered out
        # separately in necessary.
        topology = cpuinfo.get_topology(levels=colnames, order=order)

        if show_hybrid is None and cpuinfo.info["hybrid"]:
            show_hybrid = True

        if show_hybrid:
            colnames.append("hybrid")
            headers.append("Hybrid")
            fmt += "    %6s"

            _, pcore_cpus = cpuinfo.get_hybrid_cpus()
            pcore_cpus = set(pcore_cpus)
            for tline in topology:
                if tline["CPU"] in pcore_cpus:
                    tline["hybrid"] = "P-core"
                else:
                    tline["hybrid"] = "E-core"

        cpus = set(optar.get_cpus())

        topology = _filter_cpus(cpus, topology)
        topology = _filter_io_dies(optar, topology, colnames)

        if offline_ok:
            topology = _add_offline_cpus(cpus, cpuinfo, topology, colnames)

    printed_tlines = set()
    _LOG.info(fmt, *headers)
    for tline in topology:
        for lvl, val in tline.items():
            if val == CPUInfo.NA:
                tline[lvl] = "-"

        args = tuple(str(tline[name]) for name in colnames)
        tline_str = fmt % args
        if tline_str in printed_tlines:
            continue

        _LOG.info(tline_str)
        printed_tlines.add(tline_str)
