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
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import Human, YAML
from pepclibs import CPUInfo, PStates

# If the '--mechanism' option is present, the command may fail because the mechanism may not be
# supported. Ignore these failures.
_IGNORE = { ErrorNotSupported : "--mechanism" }

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
        params["modules"] = {}
        params["dies"] = {}

        for pkg in params["packages"]:
            params["cores"][pkg] = cpuinfo.get_cores(package=pkg)
            params["modules"][pkg] = cpuinfo.package_to_modules(package=pkg)
            params["dies"][pkg] = cpuinfo.get_dies(package=pkg)

        yield params

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
        for mopt in props_common.get_mechanism_opts(params):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="CPU"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="module"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="die"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_info_opts(sname="die"):
        for mopt in props_common.get_mechanism_opts(params):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="die"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_info_opts(sname="package"):
        for mopt in props_common.get_mechanism_opts(params):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_info_opts(sname="global"):
        for mopt in props_common.get_mechanism_opts(params):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates info {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for cpunum_opt in props_common.get_bad_cpunum_opts(params):
        common.run_pepc(f"pstates info {cpunum_opt}", pman, exp_exc=Error)

    # Cover '--override-cpu-model', use Sapphire Rapids Xeon CPU model number.
    common.run_pepc("pstates info --override-cpu-model 0x8F", pman)
    # Cover '--list-mechanisms'.
    common.run_pepc("pstates info --list-mechanisms", pman)

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

            maxfreq = props_common.get_max_cpu_freq(params, cpu)
            opts += [f"--max-freq {maxfreq}",
                    f"--min-freq min --max-freq {maxfreq}",
                    f"--max-freq {maxfreq} --min-freq min"]

            if pobj.prop_is_supported_cpu("max_eff_freq", cpu):
                opts += ["--max-freq lfm",
                        "--max-freq eff",
                        "--min-freq lfm",
                        "--min-freq eff"]
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
        for mopt in props_common.get_mechanism_opts(params, allow_readonly=True):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="die"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_bad_cpunum_opts(params):
                common.run_pepc(f"pstates config {opt} {cpunum_opt} {mopt}", pman, exp_exc=Error)

    for opt in _get_good_config_freq_opts(params, sname="CPU"):
        for mopt in props_common.get_mechanism_opts(params, allow_readonly=True):
            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="CPU"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="module"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="die"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

            for cpunum_opt in props_common.get_bad_cpunum_opts(params):
                common.run_pepc(f"pstates config {opt} {cpunum_opt} {mopt}", pman, exp_exc=Error)

def test_pstates_config_freq_bad(params):
    """Test 'pepc pstates config' command with bad frequency options."""

    pman = params["pman"]

    for opt in _get_bad_config_freq_opts(params):
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_good_config_freq_opts(params):
        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates config {opt} {cpunum_opt}", pman, exp_exc=Error)

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
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="CPU"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_opts(params, sname="module"):
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="module"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_opts(params, sname="die"):
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="die"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_opts(params, sname="package"):
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

    for opt in _get_good_config_opts(params, sname="global"):
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
            for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
                cmd = f"pstates config {opt} {cpunum_opt} {mopt}"
                common.run_pepc(cmd, pman, ignore=_IGNORE)

def test_pstates_config_bad(params):
    """Test 'pepc pstates config' command with bad options (excluding frequency)."""

    pman = params["pman"]

    for opt in _get_bad_config_opts(params, sname="package"):
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

    for opt in _get_bad_config_opts(params, sname="global"):
        common.run_pepc(f"pstates config {opt}", pman, exp_exc=Error)

def test_pstates_save_restore(params):
    """Test 'pepc pstates save' and 'pepc pstates restore' commands."""

    pman = params["pman"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]

    opts = ("", f"-o {tmp_path}/pstates.{hostname}")

    for opt in opts:
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="CPU"):
            common.run_pepc(f"pstates save {opt} {cpunum_opt}", pman)
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="module"):
            common.run_pepc(f"pstates save {opt} {cpunum_opt}", pman)
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="package"):
            common.run_pepc(f"pstates save {opt} {cpunum_opt}", pman)
        for cpunum_opt in props_common.get_good_cpunum_opts(params, sname="global"):
            common.run_pepc(f"pstates save {opt} {cpunum_opt}", pman)

        for cpunum_opt in props_common.get_bad_cpunum_opts(params):
            common.run_pepc(f"pstates save {opt} {cpunum_opt}", pman, exp_exc=Error)

    state_path = tmp_path / f"state.{hostname}"
    common.run_pepc(f"pstates save -o {state_path}", pman)
    state = YAML.load(state_path)

    state_modified = copy.deepcopy(state)
    for pname in state_modified.keys():
        if pname in ("min_freq", "max_freq"):
            val = state["min_freq"][0]["value"]
        elif pname.endswith("_uncore_freq"):
            val = state["min_uncore_freq"][0]["value"]
        elif state[pname][0]["value"] == "on":
            val = "off"
        elif state[pname][0]["value"] == "off":
            val = "on"
        else:
            continue

        yaml_dict = state_modified[pname][0]
        yaml_dict["value"] = val

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
    siblings = params["cpuinfo"].get_cpu_siblings(0, level=sname)
    cpus_opt = f"--cpus {Human.rangify(siblings)}"

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
    common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [-------------------------------------------------------- Min -------------------- Max]
    freq_opts = f"{min_opt} {freq2} {max_opt} {freq3}"
    common.run_pepc(f"pstates config {cpus_opt} {freq_opts}", pman)

    # [Min ------------------ Max ----------------------------------------------------------]
    freq_opts = f"{min_opt} {freq0} {max_opt} {freq1}"
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
    if pobj.prop_is_supported_cpu("turbo", cpu):
        sname = pobj.get_sname("turbo")
        siblings = cpuinfo.get_cpu_siblings(0, level=sname)
        pobj.set_prop_cpus("turbo", "on", siblings)

    if pobj.prop_is_supported_cpu("min_freq", cpu):
        _set_freq_pairs(params, "min_freq", "max_freq")

    if pobj.prop_is_supported_cpu("min_uncore_freq", cpu):
        _set_freq_pairs(params, "min_uncore_freq", "max_uncore_freq")
