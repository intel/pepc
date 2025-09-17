#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc pstates' command-line options."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
import common
import props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import Trivial
from pepclibs import CPUInfo, PStates
from pepclibs.PStates import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Final, Generator
    from props_cmdl_common import PropsCmdlTestParamsTypedDict
    from pepclibs.helperlibs.Exceptions import ExceptionType
    from pepclibs.CPUInfoTypes import ScopeNameType

# If the '--mechanism' option is present, the command may fail because the mechanism may not be
# supported. Ignore these failures.
_IGNORE: Final[dict[ExceptionType, str]] = {ErrorNotSupported: "--mechanism",
                                            ErrorTryAnotherMechanism: "--mechanism"}

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[PropsCmdlTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)
        yield props_cmdl_common.extend_params(params, pobj, cpuinfo)

def _get_good_info_opts(sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Return valid command-line options for testing 'pepc pstates info'.

    Args:
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Command-line option strings suitable for the specified scope.
    """

    if sname == "global":
        yield from ["",
                    "--turbo",
                    "--intel-pstate-mode",
                    "--governor",
                    "--governors",
                    "--governors --turbo"]
    elif sname == "package":
        yield from ["--bus-clock",
                    "--epp"]
    elif sname == "CPU":
        yield from ["--min-freq",
                    "--base-freq",
                    "--epp",
                    "--epp --base-freq",
                    "--max-turbo-freq"]
    else:
        assert False, f"BUG: Bad scope name {sname}"

def test_pstates_info(params: PropsCmdlTestParamsTypedDict):
    """
    Test the 'pepc pstates info' command.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_good_info_opts(sname="CPU"):
        for mopt in props_cmdl_common.get_mechanism_opts(params):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"pstates info {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
        props_cmdl_common.run_pepc(f"pstates info {cpu_opt}", pman, exp_exc=Error)

    # Cover '--list-mechanisms'.
    props_cmdl_common.run_pepc("pstates info --list-mechanisms", pman)

def _get_good_config_freq_opts(params: PropsCmdlTestParamsTypedDict,
                               sname: ScopeNameType = "CPU") -> Generator[str, None, None]:
    """
    Yield valid frequency configuration options for testing the 'pepc pstates config' command.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Command-line option strings suitable for the specified scope.
    """

    cpu = 0
    pobj = params["pobj"]

    if sname == "CPU":
        if pobj.prop_is_supported_cpu("min_freq", cpu):
            yield from ["--min-freq",
                        "--max-freq",
                        "--min-freq --max-freq",
                        "--min-freq min",
                        "--max-freq min",
                        "--max-freq max",
                        "--min-freq min --max-freq max",
                        "--max-freq max --min-freq min"]
            if pobj.prop_is_supported_cpu("base_freq", cpu):
                yield from ["--max-freq base",
                            "--max-freq hfm",
                            "--min-freq base",
                            "--min-freq hfm"]
    else:
        assert False, f"BUG: Bad scope name {sname}"

def test_pstates_config_freq_good(params: PropsCmdlTestParamsTypedDict):
    """
    Test the 'pepc pstates config' command with good frequency options.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_good_config_freq_opts(params, sname="CPU"):
        for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=True):
            cmd = f"pstates config {opt} {mopt}"
            props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

def _get_bad_config_freq_opts() -> Generator[str, None, None]:
    """
    Generate invalid frequency command-line options for testing 'pepc pstates config'.

    Args:
        params: The test parameters dictionary.

    Yields:
        str: A string representing an invalid frequency option for command-line testing.
    """

    yield from ["--min-freq 1000ghz",
                "--max-freq 3",
                "--max-freq hfm --mechanism kuku",
                "--min-freq maximum",
                "--min-freq max --max-freq min"]

def test_pstates_config_freq_bad(params: PropsCmdlTestParamsTypedDict):
    """
    Test the 'pepc pstates config' command with bad frequency options.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_bad_config_freq_opts():
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_freq_opts(params):
        for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
            props_cmdl_common.run_pepc(f"pstates config {opt} {cpu_opt}", pman, exp_exc=Error)

def _get_good_config_non_freq_opts(params: PropsCmdlTestParamsTypedDict,
                                   sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Yield valid non-frequency configuration options for testing the 'pepc pstates config' command.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Command-line option string suitable for testing 'pepc pstates config'.
    """

    cpu = 0
    pobj = params["pobj"]

    if sname == "global":
        if pobj.prop_is_supported_cpu("intel_pstate_mode", cpu):
            # The "off" mode is not supported when HWP is enabled.
            if pobj.get_cpu_prop("hwp", cpu)["val"] == "off":
                yield "--intel-pstate-mode off"

            # Note, the last mode is intentionally something else but "off", because in "off" mode
            # many options do not work. For example, switching turbo on/off does not work in the
            # "off" mode.
            yield from ["--intel-pstate-mode",
                        "--intel-pstate-mode passive"]

        if pobj.prop_is_supported_cpu("turbo", cpu):
            yield from ["--turbo",
                        "--turbo enable",
                        "--turbo OFF"]

    if pobj.prop_is_supported_cpu("governor", cpu):
        yield "--governor"
        governors = pobj.get_cpu_prop("governors", cpu)["val"]
        for governor in cast(list[str], governors):
            yield f"--governor {governor}"

    if pobj.prop_is_supported_cpu("epp", cpu):
        yield from ["--epp",
                    "--epp 0",
                    "--epp 128",
                    "--epp performance"]

    if pobj.prop_is_supported_cpu("epb", cpu):
        yield from ["--epb",
                    "--epb 0",
                    "--epb 15",
                    "--epb performance"]

def test_pstates_config_non_freq_good(params: PropsCmdlTestParamsTypedDict):
    """
    Test valid 'pepc pstates config' command options, not related to CPU frequency.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_good_config_non_freq_opts(params, sname="CPU"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="CPU"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_non_freq_opts(params, sname="global"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
            cmd = f"pstates config {opt} {cpu_opt}"
            props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

def _get_bad_config_non_freq_opts(params: PropsCmdlTestParamsTypedDict,
                                  sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Generate invalid non-frequency configuration options for 'pepc pstates config' command.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Invalid command-line option for 'pepc pstates config'.
    """

    cpu = 0
    pobj = params["pobj"]

    if sname == "global":
        if pobj.prop_is_supported_cpu("intel_pstate_mode", cpu):
            yield "--intel-pstate-mode Dagny"

        if pobj.prop_is_supported_cpu("turbo", cpu):
            yield "--turbo 1"

    if pobj.prop_is_supported_cpu("governor", cpu):
        yield "--governor savepower"

    if pobj.prop_is_supported_cpu("epp", cpu):
        yield from ["--epp 256",
                    "--epp green_tree"]

    if pobj.prop_is_supported_cpu("epb", cpu):
        yield from ["--epb 16",
                    "--epb green_tree"]

def test_pstates_config_non_freq_bad(params: PropsCmdlTestParamsTypedDict):
    """
    Test invalid 'pepc pstates config' command options, not related to CPU frequency.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_bad_config_non_freq_opts(params, sname="package"):
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_bad_config_non_freq_opts(params, sname="global"):
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

def _set_freq_pairs(params: PropsCmdlTestParamsTypedDict, min_pname: str, max_pname: str):
    """
    Set minimum and maximum CPU frequency pairs, validating how the order is handled.

    Args:
        params: The test parameters dictionary.
        min_pname: Name of the property for the minimum frequency.
        max_pname: Name of the property for the maximum frequency.
    """

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]

    pvinfo = pobj.get_cpu_prop("frequencies", cpu)
    if pvinfo["val"] is None:
        return

    frequencies = cast(list[int], pvinfo["val"])
    if len(frequencies) < 2:
        return

    freq0 = frequencies[0]
    freq1 = frequencies[1]
    freq2 = frequencies[-2]
    freq3 = frequencies[-1]

    min_opt = f"--{min_pname.replace('_', '-')}"
    max_opt = f"--{max_pname.replace('_', '-')}"

    sname = pobj.get_sname(min_pname)
    assert sname is not None

    siblings = params["cpuinfo"].get_cpu_siblings(0, sname=sname)
    cpus_opt = f"--cpus {Trivial.rangify(siblings)}"

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
    props_cmdl_common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_opt} {freq2} {max_opt} {freq3}"
    props_cmdl_common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
    props_cmdl_common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

def test_pstates_frequency_set_order(params: PropsCmdlTestParamsTypedDict):
    """
    Test setting minimum and maximum frequency values in different orders. Since the system's
    minimum and maximum frequencies may be configured in various ways, care must be taken when
    updating both values simultaneously.

    Args:
        params: The test parameters dictionary.
    """

    cpu = 0
    cpuinfo = params["cpuinfo"]
    pobj = params["pobj"]

    # When Turbo is disabled, the max frequency may be limited.
    if pobj.prop_is_supported_cpu("turbo", cpu):
        sname = pobj.get_sname("turbo")
        if sname:
            siblings = cpuinfo.get_cpu_siblings(0, sname=sname)
            pobj.set_prop_cpus("turbo", "on", siblings)

    if pobj.prop_is_supported_cpu("min_freq", cpu):
        _set_freq_pairs(params, "min_freq", "max_freq")
