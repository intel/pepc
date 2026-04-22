#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""Test 'pepc aspm' command-line options."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
import pytest
from tests import _Common, _PropsCommonCmdl as PropsCommonCmdl
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorPermissionDenied

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from tests._Common import CommonTestParamsTypedDict

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with _Common.get_pman(hostspec, username=username) as pman:
        params = _Common.build_params(pman)
        yield params

def test_aspm_info(params: CommonTestParamsTypedDict):
    """
    Test 'pepc aspm info'.

    Args:
        params: The test parameters dictionary.
    """

    good = [
        "",
        "--policy",
        "--policies",
        "--policy --policies"]

    pman = params["pman"]

    for option in good:
        PropsCommonCmdl.run_pepc(f"aspm info {option}", pman)

    # Error: bad device address.
    PropsCommonCmdl.run_pepc("aspm info --device bad:dev:addr.0", pman, exp_exc=Error)
    PropsCommonCmdl.run_pepc("aspm info --policy --policies --device bad:dev:addr.0", pman,
                             exp_exc=Error)

    device = _get_l1_device(pman)
    PropsCommonCmdl.run_pepc(f"aspm info --device {device}", pman)
    PropsCommonCmdl.run_pepc(f"aspm info --policy --policies --device {device}", pman)

def test_aspm_config(params):
    """
    Test 'pepc aspm config'.

    Args:
        params: The test parameters dictionary.
    """

    good = ["--policy performance",
            "--policy powersave",
            "--policy powersupersave"]

    pman = params["pman"]

    # Error: no options provided.
    PropsCommonCmdl.run_pepc("aspm config", pman, exp_exc=Error)

    # Error: bad policy name, no superuser or passwordless sudo needed.
    PropsCommonCmdl.run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)

    # Display the current ASPM policy without changing it.
    PropsCommonCmdl.run_pepc("aspm config --policy", pman)

    if not pman.is_superuser() and not pman.has_passwdless_sudo():
        pytest.skip("Superuser or passwordless sudo access is required")

    for option in good:
        try:
            PropsCommonCmdl.run_pepc(f"aspm config {option}", pman, re_raise=True)
        except ErrorPermissionDenied as err:
            # Quirk: some real hosts reject global ASPM policy sysfs writes even for root.
            # In that case the test cannot validate policy changes, so skip it.
            if not pman.is_emulated and "pcie_aspm/parameters/policy" in str(err):
                pytest.skip(f"The host kernel rejects ASPM policy sysfs writes even for root:\n"
                            f"{err}")
            raise

def _get_l1_devices(pman: ProcessManagerType) -> Generator[str, None, None]:
    """
    Yield PCI device addresses that have L1 ASPM support.

    Args:
        pman: The process manager to use for querying the system.

    Yields:
        PCI device address strings (e.g., '0000:01:00.0') for devices that have the L1 ASPM
        sysfs file.
    """

    sysfs_base = Path("/sys/bus/pci/devices")
    try:
        for entry in pman.lsdir(sysfs_base):
            if pman.exists(sysfs_base / entry["name"] / "link" / "l1_aspm"):
                yield entry["name"]
    except ErrorNotFound:
        pass

def _get_l1_device(pman: ProcessManagerType) -> str:
    """
    Return one PCI device address that has L1 ASPM support.

    Args:
        pman: The process manager to use for querying the system.

    Returns:
        A PCI device address string (e.g., '0000:01:00.0').
    """

    for device in _get_l1_devices(pman):
        return device

    pytest.skip("No PCI devices with L1 ASPM support found")
    # The return is here just to silence pylint about missing return statements, but pytest.skip()
    # will always raise an exception and never return.
    return ""

def test_aspm_info_l1(params: CommonTestParamsTypedDict):
    """
    Test 'pepc aspm info' options related to L1 ASPM.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    # Error: '--l1-aspm' requires '--device'.
    PropsCommonCmdl.run_pepc("aspm info --l1-aspm", pman, exp_exc=Error)

    device = _get_l1_device(pman)
    PropsCommonCmdl.run_pepc(f"aspm info --l1-aspm --device {device}", pman)

def test_aspm_config_l1(params: CommonTestParamsTypedDict):
    """
    Test 'pepc aspm config' options related to L1 ASPM.

    Args:
        params: The test parameters dictionary.
    """

    pman = params["pman"]

    # Error: '--l1-aspm' requires '--device', no superuser or passwordless sudo needed.
    PropsCommonCmdl.run_pepc("aspm config --l1-aspm on", pman, exp_exc=Error)

    device = _get_l1_device(pman)

    # Error paths that need a device address but not superuser or passwordless sudo.
    PropsCommonCmdl.run_pepc(f"aspm config --l1-aspm badval --device {device}", pman,
                             exp_exc=Error)
    PropsCommonCmdl.run_pepc("aspm config --l1-aspm on --device bad:dev:addr.0", pman,
                             exp_exc=Error)
    PropsCommonCmdl.run_pepc(f"aspm config --policy performance --device {device}", pman,
                             exp_exc=Error)
    PropsCommonCmdl.run_pepc(f"aspm config --policy performance --l1-aspm badval --device "
                             f"{device}", pman, exp_exc=Error)

    # Display the current L1 ASPM state and ASPM policy without changing them.
    PropsCommonCmdl.run_pepc(f"aspm config --l1-aspm --device {device}", pman)
    PropsCommonCmdl.run_pepc(f"aspm config --policy --l1-aspm --device {device}", pman)

    if not pman.is_superuser() and not pman.has_passwdless_sudo():
        pytest.skip("Superuser or passwordless sudo access is required")

    # Toggle through all valid state values.
    for val in ("on", "off", "enable", "disable", "true", "false"):
        PropsCommonCmdl.run_pepc(f"aspm config --l1-aspm {val} --device {device}", pman)

    PropsCommonCmdl.run_pepc(f"aspm config --policy performance --l1-aspm on --device {device}",
                             pman)
