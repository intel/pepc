#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc topology' command-line options."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest

from pepclibs import CPUInfo, CPUOnline
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepctools import _PepcTopology

from tests import common, props_cmdl_common

if typing.TYPE_CHECKING:
    from typing import Generator, cast, Sequence
    from pepclibs.CPUInfoTypes import ScopeNameType
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            cpuonline: A 'CPUOnline.CPUOnline' object.
        """

        cpuinfo: CPUInfo.CPUInfo
        cpuonline: CPUOnline.CPUOnline

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Create and yield a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman) as cpuonline:
        # Make sure all CPUs are online for the tests.
        cpuonline.online()

        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo
        params["cpuonline"] = cpuonline
        yield params

def _check_columns(colnames: Sequence[str], caplog: pytest.LogCaptureFixture, cmd: str):
    """
    Check that the output columns match the expected column names.

    Args:
        colnames: The expected column names.
        caplog: The pytest log capture fixture.
        cmd: The command that was run.
    """

    header_args = caplog.records[0].args
    assert header_args is not None, "No output captured from 'pepc topology info' command"

    # Verify that the first output line contains the requested column names.
    header = list(header_args)
    assert len(header) == len(colnames), \
           f"Expected {len(colnames)} columns in the output, got {len(header)}\n" \
           f"Command: pepc {cmd}\n" \
           f"Output:\n{caplog.text}"

    headers = [_PepcTopology.COLNAMES_HEADERS[colname] for colname in colnames]
    assert header == headers, \
           f"Expected columns {headers}, got {header}\n" \
           f"Command: pepc {cmd}\n" \
           f"Output:\n{caplog.text}"

def test_columns(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info --columns' command with various valid options.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    colnames: list[str] = []
    for colname in _PepcTopology.COLNAMES:
        colnames.append(colname)
        cmd = "topology info --columns " + ",".join(colnames)

        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_columns(colnames, caplog, cmd)

        # Reverse the column order and test again.
        colnames.reverse()
        cmd = "topology info --columns " + ",".join(colnames)
        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_columns(colnames, caplog, cmd)

    # Test that capitalization is ignored.
    cap_colnames = [colname.upper() for colname in _PepcTopology.COLNAMES]
    cmd = "topology info --columns " + ",".join(cap_colnames)
    props_cmdl_common.run_pepc(cmd, params["pman"])

def test_invalid_columns(params: _TestParamsTypedDict):
    """
    Test the 'pepc topology info --columns' command with various invalid options.

    Args:
        params: The test parameters.
    """

    # Test invalid column name.
    colname = "INVALID_COLUMN"
    option = "--columns " + colname
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

    # Test no column name.
    option = "--columns"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

    # Test that 'hybrid' column cannot be used without the 'CPU' column.
    option = "--columns hybrid,package"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

    # Test that 'dtype' column cannot be used without the 'die' column.
    option = "--columns dtype,cpu"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

def _fetch_topology_from_output(caplog: pytest.LogCaptureFixture,
                                drop_na: bool = True) -> list[dict[str, int | str]]:
    """
    Parse 'pepc topology info' output into a topology list.

    Args:
        caplog: The pytest log capture fixture.
        drop_na: If True, drop lines containing N/A values: offline CPUs and non-compute
                 die lines.

    Returns:
        A list of dictionaries mapping column names to values.
    """

    header_args = caplog.records[0].args
    assert header_args is not None, "No output captured from 'pepc topology info' command"

    header = [str(hdr) for hdr in header_args]
    topology: list[dict[str, int | str]] = []

    for record in caplog.records[1:]:
        assert record.args is not None, \
               "No output captured from 'pepc topology info' command"

        assert len(record.args) == len(header), \
               "The number of output columns does not match the header"

        tline: dict[str, int | str] = {}
        na_found = False
        for hdr, val in zip(header, [str(rec) for rec in record.args]):
            if Trivial.is_int(val):
                tline[hdr] = int(val)
            elif val in (_PepcTopology.OFFLINE_MARKER, _PepcTopology.NA_MARKER):
                na_found = True
                tline[hdr] = val
            else:
                tline[hdr] = val

        if drop_na and na_found:
            continue

        topology.append(tline)

    return topology

def _fetch_topology_from_output_no_na(caplog: pytest.LogCaptureFixture) -> list[dict[str, int]]:
    """
    Parse 'pepc topology info' output into a topology list, dropping N/A lines.

    The return type is declared as 'int' for all dictionary values, but this is not strictly
    accurate, as it may contain string values for non-integer columns, such as the 'Hybrid' column.
    If this is a problem, use '_fetch_topology_from_output()' instead.

    Args:
        caplog: The pytest log capture fixture.

    Returns:
        A list of dictionaries mapping column names to values.
    """

    topology = _fetch_topology_from_output(caplog, drop_na=True)

    if typing.TYPE_CHECKING:
        return cast(list[dict[str, int]], topology)
    return topology

def _check_order(order: ScopeNameType, caplog: pytest.LogCaptureFixture, cmd: str):
    """
    Check that the output is sorted in the specified order.

    Args:
        order: The scope name used for ordering.
        caplog: The pytest log capture fixture.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output_no_na(caplog)

    order_hdr = _PepcTopology.COLNAMES_HEADERS[order]

    vals_abs: list[int] = []
    vals_rel: dict[int, list[int]] = {}

    # Collect all values from the order column.
    for tline in topology:
        if order in ("core", "die"):
            # Core and die numbers are relative to the package, so they are ordered only within each
            # package.
            pkg_vals = vals_rel.setdefault(tline["Package"], [])
            pkg_vals.append(tline[order_hdr])
        else:
            vals_abs.append(tline[order_hdr])

    # Verify that the order column values are sorted.
    if vals_rel:
        for pkg, pkg_vals in vals_rel.items():
            assert pkg_vals == sorted(pkg_vals), \
                   f"The '{order}' column is not sorted in ascending order for package {pkg}\n" \
                   f"Command: pepc {cmd}\n" \
                   f"Output:\n{caplog.text}"
    else:
        assert vals_abs == sorted(vals_abs), \
               f"The '{order}' column is not sorted in ascending order\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

def test_order(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info --order' command with various valid options.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    colnames = CPUInfo.SCOPE_NAMES
    for order in CPUInfo.SCOPE_NAMES:
        cmd = f"topology info --order {order} --columns " + ",".join(colnames)

        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_order(order, caplog, cmd)

    # Test ordering by a column that is not in the list of columns to print. For example, order by
    # CPU, but CPU is not in '--columns'. Verify that this does not fail.
    order = "CPU"
    cmd = f"topology info --order {order} --columns Core,Package"
    props_cmdl_common.run_pepc(cmd, params["pman"])

    # Test that capitalization is ignored.
    cmd = "topology info --order cPu --columns " + ",".join(colnames)
    props_cmdl_common.run_pepc(cmd, params["pman"])

def test_invalid_order(params: _TestParamsTypedDict):
    """
    Test the 'pepc topology info --order' command with various invalid options.

    Args:
        params: The test parameters.
    """

    # Test invalid order name.
    order = "INVALID_ORDER"
    option = f"--order {order}"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

    # Test no order name.
    option = "--order"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

    # Test that "hybrid" cannot be used as an order.
    option = "--order hybrid"
    props_cmdl_common.run_pepc(f"topology info {option}", params["pman"], exp_exc=Error)

def _check_limited_target_cpus(caplog: pytest.LogCaptureFixture,
                               target_cpus: list[int],
                               cmd: str):
    """
    Check that only the target CPUs are present in the output.

    Args:
        caplog: The pytest log capture fixture.
        target_cpus: The expected target CPUs.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output_no_na(caplog)

    output_cpus: list[int] = []
    for tline in topology:
        output_cpus.append(tline["CPU"])

    assert output_cpus == target_cpus, \
           f"Output CPUs do not match target CPUs\n" \
           f"Command: pepc {cmd}\n" \
           f"Output:\n{caplog.text}"

def test_limited_target_cpus(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info' command with options that limit the target CPUs.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()

    if len(cpus) < 2:
        pytest.skip("The system has fewer than two CPUs, skipping the limited target CPUs tests")

    # Test with only half of the CPUs.
    mid_cpu = cpus[len(cpus) // 2]
    cmd = f"topology info --cpus 0-{mid_cpu}"

    if len(cpus) < 4:
        pytest.skip("The system has fewer than four CPUs, skipping some of the limited target CPUs "
                    "tests")

    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_cpus(caplog, list(range(0, mid_cpu + 1)), cmd)

    # Test with the last CPU only.
    last_cpu = cpus[-1]
    cmd = f"topology info --cpus {last_cpu}"

    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_cpus(caplog, [last_cpu], cmd)

    # Test with first and last CPUs.
    cmd = f"topology info --cpus 0,{last_cpu}"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_cpus(caplog, [0, last_cpu], cmd)

def _check_limited_target_cores(caplog: pytest.LogCaptureFixture,
                                target_cores: dict[int, list[int]],
                                cmd: str):
    """
    Check that only the target cores are present in the output.

    Args:
        caplog: The pytest log capture fixture.
        target_cores: The expected target cores mapped by package number.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output_no_na(caplog)

    output_cores: dict[int, list[int]] = {}
    for tline in topology:
        # If there is only one package, the 'Package' column may be missing.
        pkg = tline.get("Package", 0)
        core = tline["Core"]
        pkg_cores = output_cores.setdefault(pkg, [])
        pkg_cores.append(core)

    for pkg, cores in target_cores.items():
        assert pkg in output_cores, \
               f"Package {pkg} not found in output\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"
        # A core may appear multiple times in the output if there are multiple CPUs per core.
        output_cores_unique = sorted(set(output_cores[pkg]))
        assert output_cores_unique == cores, \
               f"Output cores for package {pkg} do not match target cores\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

def _get_target_cores(all_cores: dict[int, list[int]],
                      cores_range: tuple[int, int]) -> dict[int, list[int]]:
    """
    Get the target cores mapped by package number.

    Args:
        all_cores: All cores mapped by package number.
        cores_range: A tuple containing the first and last core numbers in the range.

    Returns:
        The target cores mapped by package number.
    """

    first_core, last_core = cores_range
    target_cores: dict[int, list[int]] = {}
    for pkg, pkg_cores in all_cores.items():
        core_nums = [core for core in range(first_core, last_core + 1) if core in pkg_cores]
        if core_nums:
            target_cores[pkg] = core_nums

    return target_cores

def test_limited_target_cores(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info' command with options that limit the target cores.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    # Keep in mind that core numbers may be non-contiguous. But package numbers are contiguous and
    # package 0 always exists.

    # Ignore systems with a single core.
    cpuinfo = params["cpuinfo"]
    cores = cpuinfo.get_cores()
    if len(cores[0]) < 2:
        pytest.skip("The system has fewer than two cores, skipping the limited target cores tests")

    first_core = cores[0][0]
    mid_core = cores[0][len(cores[0]) // 2]

    # Test with only half of the cores in package 0.
    target_cores = _get_target_cores(cores, (first_core, mid_core))
    cores_opt = Trivial.rangify(target_cores[0])
    cmd = f"topology info --package 0 --cores {cores_opt}"

    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_cores(caplog, {0: target_cores[0]}, cmd)

    # Use a custom columns list.
    cmd += " --columns package,core,die"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_cores(caplog, {0: target_cores[0]}, cmd)

    # Specify more than one package.
    target_cores = _get_target_cores(cores, (first_core, mid_core))
    cores_opts = set()
    for pkg_cores in target_cores.values():
        cores_opts.add(Trivial.rangify(pkg_cores))

    # Skip the situation with different core numbers in different packages. The command will fail
    # complaining that one of the cores in the range does not exist in some package.
    if len(cores_opts) == 1:
        cores_opt = cores_opts.pop()
        packages_opt = Trivial.rangify(target_cores)
        cmd = f"topology info --packages {packages_opt} --cores {cores_opt}"

        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_limited_target_cores(caplog, target_cores, cmd)

def _get_target_dies(all_dies: dict[int, list[int]],
                     dies_range: tuple[int, int]) -> dict[int, list[int]]:
    """
    Get the target dies mapped by package number.

    Args:
        all_dies: All dies mapped by package number.
        dies_range: A tuple containing the first and last die numbers in the range.

    Returns:
        The target dies mapped by package number.
    """

    first_die, last_die = dies_range
    target_dies: dict[int, list[int]] = {}
    for pkg, pkg_dies in all_dies.items():
        die_nums = [die for die in range(first_die, last_die + 1) if die in pkg_dies]
        if die_nums:
            target_dies[pkg] = die_nums

    return target_dies

def _check_limited_target_dies(caplog: pytest.LogCaptureFixture,
                               target_dies: dict[int, list[int]],
                               cmd: str):
    """
    Check that only the target dies are present in the output.

    Args:
        caplog: The pytest log capture fixture.
        target_dies: The expected target dies mapped by package number.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output_no_na(caplog)

    output_dies: dict[int, list[int]] = {}
    for tline in topology:
        pkg = tline.get("Package", 0)
        die = tline["Die"]
        pkg_dies = output_dies.setdefault(pkg, [])
        pkg_dies.append(die)

    for pkg, dies in target_dies.items():
        assert pkg in output_dies, \
               f"Package {pkg} not found in output\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"
        # A die may appear multiple times in the output if there are multiple CPUs per die.
        output_dies_unique = sorted(set(output_dies[pkg]))
        assert output_dies_unique == dies, \
               f"Output dies for package {pkg} do not match target dies\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

def test_limited_target_dies(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info' command with options that limit the target compute dies.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    # Keep in mind that die numbers may be non-contiguous. But package numbers are contiguous and
    # package 0 always exists. Also do not consider non-compute dies.

    # Ignore systems with a single die.
    cpuinfo = params["cpuinfo"]
    dies = cpuinfo.get_compute_dies()
    if len(dies[0]) < 2:
        pytest.skip("The system has fewer than two dies, skipping the limited target dies tests")

    first_die = dies[0][0]
    mid_die = dies[0][len(dies[0]) // 2]

    # Test with only half of the dies in package 0.
    target_dies = _get_target_dies(dies, (first_die, mid_die))
    dies_opt = Trivial.rangify(target_dies[0])
    cmd = f"topology info --package 0 --dies {dies_opt}"

    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_dies(caplog, {0: target_dies[0]}, cmd)

    # Use a custom columns list.
    cmd += " --columns cpu,package,die,hybrid"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_limited_target_dies(caplog, {0: target_dies[0]}, cmd)

    # Specify more than one package.
    target_dies = _get_target_dies(dies, (first_die, mid_die))
    dies_opts = set()
    for pkg_dies in target_dies.values():
        dies_opts.add(Trivial.rangify(pkg_dies))

    # Skip the situation with different die numbers in different packages. The command will fail
    # complaining that one of the dies in the range does not exist in some package.
    if len(dies_opts) == 1:
        dies_opt = dies_opts.pop()
        packages_opt = Trivial.rangify(target_dies)
        cmd = f"topology info --packages {packages_opt} --dies {dies_opt}"

        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_limited_target_dies(caplog, target_dies, cmd)

def _check_offline_cpus(caplog: pytest.LogCaptureFixture,
                        offline_cpus: list[int],
                        cmd: str):
    """
    Check that the offline CPUs are present in the output with proper markings.

    Args:
        caplog: The pytest log capture fixture.
        offline_cpus: The expected offline CPUs.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output(caplog, drop_na=False)

    offline_cpus_set = set(offline_cpus)
    found_offline_cpus_set = set()

    for tline in topology:
        has_offline = False
        for colname in tline:
            if tline[colname] == _PepcTopology.OFFLINE_MARKER:
                has_offline = True
                break
        if not has_offline:
            continue

        cpu = tline["CPU"]
        assert isinstance(cpu, int), \
               f"Offline CPU line has non-integer CPU value\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

        assert cpu in offline_cpus_set, \
               f"Found unexpected offline CPU {cpu}\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

        assert cpu not in found_offline_cpus_set, \
               f"Offline CPU {cpu} appears multiple times in the output\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

        found_offline_cpus_set.add(cpu)

    assert found_offline_cpus_set == offline_cpus_set, \
           f"Not all offline CPUs were found in the output\n" \
           f"Expected offline CPUs: {sorted(offline_cpus_set)}\n" \
           f"Found offline CPUs: {sorted(found_offline_cpus_set)}\n" \
           f"Command: pepc {cmd}\n" \
           f"Output:\n{caplog.text}"

def test_offline_cpus(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info' command with offline CPUs present in the system.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    # Offline the middle CPU if there are at least three CPUs.
    cpuinfo = params["cpuinfo"]
    cpus = cpuinfo.get_cpus()
    if len(cpus) < 3:
        pytest.skip("The system has fewer than three CPUs, skipping the offline CPUs test")

    mid_cpu = cpus[len(cpus) // 2]
    cpuonline = params["cpuonline"]
    cpuonline.offline([mid_cpu])

    # Verify that the offline CPU is present in the output with proper markings.
    cmd = "topology info"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_offline_cpus(caplog, [mid_cpu], cmd)

    # Offline the first half of the CPUs (excluding CPU 0) if there are at least four CPUs.
    if len(cpus) < 4:
        pytest.skip("The system has fewer than four CPUs, skipping some of the offline CPUs tests")

    offline_cpus = [cpu for cpu in cpus if 0 < cpu <= mid_cpu]
    cpuonline.offline(offline_cpus)

    cmd = "topology info"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_offline_cpus(caplog, offline_cpus, cmd)

    # Online all CPUs back.
    cpuonline.online()

def _check_noncomp_dies(caplog: pytest.LogCaptureFixture,
                        noncomp_dies_sets: dict[int, set[int]],
                        cmd: str):
    """
    Check that the non-compute dies are present in the output with proper markings.

    Args:
        caplog: The pytest log capture fixture.
        noncomp_dies_sets: The expected non-compute dies mapped by package number.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output(caplog, drop_na=False)

    found_noncomp_dies_sets: dict[int, set[int]] = {}

    for tline in topology:
        if "Die" not in tline:
            # No dies infomation, nothing to check.
            return

        no_marker = True
        for colname in tline:
            if tline[colname] == _PepcTopology.NA_MARKER:
                no_marker = False
                break
        if no_marker:
            continue

        # If there is only one package/die, the columns may be missing.
        package = tline.get("Package", 0)
        die = tline.get("Die", 0)

        assert isinstance(package, int), \
               f"Non-compute die line has non-integer Package value\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"
        assert isinstance(die, int), \
               f"Non-compute die line has non-integer Die value\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

        # Make sure all columns except Package and core are marked as N/A.
        for _colname in tline:
            if _colname in ("Package", "Die", "DieType"):
                continue
            assert tline[_colname] == _PepcTopology.NA_MARKER, \
                   f"Non-compute die column {_colname} is not marked as N/A for non-compute " \
                   f"die {die} in package {package}\n" \
                   f"Command: pepc {cmd}\n" \
                   f"Output:\n{caplog.text}"

        assert package in noncomp_dies_sets, \
               f"Found unexpected non-compute die {die} in package {package}\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"
        assert die in noncomp_dies_sets[package], \
               f"Found unexpected non-compute die {die} in package {package}\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

        pkg_found_dies = found_noncomp_dies_sets.setdefault(package, set())
        assert die not in pkg_found_dies, \
                f"Non-compute die {die} in package {package} appears multiple times in " \
                f"the output\n" \
                f"Command: pepc {cmd}\n" \
                f"Output:\n{caplog.text}"

        pkg_found_dies.add(die)

    for pkg, dies_set in noncomp_dies_sets.items():
        assert pkg in found_noncomp_dies_sets, \
               f"Package {pkg} with non-compute dies not found in output\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"
        found_dies_set = found_noncomp_dies_sets[pkg]
        assert found_dies_set == dies_set, \
               f"Output non-compute dies for package {pkg} do not match expected non-compute " \
               f"dies\n" \
               f"Expected non-compute dies: {sorted(dies_set)}\n" \
               f"Found non-compute dies: {sorted(found_dies_set)}\n" \
               f"Command: pepc {cmd}\n" \
               f"Output:\n{caplog.text}"

def _check_no_noncomp_dies(caplog: pytest.LogCaptureFixture, cmd: str):
    """
    Check that no non-compute dies are present in the output.

    Args:
        caplog: The pytest log capture fixture.
        cmd: The command that was run.
    """

    topology = _fetch_topology_from_output(caplog, drop_na=False)

    for tline in topology:
        for colname in tline:
            assert tline[colname] != _PepcTopology.NA_MARKER, \
                   f"Found unexpected non-compute die line in the output\n" \
                   f"Command: pepc {cmd}\n" \
                   f"Output:\n{caplog.text}"

def test_noncomp_dies(params: _TestParamsTypedDict, caplog: pytest.LogCaptureFixture):
    """
    Test the 'pepc topology info' command non-compute die handling.

    Args:
        params: The test parameters.
        caplog: The pytest log capture fixture.
    """

    noncomp_dies = params["cpuinfo"].get_noncomp_dies()
    # Skip systems with no non-compute dies.
    if not noncomp_dies:
        pytest.skip("The system has no non-compute dies, skipping the non-compute dies test")

    noncomp_dies_sets: dict[int, set[int]] = {}
    for pkg, dies in noncomp_dies.items():
        noncomp_dies_sets[pkg] = set(dies)

    # Verify that non-compute dies are present in the output with proper markings.
    cmd = "topology info"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_noncomp_dies(caplog, noncomp_dies_sets, cmd)

    # Verify with all dies and all packages.
    cmd = "topology info --dies all --packages all"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_noncomp_dies(caplog, noncomp_dies_sets, cmd)

    # Verify with package 0 only.
    cmd = "topology info --package 0"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_noncomp_dies(caplog, {0: noncomp_dies_sets[0]}, cmd)

    # Verify with only a subset of non-compute dies: all but the first one.
    if len(noncomp_dies_sets[0]) > 1:
        test_dies = list(noncomp_dies_sets[0])[1:]
        dies_opt = Trivial.rangify(test_dies)
        cmd = f"topology info --package 0 --dies {dies_opt}"
        caplog.clear()
        props_cmdl_common.run_pepc(cmd, params["pman"])
        _check_noncomp_dies(caplog, {0: set(test_dies)}, cmd)

    # When selecting only CPUs, cores, or modules, without specifying non-compute dies, non-compute
    # dies should not appear in the output.

    # Verify with CPU 0 only.
    cmd = "topology info --cpus 0"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_no_noncomp_dies(caplog, cmd)

    # Verify with '--cpus all'.
    cmd = "topology info --cpus all"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_no_noncomp_dies(caplog, cmd)

    # Verify with all cores.
    cmd = "topology info --cores all --packages all"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_no_noncomp_dies(caplog, cmd)

    # Verify with all modules.
    cmd = "topology info --modules all --packages all"
    caplog.clear()
    props_cmdl_common.run_pepc(cmd, params["pman"])
    _check_no_noncomp_dies(caplog, cmd)
