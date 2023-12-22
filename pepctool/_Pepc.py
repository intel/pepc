# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
pepc - Power, Energy, and Performance Configuration tool for Linux.
"""

import os
import sys
import logging
import argparse
from pathlib import Path

try:
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs.helperlibs import ArgParse, Human, Logging, ProcessManager, ProjectFiles
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CStates, PStates, Power, CPUInfo
from pepclibs._PropsClassBase import MECHANISMS

if sys.version_info < (3,7):
    raise SystemExit("Error: this tool requires python version 3.7 or higher")

_VERSION = "1.4.45"
TOOLNAME = "pepc"

_LOG = logging.getLogger()
Logging.setup_logger(prefix=TOOLNAME)

_DATASET_OPTION = {
    "short": "-D",
    "long":  "--dataset",
    "argcomplete": None,
    "kwargs": {
        "dest": "dataset",
        "help": """This option is for debugging and testing purposes only, it defines the dataset
                   that will be used to emulate a host for running the command on. Please, specify
                   dataset path, name or "all" to specify all available datasets."""
    },
}

_OVERRIDE_CPU_OPTION = {
    "short": None,
    "long":  "--override-cpu-model",
    "argcomplete": None,
    "kwargs": {
        "metavar": "MODEL",
        "dest": "override_cpu_model",
        "help": """This option is for debugging and testing purposes only. Please, provide the CPU
                   model number which the tool treats the target system CPU as."""
    },
}

_LIST_MECHANISMS_OPTION = {
    "short": None,
    "long":  "--list-mechanisms",
    "argcomplete": None,
    "kwargs": {
        "dest": "list_mechanisms",
        "action": "store_true",
        "help": """List all supported mechanisms.""",
    },
}

_CONFIG_MECHANISMS_OPTION = {
    "short": "-m",
    "long":  "--mechanisms",
    "argcomplete": None,
    "kwargs": {
        "dest": "mechanisms",
        "help": """Comma-separated list of allowed mechanisms names (e.g., 'sysfs' or 'msr'). Use
                   '--list-mechanisms' to get all names. By default, use the best available
                   mechanism is used.""",
    },
}

class PepcArgsParser(ArgParse.ArgsParser):
    """
    The default argument parser does not allow defining "global" options, so that they are present
    in every subcommand. For example, we want the SSH options to be available everywhere.
    """

    def add_option_from_dict(self, opt_info):
        """Add add an option from a dictionary describing the option."""

        args = []
        if opt_info["short"]:
            args.append(opt_info["short"])
        if opt_info["long"]:
            args.append(opt_info["long"])

        arg = self.add_argument(*args, **opt_info["kwargs"])
        if opt_info["argcomplete"] and argcomplete:
            arg.completer = getattr(argcomplete.completers, opt_info["argcomplete"])

    def _check_unknow_args(self, args, uargs, gargs):
        """
        Check unknown arguments 'uargs' for global arguments 'gargs' and add them to 'args'. This is
        a workaround for implementing global arguments.
        """

        for opt in gargs:
            if opt["short"] in uargs:
                optname = opt["short"]
            elif opt["long"] in uargs:
                optname = opt["long"]
            else:
                continue

            val_idx = uargs.index(optname) + 1
            if len(uargs) <= val_idx or uargs[val_idx].startswith("-"):
                raise Error(f"value required for argument '{optname}'")

            setattr(args, opt["kwargs"]["dest"], uargs[val_idx])
            uargs.remove(uargs[val_idx])
            uargs.remove(optname)

    def parse_args(self, *args, **kwargs): # pylint: disable=no-member
        """Parse unknown arguments from ArgParse class."""

        args, uargs = super().parse_known_args(*args, **kwargs)
        if not uargs:
            return args

        self._check_unknow_args(args, uargs, ArgParse.SSH_OPTIONS)
        self._check_unknow_args(args, uargs, (_DATASET_OPTION,))

        if uargs:
            raise Error(f"unrecognized option(s): {' '.join(uargs)}")

        if args.dataset and args.hostname != "localhost":
            raise Error("can't use dataset on remote host")

        return args

def _add_target_cpus_arguments(subpars, fmt, exclude=None):
    """
    Add target CPUs arguments, such as '--cpus' and '--packages. The input arguments are as follows.
      * subpars - the 'argparse' sub-parser to add the target CPU arguments too.
      * fmt - format string for the first sentence. Should include one '%s' that will be replaced
              with level name (CPU, module, package, etc.).
      * exclude - name of options to exclude ("nothing" by default).
    """

    if not exclude:
        exclude = set()

    if "--cpus" not in exclude:
        text = fmt % "CPUs" # pylint: disable=consider-using-f-string
        text += """ The list can include individual CPU numbers and CPU number ranges. For example,
                   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special
                   keyword 'all' to specify all CPUs. If the CPUs/cores/packages were not specified,
                   all CPUs will be used as the default value."""
        subpars.add_argument("--cpus", help=text)

    if "--cores" not in exclude:
        text = fmt % "cores" # pylint: disable=consider-using-f-string
        text += """ The list can include individual core numbers and core number ranges. The format
                   is similar to '--cpus'. Note, unlike CPU numers, core numbers are relative to
                   package numbers."""
        subpars.add_argument("--cores", help=text)

    if "--modules" not in exclude:
        text = fmt % "modules" # pylint: disable=consider-using-f-string
        text += """ The list can include individual module numbers and module number ranges. The
                format is similar to '--cpus'."""
        subpars.add_argument("--modules", help=text)

    if "--dies" not in exclude:
        text = fmt % "dies" # pylint: disable=consider-using-f-string
        text += """ The list can include individual die numbers and die number ranges. The format is
                   similar to '--cpus'."""
        subpars.add_argument("--dies", help=text)

    if "--packages" not in exclude:
        text = fmt % "packages" # pylint: disable=consider-using-f-string
        text += """ The list can include individual package numbers and package number ranges. The
                   format is similar to '--cpus'."""
        subpars.add_argument("--packages", help=text)

    if "--core-siblings" not in exclude:
        text = fmt % "core sibling indices" # pylint: disable=consider-using-f-string
        text += """ Core soblings are the CPUs sharing the same core. The list can include
                   individual core sibling indices or index ranges. For example, core x includes
                   CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean CPU 4. This option can only
                   be used to reference online CPUs, because Linux does not provide topology
                   information for offline CPUs. In the previous example if CPU 3 was offline, then
                   '0' would mean CPU 4."""
        subpars.add_argument("--core-siblings", help=text)

    if "--module-siblings" not in exclude:
        text = fmt % "module sibling indices" # pylint: disable=consider-using-f-string
        text += """ module soblings are the CPUs sharing the same module. This option is similar to
                   '--core-siblings', but it accepts module sibling indices."""
        subpars.add_argument("--module-siblings", help=text)

def _get_info_subcommand_prop_help_text(prop):
    """Format and return the "info" sub-command help text for a property described by 'prop'."""

    if prop["type"] == "bool":
        # This is a binary "on/off" type of features.
        text = f"Check if {Human.uncapitalize(prop['name'])} is enabled or disabled."
    else:
        text = f"Get {Human.uncapitalize(prop['name'])}."

    return text

def _add_info_subcommand_options(props, subpars):
    """Add options for all properties in 'props' to for the "info" subcommand."""

    spnames = set()
    for prop in props.values():
        for spname in prop.get("subprops", []):
            spnames.add(spname)

    for pname, prop in props.items():
        if pname in spnames:
            # Do not add a separate option for a sub-property. Sub-property information is printed
            # along with the property information.
            continue

        kwargs = {}
        kwargs["default"] = argparse.SUPPRESS
        kwargs["nargs"] = 0
        kwargs["help"] = _get_info_subcommand_prop_help_text(prop)
        kwargs["action"] = ArgParse.OrderedArg

        option = f"--{pname.replace('_', '-')}"
        subpars.add_argument(option, **kwargs)

def _get_config_subcommand_prop_help_text(prop):
    """Format and return the "info" sub-command help text for a property described by 'prop'."""

    if prop["type"] == "bool":
        # This is a binary "on/off" type of features.
        text = f"Enable or disable {Human.uncapitalize(prop['name'])}."
    else:
        text = f"Set {Human.uncapitalize(prop['name'])}."

    return text

def _add_config_subcommand_options(props, subpars):
    """Add options for all properties in 'props' to for the "config" sub-command."""

    for name, prop in props.items():
        if not prop["writable"]:
            continue

        kwargs = {}
        kwargs["default"] = argparse.SUPPRESS
        kwargs["nargs"] = "?"
        kwargs["help"] = _get_config_subcommand_prop_help_text(prop)
        kwargs["action"] = ArgParse.OrderedArg

        if prop["type"] == "bool":
            kwargs["metavar"] = "on/off"

        option = f"--{name.replace('_', '-')}"
        subpars.add_argument(option, **kwargs)

def build_arguments_parser():
    """A helper function which parses the input arguments."""

    text = "pepc - Power, Energy, and Performance Configuration tool for Linux."
    parser = PepcArgsParser(description=text, prog=TOOLNAME, ver=_VERSION)

    ArgParse.add_ssh_options(parser)
    parser.add_option_from_dict(_DATASET_OPTION)

    text = "Force coloring of the text output."
    parser.add_argument("--force-color", action="store_true", help=text)
    subparsers = parser.add_subparsers(title="commands", dest="a command")
    subparsers.required = True

    #
    # Create parser for the 'cpu-hotplug' command.
    #
    text = "CPU online/offline commands"
    man_msg = """Please, refer to 'pepc-cpu-hotplug' manual page for more information."""
    descr = "CPU online/offline commands. " + man_msg
    subpars = subparsers.add_parser("cpu-hotplug", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'cpu-hotplug info' command.
    #
    text = """List online and offline CPUs."""
    descr = "List online and offline CPUs. " + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cpu_hotplug_info_command)

    #
    # Create parser for the 'cpu-hotplug online' command.
    #
    text = """Bring CPUs online."""
    descr = "Bring CPUs online. " + man_msg
    subpars2 = subparsers2.add_parser("online", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cpu_hotplug_online_command)

    text = """List of CPUs to online. The list can include individual CPU numbers and CPU number
              ranges. For example, '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12.
              Use the special keyword 'all' to specify all CPUs."""
    subpars2.add_argument("--cpus", help=text)

    #
    # Create parser for the 'cpu-hotplug offline' command.
    #
    text = """Bring CPUs offline."""
    descr = "Bring CPUs offline. " + man_msg
    subpars2 = subparsers2.add_parser("offline", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cpu_hotplug_offline_command)

    _add_target_cpus_arguments(subpars2, "List of %s to offline.")

    #
    # Create parser for the 'cstates' command.
    #
    text = "CPU C-state commands."
    man_msg = "Please, refer to 'pepc-cstates' manual page for more information."
    descr = "Various commands related to CPU C-states. " + man_msg
    subpars = subparsers.add_parser("cstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    cst_list_text = """C-states should be specified by name (e.g., 'C1'). Use 'all' to specify all
                       the available Linux C-states (this is the default)."""

    #
    # Create parser for the 'cstates info' command.
    #
    text = "Get CPU C-states information."
    descr = "Get information about C-states on specified CPUs. " + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cstates_info_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to get information about.")

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    text = f"""Comma-separated list of C-states to get information about (all C-states by default).
               {cst_list_text}"""
    subpars2.add_argument("--cstates", dest="csnames", metavar="CSTATES", nargs="?", help=text,
                          default="default")

    _add_info_subcommand_options(CStates.PROPS, subpars2)

    #
    # Create parser for the 'cstates config' command.
    #
    text = "Configure C-states."
    descr = """Configure C-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed. """ + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cstates_config_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to configure.")

    text = f"""Comma-separated list of C-states to enable. {cst_list_text}"""
    subpars2.add_argument("--enable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text,
                          nargs="?")

    text = """Similar to '--enable', but specifies the list of C-states to disable."""
    subpars2.add_argument("--disable", metavar="CSTATES", action=ArgParse.OrderedArg, help=text,
                          nargs="?")

    _add_config_subcommand_options(CStates.PROPS, subpars2)

    #
    # Create parser for the 'cstates save' command.
    #
    text = "Save C-states settings."
    descr = f"""Save all the modifiable C-state settings into a file. This file can later be used
                for restoring C-state settings with the '{TOOLNAME} cstates restore' command. """ \
                + man_msg
    subpars2 = subparsers2.add_parser("save", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cstates_save_command)

    _add_target_cpus_arguments(subpars2, "List of %s to save C-state information about.")

    text = "Name of the file to save the settings to."
    subpars2.add_argument("-o", "--outfile", help=text)

    #
    # Create parser for the 'cstates restore' command.
    #
    text = "Restore C-states settings."
    descr = f"""Restore C-state settings from a file previously created with the
               '{TOOLNAME} cstates save' command. """ + man_msg
    subpars2 = subparsers2.add_parser("restore", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=cstates_restore_command)

    text = """Name of the file from which to restore the settings from, use "-" to read from the
              standard output."""
    subpars2.add_argument("-f", "--from", dest="infile", help=text)

    #
    # Create parser for the 'pstates' command.
    #
    text = "P-state commands."
    man_msg = "Please, refer to 'pepc-pstates' manual page for more information."
    descr = "Various commands related to P-states (CPU performance states). " + man_msg
    subpars = subparsers.add_parser("pstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'pstates info' command.
    #
    text = "Get P-states information."
    descr = """Get P-states information for specified CPUs. By default, prints all information for
               all CPUs. """ + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=pstates_info_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to get information about.")

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    _add_info_subcommand_options(PStates.PROPS, subpars2)

    #
    # Create parser for the 'pstates config' command.
    #
    text = """Configure P-states."""
    descr = """Configure P-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed. """ + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=pstates_config_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to configure P-States on.")

    _add_config_subcommand_options(PStates.PROPS, subpars2)

    #
    # Create parser for the 'pstates save' command.
    #
    text = "Save P-states settings."
    descr = f"""Save all the modifiable P-state settings into a file. This file can later be used
                for restoring P-state settings with the '{TOOLNAME} pstates restore' command. """ \
                + man_msg
    subpars2 = subparsers2.add_parser("save", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=pstates_save_command)

    _add_target_cpus_arguments(subpars2, "List of %s to save P-state information about.")

    text = "Name of the file to save the settings to (printed to standard output by default)."
    subpars2.add_argument("-o", "--outfile", help=text, default="-")

    #
    # Create parser for the 'pstates restore' command.
    #
    text = "Restore P-states settings."
    descr = f"""Restore P-state settings from a file previously created with the
               '{TOOLNAME} pstates save' command. """ + man_msg
    subpars2 = subparsers2.add_parser("restore", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=pstates_restore_command)

    text = """Name of the file from which to restore the settings from, use "-" to read from the
              standard output."""
    subpars2.add_argument("-f", "--from", dest="infile", help=text)

    #
    # Create parser for the 'power' command.
    #
    text = "Power commands."
    man_msg = "Please refer to 'pepc-power' manual page for more information."
    descr = "Various commands related to power configuration. " + man_msg
    subpars = subparsers.add_parser("power", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    power_exclude = set(["--core-siblings"])

    #
    # Create parser for the 'power info' command.
    #
    text = "Get power information."
    descr = """Get power information for specified CPUs. By default, prints all information for
               all CPUs. """ + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=power_info_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to get information about.",
                               exclude=power_exclude)

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    _add_info_subcommand_options(Power.PROPS, subpars2)

    #
    # Create parser for the 'power config' command.
    #
    text = """Configure power settings."""
    descr = """Configure power settings on specified CPUs. All options can be used without
               a parameter, in which case the currently configured value(s) will be printed. """ \
               + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=power_config_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to configure power settings on.",
                               exclude=power_exclude)

    _add_config_subcommand_options(Power.PROPS, subpars2)

    #
    # Create parser for the 'power save' command.
    #
    text = "Save power settings."
    man_msg = """Please, refer to 'pepc-power' manual page for more information."""
    descr = f"""Save all the modifiable power settings into a file. This file can later be used
                for restoring power settings with the '{TOOLNAME} power restore' command. """ \
                + man_msg
    subpars2 = subparsers2.add_parser("save", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=power_save_command)

    _add_target_cpus_arguments(subpars2, "List of %s to save power information about.",
                               exclude=power_exclude)

    text = "Name of the file to save the settings to (printed to standard output by default)."
    subpars2.add_argument("-o", "--outfile", help=text, default="-")

    #
    # Create parser for the 'power restore' command.
    #
    text = "Restore power settings."
    descr = f"""Restore power settings from a file previously created with the
               '{TOOLNAME} power save' command. """ + man_msg
    subpars2 = subparsers2.add_parser("restore", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=power_restore_command)

    text = """Name of the file from which to restore the settings from, use "-" to read from the
              standard output."""
    subpars2.add_argument("-f", "--from", dest="infile", help=text)

    #
    # Create parser for the 'aspm' command.
    #
    text = "PCI ASPM commands."
    man_msg = "Please, refer to 'pepc-aspm' manual page for more information."
    descr = "Manage Active State Power Management configuration. " + man_msg
    subpars = subparsers.add_parser("aspm", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Get PCI ASPM information."
    descr = "Get information about current PCI ASPM configuration. " + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=aspm_info_command)

    text = """Get current PCI ASPM policy."""
    subpars2.add_argument("--policy", action=ArgParse.OrderedArg, nargs=0, help=text)

    text = """List the available PCI ASPM policies."""
    subpars2.add_argument("--policies", action=ArgParse.OrderedArg, nargs=0, help=text)

    text = "Change PCI ASPM configuration."
    descr = "Change PCI ASPM configuration. " + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=aspm_config_command)

    text = """The PCI ASPM policy to set, use "default" to set the default policy."""
    subpars2.add_argument("--policy", action=ArgParse.OrderedArg, nargs="?", help=text)

    #
    # Create parser for the 'topology' command.
    #
    text = "CPU topology commands."
    man_msg = "Please, refer to 'pepc-topology' manual page for more information."
    descr = "Various commands related to CPU topology. " + man_msg
    subpars = subparsers.add_parser("topology", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Print CPU topology."
    descr = """Print CPU topology information. Note, the topology information for some offline CPUs
               may be unavailable, in these cases the number will be substituted with "?". Please,
               refer to 'pepc-topology' manual page for more information."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=topology_info_command)

    _add_target_cpus_arguments(subpars2, "List of %s to print topology information for.")

    orders = ", ".join([lvl.lower() for lvl in CPUInfo.LEVELS])
    text = f"""By default, the topology table is printed in CPU number order. Use this option to
               print it in a different order (e.g., core or package number order). Here are the
               supported order names: {orders}."""
    subpars2.add_argument("--order", help=text, default="CPU")

    text = """Include only online CPUs. By default offline and online CPUs are included."""
    subpars2.add_argument("--online-only", action='store_true', help=text)

    columns = ", ".join(list(CPUInfo.LEVELS) + ["hybrid"])
    text = f"""Comma-separated list of the topology columns to print. Available columns are:
            {columns}. Example: --columns Package,Core,CPU."""
    subpars2.add_argument("--columns", help=text)

    if argcomplete:
        argcomplete.autocomplete(parser)

    return parser

def parse_arguments():
    """Parse input arguments."""

    parser = build_arguments_parser()
    args = parser.parse_args()

    # It is handy to have CPU target attributes.
    if not hasattr(args, "cores"):
        setattr(args, "cores", None)
    if not hasattr(args, "modules"):
        setattr(args, "modules", None)
    if not hasattr(args, "dies"):
        setattr(args, "dies", None)
    if not hasattr(args, "core_siblings"):
        setattr(args, "core_siblings", None)
    if not hasattr(args, "module_siblings"):
        setattr(args, "module_siblings", None)

    return args

# pylint: disable=import-outside-toplevel

def topology_info_command(args, pman):
    """Implements the 'topology info' command."""

    from pepctool import _PepcTopology

    _PepcTopology.topology_info_command(args, pman)

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

def cstates_save_command(args, pman):
    """Implements the 'cstates save' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_save_command(args, pman)

def cstates_restore_command(args, pman):
    """Implements the 'cstates restore' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_restore_command(args, pman)

def pstates_info_command(args, pman):
    """Implements the 'pstates info' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_info_command(args, pman)

def pstates_config_command(args, pman):
    """Implements the 'pstates config' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_config_command(args, pman)

def pstates_save_command(args, pman):
    """Implements the 'pstates save' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_save_command(args, pman)

def pstates_restore_command(args, pman):
    """Implements the 'pstates restore' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_restore_command(args, pman)

def power_info_command(args, pman):
    """Implements the 'power info' command."""

    from pepctool import _PepcPower

    _PepcPower.power_info_command(args, pman)

def power_config_command(args, pman):
    """Implements the 'power config' command."""

    from pepctool import _PepcPower

    _PepcPower.power_config_command(args, pman)

def power_save_command(args, pman):
    """Implements the 'power save' command."""

    from pepctool import _PepcPower

    _PepcPower.power_save_command(args, pman)

def power_restore_command(args, pman):
    """Implements the 'power restore' command."""

    from pepctool import _PepcPower

    _PepcPower.power_restore_command(args, pman)

def aspm_info_command(args, pman):
    """Implements the 'aspm info'. command"""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_info_command(args, pman)

def aspm_config_command(args, pman):
    """Implements the 'aspm config' command."""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_config_command(args, pman)

def _get_next_dataset(dataset):
    """
    Yield path for each dataset specified with the '-D' option, where 'name' is the dataset name,
    'path' is the path to the dataset and 'all' all datasets in 'tests/data'.
    """

    if Path(dataset).is_dir():
        yield Path(dataset)
    elif dataset == "all":
        base = ProjectFiles.find_project_data(TOOLNAME, "tests/data", what=f"{TOOLNAME} datasets")
        for name in os.listdir(base):
            _LOG.info("\n======= emulation:%s =======", name)
            yield Path(f"{base}/{name}")
    else:
        base = ProjectFiles.find_project_data(TOOLNAME, "tests/data", what=f"{TOOLNAME} datasets")
        path = Path(base / dataset)
        if not path.is_dir():
            raise Error(f"couldn't find dataset '{dataset}', '{path}' doesn't exist")

        yield path

def _get_emul_pman(args, path):
    """
    Configure and return an 'EmulProcessManager' object for the dataset specified with the '-D'
    option.
    """

    from pepclibs.helperlibs import EmulProcessManager

    required_cmd_modules = {
        "aspm" : ["ASPM", "Systemctl"],
        "cstates" : ["CPUInfo", "CStates", "Systemctl"],
        "pstates" : ["CPUInfo", "PStates", "Systemctl"],
        "power" : ["CPUInfo", "Power"],
        "topology" : ["CPUInfo"],
        "cpu_hotplug" : ["CPUInfo", "CPUOnline", "Systemctl"],
    }

    for cmd, _modules in required_cmd_modules.items():
        if cmd in args.func.__name__:
            modules = _modules
            break
    else:
        raise Error(f"BUG: No modules specified for '{args.func.__name__}()'")

    pman = EmulProcessManager.EmulProcessManager(hostname=path.name)

    try:
        for module in modules:
            pman.init_testdata(module, path)
    except Error:
        pman.close()
        raise

    return pman

def _list_mechanisms(args):
    """Implement the '--list-mechanisms' option."""

    fname = args.func.__name__
    if fname.startswith("pstates_"):
        props = PStates.PROPS
    elif fname.startswith("cstates_"):
        props = CStates.PROPS
    elif fname.startswith("power_"):
        props = Power.PROPS
    else:
        raise Error(f"BUG: unknown function '{fname}' for '--list-mechanisms'")

    # Form a set of mechanisms used by properties in 'props'.
    mnames = set()
    for pinfo in props.values():
        for mname in pinfo["mnames"]:
            mnames.add(mname)

    info = []
    for mname, minfo in MECHANISMS.items():
        if mname in mnames:
            info.append(f"{mname} - {minfo['long']}")
            mnames.remove(mname)

    _LOG.info("* %s", "\n* ".join(info))

def main():
    """Script entry point."""

    try:
        args = parse_arguments()

        if not getattr(args, "func", None):
            _LOG.error("please, run '%s -h' for help", TOOLNAME)
            return -1

        # pylint: disable=no-member
        if args.hostname == "localhost":
            args.username = args.privkey = args.timeout = None

        if getattr(args, "list_mechanisms", None):
            _list_mechanisms(args)
        elif args.dataset:
            for path in _get_next_dataset(args.dataset):
                with _get_emul_pman(args, path) as pman:
                    args.func(args, pman)
        else:
            with ProcessManager.get_pman(args.hostname, username=args.username,
                                         privkeypath=args.privkey, timeout=args.timeout) as pman:
                args.func(args, pman)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
        return -1
    except Error as err:
        _LOG.error_out(err)

    return 0

if __name__ == "__main__":
    sys.exit(main())
