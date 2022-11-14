#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Misc tests for pepc."""

import common
from pepclibs import CPUInfo, PStates, CStates

def test_unknown_cpu_model(hostspec):
    """
    This function tests that 'PStates' and 'CStates' don't fail when getting a property on an
    unknown CPU.
    """

    emul_modules = ["CPUInfo", "PStates", "CStates"]

    with common.get_pman(hostspec, modules=emul_modules) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        cpuinfo.info["model"] = 0

        with PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:
            psobj.get_cpu_props(psobj.props, 0)

        with CStates.CStates(pman=pman, cpuinfo=cpuinfo) as csobj:
            csobj.get_cpu_props(csobj.props, 0)
