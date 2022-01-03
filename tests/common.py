#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Common bits for the 'pepc' tests."""

import sys
import logging
from pepctool import _Pepc
from MockedStuff import get_mocked_objects

logging.basicConfig(level=logging.DEBUG)
_LOG = logging.getLogger()

def run_pepc(arguments, exp_ret=None):
    """
    Run the 'pepc' command with arguments 'arguments'. Use mocked objects described in
    'get_mocked_objects()'. The 'exp_ret' value is the return value the command is expected to
    return. The test will pass, if the 'exp_ret' is not provided, or it is equal to the return
    value. Otherwise the test will fail.
    """

    with get_mocked_objects() as _:
        cmd = f"{_Pepc.__file__} {arguments}"
        _LOG.debug("running: %s", cmd)
        sys.argv = cmd.split()
        ret = _Pepc.main()

        if exp_ret is not None:
            assert ret == exp_ret
