# -*- coding: utf-8 -*
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc pstates' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import contextlib
import argparse
from typing import NamedTuple
from pepclibs.msr import MSR
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PStates, CPUInfo, _SysfsIO
from pepctool import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter
from pepctool._PepcPrinter import PrintFormatType
from pepctool._PepcSetter  import PropSetInfoTypedDict

class _CmdlineArgsType(NamedTuple):
    """
    A type for command-line arguments of the 'pepc pstates info' and 'pepc pstates config' commands.

    Attributes:
        yaml: Whether to output results in YAML format.
        override_cpu_model: Override the CPU model with a custom value.
        mechanisms: List of mechanisms to use for accessing P-state properties.
        cpus: List of CPU numbers to operate on.
        cores: List of core numbers to operate on.
        modules: List of module numbers to operate on.
        dies: List of die numbers to operate on.
        packages: List of package numbers to operate on.
        core_siblings: List of core sibling numbers to operate on.
        module_siblings: List of module sibling numbers to operate on.
        oargs: Dictionary of command line argument names and values matching the order of appearance
               in the command line.
    """

    yaml: bool
    override_cpu_model: str
    mechanisms: list[str]
    cpus: list[int]
    cores: list[int]
    modules: list[int]
    dies: list[int]
    packages: list[int]
    core_siblings: list[int]
    module_siblings: list[int]
    oargs: dict[str, str]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsType:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    return _CmdlineArgsType(yaml=getattr(args, "yaml", False),
                            override_cpu_model=args.override_cpu_model,
                            mechanisms=args.mechanisms,
                            cpus=args.cpus,
                            cores=args.cores,
                            modules=args.modules,
                            dies=args.dies,
                            packages=args.packages,
                            core_siblings=args.core_siblings,
                            module_siblings=args.module_siblings,
                            oargs=getattr(args, "oargs", {}))

def pstates_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pstates info' command to display P-states properties for the target host.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    # The output format to use.
    fmt: PrintFormatType = "yaml" if cmdl.yaml else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if cmdl.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl.override_cpu_model)

        pobj = PStates.PStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        psprint = _PepcPrinter.PStatesPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(psprint)

        mnames = None
        if cmdl.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(cmdl.mechanisms, pobj)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl.cpus, cores=cmdl.cores,
                                   modules=cmdl.modules, dies=cmdl.dies, packages=cmdl.packages,
                                   core_siblings=cmdl.core_siblings,
                                   module_siblings=cmdl.module_siblings)
        stack.enter_context(optar)

        if cmdl.oargs:
            printed = psprint.print_props("all", optar, mnames=mnames, skip_unsupported=True,
                                          group=True)
        else:
            pnames = cmdl.oargs
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            printed = psprint.print_props(pnames, optar, mnames=mnames, skip_unsupported=False)

        if not printed:
            _LOG.info("No P-states properties supported%s.", pman.hostmsg)

def pstates_config_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pstates config' command to set or display P-states properties for the target
    host.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    if not cmdl.oargs:
        raise Error("Please, provide a configuration option")

    # Options to set.
    set_opts: dict[str, PropSetInfoTypedDict] = {}
    # Options to print.
    print_opts: list[str] = []

    for optname, optval in cmdl.oargs.items():
        if optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = {"val" : optval}

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if cmdl.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl.override_cpu_model)

        msr = MSR.MSR(cpuinfo, pman=pman)
        stack.enter_context(msr)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PStates.PStates(pman=pman, msr=msr, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        mnames = None
        if cmdl.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(cmdl.mechanisms, pobj)

        psprint = _PepcPrinter.PStatesPrinter(pobj, cpuinfo)
        stack.enter_context(psprint)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl.cpus, cores=cmdl.cores,
                                   modules=cmdl.modules, dies=cmdl.dies, packages=cmdl.packages,
                                   core_siblings=cmdl.core_siblings,
                                   module_siblings=cmdl.module_siblings)
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
