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

import re
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

    hostname = config.getoption("hostname")[-1]

    deselect = []
    select = []
    if hostname != "emulation":
        # The 'dataset' option is relevant only with 'emulation' host. Remove dublicate function
        # calls from the list, and rename tests only according to hostname. E.g. with 'sklep1' as
        # hotname, the list of tests would be modified as follows.
        # test_get[bdwup0-sklep1]
        # test_get[icx2s0-sklep1]
        # test_get[ivbep0-sklep1]
        # test_div[bdwup0-sklep1]
        # test_div[icx2s0-sklep1]
        # test_div[ivbep0-sklep1]
        #
        # Would become to:
        # test_get[sklep1]
        # test_div[sklep1]

        seen = set()
        for item in items:
            if item.function not in seen:
                item.name = re.sub(r'\[.*\]', f'[{hostname}]', item.name)
                select.append(item)
                seen.add(item.function)
            else:
                deselect.append(item)
    else:
        dataset = config.getoption("dataset")[-1]
        opt_str = f"{dataset}-{hostname}]"

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
