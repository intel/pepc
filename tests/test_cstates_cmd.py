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

import copy
import pytest
import common
import props_common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import YAML
from pepclibs import CPUInfo, CStates

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
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

        medidx = int(len(allcpus)/2)
        testcpus = [allcpus[0], allcpus[medidx], allcpus[-1]]
        params["cstates"] = []

        if pobj.prop_is_supported("idle_driver", 0):
            for _, csinfo in pobj.get_cstates_info(cpus=(testcpus[0],)):
                for csname in csinfo:
                    params["cstates"].append(csname)

        yield params

def test_cstates_info(params):
    """Test 'pepc cstates info' command."""

    pman = params["pman"]

    for opt in props_common.get_good_cpunum_opts(params, sname="package"):
        common.run_pepc(f"cstates info {opt}", pman)

    for opt in props_common.get_bad_cpunum_opts(params):
        common.run_pepc(f"cstates info {opt}", pman, exp_exc=Error)

    for cstate in params["cstates"]:
        common.run_pepc(f"cstates info --cpus 0 --cstates {cstate}", pman)

    # Treat the target system as Sapphire Rapids Xeon.
    common.run_pepc("cstates info --override-cpu-model 0x8F", pman)

def test_cstates_config(params):
    """Test 'pepc cstates config' command."""

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]

    good = []
    if pobj.prop_is_supported("idle_driver", cpu):
        good += ["--enable all",
                         "--disable all",
                         f"--enable {params['cstates'][-1]}",
                         f"--disable {params['cstates'][-1]}"]

    if pobj.prop_is_supported("pkg_cstate_limit", cpu):
        good += ["--pkg-cstate-limit"]
        lock = pobj.get_cpu_prop("pkg_cstate_limit_lock", cpu)["val"]
        if lock == "off":
            limit = pobj.get_cpu_prop("pkg_cstate_limit", cpu)["val"]
            good += [f"--pkg-cstate-limit {limit.upper()}", f"--pkg-cstate-limit {limit.lower()}"]
    if pobj.prop_is_supported("c1_demotion", cpu):
        good += ["--c1-demotion", "--c1-demotion on", "--c1-demotion OFF"]
    if pobj.prop_is_supported("c1_undemotion", cpu):
        good += ["--c1-undemotion", "--c1-undemotion on", "--c1-undemotion OFF"]
    if pobj.prop_is_supported("c1e_autopromote", cpu):
        good += ["--c1e-autopromote", "--c1e-autopromote on", "--c1e-autopromote OFF"]
    if pobj.prop_is_supported("cstate_prewake", cpu):
        good += ["--cstate-prewake", "--cstate-prewake on", "--cstate-prewake OFF"]

    for opt in good:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"cstates config {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"cstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

    bad = [
        "--enable CC0",
        "--disable CC0"
        "--cstate-prewake meh"]

    for opt in bad:
        common.run_pepc(f"cstates config {opt}", pman, exp_exc=Error)

        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"cstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"cstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

    # Test without "cpunum" options.
    good = []
    bad = []

    if pobj.prop_is_supported("governor", cpu):
        good += ["--governor"]
        for governor in pobj.get_cpu_prop("governors", cpu)["val"]:
            good += [f"--governor {governor}"]
        bad += ["--governor reardenmetal"]

    for opt in good:
        common.run_pepc(f"cstates config {opt}", pman)
    for opt in bad:
        common.run_pepc(f"cstates config {opt}", pman, exp_exc=Error)

def test_cstates_save_restore(params):
    """Test 'pepc cstates save' and 'pepc cstates restore' commands."""

    pman = params["pman"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]

    good = [
        "",
        f"-o {tmp_path}/cstates.{hostname}"]

    for opt in good:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"cstates save {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"cstates save {opt} {cpunum_opt}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    common.run_pepc(f"cstates save -o {state_path}", pman)
    state = YAML.load(state_path)

    state_swap = copy.deepcopy(state)
    for pinfos in state_swap.values():
        for pinfo in pinfos:
            if pinfo["value"] == "on":
                pinfo["value"] = "off"
            elif pinfo["value"] == "off":
                pinfo["value"] = "on"

    state_swap_path = tmp_path / f"state_swap.{hostname}"
    YAML.dump(state_swap, state_swap_path)
    common.run_pepc(f"cstates restore -f {state_swap_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    common.run_pepc(f"cstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state_swap, "restoring C-states configuration failed"

    common.run_pepc(f"cstates restore -f {state_path}", pman)
    common.run_pepc(f"cstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring C-states configuration failed"
