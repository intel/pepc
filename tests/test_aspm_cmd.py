#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test module for 'pepc' project 'aspm' command."""

import typing
import pytest
import common
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.Exceptions import ExceptionType

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    with common.get_pman(hostspec) as pman:
        params = common.build_params(pman)
        yield params

def test_aspm_info(params):
    """Test 'pepc aspm info' command."""

    good = [
        "",
        "--policy",
        "--policies",
        "--policy --policies"]

    for option in good:
        common.run_pepc(f"aspm info {option}", params["pman"])

def test_aspm_config(params):
    """Test 'pepc aspm config' command."""


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
        common.run_pepc(f"aspm config {option}", pman, ignore=ignore)

    common.run_pepc("aspm config --policy badpolicyname", pman, exp_exc=Error)
