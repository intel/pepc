#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Emulation data generator for collecting system data used to emulate.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import stat
import typing
from pathlib import Path

try:
    import argcomplete
    _ARGCOMPLETE_AVAILABLE = True
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    _ARGCOMPLETE_AVAILABLE = False

from pepclibs import ProcCpuinfo, CPUModels
from pepclibs.msr import EnergyPerfBias, FSBFreq, HWPRequest, HWPRequestPkg
from pepclibs.msr import PlatformInfo, PowerCtl, PCStateConfigCtl, PMEnable, TurboRatioLimit
from pepclibs.msr import TurboRatioLimit1, SwLTROvrd, PMLogicalId, HWPCapabilities
from pepclibs.helperlibs import Logging, ArgParse, ProcessManager, YAML, Trivial
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final, TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of this tool.

        Attributes:
            hostname: The hostname of the target system.
            username: The username to use for SSH connections.
            privkey: The private key file to use for SSH authentication.
            timeout: The timeout value for SSH connections.
        """

        hostname: str
        username: str
        privkey: str
        timeout: int | float
        outdir: Path

    class _TDCollectCommandTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining a command to run to collect a piece of emulation data.

        Attributes:
            command: The command to run.
            dirname: The sub-directory name to store the command output at.
            ignore_exitcode: Whether to ignore the command's exit code.
        """

        command: str
        dirname: str
        ignore_exitcode: bool

    class _TDCollectFileTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining a file to read to collect a piece of emulation data.

        Attributes:
            path: Path to the file to read.
            readonly: Indicates if the file is read-only.
        """

        path: Path
        readonly: bool

    class _TDCollectInlFilesTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining a command to run to collect the contents of multiple files
        and how to store the output.

        Attributes:
            command: The command to run to collect the contents of multiple files.
            separator: The separator used in the output emulation data file to separate the file
                       path and its contents.
            readonly: Indicates if the files to read are read-only.
            dirname: The sub-directory name to store the command output at.
            filename: The name of the file to store the command output at.
        """

        command: str
        separator: str
        readonly: bool
        dirname: str
        filename: str

    class _TDCollectInlDirsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining a command to run to collect directory paths.

        Attributes:
            command: The command to run to collect the directory paths.
            dirname: The sub-directory name to store the command output at.
            filename: The name of the file to store the command output at.
        """

        command: str
        dirname: str
        filename: str

    class _TDCollectMSRsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining MSR registers to read when collecting emulation data.

        Attributes:
            addresses: A list of MSR addresses to read.
            separator1: The separator used in the output emulation data file to separate the MSR
                        device path and the MSR address.
            separator2: The separator used in the output emulation data file to separate the MSR
                        address and its value.
            dirname: The sub-directory name to store the collected MSR values at.
            filename: The name of the file to store the collected MSR values at.
        """

        addresses: list[int]
        separator1: str
        separator2: str
        dirname: str
        filename: str

    class _TDCollectRCopyTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining a directory to copy recursively when collecting emulation
        data.

        Attributes:
            path: The path to the directory to copy.
        """

        path: Path

    class _TDCollectTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining all the emulation data to collect.

        Attributes:
            prepare_cmds: The commands to run before collecting any emulation data.
            commands: The commands to run to collect emulation data.
            files: The files to read to collect emulation data.
            recursive_copy: The directories to copy recursively to collect emulation data.
            inlinedirs: The commands to run to collect directory paths.
            inlinefiles: The commands to run to collect the contents of multiple files.
            msrs: The MSR registers to read to collect emulation data.
        """

        prepare_cmds: list[str]
        commands: list[_TDCollectCommandTypedDict]
        files: list[_TDCollectFileTypedDict]
        recursive_copy: list[_TDCollectRCopyTypedDict]
        inlinedirs: list[_TDCollectInlDirsTypedDict]
        inlinefiles: list[_TDCollectInlFilesTypedDict]
        msrs: _TDCollectMSRsTypedDict

_TOOLNAME: Final[str] = "emulation-data-generator"
_VERSION: Final[str] = "0.1"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

_CPUInfoTDCollectInfo: _TDCollectTypedDict = {
    "commands" : [
        {"command": "lscpu", "dirname": "lscpu"},
        {"command": "uname -a", "dirname": "uname"},],
    "files" : [
        {"path": Path("/proc/cpuinfo"),
         "readonly": True}],
    "inlinefiles" : [
        # Command for reading die info.
        {"command": r"grep -H '.*' "
                    r"/sys/devices/system/cpu/cpu[0-9]*/topology/die_id "
                    r"/sys/devices/system/cpu/cpu[0-9]*/topology/die_cpus_list",
         "separator": ":",
         "readonly": True,
         "dirname": "die-info",
         "filename": "die.txt"},
        # Command for reading module info.
        {"command": r"grep -H '.*' "
                    r"/sys/devices/system/cpu/cpu[0-9]*/cache/index[0-9]/id "
                    r"/sys/devices/system/cpu/cpu[0-9]*/cache/index[0-9]/shared_cpu_list",
         "separator": ":",
         "readonly": True,
         "dirname": "module-info",
         "filename": "module.txt"},
        # Command for reading online CPUs and all CPUs.
        {"command": r"grep -H '.*' "
                    r"/sys/devices/system/cpu/online "
                    r"/sys/devices/system/cpu/present",
         "separator": ":",
         "readonly": True,
         "dirname": "cpu-info",
         "filename": "cpu.txt"},
        # Command for reading node info.
        {"command": r"grep -H '.*' "
                    r"/sys/devices/system/node/online "
                    r"/sys/devices/system/node/node[0-9]/cpulist",
         "separator": ":",
         "readonly": True,
         "dirname": "node-info",
         "filename": "node.txt"},
        # Command for reading hybrid topology info.
        {"command": r"grep -H '.*' "
                    r"/sys/devices/cpu_atom/cpus "
                    r"/sys/devices/cpu_core/cpus "
                    r"/sys/devices/cpu_lowpower/cpus",
         "separator": ":",
         "readonly": True,
         "dirname": "hybrid-info",
         "filename": "hybrid.txt"}],
    "msrs" :
        {"addresses": [
            EnergyPerfBias.MSR_ENERGY_PERF_BIAS,
            FSBFreq.MSR_FSB_FREQ,
            HWPRequest.MSR_HWP_REQUEST,
            HWPRequestPkg.MSR_HWP_REQUEST_PKG,
            HWPCapabilities.MSR_HWP_CAPABILITIES,
            PlatformInfo.MSR_PLATFORM_INFO,
            PowerCtl.MSR_POWER_CTL,
            PCStateConfigCtl.MSR_PKG_CST_CONFIG_CONTROL,
            PMEnable.MSR_PM_ENABLE,
            TurboRatioLimit.MSR_TURBO_RATIO_LIMIT,
            TurboRatioLimit1.MSR_TURBO_RATIO_LIMIT1,
            TurboRatioLimit1.MSR_TURBO_GROUP_CORECNT,
            TurboRatioLimit1.MSR_TURBO_RATIO_LIMIT_CORES,
            SwLTROvrd.MSR_SW_LTR_OVRD,
            PMLogicalId.MSR_PM_LOGICAL_ID],
         "separator1": ":",
         "separator2": "|",
         "dirname": "msr",
         "filename": "msr.txt"}
}

_ASPMTDCollectInfo: _TDCollectTypedDict = {
    "inlinefiles" : [
        {"command": r"grep -H '.*' "
                    r"/sys/module/pcie_aspm/parameters/policy",
         "separator": ":",
         "readonly": False,
         "dirname": "aspm-info",
         "filename": "aspm.txt"}]
}

_CPUOnlineTDCollectInfo: _TDCollectTypedDict = {
    "inlinefiles" : [
        {"command": r"grep -H '.*' "
                    r"/sys/devices/system/cpu/cpu[0-9]*/online",
         "separator": ":",
         "readonly": False,
         "dirname": "cpuonline-info",
         "filename": "cpuonline.txt"}],
    "inlinedirs" : [
        {"command": r"find /sys/devices/system/cpu -type d -regextype posix-extended -regex "
                    r"'.*cpu([[:digit:]]+)'",
         "dirname": "cpuonline-info",
         "filename": "cpuonline-dirs.txt"}],
}

_CStatesTDCollectInfo: _TDCollectTypedDict = {
    "files" : [
        {"path": Path("/proc/cmdline"),
         "readonly": True}],
    "inlinefiles" : [
        {"command": r"grep -H --directories=skip '.*' "
                    r"/sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[0-9]/* "
                    r"/sys/devices/system/cpu/cpuidle/*",
         "separator": ":",
         "readonly": False,
         "dirname": "cstates",
         "filename": "cstates.txt"}]
}

PStatesTDCollectInfo: _TDCollectTypedDict = {
    "prepare_cmds" : [
        "modprobe intel_uncore_frequency",
        "modprobe msr",
        "pepc pstates config --min-freq min --max-freq max --cpus all",
        "pepc uncore config --min-freq min --max-freq max --cpus all",
        "pepc cstates config --enable all --cpus all"],
    "inlinefiles" : [
        {"command": r"grep -H --directories=recurse '.*' "
                    r"/sys/devices/system/cpu/cpufreq",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "pstates.txt"},
        {"command" : r"grep -H --directories=recurse '.*' "
                     r"/sys/devices/system/cpu/intel_pstate",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "intel_pstates.txt"},
        {"command" : r"grep -H --directories=recurse '.*' "
                     r"/sys/devices/system/cpu/intel_uncore_frequency/*/*",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "uncore.txt"},
        {"command" : r"grep -H '.*' "
                     r"/sys/devices/system/cpu/cpu[0-9]*/power/energy_perf_bias",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "epb.txt"},
        {"command" : r"grep -H '.*' "
                     r"/sys/devices/system/cpu/cpu[0-9]*/acpi_cppc/* --exclude '*_ctrs'",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "cppc.txt"},
        {"command" : r"grep -H '.*' "
                     r"/sys/devices/system/cpu/cpufreq/policy[0-9]*/energy_performance_preference",
         "separator": ":",
         "readonly": False,
         "dirname": "pstates",
         "filename": "epp.txt"},
        {"command" : r"grep -H '.*' "
                     r"/sys/devices/system/cpu/cpufreq/policy[0-9]*/"
                     r"energy_performance_available_preferences",
         "separator": ":",
         "readonly": True,
         "dirname": "pstates",
         "filename": "epp_policies.txt"},
        {"command" : r"grep -H '.*' "
                     r"/sys/devices/system/cpu/cpu[0-9]*/cpufreq/bios_limit",
         "separator": ":",
         "readonly": True,
         "dirname": "pstates",
         "filename": "bios_limit.txt"}]
}

_PMQoSTDCollectInfo: _TDCollectTypedDict = {
    "inlinefiles" : [
        {"command": r"grep -H --directories=skip '.*' "
                    r"/sys/devices/system/cpu/cpu[0-9]*/power/pm_qos_resume_latency_us",
         "separator": ":",
         "readonly": False,
         "dirname": "pmqos",
         "filename": "latency_limit.txt"}]
}

_SysctlTDCollectInfo: _TDCollectTypedDict = {
    "commands" : [
        {"command": "systemctl is-active -- 'tuned'",
         "dirname": "systemctl-tuned-active",
         "ignore_exitcode": True}],
}

_TPMITDCollectInfo: _TDCollectTypedDict = {
    "recursive_copy" : [
        {"path": Path("/sys/kernel/debug/tpmi-.*")}],
}

# TODO: Currently there is ne '_TDCollectTypedDict' per module, but this is not that helpful,
# because some modules share the same emulation data. Modules also change over time, so emulation
# data location may change.
_TDCollectInfo: dict[str, _TDCollectTypedDict] = {
    "CPUInfo" : _CPUInfoTDCollectInfo,
    "ASPM" : _ASPMTDCollectInfo,
    "CPUOnline" : _CPUOnlineTDCollectInfo,
    "CStates" : _CStatesTDCollectInfo,
    "PStates" : PStatesTDCollectInfo,
    "PMQoS" : _PMQoSTDCollectInfo,
    "Systemctl" : _SysctlTDCollectInfo,
    "TPMI" : _TPMITDCollectInfo,
}

def _build_arguments_parser() -> ArgParse.ArgsParser:
    """
    Build and return the command-line arguments parser.

    Returns:
        An initialized command-line arguments parser object.
    """

    text = f"{_TOOLNAME} - Emulation data generator, for collecting and creating emulation data."
    parser = ArgParse.ArgsParser(description=text, prog=_TOOLNAME, ver=_VERSION)
    ArgParse.add_ssh_options(parser)

    text = """Path to the directory to store the output of the commands at. Default value is the
              name of the host the command is run on. See the '-H' option."""
    parser.add_argument("-o", "--outdir", type=Path, help=text)

    if _ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)

    return parser

def _parse_arguments() -> argparse.Namespace:
    """
    Parse the command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """

    parser = _build_arguments_parser()
    args = parser.parse_args()

    return args

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    hostname: str = getattr(args, "hostname", "localhost")
    username: str = getattr(args, "username", "")
    privkey: str = getattr(args, "privkey", "")
    _timeout: str = getattr(args, "timeout", "")
    timeout: int | float = 8

    if hostname == "localhost":
        if username:
            raise Error("The '--username' option requires the '--host' option")
        if privkey:
            raise Error("The '--priv-key' option requires the '--host' option")
        if _timeout:
            raise Error("The '--timeout' option requires the '--host' option")
    else:
        if not username:
            username = "root"
        if _timeout:
            timeout = Trivial.str_to_num(_timeout, what="--timeout option value")

    cmdl: _CmdlineArgsTypedDict = {}
    cmdl["hostname"] = hostname
    cmdl["username"] = username
    cmdl["privkey"] = privkey
    cmdl["timeout"] = timeout

    outdir = getattr(args, "outdir")
    if outdir:
        cmdl["outdir"] = outdir
    else:
        cmdl["outdir"] = Path(hostname)

    return cmdl

def _collect_cmd_output(pman: ProcessManagerType,
                        cmdinfo: _TDCollectCommandTypedDict,
                        outdir: Path):
    """
    Run a command on the SUT and save its output in the specified output directory.

    Args:
        pman: The process manager object that defines the SUT to run the command on.
        cmdinfo: Dictionary containing command details.
        outdir: Path to the output directory.
    """

    datapath = outdir / cmdinfo["dirname"]

    try:
        os.makedirs(datapath, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{datapath}':\n{errmsg}") from err

    res = pman.run_join(cmdinfo["command"])
    if res["exitcode"] != 0 and not cmdinfo.get("ignore_exitcode"):
        _LOG.error("Command '%s' exited with code %d", cmdinfo["command"], res["exitcode"])

    for fname, data in ("stdout", res["stdout"]), ("stderr", res["stderr"]):
        if not data:
            # No output.
            continue

        path = datapath / f"{fname}.txt"
        with open(path, "w", encoding="utf-8") as fobj:
            fobj.write(data)

def _collect_inline(pman: ProcessManagerType, inlinfo, basedir):
    """
    Collect inline emulation data by running the collection command on the SUT. The command output
    is saved to a file in the specified output directory.

    Args:
        pman: The process manager object that defines the SUT to run the command on.
        inlinfo: Dictionary containing inline emulation data collection details.
        basedir: Path to the base output directory.
    """

    cmdpath = basedir / inlinfo["dirname"]

    try:
        os.makedirs(cmdpath, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{cmdpath}':\n{errmsg}") from err

    res = pman.run_join(inlinfo["command"])
    if res["exitcode"] != 0:
        _LOG.notice("Command '%s' exited with code %d", inlinfo["command"], res["exitcode"])

    path = cmdpath / inlinfo["filename"]

    try:
        with open(path, "w", encoding="utf-8") as fobj:
            fobj.write(res["stdout"])
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to perform I/O on file '{path}':\n{errmsg}") from err

def _collect_msrs(pman: ProcessManagerType, msrinfo: _TDCollectMSRsTypedDict, basedir: Path):
    """
    Collect MSR emulation data from the SUT

    Args:
        pman: The process manager object that defines the SUT to read the MSR values from.
        msrinfo: Dictionary containing MSR data collection details.
        basedir: Path to the base output directory.
    """

    proc_cpuinfo = ProcCpuinfo.get_proc_cpuinfo(pman)
    if proc_cpuinfo["vendor"] != CPUModels.VENDOR_INTEL:
        _LOG.notice("The SUT CPU vendor is '%s', not Intel, skipping MSR collection",
                    proc_cpuinfo["vendor_name"])
        return

    lines, _ = pman.run_verify_nojoin("lscpu -p=cpu --")

    cpus = []
    for line in lines:
        if line.startswith("#"):
            continue
        cpu = int(line.strip())
        cpus.append(cpu)

    outdir = basedir / msrinfo["dirname"]
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{outdir}':\n{errmsg}") from err

    path = outdir / msrinfo["filename"]

    try:
        with open(path, "w+", encoding="utf-8") as fobj:
            for cpu in cpus:
                line = f"/dev/cpu/{cpu}/msr{msrinfo['separator1']}"

                for addr in msrinfo["addresses"]:
                    res = pman.run_join(f"rdmsr {addr} -p {cpu}")
                    if res["exitcode"] != 0:
                        continue

                    value = res["stdout"].strip()
                    line += f"{addr}{msrinfo['separator2']}{value} "

                fobj.write(line + "\n")
    except Error as err:
        raise Error(f"Failed to perform I/O on file '{path}':\n{err.indent(2)}") from err

def _copy_file(pman: ProcessManagerType, src: Path, outdir: Path):
    """
    Copy a file from the SUT.

    Args:
        pman: The process manager object that defines the remote SUT to copy the file from.
        src: Path to the source file to copy.
        outdir: Path to the destination directory.
    """

    dst = Path(outdir / str(src).lstrip("/"))
    os.makedirs(dst.parent, exist_ok=True)

    # In some cases '/proc/cpuinfo' is not fully copied when using 'scp' or 'rsync'.
    res = pman.run_join(f"cat -- '{src}'")
    if res["exitcode"] != 0:
        _LOG.notice("'cat %s' exited with code %d", src, res["exitcode"])

    with open(dst, "w", encoding="utf-8") as fobj:
        fobj.write(res["stdout"])

def _copy_dir(pman: ProcessManagerType, src: Path, outdir: Path) -> list[_TDCollectFileTypedDict]:
    """
    Recursively copy the contents of a directory from the SUT.

    Args:
        pman: The process manager object that defines the remote SUT to copy the directory from.
        src: Path to the source directory. The last part of the path may be a regular expression to
             match directories.
        outdir: Path to the destination directory.

    Returns:
        A list of dictionaries, each containing metadata for a copied file, including its path and
        read-only status.
    """

    files: list[_TDCollectFileTypedDict] = []

    for entry in pman.lsdir(src.parent):
        if not re.fullmatch(src.name, entry["name"]):
            continue

        is_dir = stat.S_ISDIR(entry["mode"])
        is_readonly = not entry["mode"] & stat.S_IWUSR

        if is_dir:
            files += _copy_dir(pman, entry["path"] / ".*", outdir)
        else:
            _copy_file(pman, entry["path"], outdir)
            files += [{"path": entry["path"], "readonly": is_readonly}]

    return files

def _generate_config_file(modname: str, tdcoll_info: _TDCollectTypedDict, outdir: Path):
    """
    Generate the emulation data module YAML configuration file.

    Args:
        modname: The name of the module to generate the configuration file for.
        tdcoll_info: The emulation data collection information dictionary.
        outdir: The output directory to store the configuration file at.
    """

    with open(outdir / f"{modname}.yaml", "w", encoding="utf-8") as fobj:
        fobj.write(f"# This file was generated by the '{_TOOLNAME}' tool.\n")
        YAML.dump(tdcoll_info, fobj)

def __main():
    """
    The entry point of the tool.

    Returns:
        int: The program exit code.
    """

    args = _parse_arguments()
    cmdl = _get_cmdline_args(args)

    with ProcessManager.get_pman(cmdl["hostname"], username=cmdl["username"],
                                 privkeypath=cmdl["privkey"], timeout=cmdl["timeout"]) as pman:
        pman.run_verify("pepc cpu-hotplug online --cpus all")

        for modname, tdcinfo in _TDCollectInfo.items():
            datapath = cmdl["outdir"] / modname

            if "prepare_cmds" in tdcinfo:
                for command in tdcinfo["prepare_cmds"]:
                    pman.run(command)
                del tdcinfo["prepare_cmds"]

            if "commands" in tdcinfo:
                for cmdinfo in tdcinfo["commands"]:
                    _collect_cmd_output(pman, cmdinfo, datapath)
                    cmdinfo["dirname"] = f"{modname}/{cmdinfo['dirname']}"

            if "files" in tdcinfo:
                for file in tdcinfo["files"]:
                    _copy_file(pman, file["path"], datapath)

            if "recursive_copy" in tdcinfo:
                files = []
                for directory in tdcinfo["recursive_copy"]:
                    files += _copy_dir(pman, Path(directory["path"]), datapath)

                del tdcinfo["recursive_copy"]
                if files:
                    tdcinfo["files"] = files

            for section in ("inlinedirs", "inlinefiles"):
                if section not in tdcinfo:
                    continue

                for inlinfo in tdcinfo[section]:
                    _collect_inline(pman, inlinfo, datapath)
                    inlinfo["dirname"] = f"{modname}/{inlinfo['dirname']}"
                    del inlinfo["command"]

            if "msrs" in tdcinfo:
                _collect_msrs(pman, tdcinfo["msrs"], datapath)
                if tdcinfo["msrs"]:
                    tdcinfo["msrs"]["dirname"] = f"{modname}/{tdcinfo['msrs']['dirname']}"

            if tdcinfo:
                _generate_config_file(modname, tdcinfo, cmdl["outdir"])

    return 0

def main():
    """
    The entry point of the tool.

    Returns:
        int: The program exit code.
    """

    exitcode = -1
    try:
        return __main()
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
    except Error as err:
        _LOG.error_out(err)

    return exitcode
