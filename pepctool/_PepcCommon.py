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
from pepclibs.helperlibs import Systemctl, Trivial, Human

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

def fmt_cpus(cpus, cpuinfo):
    """Formats and returns a string describing CPU numbers in the 'cpus' list."""

    cpus_range = Human.rangify(cpus)
    if len(cpus) == 1:
        msg = f"CPU {cpus_range}"
    else:
        msg = f"CPUs {cpus_range}"

    allcpus = cpuinfo.get_cpus()
    if set(cpus) == set(allcpus):
        msg += " (all CPUs)"
    else:
        pkgs, rem_cpus = cpuinfo.cpus_div_packages(cpus)
        if pkgs and not rem_cpus:
            # CPUs in 'cpus' are actually the packages in 'pkgs'.
            pkgs_range = Human.rangify(pkgs)
            if len(pkgs) == 1:
                msg += f" (package {pkgs_range})"
            else:
                msg += f" (packages {pkgs_range})"

    return msg

def print_val_msg(val, cpuinfo, name=None, cpus=None, prefix=None, suffix=None):
    """Format and print a message about 'name' and its value 'val'."""

    if cpus is None:
        sfx = ""
    else:
        cpus = fmt_cpus(cpus, cpuinfo)
        sfx = f" for {cpus}"

    if suffix is not None:
        sfx = sfx + suffix

    if name is not None:
        pfx = f"{name}: "
    else:
        pfx = ""

    msg = pfx
    if prefix is not None:
        msg = prefix + msg

    if val is None:
        val = "not supported"
    elif cpus is not None:
        val = f"'{val}'"

    msg += f"{val}{sfx}"
    _LOG.info(msg)
