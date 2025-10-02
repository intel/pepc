# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc tpmi' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import typing
import contextlib
from pepclibs import Tpmi, CPUInfo
from pepclibs.helperlibs import Logging, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _RegInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary used for collecting register information while running the
        'pepc tpmi read' command.

        Attributes:
            value: The register value.
            fields: A dictionary of bit field names and their values.
        """

        value: int
        fields: dict[str, int]

    class _PkgInstnacesTypedDict(TypedDict, total=False):
        """
        A typed dictionary used for collecting the 'pepc tpmi read' command results.

        Attributes:
            package: The package number.
            instances: A dictionary where keys are the instance numbers and values are dictionaries
                       where keys are register names and values the register descriptions
                       dictionaries.
        """

        package: int
        instances: dict[int, dict[str, _RegInfoTypedDict]]

    # A type for the 'pepc tpmi read' command output dictionary.
    _ReadInfoType = dict[str, dict[str, _PkgInstnacesTypedDict]]

    class _LsCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi ls' command.

        Attributes:
            long: Whether to output extra information about each feature.
            all: Whether to list all features, including the unknown ones.
        """

        long: bool
        all: bool

    class _ReadCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi read' command.

        Attributes:
            fnames: List of TPMI feature names to read.
            addrs: List of TPMI device PCI addresses to read from.
            packages: List of package numbers to operate on.
            instances: List of TPMI instance numbers to read from.
            regnames: List of register names to read.
            bfnames: List of bit field names to read.
            yaml: Whether to output results in YAML format.
        """

        fnames: list[str]
        addrs: list[str]
        packages: list[int]
        instances: list[int]
        regnames: list[str]
        bfnames: list[str]
        yaml: bool

    class _WriteCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi write' command.

        Attributes:
            fname: TPMI feature name to write.
            addrs: List of TPMI device PCI addresses to write to.
            packages: List of package numbers to operate on.
            instances: List of TPMI instance numbers to write to.
            regname: Name of the register to write to.
            bfname: Name of the bit field to write to (if any).
            value: Value to write.
        """

        fname: str
        addrs: list[str]
        packages: list[int]
        instances: list[int]
        regname: str
        bfname: str
        value: int

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_ls_cmdline_args(args: argparse.Namespace) -> _LsCmdlineArgsTypedDict:
    """
    Format 'pepc tpmi ls' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _LsCmdlineArgsTypedDict = {}
    cmdl["long"] = args.long
    cmdl["all"] = args.all

    return cmdl

def _get_read_cmdline_args(args: argparse.Namespace) -> _ReadCmdlineArgsTypedDict:
    """
    Format 'pepc tpmi read' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    if args.fnames:
        fnames = Trivial.split_csv_line(args.fnames, dedup=True)
    else:
        fnames = []

    if args.addrs:
        addrs = Trivial.split_csv_line(args.addrs, dedup=True)
    else:
        addrs = []

    if args.packages:
        packages = Trivial.split_csv_line_int(args.packages, dedup=True, what="package numbers")
    else:
        packages = []

    if args.instances:
        instances = Trivial.split_csv_line_int(args.instances, dedup=True,
                                               what="TPMI instance numbers")
    else:
        instances = []

    if args.registers:
        regnames = Trivial.split_csv_line(args.registers, dedup=True)
    else:
        regnames = []

    if args.bfnames:
        bfnames = Trivial.split_csv_line(args.bfnames, dedup=True)
    else:
        bfnames = []

    if bfnames and not regnames:
        raise Error("'--bfname' requires '--registers' to be specified")

    cmdl: _ReadCmdlineArgsTypedDict = {}
    cmdl["fnames"] = fnames
    cmdl["addrs"] = addrs
    cmdl["packages"] = packages
    cmdl["instances"] = instances
    cmdl["regnames"] = regnames
    cmdl["bfnames"] = bfnames
    cmdl["yaml"] = getattr(args, "yaml", False)

    return cmdl

def _get_write_cmdline_args(args: argparse.Namespace) -> _WriteCmdlineArgsTypedDict:
    """
    Format 'pepc tpmi write' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    if args.addrs:
        addrs = Trivial.split_csv_line(args.addrs, dedup=True)
    else:
        addrs = []

    if args.packages:
        packages = Trivial.split_csv_line_int(args.packages, dedup=True, what="package numbers")
    else:
        packages = []

    if args.instances:
        instances = Trivial.split_csv_line_int(args.instances, dedup=True,
                                               what="TPMI instance numbers")
    else:
        instances = []

    value = Trivial.str_to_int(args.value, what="value to write")

    cmdl: _WriteCmdlineArgsTypedDict = {}
    cmdl["fname"] = args.fname
    cmdl["addrs"] = addrs
    cmdl["packages"] = packages
    cmdl["instances"] = instances
    cmdl["regname"] = args.regname
    cmdl["bfname"] = args.bfname
    cmdl["value"] = value

    return cmdl

def _ls_long(fname: str, tpmi: Tpmi.Tpmi, prefix: str = ""):
    """
    Display detailed information about a feature for the 'tpmi ls -l' command.

    Args:
        fname: Name of the feature to display information for.
        tpmi: A 'Tpmi.Tpmi' object.
        prefix: String prefix for formatting log output.
    """

    # A dictionary with the info that will be printed.
    #   * first level key - package number.
    #   * second level key - PCI address.
    #   * regval - instance numbers.
    info: dict[int, dict[str, set[int]]] = {}

    for addr, package, instance in tpmi.iter_feature(fname):
        if package not in info:
            info[package] = {}
        if addr not in info[package]:
            info[package][addr] = set()
        info[package][addr].add(instance)

    for package in sorted(info):
        pfx1 = prefix + "- "
        pfx2 = prefix + "  "

        for addr in sorted(info[package]):
            _LOG.info("%sPCI address: %s", pfx1, addr)
            pfx1 = pfx2 + "- "
            pfx2 += "  "

            _LOG.info("%sPackage: %s", pfx2, package)

            instances = Trivial.rangify(info[package][addr])
            _LOG.info("%sInstances: %s", pfx2, instances)

def tpmi_ls_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'tpmi ls' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_ls_cmdline_args(args)

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman)
        stack.enter_context(cpuinfo)

        tpmi = Tpmi.Tpmi(cpuinfo.info, pman=pman)
        stack.enter_context(tpmi)

        sdicts = tpmi.get_known_features()
        if not sdicts:
            _LOG.info("Not supported TPMI features found")
        else:
            _LOG.info("Supported TPMI features")
            for sdict in sdicts:
                _LOG.info(" - %s: %s", sdict["name"], sdict["desc"].strip())
                if cmdl["long"]:
                    _ls_long(sdict["name"], tpmi, prefix="   ")

        if cmdl["all"]:
            fnames = tpmi.get_unknown_features()
            if fnames and cmdl["all"]:
                _LOG.info("Unknown TPMI features (available%s, but no spec file found)",
                          pman.hostmsg)
                txt = ", ".join(hex(fid) for fid in fnames)
                _LOG.info(" - %s", txt)

def _tpmi_read_command_print(tpmi: Tpmi.Tpmi, info: _ReadInfoType):
    """
    Print the result of the 'tpmi read' command.

    Iterate through the features, PCI addresses, instances, registers, and bitfields in the 'info'
    dictionary and print each element in a structured and indented format.

    Args:
        tpmi: A 'Tpmi.Tpmi' object.
        info: The 'pepc tpmi read' result dictionary containing TPMI read command output, organized
              by feature, address, instance, and register.
    """

    pfx = "- "
    nopfx = "  "
    for fname, feature_info in info.items():
        pfx_indent = 0
        _LOG.info("%sTPMI feature: %s", " " * pfx_indent + pfx, fname)

        fdict = tpmi.get_fdict(fname)
        for addr, addr_info in feature_info.items():
            pfx_indent = 2
            _LOG.info("%sPCI address: %s", " " * pfx_indent + pfx, addr)
            _LOG.info("%sPackage: %d", " " * pfx_indent + nopfx, addr_info["package"])

            for instance, instance_info in addr_info["instances"].items():
                pfx_indent = 4
                _LOG.info("%sInstance: %d", " " * pfx_indent + pfx, instance)

                for regname, reginfo in instance_info.items():
                    pfx_indent = 6
                    _LOG.info("%s%s: %#x", " " * pfx_indent + pfx, regname, reginfo["value"])

                    if "fields" not in reginfo:
                        continue

                    for bfname, bfval in reginfo["fields"].items():
                        bfinfo = fdict[regname]["fields"][bfname]
                        pfx_indent = 8
                        _LOG.info("%s%s[%s]: %d",
                                  " " * pfx_indent + pfx, bfname, bfinfo["bits"], bfval)

def tpmi_read_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'tpmi read' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_read_cmdline_args(args)

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman)
        stack.enter_context(cpuinfo)

        tpmi = Tpmi.Tpmi(cpuinfo.info, pman=pman)
        stack.enter_context(tpmi)

        fnames = cmdl["fnames"]
        if not cmdl["fnames"]:
            fnames = [sdict["name"] for sdict in tpmi.get_known_features()]

        # Prepare all the information to print in the 'info' dictionary.
        #  * first level key - feature name.
        #  * second level key - PCI address.
        #  * third level key - "package" or "instances".
        info: _ReadInfoType = {}
        for fname in fnames:
            info[fname] = {}

            fdict = tpmi.get_fdict(fname)

            if cmdl["regnames"]:
                regnames = cmdl["regnames"]
            else:
                # Read all registers except for the reserved ones.
                regnames = [regname for regname in fdict if not regname.startswith("RESERVED")]

            for addr, package, instance in tpmi.iter_feature(fname, addrs=cmdl["addrs"],
                                                             packages=cmdl["packages"],
                                                             instances=cmdl["instances"]):
                if addr not in info[fname]:
                    info[fname][addr] = {"package": package, "instances": {}}

                assert instance not in info[fname][addr]["instances"]
                info[fname][addr]["instances"][instance] = {}

                for regname in regnames:
                    regval = tpmi.read_register(fname, addr, instance, regname)

                    assert regname not in info[fname][addr]["instances"][instance]
                    bfinfo: dict[str, int] = {}
                    reginfo: _RegInfoTypedDict = {"value": regval, "fields": bfinfo}
                    info[fname][addr]["instances"][instance][regname] = reginfo

                    if cmdl["bfnames"]:
                        bfnames = cmdl["bfnames"]
                    else:
                        bfnames = list(fdict[regname]["fields"])

                    for bfname in bfnames:
                        if bfname.startswith("RESERVED"):
                            continue

                        bfval = tpmi.get_bitfield(regval, fname, regname, bfname)
                        bfinfo[bfname] = bfval

                    if not bfinfo:
                        # No bit fields information, probably all of them are reserved. Delete the
                        # entire "fields" key so that it does not show up in the output.
                        del reginfo["fields"]

        if not info:
            raise Error("BUG: No matches")

        if cmdl["yaml"]:
            YAML.dump(info, sys.stdout)
        else:
            _tpmi_read_command_print(tpmi, info)

def tpmi_write_command(args, pman):
    """
    Implement the 'tpmi write' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_write_cmdline_args(args)

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman)
        stack.enter_context(cpuinfo)

        tpmi = Tpmi.Tpmi(cpuinfo.info, pman=pman)
        stack.enter_context(tpmi)

        if cmdl["bfname"]:
            bfname_str = f", bit field '{cmdl['bfname']}'"
            val_str = f"{cmdl['value']}"
        else:
            bfname_str = ""
            val_str = f"{cmdl['value']:#x}"

        for addr, package, instance in tpmi.iter_feature(cmdl["fname"], addrs=cmdl["addrs"],
                                                         packages=cmdl["packages"],
                                                         instances=cmdl["instances"]):
            tpmi.write_register(cmdl["value"], cmdl["fname"], addr, instance, cmdl["regname"],
                                bfname=cmdl["bfname"])

            _LOG.info("Wrote '%s' to TPMI register '%s'%s (feature '%s', device '%s', package %d, "
                      "instance %d)",
                      val_str, cmdl["regname"], bfname_str, cmdl["fname"], addr, package, instance)
