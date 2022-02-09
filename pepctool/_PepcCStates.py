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
This module includes the "cstates" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.msr import MSR
from pepclibs import CStates, CPUInfo
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def _fmt_csnames(csnames):
    """Formats and returns the C-states list string, which can be used in messages."""

    if csnames == "all":
        msg = "all C-states"
    else:
        if len(csnames) == 1:
            msg = "C-state "
        else:
            msg = "C-states "
        msg += ",".join(csnames)

    return msg

def _fmt_cpus(cpus, cpuinfo):
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

def _print_cstate_prop_msg(name, action, val, cpuinfo, cpus=None, prefix=None):
    """Format and print a message about a C-state property 'name'."""

    if cpus is None:
        sfx = ""
    else:
        cpus = _fmt_cpus(cpus, cpuinfo)
        sfx = f" on {cpus}"

    if prefix is None:
        pfx = f"{name}"
    else:
        pfx = f"{prefix}{name}"

    if val is None:
        msg = f"{pfx}: not supported{sfx}"
    elif action:
        msg = f"{pfx}: {action} '{val}'{sfx}"
    else:
        msg = f"{pfx}: '{val}'{sfx}"

    _LOG.info(msg)

def _handle_cstate_config_opt(optname, optval, cpus, csobj, cpuinfo):
    """
    Handle a C-state configuration option 'optname'.

    Most options can be used with and without a value. In the former case, this function sets the
    corresponding C-state property to the value provided. Otherwise this function reads the current
    value of the C-state property and prints it.
    """

    if optname in csobj.props:
        csobj.set_props({optname : optval}, cpus)

        name = csobj.props[optname]["name"]
        _print_cstate_prop_msg(name, "set to", optval, cpuinfo, cpus=cpus)

def _print_cstate_prop(aggr_pinfo, pname, csobj, cpuinfo):
    """Print about C-state properties in 'aggr_pinfo'."""

    for key, kinfo in aggr_pinfo[pname].items():
        for val, cpus in kinfo.items():
            # Distinguish between properties and sub-properties.
            if key in csobj.props:
                name = csobj.props[pname]["name"]
                _print_cstate_prop_msg(name, "", val, cpuinfo, cpus=cpus)
            else:
                if val is None:
                    # Just skip unsupported sub-property instead of printing something like
                    # "Package C-state limit aliases: not supported on CPUs 0-11".
                    continue

                # Print sub-properties with a prefix and exclude CPU information, because it is the
                # same as in the (parent) property, which has already been printed.
                name = csobj.props[pname]["subprops"][key]["name"]
                _print_cstate_prop_msg(name, "", val, cpuinfo, cpus=None, prefix="  - ")


def _build_aggregate_pinfo(pnames, cpus, csobj):
    """
    Build aggregate properties dictionary for properties in the 'pnames' list. The dictionary
    has the following format.

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
    """

    aggr_pinfo = {}

    for cpu, pinfo in csobj.get_props(pnames, cpus=cpus):
        for pname in pinfo:
            if pname not in aggr_pinfo:
                aggr_pinfo[pname] = {}
            for key, val in pinfo[pname].items():
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

def handle_print_opts(opts, cpus, csobj, cpuinfo):
    """
    Handle C-state configuration options other than '--enable' and '--disable' which have to be
    printed.
    """

    if not opts:
        return

    # Build the aggregate properties information dictionary for all options we are going to
    # print about.
    aggr_pinfo = _build_aggregate_pinfo(opts, cpus, csobj)

    for pname in opts:
        _print_cstate_prop(aggr_pinfo, pname, csobj, cpuinfo)

def handle_set_opts(opts, cpus, csobj, msr, cpuinfo):
    """
    Handle C-state configuration options other than '--enable' and '--disable' which have to be
    set.
    """

    if not opts:
        return

    # Start a transaction, which will delay and aggregate MSR writes until the transaction
    # is committed.
    msr.start_transaction()

    csobj.set_props(opts, cpus)
    for pname, val in opts.items():
        name = csobj.props[pname]["name"]
        _print_cstate_prop_msg(name, "set to", val, cpuinfo, cpus=cpus)

    # Commit the transaction. This will flush all the change MSRs (if there were any).
    msr.commit_transaction()

def handle_enable_disable_opts(opts, cpus, cpuinfo, rcsobj):
    """Handle the '--enable' and '--disable' options of the 'cstates config' command."""

    for optname, optval in opts.items():
        method = getattr(rcsobj, f"{optname}_cstates")
        toggled = method(csnames=optval, cpus=cpus)

        # The 'toggled' dictionary is indexed with CPU number. But we want to print a single line
        # for all CPU numbers that have the same toggled C-states list. Build a "reversed" version
        # of the 'toggled' dictionary for these purposes.
        revdict = {}
        for cpu, csinfo in toggled.items():
            key = ",".join(csinfo["csnames"])
            if key not in revdict:
                revdict[key] = []
            revdict[key].append(cpu)

        for cstnames, cpunums in revdict.items():
            cstnames = cstnames.split(",")
            _LOG.info("%sd %s on %s",
                      optname.title(), _fmt_csnames(cstnames), _fmt_cpus(cpunums, cpuinfo))

def cstates_config_command(args, proc):
    """Implements the 'cstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    _PepcCommon.check_tuned_presence(proc)

    # The '--enable' and '--disable' optoins.
    enable_opts = {}
    # Options to set (excluding '--enable' and '--disable').
    set_opts = {}
    # Options to print (excluding '--enable' and '--disable').
    print_opts = []

    for optname, optval in args.oargs.items():
        if optname in {"enable", "disable"}:
            enable_opts[optname] = optval
        elif optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, \
         CStates.ReqCStates(proc=proc, cpuinfo=cpuinfo) as rcsobj:

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        handle_enable_disable_opts(enable_opts, cpus, cpuinfo, rcsobj)

        if not set_opts and not print_opts:
            return

        with MSR.MSR(proc=proc, cpuinfo=cpuinfo) as msr, \
            CStates.CStates(proc=proc, cpuinfo=cpuinfo, rcsobj=rcsobj, msr=msr) as csobj:

            handle_set_opts(set_opts, cpus, csobj, msr, cpuinfo)
            handle_print_opts(print_opts, cpus, csobj, cpuinfo)

def cstates_info_command(args, proc):
    """Implements the 'cstates info' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, \
         CStates.ReqCStates(proc=proc, cpuinfo=cpuinfo) as rcsobj:
        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus=0)

        first = True
        for cpu, csinfo in rcsobj.get_cstates_info(csnames=args.csnames, cpus=cpus):
            for cstate in csinfo.values():
                if not first:
                    _LOG.info("")
                first = False

                _LOG.info("CPU: %d", cpu)
                _LOG.info("Name: %s", cstate["name"])
                _LOG.info("Index: %d", cstate["index"])
                _LOG.info("Description: %s", cstate["desc"])
                _LOG.info("Status: %s", "disabled" if cstate["disable"] else "enabled")
                _LOG.info("Expected latency: %d μs", cstate["latency"])
                _LOG.info("Target residency: %d μs", cstate["residency"])
                _LOG.info("Requested: %d times", cstate["usage"])
