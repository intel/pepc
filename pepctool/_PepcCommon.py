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
Misc. helpers shared between various 'pepc' commands.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Systemctl, Trivial

_LOG = logging.getLogger()

def check_tuned_presence(proc):
    """Check if the 'tuned' service is active, and if it is, print a warning message."""

    with Systemctl.Systemctl(proc=proc) as systemctl:
        if systemctl.is_active("tuned"):
            _LOG.warning("the 'tuned' service is active%s! It may override the changes made by "
                         "'pepc'.\nConsider having 'tuned' disabled while experimenting with power "
                         "mangement settings.", proc.hostmsg)

def get_cpus(args, cpuinfo, default_cpus="all"):
    """
    Get list of CPUs based on requested packages, cores and CPUs. If no CPUs, cores and packages are
    requested, returns 'default_cpus'.
    """

    cpus = []

    if args.cpus:
        cpus += cpuinfo.normalize_cpus(cpus=args.cpus)

    if args.cores:
        packages = args.packages
        if not packages:
            if cpuinfo.get_packages_count() != 1:
                raise Error("'--cores' must be used with '--packages'")
            packages = (0,)
        cpus += cpuinfo.cores_to_cpus(cores=args.cores, packages=packages)

    if args.packages and not args.cores:
        cpus += cpuinfo.packages_to_cpus(packages=args.packages)

    if not cpus and default_cpus is not None:
        cpus = cpuinfo.normalize_cpus(default_cpus)

    return Trivial.list_dedup(cpus)
