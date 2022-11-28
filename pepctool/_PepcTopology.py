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
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def _format_row(tline, colnames):
    """Format and return a list of 'colnames' values from 'tline' dictionary."""

    res = []
    for name in colnames:
        if tline[name] is not None:
            res += [str(tline[name])]
        else:
            res += ["?"]

    return res

def topology_info_command(args, pman):
    """Implements the 'topology info' command."""

    colnames = CPUInfo.LEVELS

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

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        cpus = _PepcCommon.get_cpus(args, cpuinfo, offlined_ok=offlined_ok)

        _LOG.info(fmt, *headers)
        for tline in cpuinfo.get_topology(order=order):
            if tline["CPU"] in cpus:
                _LOG.info(fmt, *_format_row(tline, colnames))
