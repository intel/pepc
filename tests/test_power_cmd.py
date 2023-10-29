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
import common
import props_common
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed, ErrorNotSupported
from pepclibs.helperlibs import YAML
from pepclibs import CPUInfo, Power

# If the '--mechanism' option is present, the command may fail because the mechanism may not be
# supported. Ignore these failurs.
_IGNORE = { ErrorNotSupported : "--mechanism" }

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "Power"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         Power.Power(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        params["pobj"] = pobj
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

        yield params

def test_power_info(params):
    """Test 'pepc power info' command."""

    pman = params["pman"]

    for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
        for mopt in props_common.get_mechanism_opts(params):
            cmd = f"power info {cpunum_opt} {mopt}"
            common.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpunum_opt in props_common.get_bad_cpunum_opts(params):
        common.run_pepc(f"power info {cpunum_opt}", pman, exp_exc=Error)

    # Cover '--override-cpu-model', use Sapphire Rapids Xeon CPU model number.
    common.run_pepc("power info --override-cpu-model 0x8F", pman)
    # Cover '--list-mechanisms'.
    common.run_pepc("power info --list-mechanisms", pman)

def _get_good_config_opts(params):
    """Return good options for testing 'pepc power config'."""

    cpu = 0
    pobj = params["pobj"]
    opts = []

    for opt in ("ppl1-clamp", "ppl2-clamp"):
        pname = opt.replace("-", "_")
        val = pobj.get_cpu_prop(pname, cpu)["val"]
        if val is None:
            continue

        if val == 'on':
            newval = 'off'
        else:
            newval = 'on'

        opts += [f"--{opt} {newval}",
                 f"--{opt} {val}"]

    for opt in ("ppl1", "ppl2"):
        pname = opt.replace("-", "_")
        val = pobj.get_cpu_prop(pname, cpu)["val"]
        if val is None:
            continue

        newval = val - 1
        opts += [f"--{opt} {newval}",
                 f"--{opt} {val}"]

    return opts

def test_power_config(params):
    """Test 'pepc power config' command."""

    pman = params["pman"]
    ignore = _IGNORE.copy()
    ignore[ErrorVerifyFailed] = "enable"

    for opt in  _get_good_config_opts(params):
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"power config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=ignore)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"power config {opt} {cpunum_opt}", pman, exp_exc=Error)

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

    opts = ("", f"-o {tmp_path}/power.{hostname}")
    for opt in opts:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"power save {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"power save {opt} {cpunum_opt}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    common.run_pepc(f"power save -o {state_path}", pman)
    state = YAML.load(state_path)

    state_swap = _power_generate_restore_data(state, params["pobj"])
    state_swap_path = tmp_path / f"state_swap.{hostname}"
    YAML.dump(state_swap, state_swap_path)
    common.run_pepc(f"power restore -f {state_swap_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    common.run_pepc(f"power save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)

    assert read_back == state_swap, "restoring power configuration failed"

    common.run_pepc(f"power restore -f {state_path}", pman)
    common.run_pepc(f"power save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring power configuration failed"
