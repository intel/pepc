# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
pepc - Power, Energy, and Performance Configuration tool for Linux.
"""

import os
import sys
import argparse
from pathlib import Path

try:
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs.helperlibs import ArgParse, Human, Logging, ProcessManager, ProjectFiles
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CStates, PStates, PMQoS, Power, CPUInfo
from pepclibs._PropsClassBase import MECHANISMS

if sys.version_info < (3, 7):
    raise SystemExit("this tool requires python version 3.7 or higher")

_VERSION = "1.5.35"
TOOLNAME = "pepc"

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=TOOLNAME)

_DATASET_OPTION = {
    "short": "-D",
    "long":  "--dataset",
    "argcomplete": None,
    "kwargs": {
        "dest": "dataset",
        "help": """This option is for debugging and testing. It specifies the dataset to emulate a
                   host for running the command. The argument can be a dataset path or name."""
    },
}

_OVERRIDE_CPU_OPTION = {
    "short": None,
    "long":  "--override-cpu-model",
    "argcomplete": None,
    "kwargs": {
        "metavar": "VFM",
        "dest": "override_cpu_model",
        "help": f"""This option is for debugging and testing purposes only. Override the target host
                    CPU model and force {TOOLNAME} treat the host as a specific CPU model. The
                    format is '[<Vendor>:][<Family>:]<Model>'."""
    },
}

_LIST_MECHANISMS_OPTION = {
    "short": None,
    "long":  "--list-mechanisms",
    "argcomplete": None,
    "kwargs": {
        "dest": "list_mechanisms",
        "action": "store_true",
        "help": """List all supported mechanisms and exit.""",
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
        """
        Add add a command-line option described by 'opt_info'. The arguments are as follows.
          * opt_info - a dictionary describing the option to add.
        """

        args = []
        if opt_info["short"]:
            args.append(opt_info["short"])
        if opt_info["long"]:
            args.append(opt_info["long"])

        arg = self.add_argument(*args, **opt_info["kwargs"])
        if opt_info["argcomplete"] and argcomplete:
            setattr(arg, "completer", getattr(argcomplete.completers, opt_info["argcomplete"]))

    def _check_unknown_args(self, args, uargs, gargs):
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

        self._check_unknown_args(args, uargs, ArgParse.SSH_OPTIONS)
        self._check_unknown_args(args, uargs, (_DATASET_OPTION,))

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
        text += """ Specify individual CPU numbers or ranges (e.g., '1-4,7,8,10-12'). Use 'all' for
                    all CPUs. If not specified, all CPUs are used by default."""
        subpars.add_argument("--cpus", help=text)

    if "--cores" not in exclude:
        text = fmt % "cores" # pylint: disable=consider-using-f-string
        text += """ The list can include individual core numbers or ranges (e.g., '0-3,5'). Core
                   numbers are relative to their package."""
        subpars.add_argument("--cores", help=text)

    if "--modules" not in exclude:
        text = fmt % "modules" # pylint: disable=consider-using-f-string
        text += """ Specify individual module numbers or ranges (e.g., '0-3,5'). Format is similar
                    to '--cpus'."""
        subpars.add_argument("--modules", help=text)

    if "--dies" not in exclude:
        text = fmt % "dies" # pylint: disable=consider-using-f-string
        text += """ Specify die numbers or ranges (e.g., '0-3,5'). Format is similar to '--cpus'."""
        subpars.add_argument("--dies", help=text)

    if "--packages" not in exclude:
        text = fmt % "packages" # pylint: disable=consider-using-f-string
        text += """ Specify individual package numbers or ranges (e.g., '0-3,5'). Format is similar
                   to '--cpus'."""
        subpars.add_argument("--packages", help=text)

    if "--core-siblings" not in exclude:
        text = fmt % "core sibling indices" # pylint: disable=consider-using-f-string
        text += """ Specify core sibling indices or ranges (e.g., '0-1'). Core siblings are CPUs
                    sharing the same core. For example, if a core includes CPUs 2 and 3, '0' refers
                    to CPU 2 and '1' to CPU 3."""
        subpars.add_argument("--core-siblings", help=text)

    if "--module-siblings" not in exclude:
        text = fmt % "module sibling indices" # pylint: disable=consider-using-f-string
        text += """ Specify module sibling indices or ranges (e.g., '0-1'). Core siblings are CPUs
                    sharing the same module. For example, if a module includes CPUs 4, 5, 6, and 7,
                    index '0' refers to CPU 4, index '1' to CPU 5, and index '4' to CPU 7."""
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
    """Build and return the the command-line arguments parser object."""

    text = "pepc - Power, Energy, and Performance Configuration tool for Linux."
    parser = PepcArgsParser(description=text, prog=TOOLNAME, ver=_VERSION)

    ArgParse.add_ssh_options(parser)
    parser.add_option_from_dict(_DATASET_OPTION)

    text = """Force colorized output even if the output stream is not a terminal (adds ANSI escape
              codes)."""
    parser.add_argument("--force-color", action="store_true", help=text)
    subparsers = parser.add_subparsers(title="commands", dest="a command")
    subparsers.required = True

    #
    # Create parser for the 'cpu-hotplug' command.
    #
    text = "CPU online/offline commands"
    man_msg = """Refer to 'pepc-cpu-hotplug' manual page for more information."""
    descr = "CPU online/offline commands. " + man_msg
    subpars = subparsers.add_parser("cpu-hotplug", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'cpu-hotplug info' command.
    #
    text = "Display the list of online and offline CPUs."
    descr = "Display the list of online and offline CPUs. " + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_cpu_hotplug_info_command)

    #
    # Create parser for the 'cpu-hotplug online' command.
    #
    text = """Bring CPUs online."""
    descr = "Bring specified CPUs online. " + man_msg
    subpars2 = subparsers2.add_parser("online", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_cpu_hotplug_online_command)

    text = """List of CPUs to bring online. Specify individual CPU numbers or ranges, e.g.,
              '1-4,7,8,10-12' for CPUs 1 to 4, 7, 8, and 10 to 12. Use 'all' to specify all CPUs."""
    subpars2.add_argument("--cpus", help=text)

    #
    # Create parser for the 'cpu-hotplug offline' command.
    #
    text = """Bring CPUs offline."""
    descr = "Bring specified CPUs offline. " + man_msg
    subpars2 = subparsers2.add_parser("offline", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_cpu_hotplug_offline_command)

    _add_target_cpus_arguments(subpars2, "List of %s to bring offline.")

    #
    # Create parser for the 'cstates' command.
    #
    text = "CPU C-state commands."
    man_msg = "Refer to 'pepc-cstates' manual page for more information."
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
    subpars2.set_defaults(func=_cstates_info_command)

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
    subpars2.set_defaults(func=_cstates_config_command)

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
    # Create parser for the 'pstates' command.
    #
    text = "P-state commands."
    man_msg = "Refer to 'pepc-pstates' manual page for more information."
    descr = "Various commands related to P-states (CPU performance states). " + man_msg
    subpars = subparsers.add_parser("pstates", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'pstates info' command.
    #
    text = "Get P-states information."
    descr = """Get P-states information for specified CPUs. By default, print all information for
               all CPUs. """ + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_pstates_info_command)

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
    subpars2.set_defaults(func=_pstates_config_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to configure P-States on.")

    _add_config_subcommand_options(PStates.PROPS, subpars2)

    #
    # Create parser for the 'pmqos' command.
    #
    text = "PM QoS commands."
    man_msg = "Refer to 'pepc-pmqos' manual page for more information."
    descr = "Various commands related to PM QoS (Power Management Quality of Service). " + man_msg
    subpars = subparsers.add_parser("pmqos", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'pmqos info' command.
    #
    text = "Get PM QoS information."
    descr = """Get PM QoS information for specified CPUs. By default, print all information for
               all CPUs. """ + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_pmqos_info_command)

    _add_target_cpus_arguments(subpars2, "List of %s to get information about.")

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    _add_info_subcommand_options(PMQoS.PROPS, subpars2)

    #
    # Create parser for the 'pmqos config' command.
    #
    text = """Configure PM QoS."""
    descr = """Configure PM QoS on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed. """ + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_pmqos_config_command)

    _add_target_cpus_arguments(subpars2, "List of %s to configure P-States on.")

    _add_config_subcommand_options(PMQoS.PROPS, subpars2)

    #
    # Create parser for the 'power' command.
    #
    text = "Power commands."
    man_msg = "Refer to 'pepc-power' manual page for more information."
    descr = "Various commands related to power configuration. " + man_msg
    subpars = subparsers.add_parser("power", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    power_exclude = set(["--core-siblings"])

    #
    # Create parser for the 'power info' command.
    #
    text = "Get power information."
    descr = """Get power information for specified CPUs. By default, print all information for
               all CPUs. """ + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_power_info_command)

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
               a parameter, in which case the currently configured value(s) will be
               printed. """ + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_power_config_command)

    subpars2.add_option_from_dict(_OVERRIDE_CPU_OPTION)
    subpars2.add_option_from_dict(_CONFIG_MECHANISMS_OPTION)
    subpars2.add_option_from_dict(_LIST_MECHANISMS_OPTION)

    _add_target_cpus_arguments(subpars2, "List of %s to configure power settings on.",
                               exclude=power_exclude)

    _add_config_subcommand_options(Power.PROPS, subpars2)

    #
    # Create parser for the 'aspm' command.
    #
    text = "PCI ASPM commands."
    man_msg = "Refer to 'pepc-aspm' manual page for more information."
    descr = "Manage Active State Power Management configuration. " + man_msg
    subpars = subparsers.add_parser("aspm", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Get PCI ASPM information."
    descr = "Get information about current PCI ASPM configuration. " + man_msg
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_aspm_info_command)

    text = """Display the current global PCI ASPM policy. The "default" policy indicates the
              system's default."""
    subpars2.add_argument("--policy", action=ArgParse.OrderedArg, nargs=0, help=text)

    text = "List available PCI ASPM policies from '/sys/module/pcie_aspm/parameters/policy'."
    subpars2.add_argument("--policies", action=ArgParse.OrderedArg, nargs=0, help=text)

    text = "Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'."
    subpars2.add_argument("--device", metavar="ADDR", action="store", help=text)

    text = "Retrieve the L1 ASPM status (on/off) for the PCI device specified by '--device'."
    subpars2.add_argument("--l1-aspm", action=ArgParse.OrderedArg, nargs=0, help=text)

    text = "Change PCI ASPM configuration."
    descr = "Change PCI ASPM configuration. " + man_msg
    subpars2 = subparsers2.add_parser("config", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_aspm_config_command)

    text = """Set the global PCI ASPM policy. Use "default" to reset the policy to the system's
              default setting."""
    subpars2.add_argument("--policy", action=ArgParse.OrderedArg, nargs="?", help=text)

    text = "Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'."
    subpars2.add_argument("--device", metavar="ADDR", action="store", help=text)

    text = """Enable or disable L1 ASPM for the PCI device specified by '--device'. Valid values are
              'on', 'off', 'enable', 'disable', 'true', or 'false'."""
    subpars2.add_argument("--l1-aspm", metavar="on/off", action=ArgParse.OrderedArg, nargs="?",
                          help=text)

    #
    # Create parser for the 'topology' command.
    #
    text = "CPU topology commands."
    man_msg = "Refer to 'pepc-topology' manual page for more information."
    descr = "Various commands related to CPU topology. " + man_msg
    subpars = subparsers.add_parser("topology", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Print CPU topology."
    descr = """Print CPU topology information. Note, the topology information for some offline CPUs
               may be unavailable, in these cases the number will be substituted with "?". Refer to
               'pepc-topology' manual page for more information."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_topology_info_command)

    _add_target_cpus_arguments(subpars2, "List of %s to print topology information for.")

    orders = ", ".join([lvl.lower() for lvl in CPUInfo.LEVELS])
    text = f"""By default, the topology table is printed in CPU number order. Use this option to
               print it in a different order (e.g., core or package number order). Here are the
               supported order names: {orders}."""
    subpars2.add_argument("--order", help=text, default="CPU")

    text = """Include only online CPUs. By default offline and online CPUs are included."""
    subpars2.add_argument("--online-only", action="store_true", help=text)

    columns = ", ".join(list(CPUInfo.LEVELS) + ["hybrid"])
    text = f"""Comma-separated list of the topology columns to print. Available columns are:
            {columns}. Example: --columns Package,Core,CPU."""
    subpars2.add_argument("--columns", help=text)

    #
    # Create parser for the 'tpmi' command.
    #
    text = "TPMI commands."
    man_msg = """Refer to 'pepc-tpmi' manual page for more information."""
    descr = """Read, write, and discover TPMI (Topology Aware Register and PM Capsule Interface)
               registers. """ + man_msg
    subpars = subparsers.add_parser("tpmi", help=text, description=descr)

    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    #
    # Create parser for the 'tpmi ls' command.
    #
    text = "List available TPMI features."
    descr = """List TPMI features supported by the target system. """ + man_msg
    subpars2 = subparsers2.add_parser("ls", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_tpmi_ls_command)

    text = """Include information about packages, TPMI addresses, and instances."""
    subpars2.add_argument("-l", "--long", action="store_true", help=text)

    text = """List unknown TPMI features as well (the features without a spec file available)."""
    subpars2.add_argument("--all", action="store_true", help=text)

    #
    # Create parser for the 'tpmi read' command.
    #
    text = "Read TPMI registers."
    descr = """Read TPMI registers. """ + man_msg
    subpars2 = subparsers2.add_parser("read", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_tpmi_read_command)

    text = """Comma-separated list of TPMI feature names to read the register(s) for (all features
              by default)."""
    subpars2.add_argument("-F", "--features", metavar="FEATURES", dest="fnames", help=text)

    text = """Comma-separated list of TPMI device PCI addresses to read the registers from (all
              devices by default)."""
    subpars2.add_argument("-a", "--addresses", dest="addrs", help=text)

    text = """Comma-separated list of package numbers to read TPMI registers for (all packages by
              default)."""
    subpars2.add_argument("--packages", help=text)

    text = """Comma-separated list of integer TPMI instance numbers to read the registers from (all
              instances by default)."""
    subpars2.add_argument("-i", "--instances", help=text)

    text = """Comma-separated list of TPMI registers names to read (all registers by default)."""
    subpars2.add_argument("-R", "--registers", help=text)

    text = """Comma-separated list of TPMI register bit field names to read (all bit fields by
              default)."""
    subpars2.add_argument("-b", "--bitfields", metavar="BITFIELDS", dest="bfnames", help=text)

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    #
    # Create parser for the 'tpmi write' command.
    #
    text = "Write TPMI registers."
    descr = """Write to a TPMI register. """ + man_msg
    subpars2 = subparsers2.add_parser("write", help=text, description=descr, epilog=man_msg)
    subpars2.set_defaults(func=_tpmi_write_command)

    text = "Name of the TPMI feature the register belongs to."
    subpars2.add_argument("-F", "--feature", metavar="FEATURE", dest="fname", help=text,
                          required=True)

    text = """Comma-separated list of TPMI device PCI addresses to write to."""
    subpars2.add_argument("-a", "--addresses", dest="addrs", help=text)

    text = """Comma-separated list of package numbers to write the TPMI register for (all packages
              by default)."""
    subpars2.add_argument("--packages", help=text)

    text = """Comma-separated list of integer TPMI instance numbers to write to (all instances by
              default)."""
    subpars2.add_argument("-i", "--instances", help=text)

    text = """Name of the TPMI register to write to."""
    subpars2.add_argument("-R", "--register", dest="regname", help=text, required=True)

    text = """Name of the TPMI register bitfield to write to. If not specified, write to the
              register, not a bit field of the register."""
    subpars2.add_argument("-b", "--bitfield", metavar="BITFIELD", dest="bfname", help=text)

    text = "The value to write to the TPMI register or its bit field."
    subpars2.add_argument("-V", "--value", help=text, required=True)

    if argcomplete:
        argcomplete.autocomplete(parser)

    return parser

def parse_arguments():
    """Parse command-line arguments."""

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

def _topology_info_command(args, pman):
    """Implement the 'topology info' command."""

    from pepctool import _PepcTopology

    _PepcTopology.topology_info_command(args, pman)

def _tpmi_ls_command(args, pman):
    """Implement the 'tpmi ls' command."""

    from pepctool import _PepcTpmi

    _PepcTpmi.tpmi_ls_command(args, pman)

def _tpmi_read_command(args, pman):
    """Implements the 'tpmi read' command."""

    from pepctool import _PepcTpmi

    _PepcTpmi.tpmi_read_command(args, pman)

def _tpmi_write_command(args, pman):
    """Implements the 'tpmi write' command."""

    from pepctool import _PepcTpmi

    _PepcTpmi.tpmi_write_command(args, pman)

def _cpu_hotplug_info_command(args, pman):
    """Implement the 'cpu-hotplug info' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_info_command(args, pman)

def _cpu_hotplug_online_command(args, pman):
    """Implement the 'cpu-hotplug online' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_online_command(args, pman)

def _cpu_hotplug_offline_command(args, pman):
    """Implement the 'cpu-hotplug offline' command."""

    from pepctool import _PepcCPUHotplug

    _PepcCPUHotplug.cpu_hotplug_offline_command(args, pman)

def _cstates_info_command(args, pman):
    """Implement the 'cstates info' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_info_command(args, pman)

def _cstates_config_command(args, pman):
    """Implement the 'cstates config' command."""

    from pepctool import _PepcCStates

    _PepcCStates.cstates_config_command(args, pman)

def _pstates_info_command(args, pman):
    """Implement the 'pstates info' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_info_command(args, pman)

def _pstates_config_command(args, pman):
    """Implement the 'pstates config' command."""

    from pepctool import _PepcPStates

    _PepcPStates.pstates_config_command(args, pman)

def _pmqos_info_command(args, pman):
    """Implement the 'pmqos info' command."""

    from pepctool import _PepcPMQoS

    _PepcPMQoS.pmqos_info_command(args, pman)

def _pmqos_config_command(args, pman):
    """Implement the 'pmqos config' command."""

    from pepctool import _PepcPMQoS

    _PepcPMQoS.pmqos_config_command(args, pman)

def _power_info_command(args, pman):
    """Implement the 'power info' command."""

    from pepctool import _PepcPower

    _PepcPower.power_info_command(args, pman)

def _power_config_command(args, pman):
    """Implement the 'power config' command."""

    from pepctool import _PepcPower

    _PepcPower.power_config_command(args, pman)

def _aspm_info_command(args, pman):
    """Implement the 'aspm info'. command"""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_info_command(args, pman)

def _aspm_config_command(args, pman):
    """Implement the 'aspm config' command."""

    from pepctool import _PepcASPM

    _PepcASPM.aspm_config_command(args, pman)

def _get_next_dataset(dataset):
    """
    Parse the '-D' option and yield dataset path for every specified dataset. The arguments are as
    follows.
      * dataset - the '-D' option value.

    Yield paths of all found datasets if the 'dataset' argument has value "all".
    """

    if Path(dataset).is_dir():
        yield Path(dataset)
    elif dataset == "all":
        datasets = {}

        for base in ProjectFiles.search_project_data(TOOLNAME, "tests/data",
                                                     what=f"{TOOLNAME} dataset"):
            for name in os.listdir(base):
                if name == "common":
                    continue
                if name in datasets:
                    raise Error(f"multiple datasets named '{name}' found. Conflicting locations:\n"
                                f"  * {datasets[name]}\n  * {base}/{name}")
                datasets[name] = base / name
                _LOG.info("\n======= emulation:%s =======", name)
                yield base / name
    else:
        path = ProjectFiles.find_project_data(TOOLNAME, f"tests/data/{dataset}",
                                              what=f"{TOOLNAME} dataset '{dataset}'")
        yield path

def _get_emul_pman(args, commonpath, path):
    """
    Configure and return an 'EmulProcessManager' object for the dataset specified with the '-D'
    option.
    """

    from pepclibs.helperlibs import EmulProcessManager

    required_cmd_modules = {
        "aspm": ["ASPM", "Systemctl"],
        "cstates": ["CPUInfo", "CStates", "Systemctl"],
        "pstates": ["CPUInfo", "PStates", "Systemctl"],
        "pmqos": ["CPUInfo", "PMQoS"],
        "power": ["CPUInfo", "Power"],
        "topology": ["CPUInfo"],
        "cpu_hotplug": ["CPUInfo", "CPUOnline", "Systemctl"],
        "tpmi": ["TPMI"],
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
            pman.init_module(module, path, common_datapath=commonpath)
    except Error:
        pman.close()
        raise

    return pman

def _list_mechanisms(args):
    """Implement the '--list-mechanisms' option."""

    fname = args.func.__name__
    if fname.startswith("_pstates_"):
        props = PStates.PROPS
    elif fname.startswith("_cstates_"):
        props = CStates.PROPS
    elif fname.startswith("_power_"):
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
            return 0

        if args.dataset:
            commonpath = ProjectFiles.find_project_data(TOOLNAME, "tests/data/common",
                                                        what=f"common part of {TOOLNAME} datasets")
            for path in _get_next_dataset(args.dataset):
                with _get_emul_pman(args, commonpath, path) as pman:
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
