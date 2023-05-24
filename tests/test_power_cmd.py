#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""Test module for 'pepc' project 'power' command."""

import copy
import pytest
from common import get_pman, run_pepc, build_params
from pcstates_common import is_prop_supported
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed
from pepclibs.helperlibs import Human, YAML, TestRunner
from pepclibs import CPUInfo, Power
from pepctool import _Pepc

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "Power"]

    try:
        with get_pman(hostspec, modules=emul_modules) as pman, \
             CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
             Power.Power(pman=pman, cpuinfo=cpuinfo) as pobj:
            params = build_params(pman)
            params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

            params["pobj"] = pobj
            params["pinfo"] = pobj.get_cpu_props(pobj.props, 0)

            allcpus = cpuinfo.get_cpus()
            params["cpus"] = allcpus
            params["packages"] = cpuinfo.get_packages()
            params["cores"] = {}
            for pkg in params["packages"]:
                params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

            yield params
    except ErrorNotSupported:
        pytest.skip("Data not yet available for platform.")

def _get_scope_options(params):
    """Return dictionary of good and bad scope options to be used for testing."""

    pkg0_core_ranges = Human.rangify(params['cores'][0])

    good_scope_options = [
        "",
        "--packages 0 --cpus all",
        f"--cpus 0-{params['cpus'][-1]}",
        "--packages 0 --cores all",
        f"--packages 0 --cores {pkg0_core_ranges}",
        "--packages all",
        f"--packages 0-{params['packages'][-1]}"]

    bad_scope_options = [
        f"--cpus {params['cpus'][-1] + 1}",
        f"--packages 0 --cores {params['cores'][0][-1] + 1}",
        f"--packages {params['packages'][-1] + 1}"]

    # Option '--cores' must be used with '--packages', except for 1-package systems, or single
    # socket system.
    if len(params["packages"]) == 1:
        good_scope_options += [f"--cores {pkg0_core_ranges}"]
    else:
        bad_scope_options += [f"--cores {pkg0_core_ranges}"]

    return {"good" : good_scope_options, "bad" : bad_scope_options}

def test_power_info(params):
    """
    Test 'pepc power info' command.
    """

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    for option in scope_options["good"]:
        run_pepc(f"power info {option}", pman)

    for option in scope_options["bad"]:
        run_pepc(f"power info {option}", pman, exp_exc=Error)

    # Treat the target system as Sapphire Rapids Xeon.
    run_pepc("power info --override-cpu-model 0x8F", pman)

def test_power_config(params):
    """Test 'pepc power config' command."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    good_options = []

    cfg_pnames_bool = {"-enable", "-clamp"}
    cfg_pnames_limit = {""}

    for index in range(1, 3):
        for pat in cfg_pnames_bool:
            prop = f"ppl{index}{pat}"
            valname = prop.replace("-", "_")
            val = params["pinfo"][valname][valname]
            if val == 'on':
                newval = 'off'
            else:
                newval = 'on'

            if is_prop_supported(valname, params["pinfo"]):
                good_options += [f"--{prop} {newval}", f"--{prop} {val}"]

        for pat in cfg_pnames_limit:
            prop = f"ppl{index}{pat}"
            valname = prop.replace("-", "_")
            val = params["pinfo"][valname][valname]
            newval = val - 1
            if is_prop_supported(valname, params["pinfo"]):
                good_options += [f"--{prop} {newval}", f"--{prop} {val}"]

    for option in good_options:
        for scope in scope_options["good"]:
            TestRunner.run_tool(_Pepc, _Pepc.TOOLNAME, f"power config {option} {scope}", pman,
                                warn_only={ErrorVerifyFailed : "enable"})

        for scope in scope_options["bad"]:
            run_pepc(f"power config {option} {scope}", pman, exp_exc=Error)

def _try_change_value(pname, new_val, current_val, pobj):
    """
    Tries to change the named property 'pname' to the value 'new_val'. If the value can be changed,
    returns the 'new_val', if not, returns the 'current_val'. After the call, this helper restores
    the existing value 'current_val' to the property even if can be modified.
    """

    try:
        pobj.set_prop(pname, new_val, cpus="all")
    except ErrorVerifyFailed:
        return current_val

    pobj.set_prop(pname, current_val, cpus="all")

    return new_val

def _power_generate_restore_data(state, pobj):
    """
    Generates a modified restore data template from the base 'state'. Any numeric values are
    adjusted by -1, and boolean values are swapped from 'on' to 'off' and vice versa; if
    hardware allows their modification.
    """

    new_state = copy.deepcopy(state)

    for pname in new_state:
        for pinfo in new_state[pname]:
            if pinfo["value"] == "on":
                pinfo["value"] = _try_change_value(pname, "off", "on", pobj)
            elif pinfo["value"] == "off":
                pinfo["value"] = _try_change_value(pname, "on", "off", pobj)
            elif isinstance(pinfo["value"], (int, float)):
                pinfo["value"] = pinfo["value"] - 1

    return new_state

def test_power_save_restore(params):
    """Test 'pepc power save' and 'pepc power restore' commands."""

    pman = params["pman"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]
    scope_options = _get_scope_options(params)

    good_options = [
        "",
        f"-o {tmp_path}/power.{hostname}"]

    for option in good_options:
        for scope in scope_options["good"]:
            run_pepc(f"power save {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"power save {option} {scope}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    run_pepc(f"power save -o {state_path}", pman)
    state = YAML.load(state_path)

    state_swap = _power_generate_restore_data(state, params["pobj"])
    state_swap_path = tmp_path / f"state_swap.{hostname}"
    YAML.dump(state_swap, state_swap_path)
    run_pepc(f"power restore -f {state_swap_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    run_pepc(f"power save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)

    assert read_back == state_swap, "restoring power configuration failed"

    run_pepc(f"power restore -f {state_path}", pman)
    run_pepc(f"power save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring power configuration failed"
