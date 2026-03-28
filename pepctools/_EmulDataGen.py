#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Emulation data generator for collecting system data used to emulate.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import os
import stat
import types
import typing
import inspect
import pkgutil
import importlib
from pathlib import Path

try:
    argcomplete: types.ModuleType | None
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs import CPUModels, CPUInfo, CPUOnline, CStates, PStates, Uncore
import pepclibs.msr as _msr_pkg
from pepclibs.msr import _FeaturedMSR, MSR
from pepclibs.helperlibs import Logging, ArgParse, ProcessManager, YAML, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final, TypedDict, Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepctools._EmulDataConfigTypes import _EmulDataConfigMSRTypedDict
    from pepctools._EmulDataConfigTypes import _EmulDataConfigSysfsTypedDict

    class _SysfsInlineCmdTypedDict(TypedDict):
        """
        A typed dictionary describing a single sysfs inline data collection command.

        Attributes:
            command: The grep command used to read sysfs file contents.
            readonly: Whether the collected sysfs files are read-only.
        """

        command: str
        readonly: bool

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

    class _TDCollectTypedDict(TypedDict, total=False):
        """
        A typed dictionary for defining all the emulation data to collect.

        Attributes:
            commands: The commands to run to collect emulation data.
            files: The files to read to collect emulation data.
            inlinefiles: The commands to run to collect the contents of multiple files.
            msrs: The MSR registers to read to collect emulation data.
        """

        commands: list[_TDCollectCommandTypedDict]
        files: list[_TDCollectFileTypedDict]
        inlinefiles: list[_TDCollectInlFilesTypedDict]

_TOOLNAME: Final[str] = "emulation-data-generator"
_VERSION: Final[str] = "0.1"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

_CPUInfoTDCollectInfo: _TDCollectTypedDict = {
    "commands" : [
        {"command": "uname -a", "dirname": "uname"},],
    "files" : [
        {"path": Path("/proc/cpuinfo"),
         "readonly": True}],
}

_CStatesTDCollectInfo: _TDCollectTypedDict = {
    "files" : [
        {"path": Path("/proc/cmdline"),
         "readonly": True}],
}

_SysctlTDCollectInfo: _TDCollectTypedDict = {
    "commands" : [
        {"command": "systemctl is-active -- 'tuned'",
         "dirname": "systemctl-tuned-active",
         "ignore_exitcode": True}],
}

_TDCollectInfo: dict[str, _TDCollectTypedDict] = {
    "CPUInfo" : _CPUInfoTDCollectInfo,
    "CStates" : _CStatesTDCollectInfo,
    "Systemctl" : _SysctlTDCollectInfo,
}

# The sysfs data sub-directory name in the emulation data directory.
_SYSFS_SUBDIR: Final[str] = "sys"
# The sysfs inline data file name in the emulation data directory.
_SYSFS_DATA_FILE: Final[str] = "inlinefiles.txt"
# Base directory for TPMI sysfs files.
_SYSFS_TPMI_BASEDIR: Final[Path] = Path("/sys/kernel/debug")

# Each entry describes a set of sysfs files to collect, grouped by read-only status.
# 'command' is passed directly to the process manager (grep with sysfs glob patterns).
_SYSFS_INLINE_CMDS: list[_SysfsInlineCmdTypedDict] = [
    # CPU topology.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/topology/die_id "
                r"/sys/devices/system/cpu/cpu[0-9]*/topology/die_cpus_list",
     "readonly": True},
    # CPU cache info.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/cache/index[0-9]/id "
                r"/sys/devices/system/cpu/cpu[0-9]*/cache/index[0-9]/shared_cpu_list",
     "readonly": True},
    # Online CPUs and all present CPUs.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/online "
                r"/sys/devices/system/cpu/present",
     "readonly": True},
    # NUMA node info.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/node/online "
                r"/sys/devices/system/node/node[0-9]/cpulist",
     "readonly": True},
    # Hybrid CPU topology (Atom, Core, Lowpower clusters).
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/cpu_atom/cpus "
                r"/sys/devices/cpu_core/cpus "
                r"/sys/devices/cpu_lowpower/cpus",
     "readonly": True},
    # ASPM policy.
    {"command": r"grep -Z -H '.*' "
                r"/sys/module/pcie_aspm/parameters/policy",
     "readonly": False},
    # Per-CPU online state.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/online",
     "readonly": False},
    # C-state sysfs files.
    {"command": r"grep -Z -H --directories=skip '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[0-9]/* "
                r"/sys/devices/system/cpu/cpuidle/*",
     "readonly": False},
    # P-states: cpufreq (all files under the directory tree).
    {"command": r"grep -Z -H --directories=recurse '.*' "
                r"/sys/devices/system/cpu/cpufreq",
     "readonly": False},
    # P-states: Intel P-state driver.
    {"command": r"grep -Z -H --directories=recurse '.*' "
                r"/sys/devices/system/cpu/intel_pstate",
     "readonly": False},
    # P-states: Intel uncore frequency.
    {"command": r"grep -Z -H --directories=recurse '.*' "
                r"/sys/devices/system/cpu/intel_uncore_frequency/*/*",
     "readonly": False},
    # P-states: energy performance bias.
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/power/energy_perf_bias",
     "readonly": False},
    # P-states: ACPI CPPC (excluding counter files).
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/acpi_cppc/* --exclude '*_ctrs'",
     "readonly": False},
    # P-states: energy performance preference (EPP).
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpufreq/policy[0-9]*/energy_performance_preference",
     "readonly": False},
    # P-states: available EPP policies (read-only).
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpufreq/policy[0-9]*/"
                r"energy_performance_available_preferences",
     "readonly": True},
    # P-states: BIOS frequency limit (read-only).
    {"command": r"grep -Z -H '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/cpufreq/bios_limit",
     "readonly": True},
    # PM QoS resume latency limit.
    {"command": r"grep -Z -H --directories=skip '.*' "
                r"/sys/devices/system/cpu/cpu[0-9]*/power/pm_qos_resume_latency_us",
     "readonly": False},
]

# MSR data are stored in a text file, one line per MSR address, in the
# "<hex_addr>:<cpu_num>|<hex_val> ...", for example:
# 1a0:0|45 1|45 2|45 3|45 ...
# The MSR data sub-directory name in the emulation data directory.
_MSR_SUBDIR: Final[str] = "msr"
# The MSR data file name in the emulation data directory.
_MSR_DATA_FILE: Final[str] = "msr.txt"

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

    if argcomplete is not None:
        getattr(argcomplete, "autocomplete")(parser)

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
    if res.exitcode != 0 and not cmdinfo.get("ignore_exitcode"):
        _LOG.error("Command '%s' exited with code %d", cmdinfo["command"], res.exitcode)

    for fname, data in ("stdout", res.stdout), ("stderr", res.stderr):
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
    if res.exitcode != 0:
        _LOG.notice("Command '%s' exited with code %d", inlinfo["command"], res.exitcode)

    path = cmdpath / inlinfo["filename"]

    try:
        with open(path, "w", encoding="utf-8") as fobj:
            fobj.write(res.stdout)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to perform I/O on file '{path}':\n{errmsg}") from err

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
    if res.exitcode != 0:
        _LOG.notice("'cat %s' exited with code %d", src, res.exitcode)

    with open(dst, "w", encoding="utf-8") as fobj:
        fobj.write(res.stdout)

def _generate_config_file(modname: str, tdcoll_info: dict, outdir: Path):
    """
    Generate the emulation data YAML configuration file.

    Args:
        modname: The base name of the configuration file (without extension).
        tdcoll_info: The emulation data collection information dictionary.
        outdir: The output directory to store the configuration file at.
    """

    with open(outdir / f"{modname}.yml", "w", encoding="utf-8") as fobj:
        fobj.write(f"# This file was generated by the '{_TOOLNAME}' tool.\n")
        YAML.dump(tdcoll_info, fobj)

def _discover_msr_classes() -> Generator[type[_FeaturedMSR.FeaturedMSR], None, None]:
    """
    Yield all 'FeaturedMSR' subclasses found in the 'pepclibs.msr' package, one per module, in
    module iteration order.

    Yields:
        'FeaturedMSR' subclasses, one per MSR module.
    """

    yiedled: set[type[_FeaturedMSR.FeaturedMSR]] = set()

    for _, modname, ispkg in pkgutil.iter_modules(_msr_pkg.__path__):
        if modname.startswith("_") or ispkg:
            continue
        module = importlib.import_module(f"pepclibs.msr.{modname}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, _FeaturedMSR.FeaturedMSR):
                continue
            if obj is _FeaturedMSR.FeaturedMSR:
                continue
            if obj in yiedled:
                continue
            yiedled.add(obj)
            yield obj
            break

def _get_msr_data(cpuinfo: CPUInfo.CPUInfo,
                  pman: ProcessManagerType,
                  cpus: list[int]) -> Generator[tuple[int, dict[int, str]], None, None]:
    """
    Collect MSR data from the SUT for all 'FeaturedMSR' subclasses found in the 'pepclibs.msr'
    package.

    Args:
        cpuinfo: CPU information object for the SUT.
        pman: The process manager object that defines the SUT to read the MSR values from.
        cpus: List of CPU numbers to read MSR values for.

    Yields:
        Tuples of '(addr, vals)', where 'addr' is the MSR address and 'vals' is a
        '{cpu: hex_val}' dictionary for that address.
    """

    seen_addrs: set[int] = set()

    with MSR.MSR(cpuinfo, pman=pman) as msr:
        for cls in _discover_msr_classes():
            try:
                with cls(cpuinfo=cpuinfo, pman=pman, msr=msr) as fmsr:
                    addr = fmsr.regaddr
            except ErrorNotSupported:
                continue

            if addr in seen_addrs:
                raise Error(f"BUG: MSR address {addr:#x} is covered by multiple classes")

            seen_addrs.add(addr)

            vals: dict[int, str] = {}
            for cpu, regval in msr.read(addr, cpus):
                vals[cpu] = f"{regval:x}"

            yield addr, vals

def _collect_sysfs_rcopy(pman: ProcessManagerType, basedir: Path) -> Generator[Path, None, None]:
    """
    Recursively copy sysfs directories from the SUT into the output sysfs directory tree.

    Args:
        pman: The process manager object that defines the SUT to copy directories from.
        basedir: Path to the base output directory.

    Yields:
        Paths relative to the sysfs sub-directory for each copied top-level directory
        (e.g., Path("kernel/debug/dir0")).
    """

    for entry in pman.lsdir(_SYSFS_TPMI_BASEDIR):
        if not re.fullmatch(r"tpmi-.*", entry["name"]):
            continue
        if not stat.S_ISDIR(entry["mode"]):
            continue

        # The 'relative_to("/")' is needed because concatenating two paths starting with '/' would
        # ignore the first one. E.g., Path("/base") / Path("/sys/kernel/debug/dir0" would result in
        # Path("/sys/kernel/debug/dir0") instead of Path("/base/sys/kernel/debug /dir0")).
        dst = basedir / entry["path"].parent.relative_to("/")
        try:
            os.makedirs(dst, exist_ok=True)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to create directory '{dst}':\n{errmsg}") from err

        pman.rsync(entry["path"], dst, remotesrc=True)

        yield entry["path"].relative_to(f"/{_SYSFS_SUBDIR}")

def _collect_sysfs(pman: ProcessManagerType, basedir: Path, config_yml: dict):
    """
    Collect sysfs emulation data from the SUT and populate the emulation data configuration
    dictionary with sysfs information.

    Args:
        pman: The process manager object that defines the SUT to read sysfs files from.
        basedir: Path to the base output directory.
        config_yml: The emulation data configuration dictionary to populate with the sysfs section.
    """

    outdir = basedir / _SYSFS_SUBDIR
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{outdir}':\n{errmsg}") from err

    path = outdir / _SYSFS_DATA_FILE

    try:
        with open(path, "w", encoding="utf-8") as fobj:
            # The output format is one entry per line: <mode>|<sysfs_path>|<value>.
            # 'mode' is 'ro' for read-only entries and 'rw' for read-write entries.
            # '|' is used as a separator because ':' may appear in sysfs paths (e.g., PCI
            # addresses like '0000:00:00.0').
            fobj.write("# Format: <ro|rw>|<sysfs_path>|<value>\n")

            for entry in _SYSFS_INLINE_CMDS:
                res = pman.run_join(entry["command"])
                if res.exitcode != 0:
                    _LOG.notice("Command '%s' exited with code %d",
                                entry["command"], res.exitcode)

                if not res.stdout:
                    continue

                mode = "ro" if entry["readonly"] else "rw"
                for line in res.stdout.splitlines():
                    # 'grep -Z -H' separates the path and value with a '\0' byte, which avoids
                    # ambiguity when the path or value contains ':'.
                    sysfs_path, _, value = line.partition("\0")
                    fobj.write(f"{mode}|{sysfs_path}|{value}\n")
    except OSError as err:
        raise Error(f"Failed to perform I/O on file '{path}'{pman.hostmsg}:\n"
                    f"{Error(str(err)).indent(2)}") from err

    sysfs_config: _EmulDataConfigSysfsTypedDict = {
        "dirname": _SYSFS_SUBDIR,
        "inlinefiles": _SYSFS_DATA_FILE,
    }

    rcopy = list(_collect_sysfs_rcopy(pman, basedir))
    if rcopy:
        sysfs_config["rcopy"] = rcopy

    config_yml["sysfs"] = sysfs_config

def _collect_msrs(cpuinfo: CPUInfo.CPUInfo,
                  pman: ProcessManagerType,
                  basedir: Path,
                  config_yml: dict):
    """
    Collect MSR emulation data from the SUT and populate the emulation data configuration dictionary
    with MSR information.

    Args:
        cpuinfo: CPU information object for the SUT.
        pman: The process manager object that defines the SUT to read the MSR values from.
        basedir: Path to the base output directory.
        config_yml: The emulation data configuration dictionary to populate with the MSR section.
    """

    proc_cpuinfo = cpuinfo.get_proc_cpuinfo()
    if proc_cpuinfo["vendor"] != CPUModels.VENDOR_INTEL:
        _LOG.notice("The SUT CPU vendor is '%s', not Intel, skipping MSR collection",
                    proc_cpuinfo["vendor_name"])
        return

    cpus = cpuinfo.get_cpus()

    outdir = basedir / _MSR_SUBDIR
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{outdir}':\n{errmsg}") from err

    path = outdir / _MSR_DATA_FILE

    try:
        with open(path, "w+", encoding="utf-8") as fobj:
            # The output format is:
            # # <hex_addr>:<cpu_num>|<hex_val> <cpu_num>|<hex_val> ...
            # All values are hexadecimal without the '0x' prefix.
            fobj.write("# Format: <msr_hex_addr>:<cpu_num>|<hex_val> ... for every CPU ...\n")

            for addr, cpu_data in _get_msr_data(cpuinfo, pman, cpus):
                if not cpu_data:
                    continue
                pairs = " ".join(f"{cpu}|{val}" for cpu, val in cpu_data.items())
                fobj.write(f"{addr:x}:{pairs}\n")
    except OSError as err:
        raise Error(f"Failed to perform I/O on file '{path}'{pman.hostmsg}:\n"
                    f"{Error(str(err)).indent(2)}") from err

    msr_config: _EmulDataConfigMSRTypedDict = {
        "dirname": _MSR_SUBDIR,
        "filename": _MSR_DATA_FILE,
    }
    config_yml["msr"] = msr_config

def _prepare(pman: ProcessManagerType, cpuinfo: CPUInfo.CPUInfo):
    """
    Prepare the SUT for emulation data collection.

    Args:
        pman: The process manager object that defines the SUT.
        cpuinfo: CPU information object for the SUT.
    """

    with CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as onl:
        onl.online()

    cpus = cpuinfo.get_cpus()

    with PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pstates:
        try:
            pstates.set_prop_cpus("min_freq", "min", cpus)
            pstates.set_prop_cpus("max_freq", "max", cpus)
        except ErrorNotSupported:
            pass

    dies = {pkg: cpuinfo.get_package_dies(pkg) for pkg in cpuinfo.get_packages()}
    with Uncore.Uncore(pman=pman, cpuinfo=cpuinfo) as uncore:
        try:
            uncore.set_prop_dies("min_freq", "min", dies)
            uncore.set_prop_dies("max_freq", "max", dies)
        except ErrorNotSupported:
            pass

    with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as cstates:
        try:
            cstates.enable_cstates(cpus=cpus, csnames="all")
        except ErrorNotSupported:
            pass

def _do_main(pman: ProcessManagerType, outdir: Path, cpuinfo: CPUInfo.CPUInfo) -> int:
    """
    The main body of the tool.

    Args:
        pman: The process manager object that defines the SUT to collect data from.
        outdir: Path to the output directory to store the collected data at.
        cpuinfo: CPU information object for the SUT.

    Returns:
        The program exit code.
    """

    _prepare(pman, cpuinfo)

    # The contents of the 'config.yml' file, which will be created in the emulation data root
    # directory and describe the collected emulation data.
    config_yml: dict = {}

    _collect_msrs(cpuinfo, pman, outdir, config_yml)
    _collect_sysfs(pman, outdir, config_yml)
    _generate_config_file("config", config_yml, outdir)

    for modname, tdcinfo in _TDCollectInfo.items():
        datapath = outdir / modname

        if "commands" in tdcinfo:
            for cmdinfo in tdcinfo["commands"]:
                _collect_cmd_output(pman, cmdinfo, datapath)
                cmdinfo["dirname"] = f"{modname}/{cmdinfo['dirname']}"

        if "files" in tdcinfo:
            for file in tdcinfo["files"]:
                _copy_file(pman, file["path"], datapath)

        for section in ("inlinefiles",):
            if section not in tdcinfo:
                continue

            for inlinfo in tdcinfo[section]:
                _collect_inline(pman, inlinfo, datapath)
                inlinfo["dirname"] = f"{modname}/{inlinfo['dirname']}"
                del inlinfo["command"]

        if tdcinfo:
            _generate_config_file(modname, tdcinfo, outdir)

    return 0

def main():
    """
    The entry point of the tool.

    Returns:
        The program exit code.
    """

    args = _parse_arguments()
    cmdl = _get_cmdline_args(args)

    exitcode = -1
    try:
        with ProcessManager.get_pman(cmdl["hostname"], username=cmdl["username"],
                                     privkeypath=cmdl["privkey"],
                                     timeout=cmdl["timeout"]) as pman, \
             CPUInfo.CPUInfo(pman=pman) as cpuinfo:
            return _do_main(pman, cmdl["outdir"], cpuinfo)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
    except Error as err:
        _LOG.error_out(str(err))

    return exitcode
