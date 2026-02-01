# -*- coding: utf-8 -*
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc uncore' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import typing
import contextlib

from pepclibs.msr import MSR
from pepclibs.helperlibs import Logging, YAML
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import Uncore, CPUInfo, _SysfsIO
from pepctools import _PepcCommon, _OpTarget, _PepcPrinter, _PepcSetter

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict
    from pepclibs._UncoreFreqBase import UncoreDieInfoTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepctools._PepcSetter  import PropSetInfoTypedDict
    from pepctools._PepcPrinter import PrintFormatType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A type for command-line arguments of the 'pepc uncore info' and
        'pepc uncore config' commands.

        Attributes:
            override_cpu_model: Override the CPU model with a custom value.
            mechanisms: Mechanism names to use for accessing uncore properties.
            cpus: CPU numbers to operate on.
            cores: Core numbers to operate on.
            modules: Module numbers to operate on.
            dies: Die numbers to operate on.
            packages: Package numbers to operate on.
            core_siblings: Core sibling indices to operate on.
            module_siblings: Module sibling indices to operate on.
            dies_info: Display detailed non-compute dies information.
            yaml: Whether to output results in YAML format.
            oargs: Dictionary of command line argument names and values matching the order of
                   appearance in the command line.
        """

        override_cpu_model: str
        mechanisms: str
        cpus: str
        cores: str
        modules: str
        dies: str
        packages: str
        core_siblings: str
        module_siblings: str
        oargs: dict[str, str]
        dies_info: bool
        yaml: bool

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
    cmdl["override_cpu_model"] = args.override_cpu_model
    cmdl["mechanisms"] = args.mechanisms
    cmdl["cpus"] = args.cpus
    cmdl["cores"] = args.cores
    cmdl["modules"] = args.modules
    cmdl["dies"] = args.dies
    cmdl["packages"] = args.packages
    cmdl["core_siblings"] = args.core_siblings
    cmdl["module_siblings"] = args.module_siblings
    cmdl["dies_info"] = getattr(args, "dies_info", False)
    cmdl["yaml"] = getattr(args, "yaml", False)
    cmdl["oargs"] = getattr(args, "oargs", {})

    return cmdl

def _display_dies_info(cmdl: _CmdlineArgsTypedDict,
                       pman: ProcessManagerType,
                       cpuinfo: CPUInfo.CPUInfo):
    """
    Display detailed non-compute die information and exit.

    Args:
        cmdl: Parsed command-line arguments.
        pman: Process manager object for target host.
        cpuinfo: 'CPUInfo' object for retrieving CPU topology information.
    """

    with _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, dies=cmdl["dies"],
                            packages=cmdl["packages"]) as optar:
        target_dies = optar.get_all_dies(strict=True)

    with Uncore.Uncore(pman=pman, cpuinfo=cpuinfo) as pobj:
        try:
            uncfreq_sysfs_obj = pobj.get_uncfreq_sysfs_obj()
            dies_info = uncfreq_sysfs_obj.get_dies_info(target_dies)
        except ErrorNotSupported:
            uncfreq_tpmi_obj = pobj.get_uncfreq_tpmi_obj()
            dies_info = uncfreq_tpmi_obj.get_dies_info(target_dies)

    if cmdl["yaml"]:
        # Drop uninitialized keys for cleaner output.
        _dies_info: dict[int, dict[int, UncoreDieInfoTypedDict]] = {}
        for package, pkg_dies in dies_info.items():
            _dies_info.setdefault(package, {})
            for die, die_info in pkg_dies.items():
                _die_info: UncoreDieInfoTypedDict = {}
                _die_info["title"] = die_info["title"]
                if die_info["path"]:
                    _die_info["path"] = die_info["path"]
                if die_info["addr"]:
                    _die_info["addr"] = die_info["addr"]
                    _die_info["instance"] = die_info["instance"]
                    _die_info["cluster"] = die_info["cluster"]
                _dies_info[package][die] = _die_info
        YAML.dump(_dies_info, sys.stdout)
        return

    for package, pkg_dies in dies_info.items():
        _LOG.info(f"Package {package}:")
        for die, die_info in pkg_dies.items():
            _LOG.info(f"  - Die {die} ({die_info['title']}):")
            if die_info["path"]:
                _LOG.info("    Linux UFS:")
                _LOG.info(f"    - Path: {die_info['path']}")
            if die_info["addr"]:
                _LOG.info("    TPMI UFS:")
                _LOG.info(f"    - Address: {die_info['addr']}")
                _LOG.info(f"    - Instance: {die_info['instance']}")
                _LOG.info(f"    - Cluster: {die_info['cluster']}")

def uncore_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'uncore info' command which displays uncore properties of the target host.

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

        if cmdl["dies_info"]:
            _display_dies_info(cmdl, pman, cpuinfo)
            return

        if cmdl["override_cpu_model"]:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl["override_cpu_model"])

        pobj = Uncore.Uncore(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        pprinter = _PepcPrinter.UncorePrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(pprinter)

        mnames = []
        if cmdl["mechanisms"]:
            mnames = _PepcCommon.parse_mechanisms(cmdl["mechanisms"], pobj)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"],
                                   dies=cmdl["dies"], packages=cmdl["packages"],
                                   core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"])
        stack.enter_context(optar)

        if not cmdl["oargs"]:
            # No options, print everything.
            printed = pprinter.print_props("all", optar, mnames=mnames, skip_unsupp_props=True,
                                           skip_unsupp_mechanisms=True, group=True)
        else:
            pnames = _PepcCommon.expand_subprops(cmdl["oargs"], pobj.props)
            printed = pprinter.print_props(pnames, optar, mnames=mnames)

        if not printed:
            _LOG.info("No uncore properties supported%s.", pman.hostmsg)

def uncore_config_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'uncore config' command which sets or displays uncore properties of the target
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
            spinfo[optname] = {"val" : optval}

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if cmdl["override_cpu_model"]:
            _PepcCommon.override_cpu_model(cpuinfo, cmdl["override_cpu_model"])

        msr = MSR.MSR(cpuinfo, pman=pman)
        stack.enter_context(msr)

        sysfs_io = _SysfsIO.SysfsIO(pman=pman)
        stack.enter_context(sysfs_io)

        pobj = Uncore.Uncore(pman=pman, msr=msr, sysfs_io=sysfs_io, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        mnames = []
        if cmdl["mechanisms"]:
            mnames = _PepcCommon.parse_mechanisms(cmdl["mechanisms"], pobj)
        for pname_spinfo in spinfo.values():
            pname_spinfo["mnames"] = mnames

        printer = _PepcPrinter.UncorePrinter(pobj, cpuinfo)
        stack.enter_context(printer)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=cmdl["cpus"],
                                   cores=cmdl["cores"], modules=cmdl["modules"], dies=cmdl["dies"],
                                   packages=cmdl["packages"], core_siblings=cmdl["core_siblings"],
                                   module_siblings=cmdl["module_siblings"])
        stack.enter_context(optar)

        if print_opts:
            printer.print_props(print_opts, optar, mnames=mnames)

        if spinfo:
            setter = _PepcSetter.UncoreSetter(pman, pobj, cpuinfo, printer, msr=msr,
                                              sysfs_io=sysfs_io)
            stack.enter_context(setter)
            setter.set_props(spinfo, optar)

    if spinfo:
        _PepcCommon.check_tuned_presence(pman)
