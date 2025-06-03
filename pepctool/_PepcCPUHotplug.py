# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc cpu-hotplug' command.
"""

from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline
from pepctool import _PepcCommon, _OpTarget

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def cpu_hotplug_info_command(_, pman):
    """
    Implement the 'cpu-hotplug info' command. The arguments are as follows:
      * _ - ignored.
      * pman - the process manager object that defines the target host.
    """

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        for func, word in (("get_cpus", "online"), ("get_offline_cpus", "offline")):
            cpus = getattr(cpuinfo, func)()
            if cpus:
                _LOG.info("The following CPUs are %s%s: %s",
                          word, pman.hostmsg, Trivial.rangify(cpus))
            else:
                _LOG.info("No %s CPUs%s", word, pman.hostmsg)

def cpu_hotplug_online_command(args, pman):
    """
    Implement the 'cpu-hotplug online' command. The arguments are as follows:
      * args - the command line arguments.
      * pman - the process manager object that defines the target host.
    """

    if not args.cpus:
        raise Error("please, specify the CPUs to online")

    with CPUOnline.CPUOnline(loglevel=Logging.INFO, pman=pman) as onl:
        onl.online(cpus=_PepcCommon.parse_cpus_string(args.cpus))

def cpu_hotplug_offline_command(args, pman):
    """
    Implement the 'cpu-hotplug offline' command. The arguments are as follows:
      * args - the command line arguments.
      * pman - the process manager object that defines the target host.
    """

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(loglevel=Logging.INFO, pman=pman, cpuinfo=cpuinfo) as onl:

        # Some CPUs may not support offlining. Suppose it is CPU 0. If CPU 0 is in the 'cpus' list,
        # the 'onl.offline()' method will error out. This is OK in a situation when the user
        # explicitly specified CPU 0 (e.g., via '--cpus 0'). However, this is not OK if the user
        # indirectly specified CPU 0 via '--cpus all' or '--packages 0'.
        skip_unsupported = args.cpus in ("all", None)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo, cpus=args.cpus, cores=args.cores,
                                   modules=args.modules, dies=args.dies, packages=args.packages,
                                   core_siblings=args.core_siblings,
                                   module_siblings=args.module_siblings)

        onl.offline(cpus=optar.get_cpus(), skip_unsupported=skip_unsupported)
