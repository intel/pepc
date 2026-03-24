#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the '--force-color' option."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
import pytest
from tests import common, props_cmdl_common

if typing.TYPE_CHECKING:
    from typing import Generator
    from tests.common import CommonTestParamsTypedDict

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Yield a dictionary with testing parameters.

    Args:
        hostspec: Host specification used to establish the connection.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary containing test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman:
        params = common.build_params(pman)
        yield params

def test_force_color(params: CommonTestParamsTypedDict):
    """
    Test that '--force-color' option enables ANSI color codes in non-TTY output.

    Notes:
        - INFO level messages are never colored, so we test with debug ('-d') mode.
    """

    pman = params["pman"]

    # ANSI color code pattern (e.g., \x1b[32m, \x1b[1;33m, \x1b[0m for reset).
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')

    # Test 1: Run without --force-color in debug mode, output to StringIO (non-TTY).
    # Should NOT contain color codes.
    stdout, stderr = props_cmdl_common.run_pepc("-d topology info --cpus 0", pman,
                                                 capture_output=True)
    output_no_color = stdout + stderr
    has_color_codes = bool(ansi_pattern.search(output_no_color))

    assert not has_color_codes, \
        "Output to non-TTY should not contain ANSI color codes without --force-color"

    # Test 2: Run with --force-color in debug mode, output to StringIO (non-TTY).
    # Should contain color codes.
    stdout, stderr = props_cmdl_common.run_pepc("--force-color -d topology info --cpus 0", pman,
                                                 capture_output=True)
    output_with_color = stdout + stderr
    has_color_codes = bool(ansi_pattern.search(output_with_color))

    assert has_color_codes, \
        "Output to non-TTY with --force-color should contain ANSI color codes"
