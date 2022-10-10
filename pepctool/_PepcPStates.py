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
from pepctool import _PepcCommon, _PepcPCStates

_LOG = logging.getLogger()

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
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj, \
         _PepcPCStates.PepcPCStates(psobj, cpuinfo=cpuinfo) as pcstates:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        if set_opts:
            pcstates.set_props(set_opts, cpus)
        if print_opts:
            pcstates.print_props(print_opts, cpus, False)

def pstates_info_command(args, pman):
    """Implements the 'pstates info' command."""

    # Options to print.
    print_opts = []

    for optname in PStates.PROPS:
        if getattr(args, f"{optname}"):
            print_opts.append(optname)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj, \
         _PepcPCStates.PepcPCStates(psobj, cpuinfo=cpuinfo) as pcstates:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        skip_unsupported = False
        if not print_opts:
            print_opts = psobj.props
            # When printing all the options, skip the unsupported ones as they add clutter.
            skip_unsupported = True

        pcstates.print_props(print_opts, cpus, skip_unsupported)
