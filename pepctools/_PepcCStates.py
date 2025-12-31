# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc cstates' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pepclibs.msr import MSR
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CStates, CPUInfo
from pepctools import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

if typing.TYPE_CHECKING:
    import argparse
    from typing import Sequence, TypedDict, Literal, cast
    from pepclibs.PropsTypes import MechanismNameType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepctools._PepcSetter  import PropSetInfoTypedDict
    from pepctools._PepcPrinter import PrintFormatType

    class _ConfigCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc cstates config' command.

        Attributes:
            yaml: Whether to output results in YAML format.
            override_cpu_model: Override the CPU model with a custom value.
            mechanisms: List of mechanisms to use for accessing C-state properties.
            cpus: List of CPU numbers to operate on.
            cores: List of core numbers to operate on.
            modules: List of module numbers to operate on.
            dies: List of die numbers to operate on.
            packages: List of package numbers to operate on.
            core_siblings: List of core sibling indices to operate on.
            module_siblings: List of module sibling indices to operate on.
            oargs: Dictionary of command line argument names and values matching the order of
                   appearance in the command line.
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

    class _InfoCmdlineArgsTypedDict(_ConfigCmdlineArgsTypedDict):
        """
        A typed dictionary for command-line arguments of the 'pepc cstates info' command.

        Attributes:
            *: All attributes are inherited from _ConfigCmdlineArgsTypedDict.
            csnames: List of C-state names to operate on, or "all" to indicate all available
                     C-states.
        """

        csnames: list[str] | Literal["all"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_config_cmdline_args(args: argparse.Namespace) -> _ConfigCmdlineArgsTypedDict:
    """
    Format the 'pepc cstates config' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """
    cmdl: _ConfigCmdlineArgsTypedDict = {}
    cmdl["yaml"] = getattr(args, "yaml", False)
    cmdl["override_cpu_model"] = args.override_cpu_model
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

def _get_info_cmdline_args(args: argparse.Namespace) -> _InfoCmdlineArgsTypedDict:
    """
    Format the 'pepc cstates config' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    csnames: list[str] | Literal["all"]

    # 'args.csname' is "default" if '--csnames' option was not specified, and 'None' if it was
    # specified, but without an argument.
    if not args.csnames:
        csnames = "all"
    elif args.csnames == "default":
        csnames = []
    else:
        csnames = Trivial.split_csv_line(args.csnames)

    info_cmdl = _get_config_cmdline_args(args)
    if typing.TYPE_CHECKING:
        cmdl = cast(_InfoCmdlineArgsTypedDict, info_cmdl)
    else:
        cmdl = info_cmdl

    cmdl["csnames"] = csnames

    return cmdl

def cstates_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'cstates info' command which displays C-state properties of the target host.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_info_cmdline_args(args)

    # The output format to use.
    fmt: PrintFormatType = "yaml" if cmdl["yaml"] else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if cmdl["override_cpu_model"]:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl["override_cpu_model"])

        pobj = CStates.CStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        pprinter = _PepcPrinter.CStatesPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(pprinter)

        mnames: Sequence[MechanismNameType] = []
        if cmdl["mechanisms"]:
            mnames_split = _PepcCommon.parse_mechanisms(cmdl["mechanisms"], pobj)
            if typing.TYPE_CHECKING:
                mnames = cast(Sequence[MechanismNameType], mnames_split)
            else:
                mnames = mnames_split

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"], dies=cmdl["dies"],
                                   packages=cmdl["packages"], core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"])
        stack.enter_context(optar)

        printed = 0
        if not cmdl["oargs"] and not cmdl["csnames"]:
            # No options were specified. Print all the information. Skip the unsupported ones as
            # they add clutter.
            printed += pprinter.print_cstates(csnames="all", cpus=optar.get_cpus(), mnames=mnames,
                                              group=True)
            printed += pprinter.print_props("all", optar, mnames=mnames, skip_unsupported=True,
                                            group=True)
        else:
            if cmdl["csnames"]:
                csnames = cmdl["csnames"]
                if cmdl["csnames"] is None:
                    csnames = "all"
                printed += pprinter.print_cstates(csnames=csnames, cpus=optar.get_cpus(),
                                                  mnames=mnames)

            pnames = list(getattr(cmdl, "oargs", []))
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            if pnames:
                printed += pprinter.print_props(pnames, optar, mnames=mnames,
                                                skip_unsupported=False)

        if not printed:
            _LOG.info("No C-state properties supported%s", pman.hostmsg)

def cstates_config_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'cstates config' command which sets or displays C-state properties of the target
    host.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_config_cmdline_args(args)

    if not cmdl["oargs"]:
        raise Error("Please, provide a configuration option")

    # The '--enable' and '--disable' options.
    enable_opts: dict[str, str] = {}
    # Options to set (excluding '--enable' and '--disable').
    spinfo: dict[str, PropSetInfoTypedDict] = {}
    # Options to print (excluding '--enable' and '--disable').
    print_opts: list[str] = []

    for optname, optval in cmdl["oargs"].items():
        if optname in {"enable", "disable"}:
            enable_opts[optname] = optval
        elif optval is None:
            print_opts.append(optname)
        else:
            spinfo[optname] = {"val" : optval}

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if cmdl["override_cpu_model"]:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl["override_cpu_model"])

        msr = MSR.MSR(cpuinfo, pman=pman)
        stack.enter_context(msr)

        pobj = CStates.CStates(pman=pman, msr=msr, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        mnames: list[MechanismNameType] = []
        if cmdl["mechanisms"]:
            mnames = _PepcCommon.parse_mechanisms(cmdl["mechanisms"], pobj)
        for pname_spinfo in spinfo.values():
            pname_spinfo["mnames"] = mnames

        printer = _PepcPrinter.CStatesPrinter(pobj, cpuinfo)
        stack.enter_context(printer)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"], dies=cmdl["dies"],
                                   packages=cmdl["packages"], core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"])
        stack.enter_context(optar)

        all_cstates_printed = False
        for optname in list(enable_opts):
            if not enable_opts[optname]:
                # Handle the special case of '--enable' and '--disable' option without arguments. In
                # this case we just print the C-states enable/disable status.
                if not all_cstates_printed:
                    printer.print_cstates(csnames="all", cpus=optar.get_cpus(), mnames=mnames)
                    all_cstates_printed = True
                del enable_opts[optname]

        if print_opts:
            printer.print_props(print_opts, optar, mnames=mnames, skip_unsupported=False)

        if spinfo or enable_opts:
            setter = _PepcSetter.CStatesSetter(pman, pobj, cpuinfo, printer, msr=msr)
            stack.enter_context(setter)

        if enable_opts:
            for optname, optval in enable_opts.items():
                csnames: list[str] | Literal["all"]
                if optval == "all":
                    csnames = "all"
                else:
                    csnames = Trivial.split_csv_line(optval)
                enable = optname == "enable"
                setter.set_cstates(csnames, cpus=optar.get_cpus(), enable=enable,
                                   mnames=mnames)

        if spinfo:
            setter.set_props(spinfo, optar)

    if enable_opts or spinfo:
        _PepcCommon.check_tuned_presence(pman)
