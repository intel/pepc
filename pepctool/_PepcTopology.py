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

def topology_info_command(args, pman):
    """Implements the 'topology info' command."""

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        if args.columns is None:
            colnames = CPUInfo.LEVELS
        else:
            colnames = []
            for colname in Trivial.split_csv_line(args.columns):
                for key in CPUInfo.LEVELS:
                    if colname.lower() == key.lower():
                        colnames.append(key)
                        break
                else:
                    columns = ", ".join(CPUInfo.LEVELS)
                    raise Error(f"invalid colname '{colname}', use one of: {columns}")

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
