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
from pepclibs.msr import MSR
from pepclibs import CPUInfo, PStates
from pepctool import _PepcCommon
from pepctool._PepcCommon import get_cpus

_LOG = logging.getLogger()

def bool_fmt(val):
    """Convert boolean value to an "on" or "off" string."""

    return "on" if val else "off"

def _khz_fmt(val):
    """
    Convert an integer value representing "kHz" into string. To make it more human-friendly, if
    'val' is a huge number, convert it into a larger unit, like "MHz" or "GHz".
    """

    for unit in ("kHz", "MHz", "GHz"):
        if val < 1000:
            break
        val /= 1000
    return f"{val}{unit}"

def _get_scope_msg(proc, cpuinfo, nums, scope="CPU"):
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

def _print_pstates_info(proc, cpuinfo, keys=None, cpus="all"):
    """Print CPU P-states information."""

    keys_descr = PStates.CPUFREQ_KEYS_DESCR
    keys_descr.update(PStates.UNCORE_KEYS_DESCR)

    first = True
    with PStates.PStates(proc=proc, cpuinfo=cpuinfo) as cpufreq:
        for info in cpufreq.get_freq_info(cpus, keys=keys):
            if not first:
                _LOG.info("")
            first = False
            if "CPU" in info:
                _LOG.info("%s: %d", keys_descr["CPU"], info["CPU"])
            if "package" in info:
                _LOG.info("%s: %d", keys_descr["package"], info["package"])
            if "die" in info:
                _LOG.info("%s: %d", keys_descr["die"], info["die"])
            if "base" in info:
                _LOG.info("%s: %s", keys_descr["base"], _khz_fmt(info["base"]))
            if "max_eff" in info:
                _LOG.info("%s: %s", keys_descr["max_eff"], _khz_fmt(info["max_eff"]))
            if "max_turbo" in info:
                _LOG.info("%s: %s", keys_descr["max_turbo"], _khz_fmt(info["max_turbo"]))
            if "cpu_min_limit" in info:
                _LOG.info("%s: %s", keys_descr["cpu_min_limit"], _khz_fmt(info["cpu_min_limit"]))
            if "cpu_max_limit" in info:
                _LOG.info("%s: %s", keys_descr["cpu_max_limit"], _khz_fmt(info["cpu_max_limit"]))
            if "cpu_min" in info:
                _LOG.info("%s: %s", keys_descr["cpu_min"], _khz_fmt(info["cpu_min"]))
            if "cpu_max" in info:
                _LOG.info("%s: %s", keys_descr["cpu_max"], _khz_fmt(info["cpu_max"]))
            if "uncore_min_limit" in info:
                limit = _khz_fmt(info["uncore_min_limit"])
                _LOG.info("%s: %s", keys_descr["uncore_min_limit"], limit)
            if "uncore_max_limit" in info:
                limit = _khz_fmt(info["uncore_max_limit"])
                _LOG.info("%s: %s", keys_descr["uncore_max_limit"], limit)
            if "uncore_min" in info:
                _LOG.info("%s: %s", keys_descr["uncore_min"], _khz_fmt(info["uncore_min"]))
            if "uncore_max" in info:
                _LOG.info("%s: %s", keys_descr["uncore_max"], _khz_fmt(info["uncore_max"]))
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

def _get_uncore_cmd_packages(args, cpuinfo):
    """
    This helper function is used for uncore operations, which have package scope. It verifies that
    '--cpus' and '--cores' are not used with uncore commands. Returns the packages list.
    """

    if args.cpus or args.cores:
        opt = "--cpus"
        if args.cores:
            opt = "--cores"
        raise Error(f"uncore options are per-package, '{opt}' cannot be used")

    packages = args.packages
    if args.packages is None:
        packages = "all"

    return cpuinfo.normalize_packages(packages)

def _print_uncore_info(args, proc, cpuinfo):
    """Print uncore frequency information."""

    packages = _get_uncore_cmd_packages(args, cpuinfo)
    keys_descr = PStates.UNCORE_KEYS_DESCR

    first = True
    with PStates.PStates(proc=proc, cpuinfo=cpuinfo) as cpufreq:
        for info in cpufreq.get_uncore_info(packages):
            if not first:
                _LOG.info("")
            first = False

            _LOG.info("%s: %s", keys_descr["package"], info["package"])
            _LOG.info("%s: %s", keys_descr["die"], info["die"])
            _LOG.info("%s: %s", keys_descr["uncore_min"], _khz_fmt(info["uncore_min"]))
            _LOG.info("%s: %s", keys_descr["uncore_max"], _khz_fmt(info["uncore_max"]))
            _LOG.info("%s: %s", keys_descr["uncore_min_limit"], _khz_fmt(info["uncore_min_limit"]))
            _LOG.info("%s: %s", keys_descr["uncore_max_limit"], _khz_fmt(info["uncore_max_limit"]))

def pstates_info_command(args, proc):
    """Implements the 'pstates info' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        if args.uncore:
            _print_uncore_info(args, proc, cpuinfo)
        else:
            cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            _print_pstates_info(proc, cpuinfo, cpus=cpus)

def _handle_freq_opts(args, proc, cpuinfo, cpufreq):
    """implements the 'pstates set' command."""

    opts = {}
    if "minufreq" in args.oargs or "maxufreq" in args.oargs:
        packages = _get_uncore_cmd_packages(args, cpuinfo)

        opts["uncore"] = {}
        opts["uncore"]["min"] = args.oargs.get("minufreq", None)
        opts["uncore"]["max"] = args.oargs.get("maxufreq", None)
        opts["uncore"]["nums"] = packages
        opts["uncore"]["method"] = getattr(cpufreq, "set_uncore_freq")
        cpus = []
        for pkg in packages:
            cpus.append(cpuinfo.packages_to_cpus(packages=pkg)[0])
        opts["uncore"]["info_nums"] = cpus
        opts["uncore"]["info_keys"] = ["package"]
        opts["uncore"]["opt_key_map"] = (("minufreq", "uncore_min"), ("maxufreq", "uncore_max"))

    if "minfreq" in args.oargs or "maxfreq" in args.oargs:
        if "uncore" in opts:
            raise Error("cpu and uncore frequency options are mutually exclusive")
        opts["CPU"] = {}
        opts["CPU"]["min"] = args.oargs.get("minfreq", None)
        opts["CPU"]["max"] = args.oargs.get("maxfreq", None)
        opts["CPU"]["nums"] = get_cpus(args, proc, cpuinfo=cpuinfo)
        opts["CPU"]["method"] = getattr(cpufreq, "set_freq")
        opts["CPU"]["info_keys"] = ["CPU"]
        opts["CPU"]["info_nums"] = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
        opts["CPU"]["opt_key_map"] = (("minfreq", "cpu_min"), ("maxfreq", "cpu_max"))

    if not opts:
        return

    for opt, opt_info in opts.items():
        if opt_info["min"] or opt_info["max"]:
            nums, minfreq, maxfreq = opt_info["method"](opt_info["min"], opt_info["max"],
                                                        opt_info["nums"])

            msg = f"set {opt} "
            if minfreq:
                msg += f"minimum frequency to {_khz_fmt(minfreq)}"
            if maxfreq:
                if minfreq:
                    msg += " and "
                msg += f"maximum frequency to {_khz_fmt(maxfreq)}"

            scope = cpufreq.get_scope(f"{opt.lower()}-freq")
            _LOG.info("%s%s", msg, _get_scope_msg(proc, cpuinfo, nums, scope=scope))

        info_keys = []
        for info_opt, key in opt_info["opt_key_map"]:
            if info_opt in args.oargs and args.oargs.get(info_opt, None) is None:
                info_keys.append(key)

        if info_keys:
            info_keys += opt_info["info_keys"]
            _print_pstates_info(proc, cpuinfo, keys=info_keys, cpus=opt_info["info_nums"])

def _handle_pstate_opts(args, proc, cpuinfo, cpufreq):
    """Handle options related to P-state, such as getting or setting EPP or turbo value."""

    _handle_freq_opts(args, proc, cpuinfo, cpufreq)

    opts = {}
    if "epb" in args.oargs:
        opts["epb"] = {}
        opts["epb"]["keys"] = {"epb_supported", "epb_policy", "epb"}
    if "epp" in args.oargs:
        opts["epp"] = {}
        opts["epp"]["keys"] = {"epp_supported", "epp_policy", "epp"}
    if "governor" in args.oargs:
        opts["governor"] = {}
        opts["governor"]["keys"] = {"governor"}
    if "turbo" in args.oargs:
        opts["turbo"] = {}
        opts["turbo"]["keys"] = {"turbo_supported", "turbo_enabled"}

    cpus = get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)

    for optname, optinfo in opts.items():
        optval = getattr(args, optname)
        if optval is not None:

            scope = cpufreq.get_scope(optname)
            msg = _get_scope_msg(proc, cpuinfo, cpus, scope=scope)
            cpufreq.set_prop(optname, optval, cpus=cpus)
            _LOG.info("Set %s to '%s'%s", PStates.PROPS[optname]["name"], optval, msg)
        else:
            cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            optinfo["keys"].add("CPU")
            _print_pstates_info(proc, cpuinfo, keys=optinfo["keys"], cpus=cpus)

def pstates_config_command(args, proc):
    """Implements the 'pstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    _PepcCommon.check_tuned_presence(proc)

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, MSR.MSR(proc=proc) as msr:
        cpus = get_cpus(args, proc, default_cpus="all", cpuinfo=cpuinfo)

        if "turbo" in args.oargs and set(cpus) != set(cpuinfo.get_cpus()):
            _LOG.warning("the turbo setting is global, '--cpus', '--cores', and '--packages' "
                         "options are ignored")

        # Start a transaction, which will delay and aggregate MSR writes until the transaction
        # is committed.
        msr.start_transaction()

        with PStates.PStates(proc=proc, cpuinfo=cpuinfo, msr=msr) as cpufreq:
            _handle_pstate_opts(args, proc, cpuinfo, cpufreq)

        # Commit the transaction. This will flush all the change MSRs (if there were any).
        msr.commit_transaction()
