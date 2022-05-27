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

from pepclibs.helperlibs import ArgParse, Human, Logging, ProcessManager
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CStates, PStates

if sys.version_info < (3,7):
    raise SystemExit("Error: this tool requires python version 3.7 or higher")

VERSION = "1.3.6"
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
    cpu_list_dflt_txt = f"""{cpu_list_txt}. If the CPUs/cores/packages were not specified, all CPUs
                           will be used as the default value"""
    core_list_txt = """The list can include individual core numbers and core number ranges. For
                       example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
                       Use the special keyword 'all' to specify all cores"""
    pkg_list_txt = """The list can include individual package numbers and package number ranges. For
                      example, '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
                      3. Use the special keyword 'all' to specify all packages"""

    text = "pepc - Power, Energy, and Performance Configuration tool for Linux."
    parser = PepcArgsParser(description=text, prog=OWN_NAME, ver=VERSION)

    ArgParse.add_ssh_options(parser)

    text = "Force coloring of the text output."
    parser.add_argument("--force-color", action="store_true", help=text)
    subparsers = parser.add_subparsers(title="commands")
    subparsers.required = True

    #
    # Create parser for the 'cpu-hotplug' command.
    #
    text = "CPU online/offline commands."
    descr = """CPU online/offline commands."""
    subpars = subparsers.add_parser("cpu-hotplug", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'cpu-hotplug info' command.
    #
    text = """List online and offline CPUs."""
    subpars2 = subparsers2.add_parser("info", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_info_command)

    #
    # Create parser for the 'cpu-hotplug online' command.
    #
    text = """Bring CPUs online."""
    subpars2 = subparsers2.add_parser("online", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_online_command)

    text = f"""List of CPUs to online. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)
    subpars2.add_argument("--cores", help=argparse.SUPPRESS)
    subpars2.add_argument("--packages", help=argparse.SUPPRESS)

    #
    # Create parser for the 'cpu-hotplug offline' command.
    #
    text = """Bring CPUs offline."""
    subpars2 = subparsers2.add_parser("offline", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_offline_command)

    text = f"""List of CPUs to offline. {cpu_list_txt}."""
    subpars2.add_argument("--cpus", help=text)
    text = """Same as '--cpus', but specifies list of cores."""
    subpars2.add_argument("--cores", help=text)
    text = """Same as '--cpus', but specifies list of packages."""
    subpars2.add_argument("--packages", help=text)
    text = """Offline only "sibling CPUs",  making sure there is only one logical CPU per core is
              left online. The sibling CPUs will be searched for among the CPUs selected with
              '--cpus', '--cores', and '--packages'. Therefore, specifying '--cpus all --siblings'
              will effectively disable hyper-threading on Intel CPUs."""
    subpars2.add_argument("--siblings", action="store_true", help=text)

    #
    # Create parser for the 'cstates' command.
    #
    text = "CPU C-state commands."
    descr = """Various commands related to CPU C-states."""
    subpars = subparsers.add_parser("cstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    cst_list_text = """C-states should be specified by name (e.g., 'C1'). Use 'all' to specify all
                       the available Linux C-states (this is the default). Note, there is a
                       difference between Linux C-states (e.g., 'C6') and hardware C-states (e.g.,
                       Core C6 or Package C6 on many Intel platforms). The former is what Linux can
                       request, and on Intel hardware this is usually about various 'mwait'
                       instruction hints. The latter are platform-specific hardware state, entered
                       upon a Linux request."""

    #
    # Create parser for the 'cstates info' command.
    #
    text = "Get CPU C-states information."
    descr = """Get information about C-states on specified CPUs. By default, prints all information
               for all CPUs. Remember, this is information about the C-states that Linux can
               request, they are not necessarily the same as the C-states supported by the
               underlying hardware."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=cstates_info_command)

    text = f"""List of CPUs to get information about. {cpu_list_dflt_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to get information about. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to get information about. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    text = f"""Comma-sepatated list of C-states to get information about (all C-states by default).
               {cst_list_text}."""
    subpars2.add_argument("--cstates", dest="csnames", help=text, default="default")

    for name, pinfo in CStates.PROPS.items():
        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Get current setting for "
        else:
            text = "Get "

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]} This option has {pinfo["scope"]} scope."""

        subpars2.add_argument(option, action="store_true", help=text)
    #
    # Create parser for the 'cstates config' command.
    #
    text = "Configure C-states."
    descr = """Configure C-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=cstates_config_command)

    text = f"""List of CPUs to configure. {cpu_list_dflt_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    text = f"""Comma-sepatated list of C-states to enable. {cst_list_text}."""
    subpars2.add_argument("--enable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text,
                          nargs="?")

    text = """Similar to '--enable', but specifies the list of C-states to disable."""
    subpars2.add_argument("--disable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text,
                          nargs="?")

    for name, pinfo in CStates.PROPS.items():
        if not pinfo["writable"]:
            continue

        kwargs = {}
        kwargs["default"] = argparse.SUPPRESS
        kwargs["nargs"] = "?"

        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Enable or disable "
            choices = " Use \"on\" or \"off\"."
        else:
            text = "Set "
            choices = ""

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]}{choices} This option has {pinfo["scope"]} scope."""

        kwargs["help"] = text
        kwargs["action"] = ArgParse.OrderedArg
        subpars2.add_argument(option, **kwargs)

    #
    # Create parser for the 'pstates' command.
    #
    text = "P-state commands."
    descr = """Various commands related to P-states (CPU performance states)."""
    subpars = subparsers.add_parser("pstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'pstates info' command.
    #
    text = "Get P-states information."
    descr = """Get P-states information for specified CPUs. By default, prints all information for
               all CPUs."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=pstates_info_command)

    text = f"""List of CPUs to get information about. {cpu_list_dflt_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to get information about. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to get information about. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    for name, pinfo in PStates.PROPS.items():
        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Get current setting for "
        else:
            text = "Get "

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]} This option has {pinfo["scope"]} scope."""

        subpars2.add_argument(option, action="store_true", help=text)

    #
    # Create parser for the 'pstates config' command.
    #
    text = """Configure P-states."""
    descr = """Configure P-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=pstates_config_command)

    text = f"""List of CPUs to configure P-States on. {cpu_list_dflt_txt}."""
    subpars2.add_argument("--cpus", help=text)

    text = f"""List of cores to configure P-States on. {core_list_txt}."""
    subpars2.add_argument("--cores", help=text)

    text = f"""List of packages to configure P-States on. {pkg_list_txt}."""
    subpars2.add_argument("--packages", help=text)

    freq_unit = """ The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used, for
                   example '900MHz'."""
    for name, pinfo in PStates.PROPS.items():
        if not pinfo.get("writable"):
            continue

        kwargs = {}
        kwargs["default"] = argparse.SUPPRESS
        kwargs["nargs"] = "?"

        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Enable or disable "
            choices = " Use \"on\" or \"off\"."
        else:
            text = "Set "
            choices = ""

        if pinfo.get("unit") == "Hz":
            unit = freq_unit
        else:
            unit = ""

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]}{choices}{unit} This option has {pinfo["scope"]}
                    scope."""

        kwargs["help"] = text
        kwargs["action"] = ArgParse.OrderedArg
        subpars2.add_argument(option, **kwargs)

    #
    # Create parser for the 'aspm' command.
    #
    text = "PCI ASPM commands."
    descr = """Manage Active State Power Management configuration."""
    subpars = subparsers.add_parser("aspm", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Get PCI ASPM information."
    descr = """Get information about current PCI ASPM configuration."""
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

def cpu_hotplug_info_command(args, pman):
    """Implements the 'cpu-hotplug info' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_info_command(args, pman)

def cpu_hotplug_online_command(args, pman):
    """Implements the 'cpu-hotplug online' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_online_command(args, pman)

def cpu_hotplug_offline_command(args, pman):
    """Implements the 'cpu-hotplug offline' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_offline_command(args, pman)

def cstates_info_command(args, pman):
    """Implements the 'cstates info' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_info_command(args, pman)

def cstates_config_command(args, pman):
    """Implements the 'cstates config' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_config_command(args, pman)

def pstates_info_command(args, pman):
    """Implements the 'pstates info' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_info_command(args, pman)

def pstates_config_command(args, pman):
    """Implements the 'pstates info' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_config_command(args, pman)

def aspm_info_command(args, pman):
    """Implements the 'aspm info'. command"""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_info_command(args, pman)

def aspm_config_command(args, pman):
    """Implements the 'aspm config' command."""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_config_command(args, pman)

def main():
    """Script entry point."""

    try:
        args = parse_arguments()

        if not getattr(args, "func", None):
            LOG.error("please, run '%s -h' for help", OWN_NAME)
            return -1

        # pylint: disable=no-member
        if args.hostname == "localhost":
            args.username = args.privkey = args.timeout = None

        with ProcessManager.get_pman(args.hostname, username=args.username,
                                     privkeypath=args.privkey, timeout=args.timeout) as pman:
            args.func(args, pman)
    except KeyboardInterrupt:
        LOG.info("\nInterrupted, exiting")
        return -1
    except Error as err:
        LOG.error(err)
        return -1

    return 0

if __name__ == "__main__":
    sys.exit(main())
