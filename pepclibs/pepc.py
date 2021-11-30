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
pepc - Power, Energy, and Performance Configuration tool for Linux.
"""

import sys
import logging
import argparse
try:
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from wultlibs.helperlibs import Systemctl
from pepclibs.helperlibs import ArgParse, Procs, Logging, SSH, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import ASPM, CPUIdle, CPUInfo, CPUOnline, CPUFreq

if sys.version_info < (3,7):
    raise SystemExit("Error: this tool requires python version 3.7 or higher")

VERSION = "1.1.4"
OWN_NAME = "pepc"

LOG = logging.getLogger()
Logging.setup_logger(prefix=OWN_NAME)

class PepcArgsParser(ArgParse.ArgsParser):
    """
    The default argument parser does not allow defining "global" options, so that they are present
    in every subcommand. In our case we want the SSH options to be available everywhere. This class
    add the capability.
    """

    def parse_args(self, *args, **kwargs): # pylint: disable=no-member
        """Parse unknown arguments from ArgParse class."""

        args, uargs = super().parse_known_args(*args, **kwargs)
        if not uargs:
            return args

        for opt in ArgParse.SSH_OPTIONS:
            if opt.short in uargs:
                optname = opt.short
            elif opt.long in uargs:
                optname = opt.long
            else:
                continue

            val_idx = uargs.index(optname) + 1
            if len(uargs) <= val_idx or uargs[val_idx].startswith("-"):
                raise Error(f"value required for argument '{optname}'")

            setattr(args, opt.kwargs["dest"], uargs[val_idx])
            uargs.remove(uargs[val_idx])
            uargs.remove(optname)

        if uargs:
            raise Error(f"unrecognized option(s): {' '.join(uargs)}")
        return args

def check_tuned_presence(proc):
    """Check if the 'tuned' service is active, and if it is, print a warning message."""

    with Systemctl.Systemctl(proc=proc) as systemctl:
        if systemctl.is_active("tuned"):
            LOG.warning("'tuned' service is active%s, and it may prevent '%s' from changing some " \
                        "settings, or override the changes made by '%s' with 'tuned' values",
                        proc.hostmsg, OWN_NAME, OWN_NAME)

def cpu_hotplug_info_command(_, proc):
    """Implements the 'cpu-hotplug info' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        cpugeom = cpuinfo.get_cpu_geometry()

    for key, word in (("nums", "online"), ("offline_cpus", "offline")):
        if not cpugeom["CPU"][key]:
            LOG.info("No %s CPUs%s", word, proc.hostmsg)
        else:
            LOG.info("The following CPUs are %s%s:", word, proc.hostmsg)
            LOG.info("%s", Human.rangify(cpugeom["CPU"][key]))

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

def get_cpus(args, proc, default_cpus="all", cpuinfo=None):
    """
    Get list of CPUs based on requested packages, cores and CPUs. If no CPUs, cores and packages are
    requested, returns 'default_cpus'.
    """

    close = False
    cpus = []

    if not cpuinfo:
        cpuinfo = CPUInfo.CPUInfo(proc=proc)
        close = True

    try:
        if args.cpus:
            cpus += cpuinfo.get_cpu_list(cpus=args.cpus)
        if args.cores:
            cpus += cpuinfo.cores_to_cpus(cores=args.cores)
        if args.packages:
            cpus += cpuinfo.packages_to_cpus(packages=args.packages)

        if not cpus and default_cpus is not None:
            cpus = cpuinfo.get_cpu_list(default_cpus)

        cpus = Trivial.list_dedup(cpus)
    finally:
        if close:
            cpuinfo.close()

    return cpus

def cpu_hotplug_online_command(args, proc):
    """Implements the 'cpu-hotplug online' command."""

    with CPUOnline.CPUOnline(progress=logging.INFO, proc=proc) as onl:
        onl.online(cpus=args.cpus)

def cpu_hotplug_offline_command(args, proc):
    """Implements the 'cpu-hotplug offline' command."""

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo, \
        CPUOnline.CPUOnline(progress=logging.INFO, proc=proc, cpuinfo=cpuinfo) as onl:
        cpus = get_cpus(args, proc, cpuinfo=cpuinfo)

        if not args.siblings:
            onl.offline(cpus=cpus)
            return

        cpugeom = cpuinfo.get_cpu_geometry()
        siblings_to_offline = []
        for siblings in cpugeom["core"]["nums"].values():
            siblings_to_offline += siblings[1:]

        siblings_to_offline = set(cpus) & set(siblings_to_offline)

        if not siblings_to_offline:
            LOG.warning("nothing to offline%s, no siblings among the following CPUs:%s",
                         proc.hostmsg, Human.rangify(cpus))
        else:
            onl.offline(cpus=siblings_to_offline)

def cstates_info_command(args, proc):
    """Implements the 'cstates info' command."""

    cpus = get_cpus(args, proc, default_cpus=0)

    first = True
    with CPUIdle.CPUIdle(proc=proc) as cpuidle:
        for info in cpuidle.get_cstates_info(cpus=cpus, cstates=args.cstates):
            if not first:
                LOG.info("")
            first = False

            LOG.info("CPU: %d", info["CPU"])
            LOG.info("Name: %s", info["name"])
            LOG.info("Index: %d", info["index"])
            LOG.info("Description: %s", info["desc"])
            LOG.info("Status: %s", "disabled" if info["disable"] else "enabled")
            LOG.info("Expected latency: %d μs", info["latency"])
            LOG.info("Target residency: %d μs", info["residency"])
            LOG.info("Requested: %d times", info["usage"])

def cstates_set_command(args, proc):
    """Implements the 'cstates set' command."""

    if not getattr(args, "oargs", None):
        raise Error("please, provide the list of C-states to enable or disable")

    cpus = get_cpus(args, proc)

    with CPUIdle.CPUIdle(proc=proc) as cpuidle:
        for name, cstates in args.oargs:
            method = getattr(cpuidle, f"{name}_cstates")
            cpus, cstates = method(cpus=cpus, cstates=cstates)

            if cstates in ("all", None):
                msg = "all C-states"
            else:
                msg = "C-state(s) "
                msg += ", ".join(cstates)

            with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
                scope = get_scope_msg(proc, cpuinfo, cpus)
            LOG.info("%sd %s%s", name.title(), msg, scope)

def print_cstate_config_options(args, proc, cpuinfo, cpuidle, feature):
    """Print information about options related to C-state, such as C-state prewake."""

    scope = cpuidle.get_scope(feature)

    cpus = []
    if scope == "package":
        pkgs = cpuinfo.get_package_list(args.packages)
        for pkg in pkgs:
            cpus.append(cpuinfo.packages_to_cpus(packages=pkg)[0])
    else:
        cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)

    keys = cpuidle.features[feature]["keys"] + [scope]
    keys_descr = CPUIdle.CSTATE_KEYS_DESCR
    first = True

    for info in cpuidle.get_cstates_config(cpus, keys=keys):
        if info.get("pkg_cstate_limit_supported"):
            if first:
                pcsinfo = info.get("pkg_cstate_limits")
                codes_str = ", ".join(limit for limit in pcsinfo["codes"])
                LOG.info("Package C-state limits available%s: %s", proc.hostmsg, codes_str)
                if pcsinfo["aliases"]:
                    aliases_str = ",".join(f"{al}={nm}" for al, nm in pcsinfo["aliases"].items())
                    LOG.info("Aliases: %s", aliases_str)
            locked = "locked" if info["pkg_cstate_limit"]["locked"] else "un-locked"
            LOG.info("Package %s: %s, MSR is %s", info["package"],
                     info["pkg_cstate_limit"]["limit"], locked)
        if info.get("cstate_prewake_supported"):
            enabled =  bool_fmt(info["cstate_prewake"])
            LOG.info("Package %s: %s: %s", info["package"], keys_descr["cstate_prewake"], enabled)
        if "c1e_autopromote" in info:
            enabled =  bool_fmt(info["c1e_autopromote"])
            LOG.info("Package %s: %s: %s", info["package"], keys_descr["c1e_autopromote"], enabled)
        if "c1_demotion" in info:
            enabled =  bool_fmt(info["c1_demotion"])
            LOG.info("CPU %s: %s: %s", info["CPU"], keys_descr["c1_demotion"], enabled)
        if "c1_undemotion" in info:
            enabled =  bool_fmt(info["c1_undemotion"])
            LOG.info("CPU %s: %s: %s", info["CPU"], keys_descr["c1_undemotion"], enabled)
        first = False

def print_scope_warning(args, optname, scope):
    """
    Check that the the '--packages', '--cores', and '--cpus' options provided by the user for
    '--optname' match the scope 'scope' of the option. E.g., if an option has package scope,
    '--cpus' should not be used.
    """

    if scope == "package":
        if getattr(args, "cpus") or getattr(args, "cores"):
            LOG.warning("the '%s' option has package scope, so '--cpus' and '--cores' options "
                        "should not be used with '%s'. It is recommended to have it be the same "
                        "on all CPUs of a package. Otherwise the result depends on how the "
                        "platform resolves the conflicting values.", optname, optname)
    elif scope == "core":
        if getattr(args, "cpus"):
            LOG.warning("the '%s' option has core scope, so the '--cpus' option should not be "
                        "used with '%s'.\nIt is recommended to have it be the same on all CPUs "
                        "of a core. Otherwise the result depends on how the platform resolves "
                        "the conflicting values.", optname, optname)

def handle_cstate_config_options(args, proc, cpuinfo, cpuidle):
    """Handle options related to C-state, such as setting C-state prewake."""

    # The CPUs to apply the config changes to.
    cpus = get_cpus(args, proc, cpuinfo=cpuinfo)

    for feature in cpuidle.features:
        if not hasattr(args, feature):
            continue

        value = getattr(args, feature)
        if value:
            optname = "--" + feature.replace("_", "-")
            scope = cpuidle.get_scope(feature)
            print_scope_warning(args, optname, scope)

            LOG.info("Set %s to '%s' on CPUs '%s'%s",
                     feature, value, Human.rangify(cpus), proc.hostmsg)
            cpuidle.set_feature(feature, value, cpus)
        else:
            print_cstate_config_options(args, proc, cpuinfo, cpuidle, feature)

def cstates_config_command(args, proc):
    """Implements the 'cstates config' command."""

    if not any([hasattr(args, opt) for opt in CPUIdle.FEATURES]):
        raise Error("please, provide a configuration option")

    check_tuned_presence(proc)

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        with CPUIdle.CPUIdle(proc=proc, cpuinfo=cpuinfo) as cpuidle:
            handle_cstate_config_options(args, proc, cpuinfo, cpuidle)

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

def bool_fmt(val):
    """Convert boolean value to "yes" or "no" string."""

    return "yes" if val else "no"

def check_uncore_options(args):
    """Verify that '--cpus' and '--cores' are not used with uncore commands."""

    if args.cpus or args.cores:
        opt = "--cpus"
        if args.cores:
            opt = "--cores"
        raise Error(f"uncore options are per-package, '{opt}' cannot be used")

def print_pstates_info(proc, cpuinfo, keys=None, cpus="all"):
    """Print CPU P-states information."""

    keys_descr = CPUFreq.CPUFREQ_KEYS_DESCR
    keys_descr.update(CPUFreq.UNCORE_KEYS_DESCR)

    first = True
    with CPUFreq.CPUFreq(proc=proc, cpuinfo=cpuinfo) as cpufreq:
        for info in cpufreq.get_freq_info(cpus, keys=keys, fail_on_unsupported=False):
            if not first:
                LOG.info("")
            first = False
            if "CPU" in info:
                LOG.info("%s: %d", keys_descr["CPU"], info["CPU"])
            if "pkg" in info:
                LOG.info("%s: %d", keys_descr["pkg"], info["pkg"])
            if "die" in info:
                LOG.info("%s: %d", keys_descr["die"], info["die"])
            if "base" in info:
                LOG.info("%s: %s", keys_descr["base"], khz_fmt(info["base"]))
            if "max_eff" in info:
                LOG.info("%s: %s", keys_descr["max_eff"], khz_fmt(info["max_eff"]))
            if "max_turbo" in info:
                LOG.info("%s: %s", keys_descr["max_turbo"], khz_fmt(info["max_turbo"]))
            if "cpu_min_limit" in info:
                LOG.info("%s: %s", keys_descr["cpu_min_limit"], khz_fmt(info["cpu_min_limit"]))
            if "cpu_max_limit" in info:
                LOG.info("%s: %s", keys_descr["cpu_max_limit"], khz_fmt(info["cpu_max_limit"]))
            if "cpu_min" in info:
                LOG.info("%s: %s", keys_descr["cpu_min"], khz_fmt(info["cpu_min"]))
            if "cpu_max" in info:
                LOG.info("%s: %s", keys_descr["cpu_max"], khz_fmt(info["cpu_max"]))
            if "uncore_min_limit" in info:
                limit = khz_fmt(info["uncore_min_limit"])
                LOG.info("%s: %s", keys_descr["uncore_min_limit"], limit)
            if "uncore_max_limit" in info:
                limit = khz_fmt(info["uncore_max_limit"])
                LOG.info("%s: %s", keys_descr["uncore_max_limit"], limit)
            if "uncore_min" in info:
                LOG.info("%s: %s", keys_descr["uncore_min"], khz_fmt(info["uncore_min"]))
            if "uncore_max" in info:
                LOG.info("%s: %s", keys_descr["uncore_max"], khz_fmt(info["uncore_max"]))
            if "hwp_supported" in info:
                LOG.info("%s: %s", keys_descr["hwp_supported"], bool_fmt(info["hwp_supported"]))
            if "hwp_enabled" in info and info.get("hwp_supported"):
                LOG.info("%s: %s", keys_descr["hwp_enabled"], bool_fmt(info["hwp_enabled"]))
            if "turbo_supported" in info:
                LOG.info("%s: %s", keys_descr["turbo_supported"], bool_fmt(info["turbo_supported"]))
            if "turbo_enabled" in info and info.get("turbo_supported"):
                LOG.info("%s: %s", keys_descr["turbo_enabled"], bool_fmt(info["turbo_enabled"]))
            if "driver" in info:
                LOG.info("%s: %s", keys_descr["driver"], info["driver"])
            if "governor" in info:
                LOG.info("%s: %s", keys_descr["governor"], info["governor"])
            if "governors" in info:
                LOG.info("%s: %s", keys_descr["governors"], ", ".join(info["governors"]))
            if "epp_supported" in info:
                if not info.get("epp_supported"):
                    LOG.info("%s: %s", keys_descr["epp_supported"], bool_fmt(info["epp_supported"]))
                else:
                    if "epp" in info:
                        LOG.info("%s: %d", keys_descr["epp"], info["epp"])
                    if info.get("epp_policy"):
                        LOG.info("%s: %s", keys_descr["epp_policy"], info["epp_policy"])
                    if info.get("epp_policies"):
                        epp_policies_str = ", ".join(info["epp_policies"])
                        LOG.info("%s: %s", keys_descr["epp_policies"], epp_policies_str)
            if "epb_supported" in info:
                if not info.get("epb_supported"):
                    LOG.info("%s: %s", keys_descr["epb_supported"], bool_fmt(info["epb_supported"]))
                else:
                    if "epb" in info:
                        LOG.info("%s: %d", keys_descr["epb"], info["epb"])
                    if info.get("epb_policy"):
                        LOG.info("%s: %s", keys_descr["epb_policy"], info["epb_policy"])
                    if info.get("epb_policies"):
                        epb_policies_str = ", ".join(info["epb_policies"])
                        LOG.info("%s: %s", keys_descr["epb_policies"], epb_policies_str)

def print_uncore_info(args, proc):
    """Print uncore frequency information."""

    check_uncore_options(args)
    keys_descr = CPUFreq.UNCORE_KEYS_DESCR

    first = True
    with CPUFreq.CPUFreq(proc) as cpufreq:
        for info in cpufreq.get_uncore_info(args.packages):
            if not first:
                LOG.info("")
            first = False

            LOG.info("%s: %s", keys_descr["pkg"], info["pkg"])
            LOG.info("%s: %s", keys_descr["die"], info["die"])
            LOG.info("%s: %s", keys_descr["uncore_min"], khz_fmt(info["uncore_min"]))
            LOG.info("%s: %s", keys_descr["uncore_max"], khz_fmt(info["uncore_max"]))
            LOG.info("%s: %s", keys_descr["uncore_min_limit"], khz_fmt(info["uncore_min_limit"]))
            LOG.info("%s: %s", keys_descr["uncore_max_limit"], khz_fmt(info["uncore_max_limit"]))

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

    check_tuned_presence(proc)

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
                LOG.info("%s%s", msg, get_scope_msg(proc, cpuinfo, nums, scope=scope))

            info_keys = []
            for info_opt, key in opt_info["opt_key_map"]:
                if hasattr(args, info_opt) and getattr(args, info_opt, None) is None:
                    info_keys.append(key)

            if info_keys:
                info_keys += opt_info["info_keys"]
                print_pstates_info(proc, cpuinfo, keys=info_keys, cpus=opt_info["info_nums"])

def handle_pstate_config_options(args, proc, cpuinfo, cpufreq):
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

    cpus = get_cpus(args, proc, cpuinfo=cpuinfo)

    for optname, optinfo in opts.items():
        optval = getattr(args, optname)
        if optval is not None:

            scope = cpufreq.get_scope(optname)
            msg = get_scope_msg(proc, cpuinfo, cpus, scope=scope)
            cpufreq.set_feature(optname, optval, cpus=cpus)
            LOG.info("Set %s to '%s'%s", CPUFreq.FEATURES[optname]["name"], optval, msg)
        else:
            cpus = get_cpus(args, proc, default_cpus=0, cpuinfo=cpuinfo)
            optinfo["keys"].add("CPU")
            print_pstates_info(proc, cpuinfo, keys=optinfo["keys"], cpus=cpus)

def pstates_config_command(args, proc):
    """Implements the 'pstates config' command."""

    if not any((hasattr(args, "governor"), hasattr(args, "turbo"), hasattr(args, "epb"),
                hasattr(args, "epp"))):
        raise Error("please, provide a configuration option")

    check_tuned_presence(proc)

    with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
        cpus = get_cpus(args, proc, cpuinfo=cpuinfo)

        if hasattr(args, "turbo") and cpus != cpuinfo.get_cpu_list("all"):
            LOG.warning("the turbo setting is global, '--cpus', '--cores', and '--packages' "
                        "options are ignored")

        with CPUFreq.CPUFreq(proc=proc, cpuinfo=cpuinfo) as cpufreq:
            handle_pstate_config_options(args, proc, cpuinfo, cpufreq)

def aspm_info_command(_, proc):
    """Implements the 'aspm info'. command"""

    with ASPM.ASPM(proc=proc) as aspm:
        cur_policy = aspm.get_policy()
        LOG.info("Active ASPM policy%s: %s", proc.hostmsg, cur_policy)
        available_policies = ", ".join(aspm.get_policies())
        LOG.info("Available policies: %s", available_policies)

def aspm_set_command(args, proc):
    """Implements the 'aspm set' command."""

    with ASPM.ASPM(proc=proc) as aspm:
        old_policy = aspm.get_policy()
        if not args.policy:
            LOG.info("Active ASPM policy%s: %s", proc.hostmsg, old_policy)
            return

        if args.policy == old_policy:
            LOG.info("ASPM policy%s is already '%s', nothing to change", proc.hostmsg, args.policy)
        else:
            aspm.set_policy(args.policy)
            new_policy = aspm.get_policy()
            if args.policy != new_policy:
                raise Error(f"ASPM policy{proc.hostmsg} was set to '{args.policy}', but it became "
                            f"'{new_policy}' instead")
            LOG.info("ASPM policy%s was changed from '%s' to '%s'",
                     proc.hostmsg, old_policy, args.policy)

def build_arguments_parser():
    """A helper function which parses the input arguments."""

    cpu_list_txt = """The list can include individual CPU numbers and CPU number ranges. For
                      example, '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12.
                      Use the special keyword 'all' to specify all CPUs"""
    core_list_txt = """The list can include individual core numbers and core number ranges. For
                       example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
                       Use the special keyword 'all' to specify all cores"""
    pkg_list_txt = """The list can include individual package numbers and package number ranges. For
                      example, '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
                      3. Use the special keyword 'all' to specify all packages"""

    # We rename destination variables for the '--package', '--core', and '--cpu' options in some
    # cases in order to make them match level names used in the 'CPUInfo' module. See
    # 'CPUInfo.LEVELS'.

    text = "pepc - Power, Energy, and Performance Configuration tool for Linux."
    parser = PepcArgsParser(description=text, prog=OWN_NAME, ver=VERSION)

    ArgParse.add_ssh_options(parser)

    text = "Force coloring of the text output."
    parser.add_argument("--force-color", action="store_true", help=text)
    subparsers = parser.add_subparsers(title="commands", metavar="")
    subparsers.required = True

    #
    # Create parser for the 'cpu-hotplug' command.
    #
    text = "CPU online/offline commands."
    descr = """CPU online/offline commands."""
    subpars = subparsers.add_parser("cpu-hotplug", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands", metavar="")

    #
    # Create parser for the 'cpu-hotplug info' command.
    #
    text = """List online and offline CPUs."""
    subpars2 = subparsers2.add_parser("info", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_info_command)

    #
    # Create parser for the 'cpu-hotplug online' command.
    #
    text = """Bring CPUs online (all CPUs by default)."""
    subpars2 = subparsers2.add_parser("online", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_online_command)

    text = f"""List of CPUs to online. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    #
    # Create parser for the 'cpu-hotplug offline' command.
    #
    text = """Bring CPUs offline (all CPUs by default)."""
    subpars2 = subparsers2.add_parser("offline", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_offline_command)

    text = f"""List of CPUs to offline. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)
    text = """Same as '--cpus', but specifies list of cores."""
    subpars2.add_argument("--cores", help=text)
    text = """Same as '--cpus', but specifies list of packages."""
    subpars2.add_argument("--packages", help=text)
    text = """Offline all sibling CPUs, making sure there is only one logical CPU per core left
              online. If none of '--cpus', '--cores', '--package' options were specified, this option
              effectively disables hyper-threading. Otherwise, this option will find all sibling
              CPUs among the selected CPUs, and disable all siblings except for the first sibling in
              each group of CPUs belonging to the same core."""
    subpars2.add_argument("--siblings", action="store_true", help=text)

    #
    # Create parser for the 'cstates' command.
    #
    text = "CPU C-state commands."
    descr = """Various commands related to CPU C-states."""
    subpars = subparsers.add_parser("cstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands", metavar="")

    cst_list_text = """You can specify C-states either by name (e.g., 'C1') or by the index. Use
                      'all' to specify all the available C-states (this is the default)"""
    #
    # Create parser for the 'cstates info' command.
    #
    text = "Get CPU C-states information."
    descr = """Get information about C-states on specified CPUs (CPU0 by default). Remember, this is
               information about the C-states that Linux can request, they are not necessarily the
               same as the C-states supported by the underlying hardware."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=cstates_info_command)

    text = f"""Comma-sepatated list of C-states to get information about (all C-states by default).
               {cst_list_text}."""
    subpars2.add_argument("--cstates", help=text)

    text = f"""List of CPUs to get information about. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to get information about. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to get information about. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    #
    # Create parser for the 'cstates set' command.
    #
    text = "Enable or disable C-states."
    descr = """Enable or disable specified C-states on specified CPUs (all CPUs by default).
               Note, C-states will be enabled/disabled in the same order as the '--enable' and
               '--disable' options are specified."""
    subpars2 = subparsers2.add_parser("set", help=text, description=descr)
    subpars2.set_defaults(func=cstates_set_command)

    text = f"""Comma-sepatated list of C-states to enable (all by default). {cst_list_text}."""
    subpars2.add_argument("--enable", action=ArgParse.OrderedArg, help=text)

    text = """Similar to '--enable', but specifies the list of C-states to disable."""
    subpars2.add_argument("--disable", action=ArgParse.OrderedArg, help=text)

    text = f"""List of CPUs to enable the specified C-states on. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to enable the specified C-states on. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to enable the specified C-states on. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    #
    # Create parser for the 'cstates config' command.
    #
    text = """Configure other C-state aspects."""
    subpars2 = subparsers2.add_parser("config", help=text, description=text)
    subpars2.set_defaults(func=cstates_config_command)

    text = f"""List of CPUs to configure. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    for name, info in CPUIdle.FEATURES.items():
        kwargs = {}
        kwargs["default"] = argparse.SUPPRESS
        kwargs["nargs"] = "?"

        # Only the binary "on/off" type features have the "enabled" key.
        if "enabled" in info:
            text = "Enable or disable "
            kwargs["choices"] = info["choices"]
            choices = " or ".join([f"\"{val}\"" for val in info["choices"]])
            choices = f" Use {choices}."
        else:
            text = "Set "
            choices = ""

        option = f"--{name.replace('_', '-')}"
        text += f"""{info["name"]} (applicaple only to Intel CPU). {info["help"]}{choices}
                    {info["name"]} setting has {info["scope"]} scope. By default this option
                    applies to all {info["scope"]}s. If you do not pass any argument to
                    "{option}", it will print the current values."""

        kwargs["help"] = text
        subpars2.add_argument(option, **kwargs)

    #
    # Create parser for the 'pstates' command.
    #
    text = "P-state commands."
    descr = """Various commands related to P-states (CPU performance states)."""
    subpars = subparsers.add_parser("pstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands", metavar="")

    #
    # Create parser for the 'pstates info' command.
    #
    text = "Get P-states information."
    descr = "Get P-states information for specified CPUs (CPU0 by default)."
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=pstates_info_command)

    text = f"""List of CPUs to get information about. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to get information about. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to get information about. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    ucfreq_txt = """Uncore frequency is per-package, therefore, the '--cpus' and '--cores' options
                    should not be used with this option."""
    text = f"""By default this command provides CPU (core) frequency (P-state) information, but if
               this option is used, it will provide uncore frequency information instead. The uncore
               includes the interconnect between the cores, the shared cache, and other resources
               shared between the cores. {ucfreq_txt}"""
    subpars2.add_argument("--uncore", dest="uncore", action="store_true", help=text)

    #
    # Create parser for the 'pstates set' command.
    #
    text = """Set CPU or uncore frequency."""
    descr = """Set CPU frequency for specified CPUs (all CPUs by default) or uncore frequency for
               specified packages (all packages by default)."""
    subpars2 = subparsers2.add_parser("set", help=text, description=descr)
    subpars2.set_defaults(func=pstates_set_command)

    text = f"""List of CPUs to set frequencies for. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to set frequencies for. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to set frequencies for. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    freq_txt = """The default unit is 'kHz', but 'Hz', 'MHz', and 'GHz' can also be used, for
                  example '900MHz'."""
    text = f"""Set minimum CPU frequency. {freq_txt} Additionally, one of the following specifiers
               can be used: min,lfm - minimum supported frequency (LFM), eff - maximum effeciency
               frequency, base,hfm - base frequency (HFM), max - maximum supported frequency."""
    subpars2.add_argument("--min-freq", default=argparse.SUPPRESS, nargs="?", dest="minfreq",
                          help=text)

    text = """Same as '--min-freq', but for maximum CPU frequency."""
    subpars2.add_argument("--max-freq", default=argparse.SUPPRESS, nargs="?", dest="maxfreq",
                          help=text)

    text = f"""Set minimum uncore frequency. {freq_txt} Additionally, one of the following
               specifiers can be used: 'min' - the minimum supported uncore frequency, 'max' - the
               maximum supported uncore frequency. {ucfreq_txt}"""
    subpars2.add_argument("--min-uncore-freq", default=argparse.SUPPRESS, nargs="?",
                          dest="minufreq", help=text)

    text = """Same as '--min-uncore-freq', but for maximum uncore frequency."""
    subpars2.add_argument("--max-uncore-freq", default=argparse.SUPPRESS, nargs="?",
                          dest="maxufreq", help=text)

    #
    # Create parser for the 'pstates config' command.
    #
    text = """Configure other P-state aspects."""
    descr = """Configure P-states on specified CPUs."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=pstates_config_command)

    text = f"""List of CPUs to configure P-States on. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure P-States on. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure P-States on. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    text = """Set energy performance bias hint. Hint can be integer in range of [0,15]. By default
              this option applies to all CPUs."""
    subpars2.add_argument("--epb", default=argparse.SUPPRESS, nargs="?", help=text)

    text = """Set energy performance preference. Preference can be integer in range of [0,255], or
              policy string. By default this option applies to all CPUs."""
    subpars2.add_argument("--epp", default=argparse.SUPPRESS, nargs="?", help=text)

    text = """Set CPU scaling governor. By default this option applies to all CPUs."""
    subpars2.add_argument("--governor", default=argparse.SUPPRESS, nargs="?", help=text)

    text = """Enable or disable turbo mode. Turbo on/off is global."""
    subpars2.add_argument("--turbo", default=argparse.SUPPRESS, nargs="?", choices=["on", "off"],
                          help=text)

    #
    # Create parser for the 'aspm' command.
    #
    text = "PCI ASPM commands."
    descr = """Manage Active State Power Management configuration."""
    subpars = subparsers.add_parser("aspm", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands", metavar="")

    text = "Get PCI ASPM information."
    descr = """Get information about currrent PCI ASPM configuration."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=aspm_info_command)

    text = descr = """Change PCI ASPM configuration."""
    subpars2 = subparsers2.add_parser("set", help=text, description=descr)
    subpars2.set_defaults(func=aspm_set_command)

    text = """Specify the PCI ASPM policy to be set, use "default" to set the policy to its default
               value."""
    subpars2.add_argument("--policy", nargs="?", help=text)

    if argcomplete:
        argcomplete.autocomplete(parser)

    return parser

def parse_arguments():
    """Parse input arguments."""

    parser = build_arguments_parser()
    args = parser.parse_args()

    return args

def get_proc(args):
    """Returns and "SSH" object or the 'Procs' object depending on 'hostname'."""

    if args.hostname == "localhost":
        proc = Procs.Proc()
    else:
        proc = SSH.SSH(hostname=args.hostname, username=args.username, privkeypath=args.privkey,
                       timeout=args.timeout)
    return proc

def main():
    """Script entry point."""

    try:
        args = parse_arguments()

        if not getattr(args, "func", None):
            LOG.error("please, run '%s -h' for help", OWN_NAME)
            return -1

        proc = get_proc(args)
        args.func(args, proc)
    except KeyboardInterrupt:
        LOG.info("\nInterrupted, exiting")
        return -1
    except Error as err:
        LOG.error(err)
        return -1

    return 0

if __name__ == "__main__":
    sys.exit(main())
