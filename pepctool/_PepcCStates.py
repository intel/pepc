# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "cstates" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.msr import MSR
from pepclibs import CStates, CPUInfo
from pepctool import _PepcCommon, _PepcPCStates

_LOG = logging.getLogger()

def cstates_config_command(args, pman):
    """Implements the 'cstates config' command."""

    if not hasattr(args, "oargs") and not getattr(args, "restore"):
        raise Error("please, provide a configuration option")

    # The '--enable' and '--disable' options.
    enable_opts = {}
    # Options to set (excluding '--enable' and '--disable').
    set_opts = {}
    # Options to print (excluding '--enable' and '--disable').
    print_opts = []

    opts =  getattr(args, "oargs", {})
    for optname, optval in opts.items():
        if optname in {"enable", "disable"}:
            enable_opts[optname] = optval
        elif optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    if enable_opts or set_opts:
        _PepcCommon.check_tuned_presence(pman)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         MSR.MSR(pman=pman, cpuinfo=cpuinfo) as msr, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo, msr=msr) as csobj, \
         _PepcPCStates.PepcCStates(pman, csobj, cpuinfo, msr=msr) as cstates:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        if args.restore:
            cstates.restore_cstate_config(args.restore)
        else:
            cstates.set_and_print_cstates(enable_opts, set_opts, print_opts, cpus)

def cstates_info_command(args, pman):
    """Implements the 'cstates info' command."""

    # Options to print.
    print_opts = []

    for optname in CStates.PROPS:
        if getattr(args, f"{optname}"):
            print_opts.append(optname)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo) as csobj, \
         _PepcPCStates.PepcCStates(pman, csobj, cpuinfo) as cstates:
        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        #
        # Print platform configuration info.
        #
        csnames = []
        if args.csnames != "default":
            csnames = args.csnames
        if not print_opts and args.csnames == "default":
            csnames = "all"
            print_opts = csobj.props

        cstates.print_or_save_cstates(csnames, print_opts, cpus, path=args.save)
