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

# TODO: finnish annotating.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import Final, Generator
import pytest
import common
import props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import Trivial
from pepclibs import CPUInfo, PStates
from pepclibs.PStates import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from props_cmdl_common import PropsCmdlTestParamsTypedDict
    from pepclibs.helperlibs.Exceptions import ExceptionType

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
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)
        yield props_cmdl_common.extend_params(params, pobj, cpuinfo)

def _get_good_info_opts(sname="package"):
    """Return good options for testing 'pepc pstates config'."""

    if sname == "global":
        opts = ["",
                "--turbo",
                "--intel-pstate-mode",
                "--governor",
                "--governors",
                "--governors --turbo"]
        return opts

    if sname == "package":
        opts = ["--bus-clock",
                "--epp"]
        return opts

    if sname == "die":
        opts = ["--min-uncore-freq-limit",
                "--min-uncore-freq",
                "--max-uncore-freq --max-uncore-freq-limit"]
        return opts

    if sname == "CPU":
        opts = ["--min-freq",
                "--base-freq",
                "--epp",
                "--epp --base-freq",
                "--max-turbo-freq"]
        return opts

    assert False, f"BUG: bad scope name {sname}"

def test_pstates_info(params):
    """Test 'pepc pstates info' command."""

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

def _get_good_config_freq_opts(params, sname="CPU"):
    """Return good frequency options for testing 'pepc pstates config'."""

    opts = []

    cpu = 0
    pobj = params["pobj"]

    if sname == "CPU":
        if pobj.prop_is_supported_cpu("min_freq", cpu):
            opts += ["--min-freq",
                    "--max-freq",
                    "--min-freq --max-freq",
                    "--min-freq min",
                    "--max-freq min"]

            # Note, on some platforms (e.g., ADL) max. efficiency frequency may be higher than base
            # frequency.
            if pobj.prop_is_supported_cpu("max_eff_freq", cpu):
                opts += ["--max-freq lfm",
                         "--max-freq eff",
                         "--min-freq lfm",
                         "--min-freq eff",
                         "--min-freq min"]

            if pobj.prop_is_supported_cpu("min_freq", cpu) and \
               pobj.prop_is_supported_cpu("max_freq", cpu):
                opts += ["--max-freq max",
                         "--min-freq min --max-freq max",
                         "--max-freq max --min-freq min"]

            if pobj.prop_is_supported_cpu("base_freq", cpu):
                opts += ["--max-freq base",
                        "--max-freq hfm",
                        "--min-freq base",
                        "--min-freq hfm"]
        return opts

    if sname == "die":
        if pobj.prop_is_supported_cpu("min_uncore_freq", cpu):
            opts += ["--min-uncore-freq",
                    "--max-uncore-freq",
                    "--min-uncore-freq --max-uncore-freq",
                    "--min-uncore-freq min",
                    "--max-uncore-freq max",
                    "--max-uncore-freq min --max-uncore-freq max"]

        return opts

    assert False, f"BUG: bad scope name {sname}"

def _get_bad_config_freq_opts(params):
    """Return bad frequency options for testing 'pepc pstates config'."""

    cpu = 0
    pobj = params["pobj"]

    opts = ["--min-freq 1000ghz",
            "--max-freq 3",
            "--max-freq hfm --mechanism kuku",
            "--min-freq maximum",
            "--min-freq max --max-freq min"]

    if pobj.prop_is_supported_cpu("min_uncore_freq", cpu):
        opts += ["--min-uncore-freq max --max-uncore-freq min"]

    return opts

def test_pstates_config_freq_good(params):
    """Test 'pepc pstates config' command with good frequency options."""

    pman = params["pman"]

    for opt in _get_good_config_freq_opts(params, sname="die"):
        for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=True):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"pstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
                props_cmdl_common.run_pepc(f"pstates config {opt} {cpu_opt} {mopt}", pman,
                                           exp_exc=Error)

    for opt in _get_good_config_freq_opts(params, sname="CPU"):
        for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=True):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"pstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
                props_cmdl_common.run_pepc(f"pstates config {opt} {cpu_opt} {mopt}", pman,
                                           exp_exc=Error)

def test_pstates_config_freq_bad(params):
    """Test 'pepc pstates config' command with bad frequency options."""

    pman = params["pman"]

    for opt in _get_bad_config_freq_opts(params):
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_freq_opts(params):
        for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
            props_cmdl_common.run_pepc(f"pstates config {opt} {cpu_opt}", pman, exp_exc=Error)

def _get_good_config_opts(params, sname="package"):
    """Return good options for testing 'pepc pstates config'."""

    cpu = 0
    pobj = params["pobj"]
    opts = []

    if sname == "global":
        if pobj.prop_is_supported_cpu("intel_pstate_mode", cpu):
            # The "off" mode is not supported when HWP is enabled.
            if pobj.get_cpu_prop("hwp", cpu)["val"] == "off":
                opts += ["--intel-pstate-mode off"]

            # Note, the last mode is intentionally something else but "off", because in "off" mode
            # many options do not work. For example, switching turbo on/off does not work in the
            # "off" mode.
            opts += ["--intel-pstate-mode", "--intel-pstate-mode passive"]

        if pobj.prop_is_supported_cpu("turbo", cpu):
            opts += ["--turbo", "--turbo enable", "--turbo OFF"]

        return opts

    if pobj.prop_is_supported_cpu("governor", cpu):
        opts += ["--governor"]
        for governor in pobj.get_cpu_prop("governors", cpu)["val"]:
            opts += [f"--governor {governor}"]

    if pobj.prop_is_supported_cpu("epp", cpu):
        opts += ["--epp", "--epp 0", "--epp 128", "--epp performance"]

    if pobj.prop_is_supported_cpu("epb", cpu):
        opts += ["--epb", "--epb 0", "--epb 15", "--epb performance"]

    return opts

def _get_bad_config_opts(params, sname="package"):
    """Return bad options for testing 'pepc pstates config'."""

    cpu = 0
    pobj = params["pobj"]
    opts = []

    if sname == "global":
        if pobj.prop_is_supported_cpu("intel_pstate_mode", cpu):
            opts += ["--intel-pstate-mode Dagny"]

        if pobj.prop_is_supported_cpu("turbo", cpu):
            opts += ["--turbo 1"]

        return opts

    if pobj.prop_is_supported_cpu("governor", cpu):
        opts += ["--governor savepower"]

    if pobj.prop_is_supported_cpu("epp", cpu):
        opts += ["--epp 256", "--epp green_tree"]

    if pobj.prop_is_supported_cpu("epb", cpu):
        opts += ["--epb 16", "--epb green_tree"]

    return opts

def test_pstates_config_good(params):
    """Test 'pepc pstates config' command with good options (excluding frequency)."""

    pman = params["pman"]

    for opt in _get_good_config_opts(params, sname="CPU"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="CPU"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_opts(params, sname="global"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

def test_pstates_config_bad(params):
    """Test 'pepc pstates config' command with bad options (excluding frequency)."""

    pman = params["pman"]

    for opt in _get_bad_config_opts(params, sname="package"):
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_bad_config_opts(params, sname="global"):
        props_cmdl_common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

def _set_freq_pairs(params, min_pname, max_pname):
    """
    Set min. and max frequencies to various values in order to verify that the 'PState' modules set
    them correctly. The arguments 'min_pname' and 'max_pname' are the frequency property names.
    """

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]

    if "uncore" in min_pname:
        bclk = pobj.get_cpu_prop("bus_clock", cpu)["val"]
        if not bclk:
            return

        min_limit = pobj.get_cpu_prop(f"{min_pname}_limit", cpu)["val"]
        max_limit = pobj.get_cpu_prop(f"{max_pname}_limit", cpu)["val"]
        if not min_limit or not max_limit:
            return

        delta = (max_limit - min_limit) // 4
        delta -= delta % bclk

        freq0 = min_limit
        freq1 = min_limit + delta
        freq2 = max_limit - delta
        freq3 = max_limit
    else:
        pvinfo = pobj.get_cpu_prop("frequencies", cpu)
        if pvinfo["val"] is None:
            return

        frequencies = pvinfo["val"]
        if len(frequencies) < 2:
            return

        freq0 = frequencies[0]
        freq1 = frequencies[1]
        freq2 = frequencies[-2]
        freq3 = frequencies[-1]

    min_opt = f"--{min_pname.replace('_', '-')}"
    max_opt = f"--{max_pname.replace('_', '-')}"

    sname = pobj.get_sname(min_pname)
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

def test_pstates_frequency_set_order(params):
    """
    Test min. and max frequency set order. We do not know how the systems min. and max frequencies
    are configured, so we have to be careful when setting min. and max frequency simultaneously.

    See 'PStates._validate_and_set_freq()' docstring, for more information.
    """

    cpu = 0
    cpuinfo = params["cpuinfo"]
    pobj = params["pobj"]

    if cpuinfo.info["vendor"] != "GenuineIntel":
        # BClock is only supported on "GenuineIntel" CPU vendors.
        return

    # When Turbo is disabled the max frequency may be limited.
    if pobj.prop_is_supported_cpu("turbo", cpu):
        sname = pobj.get_sname("turbo")
        siblings = cpuinfo.get_cpu_siblings(0, sname=sname)
        pobj.set_prop_cpus("turbo", "on", siblings)

    if pobj.prop_is_supported_cpu("min_freq", cpu):
        _set_freq_pairs(params, "min_freq", "max_freq")

    if pobj.prop_is_supported_cpu("min_uncore_freq", cpu):
        _set_freq_pairs(params, "min_uncore_freq", "max_uncore_freq")
