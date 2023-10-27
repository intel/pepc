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
import common
import props_common
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Human, YAML
from pepclibs import CPUInfo, PStates, BClock

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "PStates", "Systemctl"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        params["cpuinfo"] = cpuinfo
        params["pobj"] = pobj
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        params["cpus"] = cpuinfo.get_cpus()
        params["packages"] = cpuinfo.get_packages()
        params["cores"] = {}
        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)

        yield params

def _get_config_options(params):
    """Return dictionary of good and bad 'pepc pstates config' option values."""

    good = []
    bad = []
    options = {}

    cpu = 0
    pobj = params["pobj"]

    if pobj.prop_is_supported("min_freq", cpu):
        good += [
            "--min-freq",
            "--max-freq",
            "--min-freq --max-freq",
            "--min-freq min",
            "--max-freq min"]
        if pobj.get_prop("turbo", cpu) == "on":
            good += [
                "--max-freq max",
                "--min-freq min --max-freq max",
                "--max-freq max --min-freq min"]
        if pobj.prop_is_supported("max_eff_freq", cpu):
            good += [
                "--max-freq lfm",
                "--max-freq eff",
                "--min-freq lfm",
                "--min-freq eff"]
        if pobj.prop_is_supported("base_freq", cpu):
            good += [
                "--max-freq base",
                "--max-freq hfm",
                "--min-freq base",
                "--min-freq hfm"]

        bad += [
            "--min-freq 1000ghz",
            "--max-freq 3",
            "--min-freq maximum",
            "--min-freq max --max-freq min"]

    if pobj.prop_is_supported("min_uncore_freq", cpu):
        good += [
            "--min-uncore-freq",
            "--max-uncore-freq",
            "--min-uncore-freq --max-uncore-freq",
            "--min-uncore-freq min",
            "--max-uncore-freq max",
            "--max-uncore-freq min --max-uncore-freq max"]
        bad += ["--min-uncore-freq max --max-uncore-freq min"]

    options["freq"] = { "good" : good, "bad" : bad }

    good = []
    bad = []

    if pobj.prop_is_supported("governor", cpu):
        good += ["--governor"]
        for governor in pobj.get_cpu_prop("governors", cpu)["val"]:
            good += [f"--governor {governor}"]
        bad += ["--governor savepower"]

    if pobj.prop_is_supported("epp", cpu):
        good += ["--epp", "--epp 0", "--epp 128", "--epp performance"]
        bad += ["--epp 256", "--epp green_tree"]

    if pobj.prop_is_supported("epb", cpu):
        good += ["--epb", "--epb 0", "--epb 15", "--epb performance"]
        bad += ["--epb 16", "--epb green_tree"]

    options["config"] = { "good" : good, "bad" : bad }

    good = []
    bad = []

    if pobj.prop_is_supported("intel_pstate_mode", cpu):
        # The "off" mode is not supported when HWP is enabled.
        if pobj.get_cpu_prop("hwp", cpu)["val"] == "off":
            good += ["--intel-pstate-mode off"]

        # Note, the last mode is intentionally something else but "off", because in "off" mode many
        # options do not work. For example, switching turbo on/off does not work in the "off" mode.
        good += ["--intel-pstate-mode", "--intel-pstate-mode passive"]
        bad += ["--intel-pstate-mode Dagny"]

    if pobj.prop_is_supported("turbo", cpu):
        good += ["--turbo", "--turbo enable", "--turbo OFF"]
        bad += ["--turbo 1"]

    options["config_global"] = { "good" : good, "bad" : bad }

    return options

def test_pstates_info(params):
    """Test 'pepc pstates info' command."""

    pman = params["pman"]

    for opt in props_common.get_good_cpunum_opts(params, sname="package"):
        common.run_pepc(f"pstates info {opt}", pman)

    for opt in props_common.get_bad_cpunum_opts(params):
        common.run_pepc(f"pstates info {opt}", pman, exp_exc=Error)

    # Treat the target system as Sapphire Rapids Xeon.
    common.run_pepc("pstates info --override-cpu-model 0x8F", pman)

def _test_pstates_config_good(params):
    """Test 'pepc pstates config' command with good argument values."""

    pman = params["pman"]
    config_options = _get_config_options(params)

    for opt in config_options["freq"]["good"]:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            if "uncore" in opt and ("package" not in cpunum_opt or "core" in cpunum_opt):
                continue
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

    for opt in config_options["config"]["good"]:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

    for opt in config_options["config_global"]["good"]:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman)

def _test_pstates_config_bad(params):
    """Test 'pepc pstates config' command with bad argument values."""

    pman = params["pman"]
    config_options = _get_config_options(params)

    # Test other config options.
    for opt in config_options["freq"]["bad"]:
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in config_options["freq"]["good"]:
        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

    for opt in config_options["config_global"]["bad"]:
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in config_options["config"]["bad"]:
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

def test_pstates_config(params):
    """Test 'pepc pstates config' command."""

    _test_pstates_config_good(params)
    _test_pstates_config_bad(params)

def test_pstates_save_restore(params):
    """Test 'pepc pstates save' and 'pepc pstates restore' commands."""

    cpu = 0
    pman = params["pman"]
    pobj = params["pobj"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]

    good = ["",
            f"-o {tmp_path}/pstates.{hostname}"]

    for option in good:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"pstates save {option} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates save {option} {cpunum_opt}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    common.run_pepc(f"pstates save -o {state_path}", pman)
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
        if pname == "min_freq_hw":
            # In most cases MSR and sysfs will modify each other, but min. CPU frequency is an
            # exception. Because sysfs min. limit is min. efficient frequency (e.g., the optimal
            # point between performance and the lowest power drain), while MSRs min. limit is min.
            # operating frequency (e.g., the lowest power drain that the CPU can operate at). This
            # means that the MSR value can be different from the sysfs value, and in this case MSR
            # will not update the sysfs value. Thus, we test that the sysfs property is set first,
            # and then the MSR property. Otherwise the sysfs property will overwrite the MSR value.
            val = pobj.get_cpu_prop("min_oper_freq", cpu)["val"]
            if val is None:
                continue
        elif state[pname][0]["value"] == "on":
            val = "off"
        elif state[pname][0]["value"] == "off":
            val = "on"
        else:
            continue

        state_modified[pname] = [{"value" : val, "cpus" : cpus}]

    state_modified_path = tmp_path / f"state_modified.{hostname}"
    YAML.dump(state_modified, state_modified_path)
    common.run_pepc(f"pstates restore -f {state_modified_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    common.run_pepc(f"pstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state_modified, "restoring P-states configuration failed"

    common.run_pepc(f"pstates restore -f {state_path}", pman)
    common.run_pepc(f"pstates save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring P-states configuration failed"

def _set_freq_pairs(params, min_pname, max_pname):
    """
    Set min. and max frequencies to various values in order to verify that the 'PState' modules set
    them correctly. The arguments 'min_pname' and 'max_pname' are the frequency property names.
    """

    cpu = 0
    pobj = params["pobj"]
    sname = pobj.get_sname(min_pname)
    siblings = params["cpuinfo"].get_cpu_siblings(0, level=sname)

    min_limit = pobj.get_cpu_prop(f"{min_pname}_limit", cpu)["val"]
    max_limit = pobj.get_cpu_prop(f"{max_pname}_limit", cpu)["val"]

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
    common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_optname} {max_limit - increment} {max_optname} {max_limit}"
    common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_optname} {min_limit} {max_optname} {min_limit + increment}"
    common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

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
    if pobj.prop_is_supported("turbo", cpu):
        sname = pobj.get_sname("turbo")
        siblings = cpuinfo.get_cpu_siblings(0, level=sname)
        pobj.set_prop("turbo", "on", siblings)

    if pobj.prop_is_supported("min_freq", cpu):
        _set_freq_pairs(params, "min_freq", "max_freq")

    if pobj.prop_is_supported("min_uncore_freq", cpu):
        _set_freq_pairs(params, "min_uncore_freq", "max_uncore_freq")
