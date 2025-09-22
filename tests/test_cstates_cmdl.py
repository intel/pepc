#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test 'pepc cstates' command-line options."""

# TODO: finnish annotating.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
import common
import props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo, CStates
from pepclibs.CStates import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Final, Generator, cast
    from props_cmdl_common import PropsCmdlTestParamsTypedDict
    from pepclibs.helperlibs.Exceptions import ExceptionType

    class TestParamsTypedDict(PropsCmdlTestParamsTypedDict, total=False):
        """
        The test parameters dictionary with keys used by the common part of the command-line
        property tests.

        Attributes:
            cstates: A list of supported requestable C-state names.
        """

        cstates: list[str]

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
         CStates.CStates(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)
        params = props_cmdl_common.extend_params(params, pobj, cpuinfo)

        if typing.TYPE_CHECKING:
            params = cast(TestParamsTypedDict, params)

        allcpus = params["cpus"]
        medidx = int(len(allcpus)/2)
        testcpus = [allcpus[0], allcpus[medidx], allcpus[-1]]
        params["cstates"] = []

        if pobj.prop_is_supported_cpu("idle_driver", 0):
            for _, csinfo in pobj.get_cstates_info(cpus=(testcpus[0],)):
                for csname in csinfo:
                    params["cstates"].append(csname)

        yield params

def test_cstates_info(params):
    """Test 'pepc cstates info' command."""

    pman = params["pman"]

    for opt in props_cmdl_common.get_good_optarget_opts(params, sname="package"):
        props_cmdl_common.run_pepc(f"cstates info {opt}", pman)

    for opt in props_cmdl_common.get_bad_optarget_opts(params):
        props_cmdl_common.run_pepc(f"cstates info {opt}", pman, exp_exc=Error)

    for cstate in params["cstates"]:
        props_cmdl_common.run_pepc(f"cstates info --cpus 0 --cstates {cstate}", pman)

    # Cover '--list-mechanisms'.
    props_cmdl_common.run_pepc("cstates info --list-mechanisms", pman)

def _get_good_config_opts(params, sname="package"):
    """Return good options for testing 'pepc cstates config'."""

    cpu = 0
    opts = []
    pobj = params["pobj"]

    if sname == "global":
        if pobj.prop_is_supported_cpu("governor", cpu):
            opts += ["--governor"]
            for governor in pobj.get_cpu_prop("governors", cpu)["val"]:
                opts += [f"--governor {governor}"]
        return opts

    if sname == "package":
        if pobj.prop_is_supported_cpu("c1e_autopromote", cpu):
            opts += ["--c1e-autopromote",
                    "--c1e-autopromote on",
                    "--c1e-autopromote OFF"]

        if pobj.prop_is_supported_cpu("cstate_prewake", cpu):
            opts += ["--cstate-prewake",
                    "--cstate-prewake on",
                    "--cstate-prewake OFF"]

        if pobj.prop_is_supported_cpu("c1_demotion", cpu):
            opts += ["--c1-demotion",
                    "--c1-demotion on",
                    "--c1-demotion OFF"]

        if pobj.prop_is_supported_cpu("c1_undemotion", cpu):
            opts += ["--c1-undemotion",
                    "--c1-undemotion on",
                    "--c1-undemotion OFF"]

        if pobj.prop_is_supported_cpu("pkg_cstate_limit", cpu):
            opts += ["--pkg-cstate-limit"]
            lock = pobj.get_cpu_prop("pkg_cstate_limit_lock", cpu)["val"]
            if lock == "off":
                limit = pobj.get_cpu_prop("pkg_cstate_limit", cpu)["val"]
                opts += [f"--pkg-cstate-limit {limit.upper()}",
                        f"--pkg-cstate-limit {limit.lower()}"]
        return opts

    if sname == "CPU":
        if pobj.prop_is_supported_cpu("idle_driver", cpu):
            opts += ["--enable all",
                    "--enable all --disable POLL",
                    "--disable all",
                    "--disable all --enable POLL"]
        return opts

    assert False, f"BUG: bad scope name {sname}"

def _get_bad_config_opts():
    """Return bad options for testing 'pepc cstates config'."""

    opts = ["--enable CC0",
            "--disable CC0",
            "--cstate-prewake meh",
            "--governor reardenmetal"]

    return opts

def test_cstates_config_good(params):
    """Test 'pepc cstates config' command with bad options."""

    pman = params["pman"]

    for opt in _get_good_config_opts(params, sname="CPU"):
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="CPU"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
        for opt in _get_good_config_opts(params, sname="package"):
            for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd , pman, ignore=_IGNORE)
        break

    for mopt in props_cmdl_common.get_mechanism_opts(params, allow_readonly=False):
        for opt in _get_good_config_opts(params, sname="global"):
            for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="global"):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                props_cmdl_common.run_pepc(cmd , pman, ignore=_IGNORE)
        break

def test_cstates_config_bad(params):
    """Test 'pepc cstates config' command with bad options."""

    pman = params["pman"]

    for opt in _get_bad_config_opts():
        props_cmdl_common.run_pepc(f"cstates config {opt}", pman, exp_exc=Error)

    for opt in _get_bad_config_opts():
        for cpu_opt in props_cmdl_common.get_good_optarget_opts(params, sname="package"):
            props_cmdl_common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)
        break

    for cpu_opt in props_cmdl_common.get_bad_optarget_opts(params):
        props_cmdl_common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)
