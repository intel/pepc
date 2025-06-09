#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'cstates' command."""

import pytest
import common
import props_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo, CStates
from pepclibs.CStates import ErrorTryAnotherMechanism

# If the '--mechanism' option is present, the command may fail because the mechanism may not be
# supported. Ignore these failures.
_IGNORE = {ErrorNotSupported: "--mechanism",
           ErrorTryAnotherMechanism: "--mechanism"}

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "CStates", "Systemctl"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CStates.CStates(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        params["pobj"] = pobj
        params["cpuinfo"] = cpuinfo
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus
        params["packages"] = cpuinfo.get_packages()

        params["cores"] = {}
        params["modules"] = {}
        params["dies"] = {}

        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_package_cores(package=pkg)
            params["modules"][pkg] = cpuinfo.package_to_modules(package=pkg)
            params["dies"][pkg] = cpuinfo.get_package_dies(package=pkg)

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

    for opt in props_common.get_good_cpu_opts(params, sname="package"):
        common.run_pepc(f"cstates info {opt}", pman)

    for opt in props_common.get_bad_cpu_opts(params):
        common.run_pepc(f"cstates info {opt}", pman, exp_exc=Error)

    for cstate in params["cstates"]:
        common.run_pepc(f"cstates info --cpus 0 --cstates {cstate}", pman)

    # Cover '--list-mechanisms'.
    common.run_pepc("cstates info --list-mechanisms", pman)

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
                    "--disable all"]
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
        for cpu_opt in props_common.get_good_cpu_opts(params, sname="CPU"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

        for cpu_opt in props_common.get_bad_cpu_opts(params):
            common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)

    for opt in _get_good_config_opts(params, sname="package"):
        for cpu_opt in props_common.get_good_cpu_opts(params, sname="global"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                common.run_pepc(cmd , pman, ignore=_IGNORE)

        for cpu_opt in props_common.get_bad_cpu_opts(params):
            common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)

    for opt in _get_good_config_opts(params, sname="global"):
        for cpu_opt in props_common.get_good_cpu_opts(params, sname="global"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"cstates config {opt} {cpu_opt} {mopt}"
                common.run_pepc(cmd , pman, ignore=_IGNORE)

        for cpu_opt in props_common.get_bad_cpu_opts(params):
            common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)

def test_cstates_config_bad(params):
    """Test 'pepc cstates config' command with bad options."""

    pman = params["pman"]

    for opt in _get_bad_config_opts():
        common.run_pepc(f"cstates config {opt}", pman, exp_exc=Error)

        for cpu_opt in props_common.get_good_cpu_opts(params, sname="package"):
            common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)

        for cpu_opt in props_common.get_bad_cpu_opts(params):
            common.run_pepc(f"cstates config {opt} {cpu_opt}", pman, exp_exc=Error)

        for mopt in props_common.get_mechanism_opts(params):
            common.run_pepc(f"cstates config {opt} {mopt}", pman, exp_exc=Error)
