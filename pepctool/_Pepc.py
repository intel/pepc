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

from pepclibs.helperlibs import ArgParse, Procs, Logging, SSH
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUIdle

if sys.version_info < (3,7):
    raise SystemExit("Error: this tool requires python version 3.7 or higher")

VERSION = "1.2.0"
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

    cst_list_text = """You can specify Linux C-states either by name (e.g., 'C1') or by the index.
                       Use 'all' to specify all the available Linux C-states (this is the default).
                       Note, there is a difference between Linux C-states (e.g., 'C6') and hardware
                       C-states (e.g., Core C6 or Package C6 on many Intel platforms). The former is
                       what Linux can request, and on Intel hardware this is usually about various
                       'mwait' instruction hints. The latter are platform-specific hardware state,
                       entered upon a Linux request."""

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
    # Create parser for the 'cstates config' command.
    #
    text = "Configure C-states."
    descr = """Configure C-states on specified CPUs."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=cstates_config_command)

    text = f"""List of CPUs to configure. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    text = f"""Comma-sepatated list of C-states to enable (all by default). {cst_list_text}."""
    subpars2.add_argument("--enable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text)

    text = """Similar to '--enable', but specifies the list of C-states to disable."""
    subpars2.add_argument("--disable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text)

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
        kwargs["action"] = ArgParse.OrderedArg
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
                    should not be used with this option"""
    text = f"""By default this command provides CPU (core) frequency (P-state) information, but if
               this option is used, it will provide uncore frequency information instead. The uncore
               includes the interconnect between the cores, the shared cache, and other resources
               shared between the cores. {ucfreq_txt}."""
    subpars2.add_argument("--uncore", dest="uncore", action="store_true", help=text)

    #
    # Create parser for the 'pstates config' command.
    #
    text = """Configure other P-state aspects."""
    descr = """Configure P-states on specified CPUs"""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=pstates_config_command)

    text = f"""List of CPUs to configure P-States on. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure P-States on. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure P-States on. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    freq_txt = """The default unit is 'kHz', but 'Hz', 'MHz', and 'GHz' can also be used, for
                  example '900MHz'"""
    text = f"""Set minimum CPU frequency. {freq_txt}. Additionally, one of the following specifiers
               can be used: min,lfm - minimum supported frequency (LFM), eff - maximum effeciency
               frequency, base,hfm - base frequency (HFM), max - maximum supported frequency.
               Applies to all CPUs by default."""
    subpars2.add_argument("--min-freq", action=ArgParse.OrderedArg, nargs="?", dest="minfreq",
                          help=text)

    text = """Same as '--min-freq', but for maximum CPU frequency."""
    subpars2.add_argument("--max-freq", action=ArgParse.OrderedArg, nargs="?", dest="maxfreq",
                          help=text)

    text = f"""Set minimum uncore frequency. {freq_txt}. Additionally, one of the following
               specifiers can be used: 'min' - the minimum supported uncore frequency, 'max' - the
               maximum supported uncore frequency. {ucfreq_txt}. Applies to all packages by
               default."""
    subpars2.add_argument("--min-uncore-freq", nargs="?", action=ArgParse.OrderedArg,
                          dest="minufreq", help=text)

    text = """Same as '--min-uncore-freq', but for maximum uncore frequency."""
    subpars2.add_argument("--max-uncore-freq", nargs="?", action=ArgParse.OrderedArg,
                          dest="maxufreq", help=text)

    text = """Set energy performance bias hint. Hint can be integer in range of [0,15]. By default
              this option applies to all CPUs."""
    subpars2.add_argument("--epb", nargs="?", action=ArgParse.OrderedArg, help=text)

    text = """Set energy performance preference. Preference can be integer in range of [0,255], or
              policy string. By default this option applies to all CPUs."""
    subpars2.add_argument("--epp", nargs="?", action=ArgParse.OrderedArg, help=text)

    text = """Set CPU scaling governor. By default this option applies to all CPUs."""
    subpars2.add_argument("--governor", nargs="?", action=ArgParse.OrderedArg, help=text)

    text = """Enable or disable turbo mode. Turbo on/off is global."""
    subpars2.add_argument("--turbo", nargs="?", choices=["on", "off"], action=ArgParse.OrderedArg,
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
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=aspm_config_command)

    text = """the PCI ASPM policy to set, use "default" to set the Linux default policy."""
    subpars2.add_argument("--policy", nargs="?", help=text)

    if argcomplete:
        argcomplete.autocomplete(parser)

    return parser

def parse_arguments():
    """Parse input arguments."""

    parser = build_arguments_parser()
    args = parser.parse_args()

    return args

# pylint: disable=import-outside-toplevel

def cpu_hotplug_info_command(args, proc):
    """Implements the 'cpu-hotplug info' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_info_command(args, proc)

def cpu_hotplug_online_command(args, proc):
    """Implements the 'cpu-hotplug online' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_info_command(args, proc)

def cpu_hotplug_offline_command(args, proc):
    """Implements the 'cpu-hotplug offline' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_offline_command(args, proc)

def cstates_info_command(args, proc):
    """Implements the 'cstates info' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_info_command(args, proc)

def cstates_config_command(args, proc):
    """Implements the 'cstates config' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_config_command(args, proc)

def pstates_info_command(args, proc):
    """Implements the 'pstates info' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_info_command(args, proc)

def pstates_config_command(args, proc):
    """Implements the 'pstates config' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_config_command(args, proc)

def aspm_info_command(args, proc):
    """Implements the 'aspm info'. command"""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_info_command(args, proc)

def aspm_config_command(args, proc):
    """Implements the 'aspm config' command."""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_config_command(args, proc)

# pylint: enable=import-outside-toplevel

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
