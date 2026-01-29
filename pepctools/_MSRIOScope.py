#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Detect I/O scope of a writable Model-Specific Register (MSR). Refer to 'docs/misc-msr-scope.md' for
more information about MSR I/O scope.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
import pkgutil
import importlib

try:
    import argcomplete
    _ARGCOMPLETE_AVAILABLE = True
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    _ARGCOMPLETE_AVAILABLE = False

from pepctools._Pepc import ArgParse
from pepclibs.helperlibs import Logging, ProcessManager, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.msr import MSR, _FeaturedMSR
from pepclibs import CPUInfo

if typing.TYPE_CHECKING:
    from typing import TypedDict, Generator
    from types import ModuleType
    import argparse
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import ScopeNameType

    class _FeatureInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary for an MSR feature an I/O scope detection test was run for.

        Attributes:
            bits_str: The bits range of the feature in the "msb:lsb" format.
            addr: The address of the MSR the feature belongs to.
            sname: The detected I/O scope name of the feature.
            expected_sname: The expected I/O scope name of the feature.
        """

        bits_str: str
        addr: int
        sname: ScopeNameType
        expected_sname: ScopeNameType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'msr-ioscope' tool.

        Attributes:
            hostname: The hostname of the target system.
            username: The username to use for SSH connections.
            privkey: The private key file to use for SSH authentication.
            timeout: The timeout value for SSH connections.
            addr: The MSR address to run I/O scope detection on.
            all_msrs: If True, run the I/O scope detection procedure for all writable MSRs supported
                      by the 'pepc' project and the target host.
            bits: The bits range to use for detecting MSR I/O scope.
            values: Two unique values to use for detecting MSR I/O scope.
            cpu: The CPU number to write to the MSR on.
        """

        hostname: str
        username: str
        privkey: str
        timeout: int | float
        addr: int
        all_msrs: bool
        bits: list[int]
        values: list[int]
        cpu: int

_TOOLNAME = "msr-ioscope"
_VERSION = "0.2"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

def _get_existing_snames(cpuinfo: CPUInfo.CPUInfo) -> list[ScopeNameType]:
    """
    Get scope names that exist on the target system.

    Args:
        cpuinfo: The target system CPU information object.

    Returns:
        A list of scope names that exist on the target system, sorted from the smallest to the
        largest scope.
    """

    snames: list[ScopeNameType] = []

    # Ensure that the scopes are in the order from the smallest to the largest.
    for sname in CPUInfo.SCOPE_NAMES:
        if sname == "node":
            # MSRs cannot have the "global" and "node" scopes.
            continue
        if sname == "module":
            if cpuinfo.get_modules_count() == cpuinfo.get_cores_count():
                # There is one core per module, which means that modules do not exist on the target
                # system.
                continue
        if sname == "die":
            if cpuinfo.get_dies_count(noncomp_dies=True) == cpuinfo.get_packages_count():
                # There is one die per package, which means that dies do not exist on the target
                # system.
                continue
        if sname == "CPU":
            if cpuinfo.get_cpus_count() == cpuinfo.get_cores_count():
                # There is one CPU per core, so CPU and core scopes are indistinguishable. Assume
                # core scope as a more common case for MSRs on Intel platforms.
                continue
        snames.append(sname)

    if not snames:
        raise Error("Could not find any scope on the target system")
    return snames

def _is_sibling(snames: list[ScopeNameType],
                sname: ScopeNameType,
                tline1: dict[ScopeNameType, int],
                tline2: dict[ScopeNameType, int]) -> bool:
    """
    Check if two topology lines are siblings at the given scope.

    Args:
        snames: All MSR scope names on the target system, sorted from the smallest to the largest.
        sname: The scope name to check for sibling relationship.
        tline1: The first topology line.
        tline2: The second topology line.

    Returns:
        True if the two topology lines are siblings at the given scope, False otherwise.
    """

    # The scopes to check are the 'sname' and all the higher scopes.
    idx = snames.index(sname)
    for _sname in snames[idx:]:
        if tline1[_sname] != tline2[_sname]:
            return False
    return True

def _check_ioscope(cpuinfo: CPUInfo.CPUInfo,
                   snames: list[ScopeNameType],
                   sname: ScopeNameType,
                   vals: dict[int, int],
                   cpu: int,
                   val: int) -> bool:
    """
    Check if the given scope name is the I/O scope of an MSR bits range.

    Args:
        cpuinfo: The target system CPU information object.
        snames: All MSR scope names on the target system, sorted from the smallest to the largest.
                Scope names irrelevant to MSRs (e.g., "node") must not be included.
        sname: The scope name to check.
        vals: A dictionary mapping CPU numbers to their MSR bit-range values.
        cpu: The CPU on which the value 'val' was written.
        val: The value that was written to one of the CPUs.

    Returns:
        True if the given scope name is the I/O scope of the MSR bits range, False otherwise.
    """

    tline = cpuinfo.get_tline_by_cpu(cpu)

    for _tline in cpuinfo.get_topology():
        if _is_sibling(snames, sname, tline, _tline):
            if vals[_tline["CPU"]] != val:
                return False
        else:
            if vals[_tline["CPU"]] == val:
                return False

    return True

def _detect_msr_bits_range_ioscope(cpuinfo: CPUInfo.CPUInfo,
                                   msr: MSR.MSR,
                                   addr: int,
                                   bits: list[int],
                                   values: list[int],
                                   cpu: int) -> ScopeNameType:
    """
    Detect the I/O scope of a bit range in an MSR.

    Args:
        cpuinfo: The target system CPU information object.
        msr: The target system MSR object.
        addr: The MSR address.
        bits: The bit range to test in the format [msb, lsb].
        values: Two unique values to write for detecting I/O scope.
        cpu: The CPU number to write to.

    Returns:
        The detected I/O scope name.
    """

    # Save the initial MSR values.
    initial_vals: dict[int, int] = {}
    for _cpu, val in msr.read_bits(addr, bits):
        initial_vals[_cpu] = val

    snames = _get_existing_snames(cpuinfo)

    # The I/O scope detection setup: set the MSR bits range to 'values[0]' on all CPUs and to
    # 'values[1]' on one of the CPUs.
    msr.write_bits(addr, bits, values[0], cpus="all", verify=True)
    msr.write_bits(addr, bits, values[1], cpus=(cpu, 0), verify=True)

    # MSR values on all CPUs after the I/O scope detection setup.
    vals: dict[int, int] = {}
    for _cpu, val in msr.read_bits(addr, bits):
        vals[_cpu] = val

    bits_str = ":".join([str(bit) for bit in bits])

    try:
        # Iterate scopes from the largest to the smallest.
        for sname in reversed(snames):
            _LOG.debug("Checking scope '%s' for MSR %#x bits %s", sname, addr, bits_str)
            if _check_ioscope(cpuinfo, snames, sname, vals, cpu, values[1]):
                _LOG.debug("  Matched")
                break
            _LOG.debug("  Not matched")
        else:
            raise Error(f"Failed to detect I/O scope of MSR {addr:#x} bits {bits_str}")
    finally:
        # Restore the MSR to the initial value.
        for _cpu, val in initial_vals.items():
            msr.write_bits(addr, bits, val, cpus=(_cpu,), verify=True)

    return sname

def _print_msr_bits_range_ioscope(cpuinfo: CPUInfo.CPUInfo,
                                  msr: MSR.MSR,
                                  cmdl: _CmdlineArgsTypedDict):
    """
    Detect and print the I/O scope of a bit range in an MSR.

    Args:
        cpuinfo: The target system CPU information object.
        msr: The target system MSR object.
        cmdl: Command-line arguments.
    """

    addr = cmdl["addr"]
    bits = cmdl["bits"]
    values = cmdl["values"]
    cpu = cmdl["cpu"]

    sname = _detect_msr_bits_range_ioscope(cpuinfo, msr, addr, bits, values, cpu)

    bits_str = ":".join([str(bit) for bit in bits])
    _LOG.info("I/O scope of MSR %#x bits %s is detected to be '%s'", addr, bits_str, sname)

def _get_featured_msr_modules() -> Generator[tuple[str, ModuleType], None, None]:
    """
    Yield all featured MSR modules supported by the 'pepc' project.

    Yields:
        A tuple of the module name and the module object.
    """

    modname = ""
    try:
        for modinfo in pkgutil.iter_modules(path=["pepclibs/msr"]):
            if modinfo.ispkg:
                continue

            modname = modinfo.name
            if modname.startswith("_"):
                continue

            _LOG.debug("Importing featured MSR module '%s'", modname)
            module = importlib.import_module(f"pepclibs.msr.{modname}")

            yield modname, module
    except Exception as err:
        errmsg = Error(str(err)).indent(2)
        if not modname:
            raise Error(f"Failed to iterate featured MSR modules:\n{errmsg}") from err
        raise Error(f"Failed to import featured MSR module {modname}:\n{errmsg}") from err

def _check_feature_ok_to_test(fmsr: _FeaturedMSR.FeaturedMSR, fname: str) -> bool:
    """
    Check if a featured MSR feature is OK to test for I/O scope.

    Args:
        fmsr: The featured MSR object.
        fname: The name of the feature to check.

    Returns:
        True if the feature can be tested, False otherwise.
    """

    if fmsr.regname == "MSR_PKG_CST_CONFIG_CONTROL" and fname == "pkg_cstate_limit":
        # Check that the package C-state limit is unlocked.
        for _, val in fmsr.read_feature("pkg_cstate_limit_lock", cpus="all"):
            if val != "off":
                finfo = fmsr.features[fname]
                bits_str = ":".join([str(bit) for bit in finfo["bits"]])
                _LOG.info("Skipping feature '%s' (bits %s) in MSR '%s' (%#x): The package C-state "
                          "limit is locked", fname, bits_str, fmsr.regname, fmsr.regaddr)
                return False

    if fmsr.regname == "MSR_HWP_REQUEST" and fname in ("min_perf_valid", "max_perf_valid",
                                                       "epp_valid"):
        # The 'min_perf_valid', 'max_perf_valid' and 'epp_valid' features in 'MSR_HWP_REQUEST' are
        # not necessarily writable. For example, on some platforms they cannot be enabled. Skip
        # them.
        return False

    return True

def _get_featured_msrs(pman: ProcessManagerType,
                       cpuinfo: CPUInfo.CPUInfo,
                       msr: MSR.MSR) -> Generator[tuple[_FeaturedMSR.FeaturedMSR, str], None, None]:
    """
    Yield featured MSR objects for every MSR supported by the 'pepc' project and the target host,
    which have at least one writable and harmless feature. Harmless features are those that are not
    expected to affect system stability when modified.

    Args:
        pman: The process manager object for the target system.
        cpuinfo: The target system CPU information object.
        msr: The target system MSR object.

    Yields:
        A tuple of the featured MSR object and feature name.
    """

    for modname, module in _get_featured_msr_modules():
        fmsr_cls = getattr(module, modname, None)
        if not fmsr_cls:
            raise Error(f"BUG: Module '{modname}' does not have the '{modname}' class")

        if not issubclass(fmsr_cls, _FeaturedMSR.FeaturedMSR):
            _LOG.debug("Skipping module '%s', not a subclass of FeaturedMSR", modname)
            continue

        try:
            fmsr = fmsr_cls(pman=pman, cpuinfo=cpuinfo, msr=msr)
        except ErrorNotSupported as err:
            _LOG.debug(err)
            _LOG.info("Skipping unsupported MSR '%s' (%#x)", fmsr_cls.regname, fmsr_cls.regaddr)
            continue

        for fname, finfo in fmsr.features.items():
            bits_str = ":".join([str(bit) for bit in finfo["bits"]])
            if not finfo["writable"]:
                _LOG.debug("Skipping read-only feature '%s' (bits %s) in MSR '%s' (%#x)",
                          fname, bits_str, fmsr_cls.regname, fmsr_cls.regaddr)
                continue

            if not fmsr.is_feature_supported(fname, cpus="all"):
                _LOG.info("Skipping unsupported feature '%s' (bits %s) in MSR '%s' (%#x)",
                          fname, bits_str, fmsr_cls.regname, fmsr_cls.regaddr)
                continue

            # Handle special cases.
            if not _check_feature_ok_to_test(fmsr, fname):
                continue

            yield fmsr, fname

def _print_ioscope_all(pman: ProcessManagerType,
                        cpuinfo: CPUInfo.CPUInfo,
                        msr: MSR.MSR,
                        cmdl: _CmdlineArgsTypedDict):
    """
    Detect I/O scope of all "featured MSRs" supported by the 'pepc' project and the target host.
    Only the writable and harmless MSR bits ranges are tested.

    Args:
        pman: The process manager object for the target system.
        cpuinfo: The target system CPU information object.
        msr: The target system MSR object.
        cmdl: Command-line arguments.
    """

    cpu = cmdl["cpu"]

    info: dict[str, dict[str, _FeatureInfoTypedDict]] = {}

    for fmsr, fname in _get_featured_msrs(pman, cpuinfo, msr):
        finfo = fmsr.features[fname]
        addr = fmsr.regaddr
        bits = list(finfo["bits"])
        bits_str = ":".join([str(bit) for bit in bits])

        if "vals" in finfo:
            values = list(finfo["vals"].values())
            if len(values) < 2:
                raise Error(f"BUG: Feature '{fname}' (bits {bits_str}) in MSR '{fmsr.regname}' "
                            f"({addr:#x}) has less than 2 unique values")
            values = values[:2]
        else:
            expected_types = ("bool", "int")
            if finfo["type"] not in expected_types:
                expected_str = ", ".join(expected_types)
                raise Error(f"BUG: Writable feature '{fname}' (bits {bits_str}) in MSR "
                            f"'{fmsr.regname}' ({fmsr.regaddr:#x}) has unexpected type "
                            f"'{finfo['type']}'. Expected one of: {expected_str}.")

            max_val = (1 << (bits[0] - bits[1] + 1)) - 1
            values = [max_val // 2, max_val // 2 + 1]

        try:
            _LOG.info("Running I/O scope detection for feature '%s' (bits %s) in MSR '%s' (%#x)",
                      fname, bits_str, fmsr.regname, addr)
            sname = _detect_msr_bits_range_ioscope(cpuinfo, msr, addr, bits, values, cpu)
            if fmsr.regname not in info:
                info[fmsr.regname] = {}
            if fname in info[fmsr.regname]:
                raise Error(f"BUG: Feature '{fname}' (bits {bits_str}) in MSR '{fmsr.regname}' "
                            f"({addr:#x}) was met twice")

            info[fmsr.regname][fname] = {"bits_str": bits_str,
                                         "addr": addr,
                                         "sname": sname,
                                         "expected_sname": finfo["sname"]}
        except Error as err:
            errmsg = err.indent(2)
            _LOG.error("Failed to detect I/O scope of feature '%s' (bits %s) in MSR '%s' "
                       "(%#x):\n%s", fname, bits_str, fmsr.regname, addr, errmsg)
            continue

    if not info:
        _LOG.info("No successful I/O scope detection results")
        return

    _LOG.info("I/O scope detection results:")
    for regname in sorted(info.keys()):
        for idx, (fname, _finfo) in enumerate(info[regname].items()):
            if idx == 0:
                _LOG.info(" - MSR '%s' (%#x):", regname, _finfo["addr"])
            _LOG.info("     Feature '%s' (bits %s): detected I/O scope is '%s'",
                      fname, _finfo["bits_str"], _finfo["sname"])
            if _finfo["sname"] != _finfo["expected_sname"]:
                _LOG.warning("Expected I/O scope is '%s', but detected '%s'",
                             _finfo["expected_sname"], _finfo["sname"])

def _build_arguments_parser() -> ArgParse.ArgsParser:
    """
    Build and return the command-line arguments parser.

    Returns:
        An initialized command-line arguments parser object.
    """

    text = f"""{_TOOLNAME} - detect I/O scope of a writable Model-Specific Register (MSR). Refer
               to 'docs/misc-msr-scope.md' for more information about MSR I/O scope."""
    parser = ArgParse.ArgsParser(description=text, prog=_TOOLNAME, ver=_VERSION)
    ArgParse.add_ssh_options(parser)

    text = """MSR address to run the I/O scope detection procedure for. Default is to run the
              I/O scope detection procedure for all writable MSRs supported by the 'pepc' project
              and the target host."""
    parser.add_argument("--addr", default="all", help=text)

    text = """Bits range to use for detecting MSR I/O scope in the "msb:lsb" format, e.g.
              "26:26" for bit 26 only, "15:0" for bits 15 to 0."""
    parser.add_argument("--bits", help=text)

    text = """Two comma-separated unique values to use for detecting MSR I/O scope."""
    parser.add_argument("--values", help=text)

    text = """CPU number to write to the MSR on, default is CPU 0."""
    parser.add_argument("--cpu", help=text, default="0")

    if _ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)

    return parser

def _parse_arguments() -> argparse.Namespace:
    """
    Parse the command-line arguments.

    Returns:
        The parsed arguments.
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

    if args.addr == "all":
        all_msrs = True
        addr = 0
        if args.bits:
            raise Error("The '--bits' option can only be used for a specific MSR address "
                        "(use the '--addr' option)")
        if args.values:
            raise Error("The '--values' option can only be used for a specific MSR address "
                        "(use the '--addr' option)")
    else:
        all_msrs = False
        addr = Trivial.str_to_int(args.addr, what="MSR address")
        if addr < 0 or addr > 0xffff:
            raise Error("Bad MSR address, should be in the [0:0xffff] range")
        if not args.bits:
            raise Error("The '--bits' option is required when the '--addr' option is used")
        if not args.values:
            raise Error("The '--values' option is required when the '--addr' option is used")

    if not all_msrs:
        bits = Trivial.split_csv_line_int(args.bits, sep=":", what="'--bits' option value")
        if len(bits) != 2:
            raise Error("Bad '--bits' option value, should be in the \"msb:lsb\" format")
        if bits[0] < bits[1]:
            raise Error("Bad '--bits' option value, msb should be >= lsb")
        if bits[0] > 63 or bits[1] < 0:
            raise Error("Bad '--bits' option value, bit numbers should be in the [0:63] range")
    else:
        # A dummy value, won't be used.
        bits = []

    if not all_msrs:
        values = Trivial.split_csv_line_int(args.values, what="'--values' option value")
        if len(values) != 2:
            raise Error("Bad '--values' option value, should contain exactly 2 unique values")
        if values[0] == values[1]:
            raise Error("Bad '--values' option value, please provide 2 unique values")
        max_val = (1 << (bits[0] - bits[1] + 1)) - 1
        for value in values:
            if value < 0 or value > max_val:
                raise Error(f"Bad '--values' option value '{value}' for bits range {args.bits}, "
                            f"should be in the [0:{max_val}] range")
    else:
        # A dummy value, won't be used.
        values = []

    cpu = Trivial.str_to_int(args.cpu, what="'--cpu' option value")
    if cpu < 0:
        raise Error("Bad '--cpu' option value, should be a non-negative integer")

    cmdl: _CmdlineArgsTypedDict = {}
    cmdl["hostname"] = hostname
    cmdl["username"] = username
    cmdl["privkey"] = privkey
    cmdl["timeout"] = timeout
    cmdl["addr"] = addr
    cmdl["all_msrs"] = all_msrs
    cmdl["bits"] = bits
    cmdl["values"] = values
    cmdl["cpu"] = cpu

    return cmdl

def main():
    """
    The entry point of the tool.

    Returns:
        The program exit code.
    """

    try:
        args = _parse_arguments()
        cmdl = _get_cmdline_args(args)

        with contextlib.ExitStack() as stack:
            pman = ProcessManager.get_pman(cmdl["hostname"], username=cmdl["username"],
                                           privkeypath=cmdl["privkey"], timeout=cmdl["timeout"])
            stack.enter_context(pman)

            cpuinfo = CPUInfo.CPUInfo(pman=pman)
            stack.enter_context(cpuinfo)

            msr = MSR.MSR(cpuinfo, pman=pman, enable_cache=False)
            stack.enter_context(msr)

            if cpuinfo.get_offline_cpus_count():
                raise Error("Please online all CPUs")

            cmdl["cpu"] = cpuinfo.normalize_cpu(cmdl["cpu"])

            if cmdl["all_msrs"]:
                _print_ioscope_all(pman, cpuinfo, msr, cmdl)
            else:
                _print_msr_bits_range_ioscope(cpuinfo, msr, cmdl)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
        return -1
    except Error as err:
        _LOG.error_out(err)

    return 0
