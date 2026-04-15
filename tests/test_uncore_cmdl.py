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
import pytest
from tests import _Common, PropsCommonCmdl
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder, ErrorNotSupported, ErrorOutOfRange

from pepclibs import CPUInfo, Uncore, _UncoreFreqTPMI, CPUOnline
from pepclibs.Uncore import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Final, Generator, cast
    from tests.PropsCommonCmdl import PropsCmdlTestParamsTypedDict
    from pepclibs.helperlibs.Exceptions import ExceptionTypeType
    from pepclibs.CPUInfoTypes import ScopeNameType

_IGNORE: Final[dict[ExceptionTypeType, str]] = {ErrorNotSupported: "", ErrorTryAnotherMechanism: ""}

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

    with _Common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Uncore.Uncore(pman=pman, cpuinfo=cpuinfo) as pobj:
        with CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as online:
            # Online all CPUs.
            online.online()
        params = _Common.build_params(pman)
        yield PropsCommonCmdl.extend_params(params, pobj, cpuinfo)

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
        for mopt in PropsCommonCmdl.get_mechanism_opts(params):
            for cpu_opt in PropsCommonCmdl.get_good_optarget_opts(params, sname="global"):
                cmd = f"uncore info {opt} {cpu_opt} {mopt}"
                PropsCommonCmdl.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpu_opt in PropsCommonCmdl.get_bad_optarget_opts(params):
        PropsCommonCmdl.run_pepc(f"uncore info {cpu_opt}", pman, exp_exc=Error)

    # Cover '--list-mechanisms'.
    PropsCommonCmdl.run_pepc("uncore info --list-mechanisms", pman)

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
        for mopt in PropsCommonCmdl.get_mechanism_opts(params, allow_readonly=True):
            for cpu_opt in PropsCommonCmdl.get_good_optarget_opts(params, sname="global"):
                cmd = f"uncore config {opt} {cpu_opt} {mopt}"
                PropsCommonCmdl.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpu_opt in PropsCommonCmdl.get_bad_optarget_opts(params):
                PropsCommonCmdl.run_pepc(f"uncore config {opt} {cpu_opt} {mopt}", pman,
                                           exp_exc=Error)

            for cpu_opt in PropsCommonCmdl.get_bad_optarget_opts(params):
                PropsCommonCmdl.run_pepc(f"uncore config {opt} {cpu_opt} {mopt}", pman,
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
        PropsCommonCmdl.run_pepc("uncore config --min-freq max --max-freq min",
                                   pman, exp_exc=ErrorBadOrder)

    for opt in _get_bad_config_freq_opts():
        PropsCommonCmdl.run_pepc(f"uncore config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_opts():
        for cpu_opt in PropsCommonCmdl.get_bad_optarget_opts(params):
            PropsCommonCmdl.run_pepc(f"uncore config {opt} {cpu_opt}", pman, exp_exc=Error)

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

    if typing.TYPE_CHECKING:
        min_limit = cast(int, min_limit)
        max_limit = cast(int, max_limit)

    bad_min_freq = min_limit - _UncoreFreqTPMI.RATIO_MULTIPLIER
    bad_max_freq = max_limit + _UncoreFreqTPMI.RATIO_MULTIPLIER

    # Only the "sysfs" mechanism validates against the min. and max. supported uncore frequency.
    cmd = f"uncore config --mechanisms sysfs --min-freq {bad_min_freq}"
    PropsCommonCmdl.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)
    cmd = f"uncore config --mechanisms sysfs --max-freq {bad_max_freq}"
    PropsCommonCmdl.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)
    cmd = f"uncore config --mechanisms sysfs --elc-low-zone-min-freq {bad_min_freq}"
    PropsCommonCmdl.run_pepc(cmd, pman, exp_exc=ErrorOutOfRange, ignore=_IGNORE)

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
    PropsCommonCmdl.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_opt} {val3} {max_opt} {val4}"
    PropsCommonCmdl.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {val1} {max_opt} {val2}"
    PropsCommonCmdl.run_pepc(f"uncore config {cpus_opt} {freq_opts}", pman)

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

        if typing.TYPE_CHECKING:
            min_limit = cast(int, min_limit)
            max_limit = cast(int, max_limit)

        delta = (max_limit - min_limit) // 4
        delta -= delta % _UncoreFreqTPMI.RATIO_MULTIPLIER

        val2 = min_limit + delta
        val3 = max_limit - delta

        _set_freq_pairs(params, "min_freq", "max_freq", min_limit, val2, val3, max_limit)

    if pobj.prop_is_supported_cpu("elc_low_threshold", 0):
        _set_freq_pairs(params, "elc_low_threshold", "elc_high_threshold", 1, 2, 99, 100)

def test_uncore_cpus_option(params: PropsCmdlTestParamsTypedDict):
    """
    Test the '--cpus' option for uncore commands.

    Uncore properties are die-scoped, so when using '--cpus', the tool translates CPU numbers to
    die numbers. This test verifies that:
    1. Single CPU from a die fails (incomplete die specification)
    2. Multiple CPUs from same die that don't cover the entire die fail
    3. All CPUs from a die succeed
    4. CPUs from multiple complete dies succeed

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]
    cpuinfo = params["cpuinfo"]
    packages = params["packages"]

    if not packages:
        return

    pkg = packages[0]
    dies = params["dies"][pkg]

    if not dies:
        return

    die = dies[0]
    die_cpus = cpuinfo.dies_to_cpus(dies=[die], packages=[pkg])

    if not die_cpus:
        return

    # Test 1: Single CPU from a die should fail validation (incomplete die).
    single_cpu = die_cpus[0]
    cmd = f"uncore config --max-freq max --cpus {single_cpu}"
    PropsCommonCmdl.run_pepc(cmd, pman, exp_exc=Error, ignore=_IGNORE)

    # Test 2: Multiple CPUs from same die (but not all) should fail if it doesn't cover all
    # CPUs.
    if len(die_cpus) > 2:
        partial_cpus = f"{die_cpus[0]},{die_cpus[1]}"
        cmd = f"uncore config --max-freq max --cpus {partial_cpus}"
        PropsCommonCmdl.run_pepc(cmd, pman, exp_exc=Error, ignore=_IGNORE)

    # Test 3: All CPUs from a die should succeed.
    all_die_cpus = Trivial.rangify(die_cpus)
    cmd = f"uncore config --max-freq max --cpus {all_die_cpus}"
    PropsCommonCmdl.run_pepc(cmd, pman, ignore=_IGNORE)

    # Test 4: CPUs from multiple complete dies should succeed.
    if len(dies) > 1:
        die2 = dies[1]
        die2_cpus = cpuinfo.dies_to_cpus(dies=[die2], packages=[pkg])
        if die2_cpus:
            all_cpus = die_cpus + die2_cpus
            all_cpus_str = Trivial.rangify(all_cpus)
            cmd = f"uncore config --max-freq max --cpus {all_cpus_str}"
            PropsCommonCmdl.run_pepc(cmd, pman, ignore=_IGNORE)
