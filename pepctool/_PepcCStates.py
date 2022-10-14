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

def _fmt_csnames(csnames):
    """Formats and returns the C-states list string, which can be used in messages."""

    if csnames == "all":
        msg = "all C-states"
    else:
        if len(csnames) == 1:
            msg = "C-state "
        else:
            msg = "C-states "
        msg += ",".join(csnames)

    return msg

def _print_cstates_status(cpus, cpuinfo, rcsobj):
    """Print brief C-state enabled/disabled status."""

    csinfo_iter = rcsobj.get_cstates_info(csnames="all", cpus=cpus)
    aggr_csinfo = _PepcCommon.build_aggregate_pinfo(csinfo_iter, sprops={"disable"})

    for csname, csinfo in aggr_csinfo.items():
        for kinfo in csinfo.values():
            for val, val_cpus in kinfo.items():
                val = "off" if val else "on"
                _PepcCommon.print_val_msg(val, cpuinfo, name=csname, cpus=val_cpus)

def _handle_enable_disable_opts(opts, cpus, cpuinfo, rcsobj):
    """Handle the '--enable' and '--disable' options of the 'cstates config' command."""

    print_cstates = False

    for optname, optval in opts.items():
        if not optval:
            # No value means that we should print the C-states information.
            print_cstates = True
            continue

        method = getattr(rcsobj, f"{optname}_cstates")
        toggled = method(csnames=optval, cpus=cpus)

        # The 'toggled' dictionary is indexed with CPU number. But we want to print a single line
        # for all CPU numbers that have the same toggled C-states list. Build a "reversed" version
        # of the 'toggled' dictionary for these purposes.
        revdict = {}
        for cpu, csinfo in toggled.items():
            key = ",".join(csinfo["csnames"])
            if key not in revdict:
                revdict[key] = []
            revdict[key].append(cpu)

        for cstnames, cpunums in revdict.items():
            cstnames = cstnames.split(",")
            _LOG.info("%sd %s on %s", optname.title(), _fmt_csnames(cstnames),
                                      _PepcCommon.fmt_cpus(cpunums, cpuinfo))

    if print_cstates:
        _print_cstates_status(cpus, cpuinfo, rcsobj)

def cstates_config_command(args, pman):
    """Implements the 'cstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    # The '--enable' and '--disable' options.
    enable_opts = {}
    # Options to set (excluding '--enable' and '--disable').
    set_opts = {}
    # Options to print (excluding '--enable' and '--disable').
    print_opts = []

    for optname, optval in args.oargs.items():
        if optname in {"enable", "disable"}:
            enable_opts[optname] = optval
        elif optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    if enable_opts or set_opts:
        _PepcCommon.check_tuned_presence(pman)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.ReqCStates(pman=pman, cpuinfo=cpuinfo) as rcsobj:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        _handle_enable_disable_opts(enable_opts, cpus, cpuinfo, rcsobj)

        if not set_opts and not print_opts:
            return

        with MSR.MSR(pman=pman, cpuinfo=cpuinfo) as msr, \
             CStates.CStates(pman=pman, cpuinfo=cpuinfo, rcsobj=rcsobj, msr=msr) as csobj, \
             _PepcPCStates.PepcPCStates(csobj, cpuinfo) as pcstates:

            msr.start_transaction()
            pcstates.set_props(set_opts, cpus)
            # Commit the transaction. This will flush all the change MSRs (if there were any).
            msr.commit_transaction()

            pcstates.print_props(print_opts, cpus)

def _print_requestable_cstates_info(args, cpus, cpuinfo, rcsobj):
    """Prints requestable C-states information."""

    csinfo_iter = rcsobj.get_cstates_info(csnames=args.csnames, cpus=cpus)
    sprops = {"disable", "latency", "residency"}
    aggr_csinfo = _PepcCommon.build_aggregate_pinfo(csinfo_iter, sprops=sprops)

    for csname, csinfo in aggr_csinfo.items():
        for key, kinfo in csinfo.items():
            for val, val_cpus in kinfo.items():
                if key == "disable":
                    val = "off" if val else "on"
                    _PepcCommon.print_val_msg(val, cpuinfo, name=csname, cpus=val_cpus)
                else:
                    if key == "latency":
                        name = "expected latency"
                    elif key == "residency":
                        name = "target residency"

                    # The first line starts with C-state name, align the second line nicely
                    # using the prefix. The end result is expected to be like this:
                    #
                    # POLL: 'on' for CPUs 0-15
                    # POLL: 'off' for CPUs 16-31
                    #       - expected latency: '0' us
                    prefix = " " * (len(csname) + 2) + "- "
                    suffix = " us"
                    _PepcCommon.print_val_msg(val, cpuinfo, name=name, prefix=prefix, suffix=suffix)

def cstates_info_command(args, pman):
    """Implements the 'cstates info' command."""

    # Options to print.
    print_opts = []

    for optname in CStates.PROPS:
        if getattr(args, f"{optname}"):
            print_opts.append(optname)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.ReqCStates(pman=pman, cpuinfo=cpuinfo) as rcsobj:
        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        #
        # Print platform configuration info.
        #
        with CStates.CStates(pman=pman, cpuinfo=cpuinfo, rcsobj=rcsobj) as csobj, \
             _PepcPCStates.PepcPCStates(csobj, cpuinfo) as pcstates:

            if args.csnames != "default":
                _print_requestable_cstates_info(args, cpus, cpuinfo, rcsobj)
            if print_opts:
                pcstates.print_props(print_opts, cpus)
            if not print_opts and args.csnames == "default":
                args.csnames = "all"
                _print_requestable_cstates_info(args, cpus, cpuinfo, rcsobj)
                pcstates.print_props(csobj.props, cpus, skip_unsupported=True)
