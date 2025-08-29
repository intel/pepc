#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Utility functions shared across multiple test modules."""

# TODO: annotate this module.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from pepclibs import PStates

def get_max_cpu_freq(pobj: PStates.PStates, cpu: int, numeric: bool = False):
    """
    Return the maximum CPU the Linux frequency driver accepts. The arguments are
    as follows.
      * params - test parameters.
      * cpu - CPU number to return the frequency for.
      * numeric - if 'False', it is OK to return non-numeric values, such as "max" or "min".
    """

    maxfreq = None
    turbo_status = pobj.get_cpu_prop("turbo", cpu)["val"]
    freqs = pobj.get_cpu_prop("frequencies", cpu)["val"]

    if turbo_status == "on":
        # On some platforms running 'acpi-cpufreq' driver, the 'max_freq_limit' contains a value
        # that cannot be used for setting the max. frequency. So check the available frequencies
        # and take the max. available in that case.
        max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]

        if freqs and max_limit:
            if max_limit == freqs[-1]:
                if numeric:
                    maxfreq = max_limit
                else:
                    maxfreq = "max"
            else:
                maxfreq = freqs[-1]
    elif freqs:
        maxfreq = freqs[-1]

    if not maxfreq:
        if numeric:
            maxfreq = pobj.get_cpu_prop("base_freq", cpu)["val"]
        else:
            maxfreq = "hfm"
    return maxfreq
