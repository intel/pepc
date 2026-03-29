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
Emulation data generator - a tool to collect data from a real system and generate emulation data
files which can be used for emulating that system.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import os
import stat
import shutil
import types
import typing
import inspect
import pkgutil
import datetime
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
from pepclibs.helperlibs.emul.EmulCommon import EMUL_CONFIG_FNAME

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final, TypedDict, Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.helperlibs.emul.EmulCommon import _EDConfTypedDict

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
            outdir: Path to the output directory.
            replace: If True, remove the output directory contents before proceeding.
        """

        hostname: str
        username: str
        privkey: str
        timeout: int | float
        outdir: Path
        replace: bool

_TOOLNAME: Final[str] = "emulation-data-generator"
_VERSION: Final[str] = "0.1"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

# The procfs data sub-directory name in the dataset directory.
_PROCFS_SUBDIR: Final[str] = "proc"

# The procfs files to collect from the SUT.
_PROCFS_FILES: list[Path] = [
    Path("/proc/cpuinfo"),
    Path("/proc/cmdline"),
    Path("/proc/version"),
    Path("/proc/mounts"),
    Path("/proc/modules"),
]

# The sysfs data sub-directory name in the dataset directory.
_SYSFS_SUBDIR: Final[str] = "sys"
# The sysfs inline data file name in the dataset directory.
_SYSFS_DATA_FILE: Final[str] = "inlinefiles.txt"
# Base directory for TPMI sysfs files.
_SYSFS_TPMI_BASEDIR: Final[Path] = Path("/sys/kernel/debug")
# Regex patterns for TPMI sysfs files that should be registered as read-write in emulation.
# 'mem_write' is the only writable TPMI debugfs file; all others are read-only.
_SYSFS_TPMI_RW_PATTERNS: Final[list[str]] = [r".*/mem_write$"]

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
# The MSR data sub-directory name in the dataset directory.
_MSR_SUBDIR: Final[str] = "msr"
# The MSR data file name in the dataset directory.
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

    text = """If the output directory already exists and is not empty, remove its contents before
              proceeding. Without this option the tool will error out if the output directory
              already exists and is not empty."""
    parser.add_argument("--replace", action="store_true", help=text)

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

    cmdl["replace"] = getattr(args, "replace", False)

    return cmdl

def _copy_file(pman: ProcessManagerType, src: Path, outdir: Path):
    """
    Copy a file from the SUT.

    Args:
        pman: The process manager object that defines the remote SUT to copy the file from.
        src: Path to the source file to copy.
        outdir: Path to the destination directory.
    """

    dst = Path(outdir / str(src).lstrip("/"))

    try:
        os.makedirs(dst.parent, exist_ok=True)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to create directory '{dst.parent}':\n{errmsg}") from err

    # In some cases '/proc/cpuinfo' is not fully copied when using 'scp' or 'rsync'.
    res = pman.run_join(f"cat -- '{src}'")
    if res.exitcode != 0:
        _LOG.notice("'cat %s' exited with code %d", src, res.exitcode)

    try:
        with open(dst, "w", encoding="utf-8") as fobj:
            fobj.write(res.stdout)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to write to file '{dst}':\n{errmsg}") from err

def _generate_config_file(outpath: Path, config_yml: _EDConfTypedDict):
    """
    Generate the emulation data YAML configuration file.

    Args:
        outpath: Path to the output configuration file.
        config_yml: The emulation data configuration dictionary.
    """

    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    config_yml["metadata"] = {
        "generated_by": {
            "tool": _TOOLNAME,
            "version": _VERSION,
            "date": date,
        }
    }
    try:
        with open(outpath, "w", encoding="utf-8") as fobj:
            YAML.dump(config_yml, fobj)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to write the configuration file '{outpath}':\n{errmsg}") from err

def _discover_msr_classes() -> Generator[type[_FeaturedMSR.FeaturedMSR], None, None]:
    """
    Yield all 'FeaturedMSR' subclasses found in the 'pepclibs.msr' package, one per module, in
    module iteration order.

    Yields:
        'FeaturedMSR' subclasses, one per MSR module.
    """

    yielded: set[type[_FeaturedMSR.FeaturedMSR]] = set()

    for _, modname, ispkg in pkgutil.iter_modules(_msr_pkg.__path__):
        if modname.startswith("_") or ispkg:
            continue
        module = importlib.import_module(f"pepclibs.msr.{modname}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, _FeaturedMSR.FeaturedMSR):
                continue
            if obj is _FeaturedMSR.FeaturedMSR:
                continue
            if obj in yielded:
                continue
            yielded.add(obj)
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

def _copy_tpmi_dir(pman: ProcessManagerType, srcdir: Path, dstdir: Path):
    """
    Recursively copy a TPMI debugfs directory from the SUT to 'dstdir'.

    Args:
        pman: The process manager object that defines the SUT to copy directories from.
        srcdir: The source directory path on the SUT.
        dstdir: The local destination directory path.

    Notes:
        - 'rsync' cannot be used here. TPMI debugfs files like 'mem_dump' are virtual kernel files
          that report 'size=0' in their 'stat()' output, but produce real content when read
          sequentially. 'rsync' uses 'stat()' to determine how many bytes to read and transfer, so
          it reads 0 bytes and creates empty destination files. Instead, this function reads each
          file using 'cat', which does not rely on 'stat()' and captures the real content.
    """

    try:
        os.makedirs(dstdir, exist_ok=True)
    except OSError as err:
        raise Error(f"Failed to create directory '{dstdir}':\n{Error(str(err)).indent(2)}") from err

    for entry in pman.lsdir(srcdir):
        dst = dstdir / entry["name"]
        if stat.S_ISDIR(entry["mode"]):
            _copy_tpmi_dir(pman, entry["path"], dst)
        elif stat.S_ISREG(entry["mode"]):
            result = pman.run_join(f"cat -- '{entry['path']}'")
            if result.exitcode != 0:
                raise Error(f"Failed to read '{entry['path']}'{pman.hostmsg}:\n"
                            f"{result.stderr.strip()}")
            try:
                with open(dst, "w", encoding="utf-8") as fobj:
                    fobj.write(result.stdout)
            except OSError as err:
                raise Error(f"Failed to write '{dst}':\n{Error(str(err)).indent(2)}") from err

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
        # ignore the first one. E.g., Path("/base") / Path("/sys/kernel/debug/dir0") would result
        # in Path("/sys/kernel/debug/dir0") instead of Path("/base/sys/kernel/debug/dir0").
        dst = basedir / entry["path"].parent.relative_to("/")
        _copy_tpmi_dir(pman, entry["path"], dst / entry["name"])

        yield entry["path"].relative_to(f"/{_SYSFS_SUBDIR}")

def _collect_sysfs(pman: ProcessManagerType, basedir: Path, config_yml: _EDConfTypedDict):
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

    rcopy_paths = list(_collect_sysfs_rcopy(pman, basedir))

    config_yml["sysfs"] = {
        "dirname": _SYSFS_SUBDIR,
        "inlinefiles": _SYSFS_DATA_FILE,
    }
    if rcopy_paths:
        config_yml["sysfs"]["rcopy"] = {
            "paths": rcopy_paths,
            "rw_patterns": _SYSFS_TPMI_RW_PATTERNS,
        }

def _collect_procfs(pman: ProcessManagerType, basedir: Path, config_yml: _EDConfTypedDict):
    """
    Collect procfs emulation data from the SUT and populate the emulation data configuration
    dictionary with procfs information.

    Args:
        pman: The process manager object that defines the SUT to read procfs files from.
        basedir: Path to the base output directory.
        config_yml: The emulation data configuration dictionary to populate with the procfs section.
    """

    # Current design: all procfs files are always treated as read-only.
    for src in _PROCFS_FILES:
        _copy_file(pman, src, basedir)

    config_yml["procfs"] = {
        "dirname": _PROCFS_SUBDIR,
    }

def _collect_msrs(cpuinfo: CPUInfo.CPUInfo,
                  pman: ProcessManagerType,
                  basedir: Path,
                  config_yml: _EDConfTypedDict):
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

    config_yml["msr"] = {
        "dirname": _MSR_SUBDIR,
        "filename": _MSR_DATA_FILE,
    }

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

    # The contents of the main configuration file (EMUL_CONFIG_FNAME), which will be
    # created in the emulation data root directory and describe the collected emulation data.
    config_yml: _EDConfTypedDict = {}
    config_yml["metadata"] = {}

    _collect_msrs(cpuinfo, pman, outdir, config_yml)
    _collect_sysfs(pman, outdir, config_yml)
    _collect_procfs(pman, outdir, config_yml)

    _generate_config_file(outdir / EMUL_CONFIG_FNAME, config_yml)

    return 0

def main():
    """
    The entry point of the tool.

    Returns:
        The program exit code.
    """

    args = _parse_arguments()
    cmdl = _get_cmdline_args(args)

    exitcode = 1
    try:
        outdir = cmdl["outdir"]
        if outdir.exists() and any(outdir.iterdir()):
            if not cmdl["replace"]:
                raise Error(f"Output directory '{outdir}' already exists and is not empty. Use "
                            f"'--replace' to remove its contents and proceed.")
            shutil.rmtree(outdir)

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
