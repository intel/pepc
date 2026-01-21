# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Tero Kristo <tero.kristo@linux.intel.com>

"""
Implement the 'pepc tpmi' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import typing

from pepclibs import TPMI, CPUInfo
from pepclibs.helperlibs import Logging, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict, Iterable, Generator
    from pepclibs.TPMI import RegDictTypedDict
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

    class _PkgInstancesTypedDict(TypedDict, total=False):
        """
        A typed dictionary used for collecting the 'pepc tpmi read' command results.

        Attributes:
            package: The package number.
            instances: A dictionary of instances, clusters, and registers of the cluster:
                       {instance: {cluster: {_RegInfoTypedDict}}}.
        """

        package: int
        instances: dict[int, dict[int, dict[str, _RegInfoTypedDict]]]

    # A type for the 'pepc tpmi read' command output dictionary.
    # {feature_name: {pci_address: _PkgInstancesTypedDict}}.
    _ReadInfoType = dict[str, dict[str, _PkgInstancesTypedDict]]

    class _LsCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi ls' command.

        Attributes:
            topology: Whether to output TPMI topology information.
            fnames: List of TPMI feature names to display.
            unknown: Include unknown TPMI features (without spec files) in the output.
        """

        topology: bool
        fnames: list[str]
        unknown: bool

    class _ReadCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi read' command.

        Attributes:
            fnames: List of TPMI feature names to read.
            addrs: List of TPMI device PCI addresses to read from.
            packages: List of package numbers to operate on.
            instances: List of TPMI instance numbers to read from.
            clusters: List of TPMI cluster numbers to read from.
            regnames: List of register names to read.
            bfnames: List of bit field names to read.
            no_bitfields: Whether to skip decoding and displaying bit field values.
            yaml: Whether to output results in YAML format.
        """

        fnames: list[str]
        addrs: list[str]
        packages: list[int]
        instances: list[int]
        clusters: list[int]
        regnames: list[str]
        bfnames: list[str]
        no_bitfields: bool
        yaml: bool

    class _WriteCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi write' command.

        Attributes:
            fname: TPMI feature name to write.
            addrs: List of TPMI device PCI addresses to write to.
            packages: List of package numbers to operate on.
            instances: List of TPMI instance numbers to write to.
            clusters: List of TPMI cluster numbers to write to.
            regname: Name of the register to write to.
            bfname: Name of the bit field to write to (if any).
            value: Value to write.
        """

        fname: str
        addrs: list[str]
        packages: list[int]
        instances: list[int]
        clusters: list[int]
        regname: str
        bfname: str
        value: int

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_ls_cmdline_args(args: argparse.Namespace) -> _LsCmdlineArgsTypedDict:
    """
    Parse and format 'pepc tpmi ls' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _LsCmdlineArgsTypedDict = {}

    if args.fnames:
        fnames = Trivial.split_csv_line(args.fnames, dedup=True)
    else:
        fnames = []

    cmdl["topology"] = args.topology
    cmdl["fnames"] = fnames
    cmdl["unknown"] = args.unknown
    return cmdl

def _get_read_cmdline_args(args: argparse.Namespace) -> _ReadCmdlineArgsTypedDict:
    """
    Parse and format 'pepc tpmi read' command-line arguments into a typed dictionary.

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

    if args.clusters:
        clusters = Trivial.split_csv_line_int(args.clusters, dedup=True,
                                               what="TPMI cluster numbers")
    else:
        clusters = []

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
    cmdl["clusters"] = clusters
    cmdl["regnames"] = regnames
    cmdl["bfnames"] = bfnames
    cmdl["no_bitfields"] = args.no_bitfields
    cmdl["yaml"] = args.yaml

    return cmdl

def _get_write_cmdline_args(args: argparse.Namespace) -> _WriteCmdlineArgsTypedDict:
    """
    Parse and format 'pepc tpmi write' command-line arguments into a typed dictionary.

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

    if args.clusters:
        clusters = Trivial.split_csv_line_int(args.clusters, dedup=True,
                                               what="TPMI cluster numbers")
    else:
        clusters = []

    value = Trivial.str_to_int(args.value, what="value to write")

    cmdl: _WriteCmdlineArgsTypedDict = {}
    cmdl["fname"] = args.fname
    cmdl["addrs"] = addrs
    cmdl["packages"] = packages
    cmdl["instances"] = instances
    cmdl["clusters"] = clusters
    cmdl["regname"] = args.regname
    cmdl["bfname"] = args.bfname
    cmdl["value"] = value

    return cmdl

def _pfx_bullet(level: int) -> str:
    """
    Return a prefix string with a bullet for the given indentation level.

    Args:
        level: Indentation level.

    Returns:
        A prefix string with a bullet.
    """

    return "  " * level + "- "

def _pfx_blanks(level: int) -> str:
    """
    Return a prefix string with blanks for the given indentation level.

    Args:
        level: Indentation level.

    Returns:
        A prefix string with blanks.
    """

    return "  " * level + "  "

def _ls_topology(fname: str, tpmi: TPMI.TPMI, level: int = 0):
    """
    Display TPMI topology for a feature.

    Args:
        fname: Name of the feature to display topology for.
        tpmi: A 'TPMI.TPMI' object.
        level: The starting indentation level for formatting log output.
    """

    # Dictionary with the info to print: {package: {addr: {instances}}}.
    info: dict[int, dict[str, set[int]]] = {}

    for package, addr, instance in tpmi.iter_feature(fname):
        if package not in info:
            info[package] = {}
        if addr not in info[package]:
            info[package][addr] = set()
        info[package][addr].add(instance)

    for package in sorted(info):
        for addr in sorted(info[package]):
            _LOG.info("%sPCI address: %s", _pfx_bullet(level), addr)

            _LOG.info("%sPackage: %d", _pfx_blanks(level), package)

            if fname != "ufs":
                instances = Trivial.rangify(info[package][addr])
                _LOG.info("%sInstances: %s", _pfx_blanks(level), instances)
                continue

            for instance in sorted(info[package][addr]):
                _LOG.info("%sInstance: %d", _pfx_bullet(level + 1), instance)
                for _, _, _, cluster in tpmi.iter_ufs_feature(packages=(package,), addrs=(addr,),
                                                              instances=(instance,)):
                    _LOG.info("%sCluster: %d", _pfx_bullet(level + 2), cluster)

def tpmi_ls_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'tpmi ls' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_ls_cmdline_args(args)

    if cmdl["unknown"] and cmdl["topology"]:
        raise Error("'--unknown' and '--topology' options cannot be used together")

    with CPUInfo.CPUInfo(pman) as cpuinfo:
        tpmi = cpuinfo.get_tpmi()

        sdicts = tpmi.get_known_features()
        if not sdicts:
            _LOG.info("No supported TPMI features found")
        else:
            _LOG.info("Supported TPMI features")

            fnames = cmdl["fnames"] or sdicts

            for fname in fnames:
                if fname not in sdicts:
                    raise Error(f"TPMI feature '{fname}' does not exist")

                sdict = sdicts[fname]
                _LOG.info("- %s: %s", sdict["name"], sdict["desc"].strip())
                if cmdl["topology"]:
                    _ls_topology(sdict["name"], tpmi, level=1)

        if cmdl["unknown"]:
            _LOG.info("Unknown TPMI features (available%s, but no spec file found)",
                      pman.hostmsg)
            fids = tpmi.get_unknown_features()
            txt = ", ".join(hex(fid) for fid in fids)
            _LOG.info(" - %s", txt)

def _print_registers(reginfos: dict[str, _RegInfoTypedDict],
                     fdict: dict[str, RegDictTypedDict],
                     level: int):
    """
    Print TPMI register information.

    Args:
        reginfos: A dictionary where keys are register names and values are register information
                  dictionaries.
        fdict: The TPMI feature dictionary.
        level: The starting indentation level for formatting log output.
    """

    for regname, reginfo in reginfos.items():
        if "fields" not in reginfo:
            _LOG.info("%s%s: %#x", _pfx_blanks(level), regname, reginfo["value"])
            continue

        _LOG.info("%s%s: %#x", _pfx_bullet(level), regname, reginfo["value"])

        for bfname, bfval in reginfo["fields"].items():
            bfinfo = fdict[regname]["fields"][bfname]
            _LOG.info("%s%s[%d:%d]: %d", _pfx_blanks(level + 1), bfname,
                    bfinfo["bits"][0], bfinfo["bits"][1], bfval)

def _print_tpmi_info(tpmi: TPMI.TPMI, info: _ReadInfoType):
    """
    Print the result of the 'tpmi read' command.

    Iterate through the features, PCI addresses, instances, clusters, registers, and bit fields in
    the 'info' dictionary and print each element in a structured and indented format.

    Args:
        tpmi: A 'TPMI.TPMI' object.
        info: A dictionary containing features, PCI addresses, instances, clusters, registers, and
              bit fields.
    """

    for fname, feature_info in info.items():
        _LOG.info("%sTPMI feature: %s", _pfx_bullet(0), fname)

        fdict = tpmi.get_fdict(fname)
        for addr, addr_info in feature_info.items():
            _LOG.info("%sPCI address: %s", _pfx_bullet(1), addr)
            _LOG.info("%sPackage: %d", _pfx_blanks(1), addr_info["package"])

            for instance, instance_info in addr_info["instances"].items():
                _LOG.info("%sInstance: %d", _pfx_bullet(1), instance)

                if fname != "ufs":
                    _print_registers(instance_info[0], fdict, 2)
                    continue

                for cluster, cluster_info in instance_info.items():
                    _LOG.info("%sCluster: %d", _pfx_bullet(2), cluster)
                    _print_registers(cluster_info, fdict, 3)

def tpmi_read_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'tpmi read' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_read_cmdline_args(args)

    with CPUInfo.CPUInfo(pman) as cpuinfo:
        tpmi = cpuinfo.get_tpmi()

        sdicts = tpmi.get_known_features()

        fnames = cmdl["fnames"] or sdicts

        # Prepare all the information to print in the 'info' dictionary.
        # {fname: {addr: _PkgInstancesTypedDict}}.
        info: _ReadInfoType = {}
        for fname in fnames:
            info[fname] = {}

            fdict = tpmi.get_fdict(fname)

            regnames = cmdl["regnames"] or fdict
            iterator = tpmi.iter_feature_cluster(fname, packages=cmdl["packages"],
                                                 addrs=cmdl["addrs"], instances=cmdl["instances"],
                                                 clusters=cmdl["clusters"])
            for package, addr, instance, cluster in iterator:
                if addr not in info[fname]:
                    info[fname][addr] = {"package": package, "instances": {}}

                if instance not in info[fname][addr]["instances"]:
                    info[fname][addr]["instances"][instance] = {}

                instance_info = info[fname][addr]["instances"][instance]

                for regname in regnames:
                    if cluster != 0 and regname in TPMI.UFS_HEADER_REGNAMES:
                        # Header registers are per-instance, not per-cluster. Represent them as
                        # cluster 0 only for consistent and easy-to-read output.
                        _cluster = 0

                        if _cluster in instance_info and regname in instance_info[_cluster]:
                            # Header register already read for this instance.
                            continue
                    else:
                        _cluster = cluster

                    instance_info.setdefault(_cluster, {})

                    regval = tpmi.read_register_cluster(fname, addr, instance, _cluster, regname)

                    bfinfo: dict[str, int] = {}
                    reginfo: _RegInfoTypedDict = {"value": regval}
                    instance_info[_cluster][regname] = reginfo

                    if cmdl["no_bitfields"]:
                        continue

                    reginfo["fields"] = bfinfo

                    if cmdl["bfnames"]:
                        bfnames = cmdl["bfnames"]
                    else:
                        bfnames = list(fdict[regname]["fields"])

                    for bfname in bfnames:
                        bfval = tpmi.get_bitfield(regval, fname, regname, bfname)
                        bfinfo[bfname] = bfval

        if not info:
            raise Error("BUG: No matches")

        if cmdl["yaml"]:
            YAML.dump(info, sys.stdout, int_format="%#x")
        else:
            _print_tpmi_info(tpmi, info)

def tpmi_write_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'tpmi write' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_write_cmdline_args(args)

    with CPUInfo.CPUInfo(pman) as cpuinfo:
        tpmi = cpuinfo.get_tpmi()

        if cmdl["bfname"]:
            bfname_str = f", bit field '{cmdl['bfname']}'"
            val_str = f"{cmdl['value']}"
        else:
            bfname_str = ""
            val_str = f"{cmdl['value']:#x}"

        fname = cmdl["fname"]
        iterator = tpmi.iter_feature_cluster(fname, packages=cmdl["packages"], addrs=cmdl["addrs"],
                                             instances=cmdl["instances"], clusters=cmdl["clusters"])

        for package, addr, instance, cluster in iterator:
            tpmi.write_register_cluster(cmdl["value"], fname, addr, instance, cluster,
                                        cmdl["regname"], bfname=cmdl["bfname"])

            where = f"feature '{fname}', device '{addr}', package {package}, instance {instance}"
            if fname == "ufs" or cmdl["clusters"]:
                where += f", cluster {cluster}"
            _LOG.info("Wrote '%s' to TPMI register '%s'%s (%s)",
                      val_str, cmdl["regname"], bfname_str, where)
