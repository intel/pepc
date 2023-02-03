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
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from pepclibs.helperlibs import Systemctl, Trivial

_LOG = logging.getLogger()

def check_tuned_presence(pman):
    """Check if the 'tuned' service is active, and if it is, print a warning message."""

    with Systemctl.Systemctl(pman=pman) as systemctl:
        try:
            if systemctl.is_active("tuned"):
                _LOG.warning("the 'tuned' service is active%s! It may override the changes made by "
                             "'pepc'.\nConsider having 'tuned' disabled while experimenting with "
                             "power management settings.", pman.hostmsg)
        except ErrorNotFound:
            pass
        except Error as err:
            _LOG.warning("failed to check for 'tuned' presence:\n%s", err.indent(2))

def get_cpus(args, cpuinfo, default_cpus="all", offlined_ok=False):
    """
    Get list of CPUs based on requested packages, cores and CPUs numbers. If no CPUs, cores and
    packages are requested, returns 'default_cpus'.

    By default, requested offlined CPUs are not allowed and will cause an exception. Use
    'offlined_ok=True' to allow offlined CPUs. When the argument is "all", all online CPUs are
    included and no exception is raised for offline CPUs, with 'offlined_ok=True' "all" will include
    online and offline CPUs. For package and core 'offlined_ok=True' does nothing, due to offline
    CPUs not having a package and core number.
    """

    cpus = []

    if args.cpus:
        cpus += cpuinfo.normalize_cpus(cpus=args.cpus, offlined_ok=offlined_ok)

    if args.cores:
        packages = args.packages
        if not packages:
            if cpuinfo.get_packages_count() != 1:
                raise Error("'--cores' must be used with '--packages'")
            packages = (0,)
        cpus += cpuinfo.cores_to_cpus(cores=args.cores, packages=packages)

    if args.packages and not args.cores:
        cpus += cpuinfo.packages_to_cpus(packages=args.packages)

    if not cpus:
        if args.core_siblings:
            raise Error("'--core-siblings' cannot be used without one of '--cpus', '--cores' or " \
                        "'--packages'")

        if default_cpus is not None:
            return cpuinfo.normalize_cpus(default_cpus, offlined_ok=offlined_ok)

        return cpus

    if args.core_siblings:
        return cpuinfo.select_core_siblings(cpus, args.core_siblings)

    return Trivial.list_dedup(cpus)
