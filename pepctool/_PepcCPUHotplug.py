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
        for func, word in (("get_cpus", "online"), ("get_offline_cpus", "offline")):
            cpus = getattr(cpuinfo, func)()
            if cpus:
                _LOG.info("The following CPUs are %s%s: %s",
                          word, proc.hostmsg, Human.rangify(cpus))
            else:
                _LOG.info("No %s CPUs%s", word, proc.hostmsg)

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

        # Some CPUs may not support offlining. Suppose it is CPU 0. If CPU 0 is in the 'cpus' list,
        # the 'onl.offline()' method will error out. This is OK in a situation when the user
        # explicitely specified CPU 0 (e.g., via '--cpus 0'). However, this is not OK if the user
        # indirectly specified CPU 0 it via '--cpus all'. Let's recognize the latter as a special
        # case and just skip all CPUs that do not support offlining.
        skip_unsupported = args.cpus == "all" and args.cores is None and args.packages is None

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus=None)

        if not cpus:
            raise Error("please, specify the CPUs to offline")

        if not args.siblings:
            onl.offline(cpus=cpus, skip_unsupported=skip_unsupported)
            return

        siblings_to_offline = set()
        for cpu in cpus:
            core = cpuinfo.cpu_to_core(cpu)
            siblings = cpuinfo.cores_to_cpus(cores=(core,))
            siblings_to_offline.update(siblings[1:])

        siblings_to_offline = set(cpus).intersection(siblings_to_offline)

        if not siblings_to_offline:
            _LOG.warning("nothing to offline%s, no siblings among the following CPUs:%s",
                         proc.hostmsg, Human.rangify(cpus))
        else:
            onl.offline(cpus=siblings_to_offline)
