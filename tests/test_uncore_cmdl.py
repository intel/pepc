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

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
from tests import common, props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder, ErrorNotSupported, ErrorOutOfRange

from pepclibs import CPUInfo, Uncore, _UncoreFreqTPMI
from pepclibs.Uncore import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Final, Generator
    from tests.props_cmdl_common import PropsCmdlTestParamsTypedDict
    from pepclibs.helperlibs.Exceptions import ExceptionType
    from pepclibs.CPUInfoTypes import ScopeNameType

_IGNORE: Final[dict[ExceptionType, str]] = {ErrorNotSupported: "",
                                            ErrorTryAnotherMechanism: ""}

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[PropsCmdlTestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
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
                "--max-freq",
                "--max-freq --max-freq-limit",
                "--elc-low-zone-min-freq",
                "--elc-mid-zone-min-freq",
                "--elc-low-zone-min-freq --max-freq",
                "--elc-low-threshold",
                "--elc-high-threshold",
                "--elc-high-threshold-status",
                "--elc-low-threshold --elc-high-threshold"]

def test_uncore_info(params: PropsCmdlTestParamsTypedDict):
    """
    Test 'pepc uncore info'.

    Args:
        params: The test parameters dictionary.
    """

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

def _get_good_config_opts() -> Generator[str, None, None]:
    """
    Yield valid configuration options for testing the 'pepc uncore config' command.

    Yields:
        Command-line option strings suitable for the specified scope.
    """

    yield from ["--min-freq",
                "--max-freq",
                "--min-freq --max-freq",
                "--min-freq min",
                "--max-freq mdl",
                "--max-freq min --max-freq max",

                "--elc-low-zone-min-freq",
                "--elc-mid-zone-min-freq",
                "--elc-low-zone-min-freq --elc-mid-zone-min-freq",
                "--elc-low-zone-min-freq min",
                "--elc-mid-zone-min-freq mdl",
                "--elc-mid-zone-min-freq min --elc-mid-zone-min-freq max",

                "--elc-high-threshold-status",
                "--elc-low-threshold",
                "--elc-high-threshold 85",
                "--elc-high-threshold-status off",
                "--elc-low-threshold 65",
                "--elc-high-threshold 78",
                "--elc-high-threshold-status on --elc-low-threshold 17"]

def test_uncore_config_good(params: PropsCmdlTestParamsTypedDict):
    """
    Test valid 'pepc uncore config' command options.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    for opt in _get_good_config_opts():
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
                "--elc-low-zone-min-freq 4",
                "--elc-low-threshold 101",
                "--elc-high-threshold -10",
                "--elc-low-threshold 10 --elc-high-threshold 5",
                "--elc-high-threshold-status b1"]

def test_uncore_config_freq_bad(params: PropsCmdlTestParamsTypedDict):
    """
    Test the 'pepc uncore config' command with bad frequency options.

    Args:
        params: The test parameters dictionary.
    """

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]

    try:
        min_limit = pobj.get_cpu_prop("min_freq_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]
    except ErrorNotSupported:
        return

    if min_limit != max_limit:
        props_cmdl_common.run_pepc("uncore config --min-freq max --max-freq min",
                                   pman, exp_exc=ErrorBadOrder)

    for opt in _get_bad_config_freq_opts():
        props_cmdl_common.run_pepc(f"uncore config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_opts():
        for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
            props_cmdl_common.run_pepc(f"uncore config {opt} {cpu_opt}", pman, exp_exc=Error)

def test_uncore_set_range(params: PropsCmdlTestParamsTypedDict):
    """
    Test setting out of range frequency and ELC threshold values.

    Args:
        params: The test parameters dictionary.
    """

    cpu = 0
    pobj = params["pobj"]
    pman = params["pman"]

    try:
        min_limit = pobj.get_cpu_prop("min_freq_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]
    except ErrorNotSupported:
        return

    min_limit = cast(int, min_limit)
    max_limit = cast(int, max_limit)

    bad_min_freq = min_limit - _UncoreFreqTPMI.RATIO_MULTIPLIER
    bad_max_freq = max_limit + _UncoreFreqTPMI.RATIO_MULTIPLIER

    # Only the "sysfs" mechanism validates against the min. and max. supported uncore frequency.
    cmd = f"uncore config --mechanisms sysfs --min-freq {bad_min_freq}"
    props_cmdl_common.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)
    cmd = f"uncore config --mechanisms sysfs --max-freq {bad_max_freq}"
    props_cmdl_common.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)
    cmd = f"uncore config --mechanisms sysfs --elc-low-zone-min-freq {bad_min_freq}"
    props_cmdl_common.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)

def _set_freq_pairs(params: PropsCmdlTestParamsTypedDict,
                    min_pname: str,
                    max_pname: str,
                    val1: int,
                    val2: int,
                    val3: int,
                    val4: int):
    """
    Set minimum and maximum uncore frequency or ELC threshold pairs, validating how the order is
    handled.

    Args:
        params: The test parameters dictionary.
        min_pname: Name of the property for the minimum frequency/ELC threshold.
        max_pname: Name of the property for the maximum frequency/ELC threshold.
        val1: Any low value of the property.
        val2: A value of the property > val1.
        val3: A value of the property > val2.
        val4: A value of the property > val3.
    """

    pman = params["pman"]


    min_opt = f"--{min_pname.replace('_', '-')}"
    max_opt = f"--{max_pname.replace('_', '-')}"
    cpus_opt = "--cpus all"

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {val1} {max_opt} {val2}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_opt} {val3} {max_opt} {val4}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {val1} {max_opt} {val2}"
    props_cmdl_common.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

def test_uncore_set_order(params: PropsCmdlTestParamsTypedDict):
    """
    Test setting frequency and ELC threshold values in various orders to verify that the tool
    correctly handles value ordering.

    Args:
        params: The test parameters dictionary.
    """

    cpu = 0
    pobj = params["pobj"]

    if pobj.prop_is_supported_cpu("min_freq", cpu) and \
       pobj.prop_is_supported_cpu("max_freq", cpu):
        min_limit = pobj.get_cpu_prop("min_freq_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]

        min_limit = cast(int, min_limit)
        max_limit = cast(int, max_limit)

        delta = (max_limit - min_limit) // 4
        delta -= delta % _UncoreFreqTPMI.RATIO_MULTIPLIER

        val2 = min_limit + delta
        val3 = max_limit - delta

        _set_freq_pairs(params, "min_freq", "max_freq", min_limit, val2, val3, max_limit)

    if pobj.prop_is_supported_cpu("elc_low_threshold", 0):
        _set_freq_pairs(params, "elc_low_threshold", "elc_high_threshold", 1, 2, 99, 100)
