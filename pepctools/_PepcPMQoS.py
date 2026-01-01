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

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import PMQoS, CPUInfo, _SysfsIO
from pepctools import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict
    from pepclibs.PropsTypes import MechanismNameType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepctools._PepcSetter  import PropSetInfoTypedDict
    from pepctools._PepcPrinter import PrintFormatType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc pmqos info' and 'pepc pmqos
        config' commands.

        Attributes:
            yaml: Whether to output results in YAML format.
            mechanisms: Mechanism names to use for accessing P-state properties.
            cpus: CPU numbers to operate on.
            cores: Core numbers to operate on.
            modules: Module numbers to operate on.
            dies: Die numbers to operate on.
            packages: Package numbers to operate on.
            core_siblings: Core sibling indices to operate on.
            module_siblings: Module sibling indices to operate on.
            oargs: Dictionary of command line argument names and values matching the order of
                   appearance in the command line.
        """

        yaml: bool
        mechanisms: str
        cpus: str
        cores: str
        modules: str
        dies: str
        packages: str
        core_siblings: str
        module_siblings: str
        oargs: dict[str, str]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _CmdlineArgsTypedDict = {}
    cmdl["yaml"] = getattr(args, "yaml", False)
    cmdl["mechanisms"] = args.mechanisms
    cmdl["cpus"] = args.cpus
    cmdl["cores"] = args.cores
    cmdl["modules"] = args.modules
    cmdl["dies"] = args.dies
    cmdl["packages"] = args.packages
    cmdl["core_siblings"] = args.core_siblings
    cmdl["module_siblings"] = args.module_siblings
    cmdl["oargs"] = getattr(args, "oargs", {})

    return cmdl

def pmqos_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pstates pmqos' command which displays PM QoS properties.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    # The output format to use.
    fmt: PrintFormatType = "yaml" if cmdl["yaml"] else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        pobj = PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        pprinter = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(pprinter)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if not hasattr(args, "oargs"):
            # No options, print everything.
            printed = pprinter.print_props("all", optar, skip_unsupported=True, group=True)
        else:
            pnames = list(getattr(args, "oargs"))
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            printed = pprinter.print_props(pnames, optar, skip_unsupported=False)

        if not printed:
            _LOG.info("No PM QoS properties supported%s.", pman.hostmsg)

def pmqos_config_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pmqos config' command which sets or displays PM QoS properties of the target
    host.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)

    if not cmdl["oargs"]:
        raise Error("Please, provide a configuration option")

    # Options to set.
    spinfo: dict[str, PropSetInfoTypedDict] = {}
    # Options to print.
    print_opts: list[str] = []

    for optname, optval in cmdl["oargs"].items():
        if optval is None:
            print_opts.append(optname)
        else:
            spinfo[optname] = {"val" : optval, "mnames": ()}
            if optname in ("latency_limit", "global_latency_limit"):
                spinfo[optname]["default_unit"] = "us"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = PMQoS.PMQoS(pman=pman, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        printer = _PepcPrinter.PMQoSPrinter(pobj, cpuinfo)
        stack.enter_context(printer)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)
        stack.enter_context(optar)

        if print_opts:
            printer.print_props(print_opts, optar, skip_unsupported=False)

        if spinfo:
            setter = _PepcSetter.PMQoSSetter(pman, pobj, cpuinfo, printer, sysfs_io=sysfs_io)
            stack.enter_context(setter)
            setter.set_props(spinfo, optar)

    if spinfo:
        _PepcCommon.check_tuned_presence(pman)
