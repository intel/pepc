#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'pmqos' command."""

import copy
import pytest
import common
import props_common
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import YAML
from pepclibs import CPUInfo, PMQoS

# If the '--mechanism' option is present, the command may fail because the mechanism may not be
# supported. Ignore these failures.
_IGNORE = {ErrorNotSupported : "--mechanism"}

@pytest.fixture(name="params", scope="module")
def get_params(hostspec, tmp_path_factory):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo", "PMQoS"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PMQoS.PMQoS(pman=pman, cpuinfo=cpuinfo) as pobj:
        params = common.build_params(pman)

        params["pobj"] = pobj
        params["cpuinfo"] = cpuinfo
        params["tmp_path"] = tmp_path_factory.mktemp(params["hostname"])

        allcpus = cpuinfo.get_cpus()
        params["cpus"] = allcpus

        yield params

def test_pmqos_info(params):
    """Test 'pepc pmqos info' command."""

    pman = params["pman"]

    common.run_pepc(f"pmqos info", pman)
    common.run_pepc(f"pmqos info --cpus 0", pman)

    # Cover '--override-cpu-model', use Sapphire Rapids Xeon CPU model number.
    common.run_pepc("pmqos info --override-cpu-model 0x8F", pman)
    # Cover '--list-mechanisms'.
    common.run_pepc("pmqos info --list-mechanisms", pman)

def _get_good_config_opts(params):
    """Return good options for testing 'pepc pmqos config'."""

    cpu = 0
    opts = []
    pobj = params["pobj"]

    if pobj.prop_is_supported_cpu("latency_limit", cpu):
        opts += ["--latency-limit"]
        return opts

    return []

def _get_bad_config_opts():
    """Return bad options for testing 'pepc pmqos config'."""

    opts = ["--latency-limit 5mb",
            "--latency-limit 1Hz"]
    return opts

def test_pmqos_config_good(params):
    """Test 'pepc pmqos config' command with bad options."""

    pman = params["pman"]

    for opt in _get_good_config_opts(params):
        for mopt in props_common.get_mechanism_opts(params, allow_readonly=False):
            cmd = f"pmqos config {opt} --cpus 0 {mopt}"
            common.run_pepc(cmd, pman, ignore=_IGNORE)

def test_pmqos_config_bad(params):
    """Test 'pepc pmqos config' command with bad options."""

    pman = params["pman"]

    for opt in _get_bad_config_opts():
        common.run_pepc(f"pmqos config {opt}", pman, exp_exc=Error)
        common.run_pepc(f"pmqos config --cpus 0 {opt}", pman, exp_exc=Error)
        for mopt in props_common.get_mechanism_opts(params):
            common.run_pepc(f"pmqos config {opt} {mopt}", pman, exp_exc=Error)

def test_pmqos_save_restore(params):
    """Test 'pepc pmqos save' and 'pepc pmqos restore' commands."""

    pman = params["pman"]
    hostname = params["hostname"]
    tmp_path = params["tmp_path"]

    opts = ("", f"-o {tmp_path}/pmqos.{hostname}")

    for opt in opts:
        common.run_pepc(f"pmqos save {opt}", pman)
        common.run_pepc(f"pmqos save {opt} --cpus 0", pman)

    state_path = tmp_path / f"state.{hostname}"
    common.run_pepc(f"pmqos save -o {state_path}", pman)
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
    common.run_pepc(f"pmqos restore -f {state_swap_path}", pman)

    state_read_back_path = tmp_path / f"state_read_back.{hostname}"
    common.run_pepc(f"pmqos save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state_swap, "restoring PM QoS configuration failed"

    common.run_pepc(f"pmqos restore -f {state_path}", pman)
    common.run_pepc(f"pmqos save -o {state_read_back_path}", pman)
    read_back = YAML.load(state_read_back_path)
    assert read_back == state, "restoring PM QoS configuration failed"