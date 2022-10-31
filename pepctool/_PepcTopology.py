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
from pepclibs import CPUInfo

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

    colnames = tuple(reversed(CPUInfo.LEVELS))

    # Create format string, example: '%7s    %3s    %4s    %4s    %3s'.
    fmt = "    ".join([f"%{len(info)}s" for info in colnames])

    # Create list of level names with the first letter capitalized. Example:
    # ["CPU", "Core", "Node", "Die", "Package"]
    headers = [info[0].upper() + info[1:] for info in colnames]

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        _LOG.info(fmt, *headers)

        for tline in cpuinfo.get_topology():
            _LOG.info(fmt, *_format_row(tline, colnames))
