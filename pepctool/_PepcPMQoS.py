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

import contextlib
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PMQoS, CPUInfo, _SysfsIO
from pepctool import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

_LOG = Logging.getLogger(f"pepc.{__name__}")

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

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        pobj = PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo, fmt=fmt)
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

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PMQoS.PMQoS(pman=pman, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        mnames = None
        if args.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(args.mechanisms, pobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo)
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if print_opts:
            psprint.print_props(print_opts, optar, mnames=mnames, skip_unsupported=False)

        if set_opts:
            psset = _PepcSetter.PMQoSSetter(pman, pobj, cpuinfo, psprint, sysfs_io=sysfs_io)
            stack.enter_context(psset)
            psset.set_props(set_opts, optar, mnames=mnames)

    if set_opts:
        _PepcCommon.check_tuned_presence(pman)

def pmqos_save_command(args, pman):
    """
    Implement the 'pmqos save' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        pobj = PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        fobj = None
        if args.outfile != "-":
            try:
                # pylint: disable=consider-using-with
                fobj = open(args.outfile, "w", encoding="utf-8")
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"failed to open file '{args.outfile}':\n{msg}") from None

            stack.enter_context(fobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo, fobj=fobj, fmt="yaml")
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if not psprint.print_props("all", optar, skip_ro=True, skip_unsupported=True):
            _LOG.info("No writable PM QoS properties supported%s.", pman.hostmsg)

def pmqos_restore_command(args, pman):
    """
    Implement the 'pmqos restore' command. The arguments are as follows.
      * args - command line arguments dictionary
      * pman - the process manager object for the target host
    """

    if not args.infile:
        raise Error("please, specify the file to restore from (use '-' to restore from standard "
                    "input)")

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo)
        stack.enter_context(psprint)

        psset = _PepcSetter.PMQoSSetter(pman, pobj, cpuinfo, psprint, sysfs_io=sysfs_io)
        stack.enter_context(psset)

        psset.restore(args.infile)
