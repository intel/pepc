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
from pepclibs.helperlibs import Systemctl, Trivial, Human

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

def print_prop_msg(val, cpuinfo, name=None, action=None, cpus=None, prefix=None):
    """Format and print a message about a C-state property 'name'."""

    if cpus is None:
        sfx = ""
    else:
        cpus = fmt_cpus(cpus, cpuinfo)
        sfx = f" for {cpus}"

    if name is None:
        pfx = ""
    else:
        pfx = f"{name}: "

    if prefix is not None:
        pfx = f"{prefix}{pfx}"

    if val is None:
        msg = f"{pfx}not supported{sfx}"
    elif action is not None:
        msg = f"{pfx}{action} '{val}'{sfx}"
    else:
        msg = f"{pfx}'{val}'{sfx}"

    _LOG.info(msg)

def print_aggr_props(aggr_pinfo, sobj, cpuinfo):
    """Print the aggregate C-state or P-state properties information."""

    for pname in aggr_pinfo:
        for key, kinfo in aggr_pinfo[pname].items():
            for val, cpus in kinfo.items():
                # Distinguish between properties and sub-properties.
                if key in sobj.props:
                    name = sobj.props[pname]["name"]
                    print_prop_msg(val, cpuinfo, name=name, cpus=cpus)
                else:
                    if val is None:
                        # Just skip unsupported sub-property instead of printing something like
                        # "Package C-state limit aliases: not supported on CPUs 0-11".
                        continue

                    # Print sub-properties with a prefix and exclude CPU information, because it is
                    # the same as in the (parent) property, which has already been printed.
                    name = sobj.props[pname]["subprops"][key]["name"]
                    print_prop_msg(val, cpuinfo, name=name, cpus=None, prefix="  - ")

def build_aggregate_pinfo(pinfo_iter, sprops=None):
    """
    Build the aggregated properties dictionary for properties in the 'pinfo_iter' iterator. The
    iterator must provide the (cpu, pinfo) tuples, just like 'CStates.get_props()' or
    'ReqCState.get_cstates_info()' do.

    The dictionary has the following format.

    { property1_name: { property1_name: { value1 : [ list of CPUs having value1],
                                          value2 : [ list of CPUs having value2],
                                          ... and so on of all values ...},
                        subprop1_name:  { value1 : [ list of CPUs having value1],
                                          value2 : [ list of CPUs having value2]
                                          ... and so on of all values ...},
                        ... and so on for all sub-properties ...},
      ... and so on for all properties ... }

      * property1_name - the first property name (e.g., 'pkg_cstate_limit').
      * subprop1_name - the first sub-property name (e.g., 'pkg_cstate_limit_locked').
      * value1, value2, etc - are all the different values for the property/sub-property (e.g.,
                              'True' or 'True')

    In other words, the aggregate dictionary mapping of property/sub-property values to the list of
    CPUs having these values.

    The 'sprops' argument can be used to limit the sub-properties to only the names in 'sprops'.
    """

    aggr_pinfo = {}

    for cpu, pinfo in pinfo_iter:
        for pname in pinfo:
            if pname not in aggr_pinfo:
                aggr_pinfo[pname] = {}
            for key, val in pinfo[pname].items():
                if sprops is not None and key not in sprops:
                    continue
                # Make sure 'val' is "hashable" and can be used as a dictionary key.
                if isinstance(val, list):
                    if not val:
                        continue
                    val = ", ".join(val)
                elif isinstance(val, dict):
                    if not val:
                        continue
                    val = ", ".join(f"{k}={v}" for k, v in val.items())

                if key not in aggr_pinfo[pname]:
                    aggr_pinfo[pname][key] = {}
                if val not in aggr_pinfo[pname][key]:
                    aggr_pinfo[pname][key][val] = []

                aggr_pinfo[pname][key][val].append(cpu)

    return aggr_pinfo
