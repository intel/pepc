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
from pepclibs import CPUIdle, CPUInfo, _PepcCommon

_LOG = logging.getLogger()

def fmt_cstates(cstates):
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

def fmt_cpus(cpus):
    """Fromats and returns the CPU numbers string, which can be used in messages."""

    if len(cpus) == 1:
        msg = "CPU "
    else:
        msg = "CPUs "

    return msg + Human.rangify(cpus)

def print_cstate_feature_message(name, action, val, cpus):
    """Format an print a message about a C-state feature 'name'."""

    if isinstance(val, bool):
        val = _PepcCommon.bool_fmt(val)

    cpus = fmt_cpus(cpus)

    if action:
        msg = f"{name}: {action} '{val}' on {cpus}"
    else:
        msg = f"{name}: '{val}' {cpus}"

    _LOG.info(msg)

def handle_cstate_config_opt(optname, optval, cpus, cpuidle):
    """
    Handle a C-state configuration option 'optname'.

    Most options can be used with and without a value. In the former case, this function sets the
    corresponding feature to the value provided. Otherwise this function reads the current value of
    the feature and prints it.
    """

    if optname in cpuidle.features:
        feature = optname
        val = optval

        cpuidle.set_feature(feature, val, cpus)

        name = cpuidle.features[feature]["name"]
        print_cstate_feature_message(name, "set to", val, cpus)
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
            _LOG.info("%sd %s on %s", optname.title(), fmt_cstates(cstnames), fmt_cpus(cpunums))

def print_cstate_feature(finfo):
    """Print C-state feature information."""

    for key, kinfo in finfo.items():
        descr = CPUIdle.CSTATE_KEYS_DESCR[key]

        for val, cpus in kinfo.items():
            if key.endswith("_supported") and val:
                # Supported features will have some other key(s) in 'kinfo', which will be printed.
                # So no need to print the "*_supported" key in case it is 'True'.
                continue

            print_cstate_feature_message(descr, "", val, cpus)

def build_finfos(features, cpus, cpuidle):
    """
    Build features dictionary, describing all featrues in the 'features' list.
    """

    all_keys = []
    finfos = {}
    key2f = {}

    for feature in features:
        finfos[feature] = {}
        for key in cpuidle.features[feature]["keys"]:
            key2f[key] = feature
            all_keys.append(key)

    all_keys.append("CPU")

    for csinfo in cpuidle.get_cstates_config(cpus, keys=all_keys):
        for key, val in csinfo.items():
            if key == "CPU":
                continue

            finfo = finfos[key2f[key]]
            if key not in finfo:
                finfo[key] = {}

            # We are going to used values as dictionary keys, in order to aggregate all CPU numbers
            # having the same value. But the 'pkg_cstate_limits' value is a dictionary, so turn it
            # into a string first.

            if key == "pkg_cstate_limits":
                codes = ", ".join(limit for limit in val["codes"])
                if val["aliases"]:
                    aliases = ",".join(f"{al}={nm}" for al, nm in val["aliases"].items())
                    codes += f" (aliases: {aliases})"
                val = codes

            if val not in finfo[key]:
                finfo[key][val] = [csinfo["CPU"]]
            else:
                finfo[key][val].append(csinfo["CPU"])

    return finfos

def print_scope_warnings(args, cpuidle):
    """
    Check that the the '--packages', '--cores', and '--cpus' options provided by the user to match
    the scope of all the options.
    """

    pkg_warn, core_warn = [], []

    for feature in CPUIdle.FEATURES:
        if not getattr(args, feature, None):
            continue

        scope = cpuidle.get_scope(feature)
        if scope == "package" and getattr(args, "cpus") or getattr(args, "cores"):
            pkg_warn.append(feature)
        elif scope == "core" and getattr(args, "cpus"):
            core_warn.append(feature)

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

    # The features to print about.
    print_features = []

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        with CPUIdle.CPUIdle(proc=proc, cpuinfo=cpuinfo) as cpuidle:
            print_scope_warnings(args, cpuidle)

            # Find all features we'll need to print about, and get their values.
            for optname, optval in args.oargs.items():
                if not optval:
                    print_features.append(optname)

            # Build features information dictionary for all options that are going to be printed.
            cpus = _PepcCommon.get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)
            finfos = build_finfos(print_features, cpus, cpuidle)

            # Now handle the options one by one, in the same order as they go in the command line.
            for optname, optval in args.oargs.items():
                if not optval:
                    print_cstate_feature(finfos[optname])
                else:
                    handle_cstate_config_opt(optname, optval, cpus, cpuidle)

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
