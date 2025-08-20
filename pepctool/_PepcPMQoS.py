# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc pmqos' command.
"""

# TODO: annotate and modernize this module. Define a type for 'args'.
import contextlib
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PMQoS, CPUInfo, _SysfsIO
from pepctool import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def pmqos_info_command(args, pman):
    """
    Implement the 'pmqos info' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

    # The output format to use.
    fmt = "yaml" if args.yaml else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        pobj = PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if not hasattr(args, "oargs"):
            printed = psprint.print_props("all", optar, skip_unsupported=True,
                                          group=True)
        else:
            pnames = list(getattr(args, "oargs"))
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            printed = psprint.print_props(pnames, optar, skip_unsupported=False)

        if not printed:
            _LOG.info("No PM QoS properties supported%s.", pman.hostmsg)

def pmqos_config_command(args, pman):
    """
    Implement the 'pmqos config' command. The arguments are as follows.
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
            set_opts[optname] = {"val": optval}
            if optname in ("latency_limit", "global_latency_limit"):
                set_opts[optname]["default_unit"] = "us"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PMQoS.PMQoS(pman=pman, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo)
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if print_opts:
            psprint.print_props(print_opts, optar, skip_unsupported=False)

        if set_opts:
            psset = _PepcSetter.PMQoSSetter(pman, pobj, cpuinfo, psprint, sysfs_io=sysfs_io)
            stack.enter_context(psset)
            psset.set_props(set_opts, optar)

    if set_opts:
        _PepcCommon.check_tuned_presence(pman)
