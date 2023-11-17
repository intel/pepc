# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "cpu-hotplug" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Human
from pepclibs import CPUInfo, CPUOnline
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def cpu_hotplug_info_command(_, pman):
    """Implements the 'cpu-hotplug info' command."""

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        for func, word in (("get_cpus", "online"), ("get_offline_cpus", "offline")):
            cpus = getattr(cpuinfo, func)()
            if cpus:
                _LOG.info("The following CPUs are %s%s: %s",
                          word, pman.hostmsg, Human.rangify(cpus))
            else:
                _LOG.info("No %s CPUs%s", word, pman.hostmsg)

def cpu_hotplug_online_command(args, pman):
    """Implements the 'cpu-hotplug online' command."""

    if not args.cpus:
        raise Error("please, specify the CPUs to online")

    with CPUOnline.CPUOnline(progress=logging.INFO, pman=pman) as onl:
        onl.online(cpus=_PepcCommon.parse_cpus_string(args.cpus))

def cpu_hotplug_offline_command(args, pman):
    """Implements the 'cpu-hotplug offline' command."""

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
        CPUOnline.CPUOnline(progress=logging.INFO, pman=pman, cpuinfo=cpuinfo) as onl:

        # Some CPUs may not support offlining. Suppose it is CPU 0. If CPU 0 is in the 'cpus' list,
        # the 'onl.offline()' method will error out. This is OK in a situation when the user
        # explicitly specified CPU 0 (e.g., via '--cpus 0'). However, this is not OK if the user
        # indirectly specified CPU 0 via '--cpus all' or '--packages 0'.
        skip_unsupported = args.cpus in ("all", None)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus=None)

        if not cpus:
            raise Error("please, specify the CPUs to offline")

        onl.offline(cpus=cpus, skip_unsupported=skip_unsupported)
