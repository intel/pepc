# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#
# Contributor: Len Brown <len.brown@intel.com>

"""
This module provides a capability for discovering bus clock speed (FSB speed) on Intel CPUs.
"""

from pepclibs.msr import FSBFreq
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

def get_bclk(pman, fsbfreq=None, cpu=0):
    """
    Discover bus clock speed for CPU 'cpu' in megahertz (MHz). The arguments are as follows.
      * pman - the process manager object that defines the host to discover bus clock speed for.
      * fsbfreq - an 'FSBFreq.FSBFreq()' object which should be used for accessing MSR registers.
      * cpu - CPU number to discover the bus clock speed for. Can be an integer or a string with
              an integer number.
    """

    close_fsbfreq = False
    bclk = None

    if not fsbfreq:
        fsbfreq = FSBFreq.FSBFreq(pman=pman)
        close_fsbfreq = True

    try:
        bclk = fsbfreq.read_cpu_feature("fsb", cpu)
    except ErrorNotSupported:
        # Fall back to 100MHz clock speed.
        bclk = 100.0
    finally:
        if close_fsbfreq:
            fsbfreq.close()

    return bclk
