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
import contextlib
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.msr import MSR
from pepclibs import PStates, CPUInfo
from pepctool import _PepcCommon, _PepcPrinter, _PepcSetter

_LOG = logging.getLogger()

def pstates_info_command(args, pman):
    """Implements the 'pstates info' command."""

    # The options to print.
    if not hasattr(args, "oargs"):
        pnames = "all"
    else:
        pnames = list(getattr(args, "oargs"))

    # The output format to use.
    fmt = "yaml" if args.yaml else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        psobj = PStates.PStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(psobj)

        psprint = _PepcPrinter.PStatesPrinter(psobj, cpuinfo, fmt=fmt)
        stack.enter_context(psprint)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        skip_unsupported = False
        if not pnames:
            pnames = "all"
            # When printing all the options, skip the unsupported ones as they add clutter.
            skip_unsupported = True

        if not psprint.print_props(pnames=pnames, cpus=cpus, skip_unsupported=skip_unsupported):
            _LOG.info("No P-states properties supported%s.", pman.hostmsg)

def pstates_config_command(args, pman):
    """Implements the 'pstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    # Options to set.
    set_opts = {}
    # Options to print.
    print_opts = []

    opts = getattr(args, "oargs", {})
    for optname, optval in opts.items():
        if optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        msr = MSR.MSR(pman, cpuinfo=cpuinfo)
        stack.enter_context(msr)

        psobj = PStates.PStates(pman=pman, msr=msr, cpuinfo=cpuinfo)
        stack.enter_context(psobj)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        psprint = _PepcPrinter.PStatesPrinter(psobj, cpuinfo)
        stack.enter_context(psprint)

        if print_opts:
            psprint.print_props(pnames=print_opts, cpus=cpus, skip_unsupported=False)

        if set_opts:
            psset = _PepcSetter.PStatesSetter(psobj, cpuinfo, psprint, msr=msr)
            stack.enter_context(psset)
            psset.set_props(set_opts, cpus=cpus)

    if set_opts:
        _PepcCommon.check_tuned_presence(pman)

def pstates_save_command(args, pman):
    """Implements the 'pstates save' command."""

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        psobj = PStates.PStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(psobj)

        fobj = None
        if args.outfile != "-":
            try:
                # pylint: disable=consider-using-with
                fobj = open(args.outfile, "w", encoding="utf-8")
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"failed to open file '{args.outfile}':\n{msg}") from None

            stack.enter_context(fobj)

        psprint = _PepcPrinter.PStatesPrinter(psobj, cpuinfo, fobj=fobj, fmt="yaml")
        stack.enter_context(psprint)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        if not psprint.print_props(cpus=cpus, skip_ro=True, skip_unsupported=True):
            _LOG.info("No writable P-states properties supported%s.", pman.hostmsg)

def pstates_restore_command(args, pman):
    """Implements the 'pstates restore' command."""

    if not args.infile:
        raise Error("please, specify the file to restore from (use '-' to restore from standard "
                    "input)")

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        msr = MSR.MSR(pman, cpuinfo=cpuinfo)
        stack.enter_context(msr)

        psobj = PStates.PStates(pman=pman, msr=msr, cpuinfo=cpuinfo)
        stack.enter_context(psobj)

        psprint = _PepcPrinter.PStatesPrinter(psobj, cpuinfo)
        stack.enter_context(psprint)

        psset = _PepcSetter.PStatesSetter(psobj, cpuinfo, psprint, msr=msr)
        stack.enter_context(psset)

        psset.restore(args.infile)
