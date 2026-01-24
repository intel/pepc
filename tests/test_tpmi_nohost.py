
#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test the public methods of the 'TPMI.py' module for the debugfs dump decoding case (working with a
dump of the TPMI debugfs directories, instead of working with a live system).

The test uses a partial dump of TPMI debugfs directory structure stored in the
'test-data/test_tpmi_nohost/debugfs-dump' and including:
 - 3 known features: ufs, rapl, and tpmi_info.
 - 1 unknown feature with ID 0xFE.

The test also assumes specific values for various registers in the dump.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path

from tests import common
from pepclibs import TPMI

def _get_tpmi_instance() -> TPMI.TPMI:
    """
    Create and return a TPMI instance for the test debugfs dump.
    """

    debugfs_dump_path = common.get_test_data_path(__file__) / Path("debugfs-dump")
    tpmi = TPMI.TPMI(base=debugfs_dump_path)
    return tpmi

def test_get_unknown_features():
    """
    Test the TPMI.get_unknown_features() method.
    """

    tpmi = _get_tpmi_instance()

    unknown_fids = tpmi.get_unknown_features()
    assert unknown_fids == [0xFE], f"Unexpected unknown feature IDs: {unknown_fids}"

def test_get_known_features():
    """
    Test the TPMI.get_known_features() method.
    """

    tpmi = _get_tpmi_instance()

    sdicts = tpmi.get_known_features()
    expected_fnames = {"ufs", "rapl", "tpmi_info"}
    assert set(sdicts) == expected_fnames, \
           f"Unexpected known feature names: {list(sdicts)}"

def test_get_fdict():
    """
    Test the TPMI.get_fdict() method.
    """

    tpmi = _get_tpmi_instance()

    fdict = tpmi.get_fdict("ufs")

    expecter_regnames = ["UFS_HEADER", "UFS_STATUS"]
    for regname in expecter_regnames:
        assert regname in fdict, f"Register '{regname}' not found in the UFS feature fdict"

    bfdict = fdict["UFS_STATUS"]
    expected_bfnames = ["CURRENT_RATIO", "AGENT_TYPE_CORE"]
    for bfname in expected_bfnames:
        assert bfname in bfdict["fields"], \
               f"Bitfield '{bfname}' not found in the UFS_STATUS register"

def test_iter_feature():
    """
    Test the TPMI.iter_feature() method.
    """

    tpmi = _get_tpmi_instance()

    expected = {"rapl": [(0, '0000:00:02.1', 0)],
                "ufs": [(0, '0000:00:02.1', 0),
                        (0, '0000:00:02.1', 2),
                        (0, '0001:00:02.1', 2)],
                "tpmi_info": [(0, '0000:00:02.1', 0),
                              (0, '0001:00:02.1', 0)]}

    for fname, expected_list in expected.items():
        result: list[tuple[int, str, int]] = []
        for package, addr, instance in tpmi.iter_feature(fname):
            result.append((package, addr, instance))

        assert result == expected_list, f"Unexpected iter_feature('{fname}') result: {result}"

def test_iter_feature_clusterd():
    """
    Test the TPMI.iter_feature() method with clustered features.
    """

    tpmi = _get_tpmi_instance()

    expected = {"rapl": [(0, '0000:00:02.1', 0, 0)],
                "ufs": [(0, "0000:00:02.1", 0, 0),
                        (0, "0000:00:02.1", 2, 0),
                        (0, "0000:00:02.1", 2, 1),
                        (0, "0001:00:02.1", 2, 0),
                        (0, "0001:00:02.1", 2, 1)],
                "tpmi_info": [(0, '0000:00:02.1', 0, 0),
                              (0, '0001:00:02.1', 0, 0)]}

    for fname, expected_list in expected.items():
        result: list[tuple[int, str, int, int]] = []
        for package, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
            result.append((package, addr, instance, cluster))

        assert result == expected_list, \
               f"Unexpected iter_feature_cluster('{fname}') result: {result}"

    # Test limiting PCI addresses.
    expected = {"rapl": [(0, '0000:00:02.1', 0, 0)],
                "ufs": [(0, "0000:00:02.1", 0, 0),
                        (0, "0000:00:02.1", 2, 0),
                        (0, "0000:00:02.1", 2, 1)],
                "tpmi_info": [(0, '0000:00:02.1', 0, 0)]}
    for fname, expected_list in expected.items():
        result = []
        iterator = tpmi.iter_feature_cluster(fname, addrs=["0000:00:02.1"])
        for package, addr, instance, cluster in iterator:
            result.append((package, addr, instance, cluster))

        assert result == expected_list, \
               f"Unexpected iter_feature_cluster('{fname}', addrs=...) result: {result}"

    # Test limiting by instances.
    expected = {"rapl": [(0, '0000:00:02.1', 0, 0)],
                "ufs": [(0, "0000:00:02.1", 0, 0)],
                "tpmi_info": [(0, '0000:00:02.1', 0, 0),
                              (0, '0001:00:02.1', 0, 0)]}
    for fname, expected_list in expected.items():
        result = []
        iterator = tpmi.iter_feature_cluster(fname, instances=[0])
        for package, addr, instance, cluster in iterator:
            result.append((package, addr, instance, cluster))

        assert result == expected_list, \
               f"Unexpected iter_feature_cluster('{fname}', instances=...) result: {result}"

    # Limit clusters for UFS feature.
    expected = {"ufs": [(0, "0000:00:02.1", 2, 1),
                        (0, "0001:00:02.1", 2, 1)]}

    result = []
    iterator = tpmi.iter_feature_cluster("ufs", clusters=[1])
    for package, addr, instance, cluster in iterator:
        result.append((package, addr, instance, cluster))

    assert result == expected["ufs"], \
           f"Unexpected iter_feature_cluster('ufs', clusters=[1]) result: {result}"

def test_read_register():
    """
    Test the TPMI.read_register() method.
    """

    tpmi = _get_tpmi_instance()

    # Read UFS_STATUS register for address '0000:00:02.1', instance 2.
    value = tpmi.read_register("ufs", "0000:00:02.1", 2, "UFS_STATUS")
    assert value == 0xa52fc5f04092008, \
           f"Unexpected UFS_STATUS register value: {value:#x}"

    # Read RAPL_POWER_LIMIT register for address '0000:00:02.1', instance 0.
    value = tpmi.read_register("rapl", "0000:00:02.1", 0, "SOCKET_RAPL_ENERGY_STATUS")
    assert value == 0x104a8b7cde85806f, \
           f"Unexpected SOCKET_RAPL_ENERGY_STATUS register value: {value:#x}"

def test_read_bitfield():
    """
    Test the TPMI.read_bitfield() method.
    """

    tpmi = _get_tpmi_instance()

    # Read CURRENT_RATIO bitfield from UFS_STATUS register for address '0000:00:02.1',
    # instance 2.
    value = tpmi.read_register("ufs", "0000:00:02.1", 2, "UFS_STATUS", bfname="CURRENT_RATIO")
    assert value == 0x8, f"Unexpected CURRENT_RATIO bitfield value: {value:#x}"

    # Read AGENT_TYPE_IO bitfield from UFS_STATUS register for address '0000:00:02.1',
    # instance 2.
    value = tpmi.read_register("ufs", "0000:00:02.1", 2, "UFS_STATUS", bfname="AGENT_TYPE_IO")
    assert value == 0x1, f"Unexpected AGENT_TYPE_IO bitfield value: {value:#x}"
