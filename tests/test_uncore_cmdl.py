#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc uncore' command-line options."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
import common
import props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

from pepclibs import CPUInfo, Uncore, _UncoreFreqTpmi
from pepclibs.Uncore import ErrorTryAnotherMechanism

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
def get_params(hostspec: str) -> Generator[PropsCmdlTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for running the test.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Uncore.Uncore(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)
        yield props_cmdl_common.extend_params(params, pobj, cpuinfo)

def _get_good_info_opts() -> Generator[str, None, None]:
    """
    Return valid command-line options for testing 'pepc uncore info'.

    Yields:
        Command-line option strings suitable for the specified scope.
    """

    yield from ["--min-freq-limit",
                "--min-freq",
                "--max-freq --max-freq-limit"]

def test_uncore_info(params: PropsCmdlTestParamsTypedDict):
    """Test the 'pepc uncore info' command."""

    pman = params["pman"]

    for opt in _get_good_info_opts():
        for mopt in props_cmdl_common.get_mechanism_opts(params):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"uncore info {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
        props_cmdl_common.run_pepc(f"uncore info {cpu_opt}", pman, exp_exc=Error)

    # Cover '--list-mechanisms'.
    props_cmdl_common.run_pepc("uncore info --list-mechanisms", pman)

def _get_good_config_freq_opts() -> Generator[str, None, None]:
    """
    Yield valid frequency configuration options for testing the 'pepc uncore config' command.

    Yields:
        Command-line option strings suitable for the specified scope.
    """

    yield from ["--min-freq",
                "--max-freq",
                "--min-freq --max-freq",
                "--min-freq min",
                "--max-freq max",
                "--max-freq min --max-freq max"]

def test_uncore_config_freq_good(params: PropsCmdlTestParamsTypedDict):
    """Test the 'pepc uncore config' command with good frequency options."""

    pman = params["pman"]

    for opt in _get_good_config_freq_opts():
        for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=True):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"uncore config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
                props_cmdl_common.run_pepc(f"uncore config {opt} {cpu_opt} {mopt}", pman,
                                           exp_exc=Error)

            for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
                props_cmdl_common.run_pepc(f"uncore config {opt} {cpu_opt} {mopt}", pman,
                                           exp_exc=Error)

def _get_bad_config_freq_opts() -> Generator[str, None, None]:
    """
    Generate invalid frequency command-line options for testing 'pepc uncore config'.

    Yields:
        str: A string representing an invalid frequency option for command-line testing.
    """

    yield from ["--min-freq 1000ghz",
                "--max-freq 3",
                "--max-freq hfm --mechanism kuku",
                "--min-freq maximum",
                "--min-freq max --max-freq min"]

def test_uncore_config_freq_bad(params: PropsCmdlTestParamsTypedDict):
    """Test the 'pepc uncore config' command with bad frequency options."""

    pman = params["pman"]

    for opt in _get_bad_config_freq_opts():
        props_cmdl_common.run_pepc(f"uncore config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_freq_opts():
        for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
            props_cmdl_common.run_pepc(f"uncore config {opt} {cpu_opt}", pman, exp_exc=Error)

def _get_good_config_non_freq_opts(params: PropsCmdlTestParamsTypedDict,
                                   sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Yield valid non-frequency configuration options for testing the 'pepc uncore config' command.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Command-line option string suitable for testing 'pepc uncore config'.
    """

    # TODO: add threshold options.
    yield from []

def test_uncore_config_non_freq_good(params: PropsCmdlTestParamsTypedDict):
    """Test the 'pepc uncore config' command with good options (excluding frequency)."""

    pman = params["pman"]

    for opt in _get_good_config_non_freq_opts(params, sname="CPU"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="CPU"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"uncore config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_non_freq_opts(params, sname="global"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"uncore config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

def _get_bad_config_non_freq_opts(params: PropsCmdlTestParamsTypedDict,
                                  sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Generate invalid non-frequency configuration options for 'pepc uncore config' command.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Invalid command-line option for 'pepc uncore config'.
    """

    # TODO: add threshold options.
    yield from []

def test_uncore_config_non_freq_bad(params: PropsCmdlTestParamsTypedDict):
    """Test the 'pepc uncore config' command with bad options (excluding frequency)."""

    pman = params["pman"]

    for opt in _get_bad_config_non_freq_opts(params, sname="package"):
        props_cmdl_common.run_pepc(f"uncore config {opt}", pman, exp_exc=Error)

    for opt in _get_bad_config_non_freq_opts(params, sname="global"):
        props_cmdl_common.run_pepc(f"uncore config {opt}", pman, exp_exc=Error)

def _set_freq_pairs(params: PropsCmdlTestParamsTypedDict, min_pname: str, max_pname: str):
    """
    Set minimum and maximum frequency pairs for CPU or uncore properties, taking care of the
    ordering constraints.

    Args:
        params: The test parameters dictionary.
        min_pname: Name of the property for the minimum frequency.
        max_pname: Name of the property for the maximum frequency.
    """

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]

    min_limit = pobj.get_cpu_prop(f"{min_pname}_limit", cpu)["val"]
    max_limit = pobj.get_cpu_prop(f"{max_pname}_limit", cpu)["val"]
    if not min_limit or not max_limit:
        return

    min_limit = cast(int, min_limit)
    max_limit = cast(int, max_limit)

    delta = (max_limit - min_limit) // 4
    delta -= delta % _UncoreFreqTpmi.RATIO_MULTIPLIER

    freq0 = min_limit
    freq1 = min_limit + delta
    freq2 = max_limit - delta
    freq3 = max_limit

    min_opt = f"--{min_pname.replace('_', '-')}"
    max_opt = f"--{max_pname.replace('_', '-')}"

    sname = pobj.get_sname(min_pname)
    assert sname is not None

    cpus_opt = "--cpus all"

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_opt} {freq2} {max_opt} {freq3}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

def test_uncore_frequency_set_order(params: PropsCmdlTestParamsTypedDict):
    """
    Test setting minimum and maximum frequency values in different orders. Since the system's
    minimum and maximum frequencies may be configured in various ways, care must be taken when
    updating both values simultaneously.
    """

    _set_freq_pairs(params, "min_freq", "max_freq")
