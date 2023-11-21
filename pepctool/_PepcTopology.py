# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>

"""
This module includes the "topology" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo
from pepctool import _PepcCommon

_LOG = logging.getLogger()

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

def topology_info_command(args, pman):
    """Implements the 'topology info' command."""

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
                        raise Error(f"invalid colname '{colname}', use one of: {columns}")

        if show_hybrid and not cpuinfo.info["hybrid"]:
            raise Error(f"no hybrid CPU found{pman.hostmsg}, found {cpuinfo.cpudescr}")
        order = args.order
        for lvl in CPUInfo.LEVELS:
            if order.lower() == lvl.lower():
                order = lvl
                break
        else:
            raise Error(f"invalid order '{order}', use one of: {', '.join(CPUInfo.LEVELS)}")

        offlined_ok = not args.online_only

        # Create format string, example: '%7s    %3s    %4s    %4s    %3s'.
        fmt = "    ".join([f"%{len(name)}s" for name in colnames])

        # Create list of level names with the first letter capitalized. Example:
        # ["CPU", "Core", "Node", "Die", "Package"]
        headers = [name[0].upper() + name[1:] for name in colnames]

        cpus = _PepcCommon.get_cpus(args, cpuinfo, offlined_ok=offlined_ok)
        topology = cpuinfo.get_topology(levels=colnames, order=order)

        if show_hybrid is None and cpuinfo.info["hybrid"]:
            show_hybrid = True

        if show_hybrid:
            colnames.append("hybrid")
            headers.append("Hybrid")
            fmt += "    %6s"

            performance_cores = set(cpuinfo.get_hybrid_cpu_topology()["pcore"])
            for tline in topology:
                if tline["CPU"] in performance_cores:
                    tline["hybrid"] = "P-core"
                else:
                    tline["hybrid"] = "E-core"

        if offlined_ok:
            # Offline CPUs are not present in 'topology' list. Thus, we add them to the list with
            # "?" as level number.
            for cpu in cpuinfo.get_offline_cpus():
                tline = {name : "?" for name in colnames}
                tline["CPU"] = cpu
                topology.append(tline)

    _LOG.info(fmt, *headers)
    for tline in topology:
        if tline["CPU"] in cpus:
            _LOG.info(fmt, *[str(tline[name]) for name in colnames])
