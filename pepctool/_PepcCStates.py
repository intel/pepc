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
from pepclibs import CPUIdle, CPUInfo
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def _fmt_cstates(cstates):
    """Fromats and returns the C-states list string, which can be used in messages."""

    if cstates in ("all", None):
        msg = "all C-states"
    else:
        if len(cstates) == 1:
            msg = "C-state "
        else:
            msg = "C-states "
        msg += ",".join(cstates)

    return msg

def _fmt_cpus(cpus):
    """Fromats and returns the CPU numbers string, which can be used in messages."""

    if len(cpus) == 1:
        msg = "CPU "
    else:
        msg = "CPUs "

    return msg + Human.rangify(cpus)

def _print_cstate_prop_msg(prop, action, val, cpus):
    """Format an print a message about a C-state property 'prop'."""

    if isinstance(val, bool):
        val = _PepcCommon.bool_fmt(val)

    cpus = _fmt_cpus(cpus)

    if action:
        msg = f"{prop}: {action} '{val}' on {cpus}"
    else:
        msg = f"{prop}: '{val}' on {cpus}"

    _LOG.info(msg)

def _handle_cstate_config_opt(optname, optval, cpus, cpuidle):
    """
    Handle a C-state configuration option 'optname'.

    Most options can be used with and without a value. In the former case, this function sets the
    corresponding C-state property to the value provided. Otherwise this function reads the current
    value of the C-state priperty and prints it.
    """

    if optname in cpuidle.props:
        cpuidle.set_prop(optname, optval, cpus)

        name = cpuidle.props[optname]["name"]
        _print_cstate_prop_msg(name, "set to", optval, cpus)
    else:
        method = getattr(cpuidle, f"{optname}_cstates")
        toggled = method(cpus=cpus, cstates=optval)

        # The 'toggled' dictionary is indexed with CPU number. But we want to print a single line
        # for all CPU numbers that have the same toggled C-states list (the assumption here is that
        # the system may be hybrid and different CPUs have different C-states). Therefore, built a
        # "revered" verion of the 'toggled' dictionary.
        revdict = {}
        for cpu, csinfo in toggled.items():
            key = ",".join(csinfo["cstates"])
            if key not in revdict:
                revdict[key] = []
            revdict[key].append(cpu)

        for cstnames, cpunums in revdict.items():
            cstnames = cstnames.split(",")
            _LOG.info("%sd %s on %s", optname.title(), _fmt_cstates(cstnames), _fmt_cpus(cpunums))

def _print_cstate_prop(prop, pinfo, cpuidle):
    """Print about C-state properties in 'pinfo'."""

    for key, kinfo in pinfo.items():
        for val, cpus in kinfo.items():
            if key.endswith("_supported") and val:
                # Supported properties will have some other key(s) in 'kinfo', which will be
                # printed. So no need to print the "*_supported" key in case it is 'True'.
                continue

            _print_cstate_prop_msg(cpuidle.props[prop]["keys"][key], "", val, cpus)

def _build_pinfos(props, cpus, cpuidle):
    """Build the properties dictionary for proparties in the 'props' list."""

    all_keys = []
    pinfos = {}
    key2f = {}

    for prop in props:
        pinfos[prop] = {}
        for key in cpuidle.props[prop]["keys"]:
            key2f[key] = prop
            all_keys.append(key)

    all_keys.append("CPU")

    for csinfo in cpuidle.get_cstates_config(cpus, keys=all_keys):
        for key, val in csinfo.items():
            if key == "CPU":
                continue

            pinfo = pinfos[key2f[key]]
            if key not in pinfo:
                pinfo[key] = {}

            # We are going to used values as dictionary keys, in order to aggregate all CPU numbers
            # having the same value. But the 'pkg_cstate_limits' value is a list, so turn it into a
            # string first.
            if key == "pkg_cstate_limits":
                val = ", ".join(val)

            if val not in pinfo[key]:
                pinfo[key][val] = [csinfo["CPU"]]
            else:
                pinfo[key][val].append(csinfo["CPU"])

    return pinfos

def _print_scope_warnings(args, cpuidle):
    """
    Check that the the '--packages', '--cores', and '--cpus' options provided by the user to match
    the scope of all the options.
    """

    pkg_warn, core_warn = [], []

    for prop in cpuidle.props:
        if not getattr(args, prop, None):
            continue

        scope = cpuidle.get_scope(prop)
        if scope == "package" and (getattr(args, "cpus") or getattr(args, "cores")):
            pkg_warn.append(prop)
        elif scope == "core" and getattr(args, "cpus"):
            core_warn.append(prop)

    if pkg_warn:
        opts = ", ".join([f"'--{opt.replace('_', '-')}'" for opt in pkg_warn])
        _LOG.warning("the following option(s) have package scope: %s, but '--cpus' or '--cores' "
                     "were used.\n\tInstead, it is recommented to specify all CPUs in a package,"
                     "totherwise the result may be undexpected and platform-dependent.", opts)
    if core_warn:
        opts = ", ".join([f"'--{opt.replace('_', '-')}'" for opt in core_warn])
        _LOG.warning("the following option(s) have core scope: %s, but '--cpus' was used."
                     "\n\tInstead, it is recommented to specify all CPUs in a core,"
                     "totherwise the result may be undexpected and platform-dependent.", opts)

def cstates_config_command(args, proc):
    """Implements the 'cstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    _PepcCommon.check_tuned_presence(proc)

    # The C-state properties to print about.
    print_props = []

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        with CPUIdle.CPUIdle(proc=proc, cpuinfo=cpuinfo) as cpuidle:
            _print_scope_warnings(args, cpuidle)

            # Find all properties we'll need to print about, and get their values.
            for optname, optval in args.oargs.items():
                if not optval:
                    print_props.append(optname)

            # Build properties information dictionary for all options that are going to be printed.
            cpus = _PepcCommon.get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)
            pinfos = _build_pinfos(print_props, cpus, cpuidle)

            # Now handle the options one by one, in the same order as they go in the command line.
            for optname, optval in args.oargs.items():
                if not optval:
                    _print_cstate_prop(optname, pinfos[optname], cpuidle)
                else:
                    _handle_cstate_config_opt(optname, optval, cpus, cpuidle)

def cstates_info_command(args, proc):
    """Implements the 'cstates info' command."""

    cpus = _PepcCommon.get_cpus(args, proc, default_cpus=0)

    first = True
    with CPUIdle.CPUIdle(proc=proc) as cpuidle:
        for info in cpuidle.get_cstates_info(cpus=cpus, cstates=args.cstates):
            if not first:
                _LOG.info("")
            first = False

            _LOG.info("CPU: %d", info["CPU"])
            _LOG.info("Name: %s", info["name"])
            _LOG.info("Index: %d", info["index"])
            _LOG.info("Description: %s", info["desc"])
            _LOG.info("Status: %s", "disabled" if info["disable"] else "enabled")
            _LOG.info("Expected latency: %d μs", info["latency"])
            _LOG.info("Target residency: %d μs", info["residency"])
            _LOG.info("Requested: %d times", info["usage"])
