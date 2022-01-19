#!/usr/bin/python3
#
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

def cpu_hotplug_info_command(_, proc):
    """Implements the 'cpu-hotplug info' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        cpugeom = cpuinfo.get_cpu_geometry()

    for key, word in (("nums", "online"), ("offline_cpus", "offline")):
        if not cpugeom["CPU"][key]:
            _LOG.info("No %s CPUs%s", word, proc.hostmsg)
        else:
            _LOG.info("The following CPUs are %s%s: %s",
                      word, proc.hostmsg, Human.rangify(cpugeom["CPU"][key]))

def cpu_hotplug_online_command(args, proc):
    """Implements the 'cpu-hotplug online' command."""

    if not args.cpus:
        raise Error("please, specify the CPUs to online")

    with CPUOnline.CPUOnline(progress=logging.INFO, proc=proc) as onl:
        onl.online(cpus=args.cpus)

def cpu_hotplug_offline_command(args, proc):
    """Implements the 'cpu-hotplug offline' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, \
        CPUOnline.CPUOnline(progress=logging.INFO, proc=proc, cpuinfo=cpuinfo) as onl:
        cpus = _PepcCommon.get_cpus(args, proc, default_cpus=None, cpuinfo=cpuinfo)

        if not cpus:
            raise Error("please, specify the CPUs to offline")

        if not args.siblings:
            onl.offline(cpus=cpus)
            return

        cpugeom = cpuinfo.get_cpu_geometry()
        siblings_to_offline = []
        for siblings in cpugeom["core"]["nums"].values():
            siblings_to_offline += siblings[1:]

        siblings_to_offline = set(cpus) & set(siblings_to_offline)

        if not siblings_to_offline:
            _LOG.warning("nothing to offline%s, no siblings among the following CPUs:%s",
                         proc.hostmsg, Human.rangify(cpus))
        else:
            onl.offline(cpus=siblings_to_offline)
