# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc pstates' command.
"""

import contextlib
from pepclibs.msr import MSR
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PStates, CPUInfo, _SysfsIO
from pepctool import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def pstates_info_command(args, pman):
    """
    Implement the 'pstates info' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

    # The output format to use.
    fmt = "yaml" if args.yaml else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        pobj = PStates.PStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PStatesPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(psprint)

        mnames = None
        if args.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(args.mechanisms, pobj)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if not hasattr(args, "oargs"):
            printed = psprint.print_props("all", optar, mnames=mnames, skip_unsupported=True,
                                          group=True)
        else:
            pnames = list(getattr(args, "oargs"))
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            printed = psprint.print_props(pnames, optar, mnames=mnames, skip_unsupported=False)

        if not printed:
            _LOG.info("No P-states properties supported%s.", pman.hostmsg)

def pstates_config_command(args, pman):
    """
    Implement the 'pstates config' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

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
            set_opts[optname] = {"val" : optval}

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        msr = MSR.MSR(cpuinfo, pman=pman)
        stack.enter_context(msr)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PStates.PStates(pman=pman, msr=msr, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        mnames = None
        if args.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(args.mechanisms, pobj)

        psprint = _PepcPrinter.PStatesPrinter(pobj, cpuinfo)
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if print_opts:
            psprint.print_props(print_opts, optar, mnames=mnames, skip_unsupported=False)

        if set_opts:
            psset = _PepcSetter.PStatesSetter(pman, pobj, cpuinfo, psprint, msr=msr,
                                              sysfs_io=sysfs_io)
            stack.enter_context(psset)
            psset.set_props(set_opts, optar, mnames=mnames)

    if set_opts:
        _PepcCommon.check_tuned_presence(pman)
