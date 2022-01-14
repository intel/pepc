#!/usr/bin/env python
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""This configuration file adds the custom '--host' option for the tests."""

from collections import namedtuple

_PytestOptions = namedtuple("PytestOptions", ["short", "long", "dest", "default", "help"])
_PYTEST_OPTS = (_PytestOptions("-H", "--host", "hostname", "emulation",
                               """Name of the host to run the test on, or "emulation" (default) to
                                  run locally and emulate real hardware."""),
                _PytestOptions("-D", "--dataset", "dataset", "icx2s0",
                               """Name of the dataset used to emulate the real hardware."""), )

def pytest_addoption(parser):
    """Add custom pytest options."""

    for opt in _PYTEST_OPTS:
        kwargs = {"dest" : opt.dest, "default" : [opt.default], "help" : opt.help,
                  "action" : "append"}
        parser.addoption(opt.short, opt.long, **kwargs)

def pytest_generate_tests(metafunc):
    """Generate tests with custom options."""

    # The "v1" tests do not expect extra options.
    if "_v1_" in str(metafunc.function):
        return

    for opt in _PYTEST_OPTS:
        optval = metafunc.config.getoption(opt.dest, default=None)
        # Option value is a list, remove default (first element) if option provided in commandline.
        if optval:
            if len(optval) > 1:
                optval = optval[1:]
            metafunc.parametrize(opt.dest, optval)
