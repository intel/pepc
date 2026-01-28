#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test 'pepc aspm' command-line options."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common, props_cmdl_common
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.helperlibs.Exceptions import ExceptionType
    from tests.common import CommonTestParamsTypedDict

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

    with common.get_pman(hostspec, username=username) as pman:
        params = common.build_params(pman)
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

    for option in good:
        props_cmdl_common.run_pepc(f"aspm info {option}", params["pman"])

def test_aspm_config(params):
    """
    Test 'pepc aspm config'.

    Args:
        params: The test parameters dictionary.
    """


    good = [
        "--policy",
        "--policy performance",
        "--policy powersave",
        "--policy powersupersave"]

    ignore: dict[ExceptionType, str] | None = None
    pman = params["pman"]

    if pman.is_remote:
        # On a non-emulated system writing the policy sysfs file may end up with a "permission
        # denied" error. Ignore these errors, they mean the host does not allow for changing the
        # policy.
        ignore = { ErrorPermissionDenied : "aspm config --policy " }

    for option in good:
        props_cmdl_common.run_pepc(f"aspm config {option}", pman, ignore=ignore)

    props_cmdl_common.run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)
