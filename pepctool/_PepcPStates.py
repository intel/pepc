#!/usr/bin/python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "pstates" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PStates, CPUInfo
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def _handle_set_opts(opts, cpus, psobj, cpuinfo):
    """
    Handle C-state configuration options other than '--enable' and '--disable' which have to be
    set.
    """

    psobj.set_props(opts, cpus)
    for pname in opts:
        # Read back the just set value.
        _, pinfo = next(psobj.get_props((pname,), cpus=cpus))
        val = pinfo[pname][pname]
        _PepcCommon.print_prop_msg(psobj.props[pname], val, cpuinfo, action="set to", cpus=cpus)

def _handle_print_opts(opts, cpus, psobj, cpuinfo):
    """Handle P-state configuration options that have to be printed."""

    # Build the aggregate properties information dictionary for all options we are going to print
    # about.
    pinfo_iter = psobj.get_props(opts, cpus=cpus)
    aggr_pinfo = _PepcCommon.build_aggregate_pinfo(pinfo_iter)

    _PepcCommon.print_aggr_props(aggr_pinfo, psobj, cpuinfo)

def pstates_config_command(args, pman):
    """Implements the 'pstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    _PepcCommon.check_tuned_presence(pman)

    # Options to set.
    set_opts = {}
    # Options to print.
    print_opts = []

    for optname, optval in args.oargs.items():
        if optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        if set_opts:
            _handle_set_opts(set_opts, cpus, psobj, cpuinfo)
        if print_opts:
            _handle_print_opts(print_opts, cpus, psobj, cpuinfo)

def pstates_info_command(args, pman):
    """Implements the 'pstates info' command."""

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:
        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        pinfo_iter = psobj.get_props(psobj.props, cpus=cpus)
        aggr_pinfo = _PepcCommon.build_aggregate_pinfo(pinfo_iter)
        _PepcCommon.print_aggr_props(aggr_pinfo, psobj, cpuinfo)
