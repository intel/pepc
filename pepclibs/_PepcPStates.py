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
This module includes the "pstates" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUFreq, _PepcCommon
from pepclibs._PepcCommon import bool_fmt, get_cpus

_LOG = logging.getLogger()

def khz_fmt(val):
    """
    Convert an integer value representing "kHz" into string. To make it more human-friendly, if
    'val' is a huge number, convert it into a larger unit, like "MHz" or "GHz".
    """

    for unit in ("kHz", "MHz", "GHz"):
        if val < 1000:
            break
        val /= 1000
    return f"{val}{unit}"

def check_uncore_options(args):
    """Verify that '--cpus' and '--cores' are not used with uncore commands."""

    if args.cpus or args.cores:
        opt = "--cpus"
        if args.cores:
            opt = "--cores"
        raise Error(f"uncore options are per-package, '{opt}' cannot be used")

def get_scope_msg(proc, cpuinfo, nums, scope="CPU"):
    """
    Helper function to return user friendly string of host information and the CPUs or packages
    listed in 'nums'.
    """

    scopes = ("CPU", "core", "package", "global")
    if scope not in scopes:
        raise Error(f"bad scope '{scope}' use one of following: {', '.join(scopes)}")

    get_method = getattr(cpuinfo, f"get_{scope.lower()}s", None)
    if get_method:
        all_nums = get_method()

        if nums in ("all", None) or nums == all_nums:
            scope = f"all {scope}s"
        else:
            scope = f"{scope}(s): {Human.rangify(nums)}"
    else:
        scope = "all CPUs in all packages (globally)"

    return f"{proc.hostmsg} for {scope}"

def print_pstates_info(proc, cpuinfo, keys=None, cpus="all"):
    """Print CPU P-states information."""

    keys_descr = CPUFreq.CPUFREQ_KEYS_DESCR
    keys_descr.update(CPUFreq.UNCORE_KEYS_DESCR)

    first = True
    with CPUFreq.CPUFreq(proc=proc, cpuinfo=cpuinfo) as cpufreq:
        for info in cpufreq.get_freq_info(cpus, keys=keys, fail_on_unsupported=False):
            if not first:
                _LOG.info("")
            first = False
            if "CPU" in info:
                _LOG.info("%s: %d", keys_descr["CPU"], info["CPU"])
            if "pkg" in info:
                _LOG.info("%s: %d", keys_descr["pkg"], info["pkg"])
            if "die" in info:
                _LOG.info("%s: %d", keys_descr["die"], info["die"])
            if "base" in info:
                _LOG.info("%s: %s", keys_descr["base"], khz_fmt(info["base"]))
            if "max_eff" in info:
                _LOG.info("%s: %s", keys_descr["max_eff"], khz_fmt(info["max_eff"]))
            if "max_turbo" in info:
                _LOG.info("%s: %s", keys_descr["max_turbo"], khz_fmt(info["max_turbo"]))
            if "cpu_min_limit" in info:
                _LOG.info("%s: %s", keys_descr["cpu_min_limit"], khz_fmt(info["cpu_min_limit"]))
            if "cpu_max_limit" in info:
                _LOG.info("%s: %s", keys_descr["cpu_max_limit"], khz_fmt(info["cpu_max_limit"]))
            if "cpu_min" in info:
                _LOG.info("%s: %s", keys_descr["cpu_min"], khz_fmt(info["cpu_min"]))
            if "cpu_max" in info:
                _LOG.info("%s: %s", keys_descr["cpu_max"], khz_fmt(info["cpu_max"]))
            if "uncore_min_limit" in info:
                limit = khz_fmt(info["uncore_min_limit"])
                _LOG.info("%s: %s", keys_descr["uncore_min_limit"], limit)
            if "uncore_max_limit" in info:
                limit = khz_fmt(info["uncore_max_limit"])
                _LOG.info("%s: %s", keys_descr["uncore_max_limit"], limit)
            if "uncore_min" in info:
                _LOG.info("%s: %s", keys_descr["uncore_min"], khz_fmt(info["uncore_min"]))
            if "uncore_max" in info:
                _LOG.info("%s: %s", keys_descr["uncore_max"], khz_fmt(info["uncore_max"]))
            if "hwp_supported" in info:
                _LOG.info("%s: %s", keys_descr["hwp_supported"], bool_fmt(info["hwp_supported"]))
            if "hwp_enabled" in info and info.get("hwp_supported"):
                _LOG.info("%s: %s", keys_descr["hwp_enabled"], bool_fmt(info["hwp_enabled"]))
            if "turbo_supported" in info:
                _LOG.info("%s: %s", keys_descr["turbo_supported"],
                                    bool_fmt(info["turbo_supported"]))
            if "turbo_enabled" in info and info.get("turbo_supported"):
                _LOG.info("%s: %s", keys_descr["turbo_enabled"], bool_fmt(info["turbo_enabled"]))
            if "driver" in info:
                _LOG.info("%s: %s", keys_descr["driver"], info["driver"])
            if "governor" in info:
                _LOG.info("%s: %s", keys_descr["governor"], info["governor"])
            if "governors" in info:
                _LOG.info("%s: %s", keys_descr["governors"], ", ".join(info["governors"]))
            if "epp_supported" in info:
                if not info.get("epp_supported"):
                    _LOG.info("%s: %s", keys_descr["epp_supported"],
                                        bool_fmt(info["epp_supported"]))
                else:
                    if "epp" in info:
                        _LOG.info("%s: %d", keys_descr["epp"], info["epp"])
                    if info.get("epp_policy"):
                        _LOG.info("%s: %s", keys_descr["epp_policy"], info["epp_policy"])
                    if info.get("epp_policies"):
                        epp_policies_str = ", ".join(info["epp_policies"])
                        _LOG.info("%s: %s", keys_descr["epp_policies"], epp_policies_str)
            if "epb_supported" in info:
                if not info.get("epb_supported"):
                    _LOG.info("%s: %s", keys_descr["epb_supported"],
                                        bool_fmt(info["epb_supported"]))
                else:
                    if "epb" in info:
                        _LOG.info("%s: %d", keys_descr["epb"], info["epb"])
                    if info.get("epb_policy"):
                        _LOG.info("%s: %s", keys_descr["epb_policy"], info["epb_policy"])
                    if info.get("epb_policies"):
                        epb_policies_str = ", ".join(info["epb_policies"])
                        _LOG.info("%s: %s", keys_descr["epb_policies"], epb_policies_str)

def print_uncore_info(args, proc):
    """Print uncore frequency information."""

    check_uncore_options(args)
    keys_descr = CPUFreq.UNCORE_KEYS_DESCR

    first = True
    with CPUFreq.CPUFreq(proc) as cpufreq:
        for info in cpufreq.get_uncore_info(args.packages):
            if not first:
                _LOG.info("")
            first = False

            _LOG.info("%s: %s", keys_descr["pkg"], info["pkg"])
            _LOG.info("%s: %s", keys_descr["die"], info["die"])
            _LOG.info("%s: %s", keys_descr["uncore_min"], khz_fmt(info["uncore_min"]))
            _LOG.info("%s: %s", keys_descr["uncore_max"], khz_fmt(info["uncore_max"]))
            _LOG.info("%s: %s", keys_descr["uncore_min_limit"], khz_fmt(info["uncore_min_limit"]))
            _LOG.info("%s: %s", keys_descr["uncore_max_limit"], khz_fmt(info["uncore_max_limit"]))

def pstates_info_command(args, proc):
    """Implements the 'pstates info' command."""

    if args.uncore:
        print_uncore_info(args, proc)
    else:
        with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
            cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            print_pstates_info(proc, cpuinfo, cpus=cpus)

def pstates_set_command(args, proc):
    """implements the 'pstates set' command."""

    _PepcCommon.check_tuned_presence(proc)

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, \
        CPUFreq.CPUFreq(proc=proc, cpuinfo=cpuinfo) as cpufreq:
        opts = {}
        if hasattr(args, "minufreq") or hasattr(args, "maxufreq"):
            check_uncore_options(args)
            opts["uncore"] = {}
            opts["uncore"]["min"] = getattr(args, "minufreq", None)
            opts["uncore"]["max"] = getattr(args, "maxufreq", None)
            opts["uncore"]["nums"] = args.packages
            opts["uncore"]["method"] = getattr(cpufreq, "set_uncore_freq")
            cpus = []
            for pkg in cpuinfo.get_package_list(args.packages):
                cpus.append(cpuinfo.packages_to_cpus(packages=pkg)[0])
            opts["uncore"]["info_nums"] = cpus
            opts["uncore"]["info_keys"] = ["pkg"]
            opts["uncore"]["opt_key_map"] = (("minufreq", "uncore_min"), ("maxufreq", "uncore_max"))

        if hasattr(args, "minfreq") or hasattr(args, "maxfreq"):
            if "uncore" in opts:
                raise Error("cpu and uncore frequency options are mutually exclusive")
            opts["CPU"] = {}
            opts["CPU"]["min"] = getattr(args, "minfreq", None)
            opts["CPU"]["max"] = getattr(args, "maxfreq", None)
            opts["CPU"]["nums"] = get_cpus(args, proc, cpuinfo=cpuinfo)
            opts["CPU"]["method"] = getattr(cpufreq, "set_freq")
            opts["CPU"]["info_keys"] = ["CPU"]
            opts["CPU"]["info_nums"] = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            opts["CPU"]["opt_key_map"] = (("minfreq", "cpu_min"), ("maxfreq", "cpu_max"))

        if not opts:
            raise Error("please, specify a frequency to change")

        for opt, opt_info in opts.items():
            if opt_info["min"] or opt_info["max"]:
                nums, minfreq, maxfreq = opt_info["method"](opt_info["min"], opt_info["max"],
                                                            opt_info["nums"])

                msg = f"set {opt} "
                if minfreq:
                    msg += f"minimum frequency to {khz_fmt(minfreq)}"
                if maxfreq:
                    if minfreq:
                        msg += " and "
                    msg += f"maximum frequency to {khz_fmt(maxfreq)}"

                scope = cpufreq.get_scope(f"{opt.lower()}-freq")
                _LOG.info("%s%s", msg, get_scope_msg(proc, cpuinfo, nums, scope=scope))

            info_keys = []
            for info_opt, key in opt_info["opt_key_map"]:
                if hasattr(args, info_opt) and getattr(args, info_opt, None) is None:
                    info_keys.append(key)

            if info_keys:
                info_keys += opt_info["info_keys"]
                print_pstates_info(proc, cpuinfo, keys=info_keys, cpus=opt_info["info_nums"])

def handle_pstate_opts(args, proc, cpuinfo, cpufreq):
    """Handle options related to P-state, such as getting or setting EPP or turbo value."""

    opts = {}

    if hasattr(args, "epb"):
        opts["epb"] = {}
        opts["epb"]["keys"] = {"epb_supported", "epb_policy", "epb"}
    if hasattr(args, "epp"):
        opts["epp"] = {}
        opts["epp"]["keys"] = {"epp_supported", "epp_policy", "epp"}
    if hasattr(args, "governor"):
        opts["governor"] = {}
        opts["governor"]["keys"] = {"governor"}
    if hasattr(args, "turbo"):
        opts["turbo"] = {}
        opts["turbo"]["keys"] = {"turbo_supported", "turbo_enabled"}

    cpus = get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)

    for optname, optinfo in opts.items():
        optval = getattr(args, optname)
        if optval is not None:

            scope = cpufreq.get_scope(optname)
            msg = get_scope_msg(proc, cpuinfo, cpus, scope=scope)
            cpufreq.set_feature(optname, optval, cpus=cpus)
            _LOG.info("Set %s to '%s'%s", CPUFreq.FEATURES[optname]["name"], optval, msg)
        else:
            cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            optinfo["keys"].add("CPU")
            print_pstates_info(proc, cpuinfo, keys=optinfo["keys"], cpus=cpus)

def pstates_config_command(args, proc):
    """Implements the 'pstates config' command."""

    if not any((hasattr(args, "governor"), hasattr(args, "turbo"), hasattr(args, "epb"),
                hasattr(args, "epp"))):
        raise Error("please, provide a configuration option")

    _PepcCommon.check_tuned_presence(proc)

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        cpus = get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)

        if hasattr(args, "turbo") and cpus != cpuinfo.get_cpu_list("all"):
            _LOG.warning("the turbo setting is global, '--cpus', '--cores', and '--packages' "
                         "options are ignored")

        with CPUFreq.CPUFreq(proc=proc, cpuinfo=cpuinfo) as cpufreq:
            handle_pstate_opts(args, proc, cpuinfo, cpufreq)
