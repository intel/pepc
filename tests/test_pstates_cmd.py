#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'pstates' command."""

import copy
import pytest
from common import get_pman, run_pepc, build_params
from props_common import get_siblings, is_prop_supported
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Human, YAML
from pepclibs import CPUInfo, PStates, BClock

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "PStates", "Systemctl"]

    with get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:
        params = build_params(pman)
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        params["cpuinfo"] = cpuinfo
        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)
        params["siblings"] = get_siblings(cpuinfo, cpu=0)

        params["psobj"] = psobj

        cpu0_pinfo = {}
        for pname in psobj.props:
            cpu0_pinfo[pname] = psobj.get_cpu_prop(pname, 0)["val"]
        params["cpu0_pinfo"] = cpu0_pinfo

        yield params

def _get_scope_options(params):
    """Return dictionary of good and bad scope options to be used for testing."""

    pkg0_core_ranges = Human.rangify(params['cores'][0])

    good_options = [
        "",
        "--packages 0 --cpus all",
        f"--cpus 0-{params['cpus'][-1]}",
        "--packages 0 --cores all",
        f"--packages 0 --cores {pkg0_core_ranges}",
        "--packages all",
        f"--packages 0-{params['packages'][-1]}"]

    bad_options = [
        f"--cpus {params['cpus'][-1] + 1}",
        f"--packages 0 --cores {params['cores'][0][-1] + 1}",
        f"--packages {params['packages'][-1] + 1}"]

    # Option '--cores' must be used with '--packages', except for 1-package systems, or single
    # socket system.
    if len(params["packages"]) == 1:
        good_options += [f"--cores {pkg0_core_ranges}"]
    else:
        bad_options += [f"--cores {pkg0_core_ranges}"]

    good_global_options = [
        "",
        "--cpus all",
        "--packages all",
        f"--cpus  0-{params['cpus'][-1]}"]

    return {"good" : good_options, "bad" : bad_options, "good_global" : good_global_options}

def _get_config_options(params):
    """Return dictionary of good and bad 'pepc pstates config' option values."""

    options = {}

    good_options = []
    bad_options = []

    if is_prop_supported("min_freq", params["cpu0_pinfo"]):
        good_options += [
            "--min-freq",
            "--max-freq",
            "--min-freq --max-freq",
            "--min-freq min",
            "--max-freq min"]
        if is_prop_supported("turbo", params["cpu0_pinfo"]) and \
            params["cpu0_pinfo"]["turbo"] == "on":
            good_options += [
                "--max-freq max",
                "--min-freq min --max-freq max",
                "--max-freq max --min-freq min"]
        if is_prop_supported("max_eff_freq", params["cpu0_pinfo"]):
            good_options += [
                "--max-freq lfm",
                "--max-freq eff",
                "--min-freq lfm",
                "--min-freq eff"]
        if is_prop_supported("base_freq", params["cpu0_pinfo"]):
            good_options += [
                "--max-freq base",
                "--max-freq hfm",
                "--min-freq base",
                "--min-freq hfm"]

        bad_options += [
            "--min-freq 1000ghz",
            "--max-freq 3",
            "--min-freq maximum",
            "--min-freq max --max-freq min"]

    if is_prop_supported("min_uncore_freq", params["cpu0_pinfo"]):
        good_options += [
            "--min-uncore-freq",
            "--max-uncore-freq",
            "--min-uncore-freq --max-uncore-freq",
            "--min-uncore-freq min",
            "--max-uncore-freq max",
            "--max-uncore-freq min --max-uncore-freq max"]
        bad_options += ["--min-uncore-freq max --max-uncore-freq min"]

    options["freq"] = { "good" : good_options, "bad" : bad_options }

    good_options = []
    bad_options = []

    if is_prop_supported("governor", params["cpu0_pinfo"]):
        good_options += ["--governor"]
        for governor in params["cpu0_pinfo"]["governors"]:
            good_options += [f"--governor {governor}"]
        bad_options += ["--governor savepower"]

    if is_prop_supported("epp", params["cpu0_pinfo"]):
        good_options += ["--epp", "--epp 0", "--epp 128", "--epp performance"]
        bad_options += ["--epp 256", "--epp green_tree"]

    if is_prop_supported("epb", params["cpu0_pinfo"]):
        good_options += ["--epb", "--epb 0", "--epb 15", "--epb performance"]
        bad_options += ["--epb 16", "--epb green_tree"]

    options["config"] = { "good" : good_options, "bad" : bad_options }

    good_options = []
    bad_options = []

    if is_prop_supported("intel_pstate_mode", params["cpu0_pinfo"]):
        # The "off" mode is not supported when HWP is enabled.
        if is_prop_supported("hwp", params["cpu0_pinfo"]) and params["cpu0_pinfo"]["hwp"] == "off":
            good_options += ["--intel-pstate-mode off"]

        # Note, the last mode is intentionally something else but "off", because in "off" mode many
        # options do not work. For example, switching turbo on/off does not work in the "off" mode.
        good_options += ["--intel-pstate-mode",
                         "--intel-pstate-mode passive"]

        bad_options += ["--intel-pstate-mode Dagny"]

    if is_prop_supported("turbo", params["cpu0_pinfo"]):
        good_options += ["--turbo", "--turbo enable", "--turbo OFF"]
        bad_options += ["--turbo 1"]

    options["config_global"] = { "good" : good_options, "bad" : bad_options }

    return options

def test_pstates_info(params):
    """Test 'pepc pstates info' command."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)

    for option in scope_options["good"]:
        run_pepc(f"pstates info {option}", pman)

    for option in scope_options["bad"]:
        run_pepc(f"pstates info {option}", pman, exp_exc=Error)

    # Treat the target system as Sapphire Rapids Xeon.
    run_pepc("pstates info --override-cpu-model 0x8F", pman)

def _test_pstates_config_good(params):
    """Test 'pepc pstates config' command with good argument values."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)
    config_options = _get_config_options(params)

    for option in config_options["freq"]["good"]:
        for scope in scope_options["good"]:
            if "uncore" in option and ("package" not in scope or "core" in scope):
                continue
            run_pepc(f"pstates config {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["config"]["good"]:
        for scope in scope_options["good"]:
            run_pepc(f"pstates config {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["config_global"]["good"]:
        for scope in scope_options["good_global"]:
            run_pepc(f"pstates config {option} {scope}", pman)

def _test_pstates_config_bad(params):
    """Test 'pepc pstates config' command with bad argument values."""

    pman = params["pman"]
    scope_options = _get_scope_options(params)
    config_options = _get_config_options(params)

    # Test other config options.
    for option in config_options["freq"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

    for option in config_options["freq"]["good"]:
        for scope in scope_options["bad"]:
            run_pepc(f"pstates config {option} {scope}", pman, exp_exc=Error)

    for option in config_options["config_global"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

    for option in config_options["config"]["bad"]:
        run_pepc(f"pstates config {option}", pman, exp_exc=Error)

def test_pstates_config(params):
    """Test 'pepc pstates config' command."""

    _test_pstates_config_good(params)
    _test_pstates_config_bad(params)

def test_pstates_save_restore(params):
    """Test 'pepc pstates save' and 'pepc pstates restore' commands."""

    pman = params["pman"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]
    scope_options = _get_scope_options(params)

    good_options = [
        "",
        f"-o {tmp_path}/pstates.{hostname}"]

    for option in good_options:
        for scope in scope_options["good"]:
            run_pepc(f"pstates save {option} {scope}", pman)

        for scope in scope_options["bad"]:
            run_pepc(f"pstates save {option} {scope}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    run_pepc(f"pstates save -o {state_path}", pman)
    state = YAML.load(state_path)

    cpus = Human.rangify(params["cpus"])
    state_modified = copy.deepcopy(state)
    for pname in state_modified.keys():
        if pname in ("min_freq", "max_freq"):
            val = state["min_freq"][0]["value"]
        elif pname.endswith("_uncore_freq"):
            val = state["min_uncore_freq"][0]["value"]
        elif pname in ("epb", "epb_hw"):
            # Restoring 'epb' will also modify 'epb_hw' and vise versa. Thus, if one is changed,
            # both have to be changed.
            val = int((state[pname][0]["value"] + 1) / 2)
        if pname == "min_freq_hw" and is_prop_supported("min_oper_freq", params["cpu0_pinfo"]):
            # In most cases MSR and sysfs will modify each other, but min. CPU frequency is an
            # exception. Because sysfs min. limit is min. efficient frequency (e.g., the optimal
            # point between performance and the lowest power drain), while MSRs min. limit is min.
            # operating frequency (e.g., the lowest power drain that the CPU can operate at). This
            # means that the MSR value can be different from the sysfs value, and in this case MSR
            # will not update the sysfs value. Thus, we test that the sysfs property is set first,
            # and then the MSR property. Otherwise the sysfs property will overwrite the MSR value.
            val = params["cpu0_pinfo"]["min_oper_freq"]
        elif state[pname][0]["value"] == "on":
            val = "off"
        elif state[pname][0]["value"] == "off":
            val = "on"
        else:
            continue

        state_modified[pname] = [{"value" : val, "cpus" : cpus}]

    state_modified_path = tmp_path / f"state_modified.{hostname}"
    YAML.dump(state_modified, state_modified_path)
    run_pepc(f"pstates restore -f {state_modified_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    run_pepc(f"pstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state_modified, "restoring P-states configuration failed"

    run_pepc(f"pstates restore -f {state_path}", pman)
    run_pepc(f"pstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring P-states configuration failed"

def _set_freq_pairs(params, min_pname, max_pname):
    """
    Set min. and max frequencies to various values in order to verify that the 'PState' modules set
    them correctly. The arguments 'min_pname' and 'max_pname' are the frequency property names.
    """

    sname = params["psobj"].get_sname(min_pname)
    siblings = params["siblings"][sname]

    min_limit = params["cpu0_pinfo"][f"{min_pname}_limit"]
    max_limit = params["cpu0_pinfo"][f"{max_pname}_limit"]

    bclk_MHz = BClock.get_bclk(params["pman"], cpu=0)
    bclk_Hz = int(bclk_MHz * 1000000)
    a_quarter = int((max_limit - min_limit) / 4)
    increment = a_quarter - a_quarter % bclk_Hz

    pman = params["pman"]
    min_optname = f"--{min_pname.replace('_', '-')}"
    max_optname = f"--{max_pname.replace('_', '-')}"
    cpus_opt = f"--cpus {Human.rangify(siblings)}"

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_optname} {min_limit} {max_optname} {min_limit + increment}"
    run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_optname} {max_limit - increment} {max_optname} {max_limit}"
    run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_optname} {min_limit} {max_optname} {min_limit + increment}"
    run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

def test_pstates_frequency_set_order(params):
    """
    Test min. and max frequency set order. We do not know how the systems min. and max frequencies
    are configured, so we have to be careful when setting min. and max frequency simultaneously.

    See 'PStates._validate_and_set_freq()' docstring, for more information.
    """

    if params["cpuinfo"].info["vendor"] != "GenuineIntel":
        # BClock is only supported on "GenuineIntel" CPU vendors.
        return

    # When Turbo is disabled the max frequency may be limited.
    if is_prop_supported("turbo", params["cpu0_pinfo"]):
        sname = params["psobj"].get_sname("turbo")
        cpus = params["siblings"][sname]
        params["psobj"].set_prop("turbo", "on", cpus)

    if is_prop_supported("min_freq", params["cpu0_pinfo"]):
        _set_freq_pairs(params, "min_freq", "max_freq")

    if is_prop_supported("min_uncore_freq", params["cpu0_pinfo"]):
        _set_freq_pairs(params, "min_uncore_freq", "max_uncore_freq")
