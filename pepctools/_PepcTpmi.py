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
from pathlib import Path

from pepclibs import TPMI, CPUInfo
from pepclibs.helperlibs import Logging, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict
    from pepclibs.TPMI import RegDictTypedDict, SDictTypedDict, SDDTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _LsInfoFeatureTypedDict(TypedDict, total=False):
        """
        A TPMI feature information typed dictionary used for collecting 'pepc tpmi ls' command
        results.

        Attributes:
            name: The feature name.
            desc: The feature description.
            feature_id: The feature ID.
        """

        name: str
        desc: str
        feature_id: int

    class _LsInfoFlatTypedDict(TypedDict, total=False):
        """
        A typed dictionary for the information collected for the 'pepc tpmi ls' command (no
        '--topology' option).

        Attributes:
            supported: Supported TPMI features information (keys are feature names).
            unknown: List of unknown TPMI feature IDs.
        """

        supported: dict[str, _LsInfoFeatureTypedDict]
        unknown: list[int]

    class _LsInfoTopologyAddrTypedDict(TypedDict, total=False):
        """
        A typed dictionary for TPMI topology address information used in the 'pepc tpmi ls' command
        with '--topology' option.

        Attributes:
            package: The package number.
            instances: Instances information: {instance: [clusters]}.
        """

        package: int
        instances: dict[int, list[int]]

    class _LsInfoTopologyTypedDict(TypedDict, total=False):
        """
        A typed dictionary for the information collected for the 'pepc tpmi ls' command with
        '--topology' option.

        Attributes:
            supported: Supported TPMI features information (keys are feature names).
            topology: TPMI topology information: {fname: {addr: _LsInfoTopologyAddrTypedDict}}.
        """

        supported: dict[str, _LsInfoFeatureTypedDict]
        topology: dict[str, dict[str, _LsInfoTopologyAddrTypedDict]]

    class _ReadInfoRegTypedDict(TypedDict, total=False):
        """
        A TPMI register information typed dictionary used for collecting the 'pepc tpmi read'
        command results.

        Attributes:
            value: The register value.
            fields: A dictionary of bit field names and their values.
        """

        value: int
        fields: dict[str, int]

    class _ReadInfoInstancesTypedDict(TypedDict, total=False):
        """
        An instance information typed dictionary used for collecting the 'pepc tpmi read' command
        results.

        Attributes:
            package: The package number.
            instances: A dictionary of instances, clusters, and registers of the cluster:
                       {instance: {cluster: {_ReadInfoRegTypedDict}}}.
        """

        package: int
        instances: dict[int, dict[int, dict[str, _ReadInfoRegTypedDict]]]

    # A type for the 'pepc tpmi read' command output dictionary.
    # {feature_name: {pci_address: _ReadInfoInstancesTypedDict}}.
    _ReadInfoType = dict[str, dict[str, _ReadInfoInstancesTypedDict]]

    class _LsCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc tpmi ls' command.

        Attributes:
            list_specs: If 'True', list available TPMI spec files and exit.
            topology: Whether to output TPMI topology information.
            fnames: List of TPMI feature names to display.
            unknown: Include unknown TPMI features (without spec files) in the output.
            yaml: Whether to output results in YAML format.
        """

        list_specs: bool
        topology: bool
        fnames: list[str]
        unknown: bool
        yaml: bool

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

    cmdl["list_specs"] = args.list_specs
    cmdl["topology"] = args.topology
    cmdl["fnames"] = fnames
    cmdl["unknown"] = args.unknown
    cmdl["yaml"] = args.yaml

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
        raise Error("'--bitfields' requires '--registers' to be specified")

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
    cmdl["bfname"] = getattr(args, "bfname", "")
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

def _list_specs(sdicts: dict[str, SDictTypedDict],
                sdds: dict[Path, SDDTypedDict],
                yaml: bool):
    """
    List available TPMI spec files.

    Args:
        sdicts: A dictionary of TPMI spec dictionaries.
        sdds: A dictionary of scanned spec directory dictionaries.
        yaml: Whether to output in YAML format.
    """

    # For better readability sort spec files by feature ID.
    sdicts = dict(sorted(sdicts.items(), key=lambda item: item[1]["feature_id"]))

    if yaml:
        info = {"sdds": sdds, "specs": sdicts}
        YAML.dump(info, sys.stdout)
        return

    _LOG.info("TPMI spec directories information:")
    for specdir, sdd in sdds.items():
        vfm = sdd["vfm"]
        idxdict = sdd["idxdict"]

        _LOG.info("- %s", specdir)
        _LOG.info("  Format version: %s", idxdict["version"])
        _LOG.info("  VFM: %s", vfm)
        _LOG.info("  Platform Name: %s", idxdict["vfms"][vfm]["platform_name"])
        _LOG.info("  Spec Sub-directory Path: %s", specdir / idxdict["vfms"][vfm]["subdir"])

    _LOG.info("TPMI spec files:")
    for fname in sdicts:
        sdict = sdicts[fname]
        _LOG.info("- %s (%d): %s", sdict["name"], sdict["feature_id"], sdict["desc"])
        _LOG.info("  Spec file: %s", sdict["path"])

def _get_ls_supported(cmdl: _LsCmdlineArgsTypedDict,
                      sdicts: dict[str, SDictTypedDict]) -> dict[str, _LsInfoFeatureTypedDict]:
    """
    Get supported TPMI features information for the 'pepc tpmi ls' command.

    Args:
        cmdl: Parsed command-line arguments.
        sdicts: A dictionary of TPMI spec dictionaries.

    Returns:
        A dictionary where keys are TPMI feature names and values are feature information
        dictionaries.
    """
    info: dict[str, _LsInfoFeatureTypedDict] = {}

    fnames = cmdl["fnames"] or sdicts

    for fname in fnames:
        if fname not in sdicts:
            raise Error(f"No spec file for TPMI feature '{fname}' found")

        sdict = sdicts[fname]
        info[fname] = {
            "name": sdict["name"],
            "desc": sdict["desc"],
            "feature_id": sdict["feature_id"],
        }

    # Sort supported features by feature ID for better readability.
    return dict(sorted(info.items(), key=lambda item: item[1]["feature_id"]))

def _tpmi_ls_flat(cmdl: _LsCmdlineArgsTypedDict, tpmi: TPMI.TPMI):
    """
    Implement the flat output for the 'tpmi ls' command (no '--topology').

    Args:
        cmdl: Parsed command-line arguments.
        tpmi: A 'TPMI.TPMI' object.
    """

    info: _LsInfoFlatTypedDict = {"supported": {}}

    sdicts = tpmi.get_known_features()
    if sdicts:
        info["supported"] = _get_ls_supported(cmdl, sdicts)

    if cmdl["unknown"]:
        info["unknown"] = tpmi.get_unknown_features()

    if cmdl["yaml"]:
        YAML.dump(info, sys.stdout)
        return

    if not info["supported"]:
        _LOG.info("No supported TPMI features found")
    else:
        _LOG.info("Supported TPMI features")

        for fname, finfo in info["supported"].items():
            _LOG.info("- %s (%s): %s", fname, finfo["feature_id"], finfo["desc"])

    if info.get("unknown"):
        _LOG.info("TPMI features supported by the target platform, but no spec files found")
        _LOG.info(" - %s", ", ".join(hex(fid) for fid in info["unknown"]))

def _get_ls_topology(tpmi: TPMI.TPMI, fname: str) -> dict[str, _LsInfoTopologyAddrTypedDict]:
    """
    Get TPMI topology information for a feature.

    Args:
        tpmi: A 'TPMI.TPMI' object.
        fname: Name of the feature to get topology for.

    Returns:
        A dictionary containing TPMI topology information for the feature.
    """

    info: dict[str, _LsInfoTopologyAddrTypedDict] = {}

    for package, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
        info.setdefault(addr, {"package": package, "instances": {}})
        info[addr]["instances"].setdefault(instance, []).append(cluster)

    return info

def _tpmi_ls_topology(cmdl: _LsCmdlineArgsTypedDict, tpmi: TPMI.TPMI):
    """
    Implement the topology output for the 'tpmi ls' command ('--topology').

    Args:
        cmdl: Parsed command-line arguments.
        tpmi: A 'TPMI.TPMI' object.
    """

    supported_info: dict[str, _LsInfoFeatureTypedDict] = {}
    topology: dict[str, dict[str, _LsInfoTopologyAddrTypedDict]] = {}
    info: _LsInfoTopologyTypedDict = {"supported": supported_info, "topology": topology}

    sdicts = tpmi.get_known_features()
    if not sdicts:
        _LOG.info("No supported TPMI features found")
        return

    info["supported"] = _get_ls_supported(cmdl, sdicts)

    for fname in info["supported"]:
        topology[fname] = _get_ls_topology(tpmi, fname)

    if cmdl["yaml"]:
        YAML.dump(info, sys.stdout)
        return

    _LOG.info("Supported TPMI features")

    for fname, finfo in info["supported"].items():
        _LOG.info("- %s (%d): %s", fname, finfo["feature_id"], finfo["desc"].strip())

        for addr, addr_info in topology[fname].items():
            _LOG.info("%sPCI address: %s", _pfx_bullet(1), addr)
            package = addr_info["package"]
            _LOG.info("%sPackage: %d", _pfx_blanks(1), package)

            if fname != "ufs":
                instances = Trivial.rangify(addr_info["instances"])
                _LOG.info("%sInstances: %s", _pfx_blanks(1), instances)
                continue

            for instance in addr_info["instances"]:
                _LOG.info("%sInstance: %d", _pfx_bullet(2), instance)
                for cluster in addr_info["instances"][instance]:
                    _LOG.info("%sCluster: %d", _pfx_bullet(3), cluster)

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

        if cmdl["list_specs"]:
            _list_specs(tpmi.sdicts, tpmi.sdds, cmdl["yaml"])
            return

        if cmdl["topology"]:
            _tpmi_ls_topology(cmdl, tpmi)
            return

        _tpmi_ls_flat(cmdl, tpmi)

def _print_registers(reginfos: dict[str, _ReadInfoRegTypedDict],
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
                    reginfo: _ReadInfoRegTypedDict = {"value": regval}
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
