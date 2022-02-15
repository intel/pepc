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

_PytestOption = namedtuple("PytestOptions", ["short", "long", "dest", "default", "help", "private"])
_PYTEST_OPTS = (_PytestOption("-H", "--host", "hostname", "emulation",
                               """Name of the host to run the test on, or "emulation" (default) to
                                  run locally and emulate real hardware.""", False),
                _PytestOption("-D", "--dataset", "dataset", "all",
                              """Name of the dataset used to emulate the real hardware.""", True), )

def pytest_addoption(parser):
    """Add custom pytest options."""

    for opt in _PYTEST_OPTS:
        kwargs = {"dest" : opt.dest, "default" : [opt.default], "help" : opt.help,
                  "action" : "append"}
        parser.addoption(opt.short, opt.long, **kwargs)

def pytest_collection_modifyitems(session, config, items): # pylint: disable=unused-argument
    """Inspect and modify list of collected tests."""

    dataset = config.getoption("dataset")[-1]
    hostname = config.getoption("hostname")[-1]
    opt_str = f"[{dataset}-{hostname}]"

    deselect = []
    select = []
    for item in items:
        if item.name.startswith("test_v1_") or dataset == "all" or opt_str in item.name:
            select.append(item)
        else:
            deselect.append(item)

    config.hook.pytest_deselected(items=deselect)
    items[:] = select

def pytest_generate_tests(metafunc):
    """Generate tests with custom options."""

    # The "v1" tests do not expect extra options.
    if "_v1_" in str(metafunc.function):
        return

    for opt in _PYTEST_OPTS:
        if opt.private:
            continue

        optval = metafunc.config.getoption(opt.dest, default=None)
        # Option value is a list, remove default (first element) if option provided in commandline.
        if optval:
            if len(optval) > 1:
                optval = optval[1:]
            metafunc.parametrize(opt.dest, optval)
