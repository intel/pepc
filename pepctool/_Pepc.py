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
from pepclibs import CStates, PStates, CPUInfo

if sys.version_info < (3,7):
    raise SystemExit("Error: this tool requires python version 3.7 or higher")

_VERSION = "1.3.46"
_OWN_NAME = "pepc"

_LOG = logging.getLogger()
Logging.setup_logger(prefix=_OWN_NAME)

DATASET_OPTIONS = [
    {
        "short" : "-D",
        "long" : "--dataset",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "dataset",
            "help" : f"""This option is for debugging and testing purposes only, it defines the
                         dataset that will be used to emulate a host for running the command on.
                         Please, specify dataset path or name. In the latter case, it will be
                         searched for in the following locations:
                         {ProjectFiles.get_project_data_search_descr('pepc', 'tests/data')}.
                         Use 'all' to specify all available datasets.
                         """
        },
    },
]

class PepcArgsParser(ArgParse.ArgsParser):
    """
    The default argument parser does not allow defining "global" options, so that they are present
    in every subcommand. For example, we want the SSH options to be available everywhere.
    """

    def add_dataset_options(self):
        """Add dataset options to argument parser."""

        for opt in DATASET_OPTIONS:
            arg = self.add_argument(opt["short"], opt["long"], **opt["kwargs"])
            if opt["argcomplete"] and argcomplete:
                arg.completer = getattr(argcomplete.completers, opt["argcomplete"])

    def _check_unknow_args(self, args, uargs, gargs): # pylint: disable=no-self-use
        """
        Check unknown arguments 'uargs' for global arguments 'gargs' and add them to 'args'.
        This is a workaround for implementing global arguments.
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
        self._check_unknow_args(args, uargs, DATASET_OPTIONS)

        if uargs:
            raise Error(f"unrecognized option(s): {' '.join(uargs)}")

        if args.dataset and args.hostname != "localhost":
            raise Error("can't use dataset on remote host")

        return args

def _add_cpu_subset_arguments(subpars, fmt):
    """
    Add CPU subset arguments, argument 'fmt' should include '%s' that will be replaced by the subset
    name.
    """

    text = fmt % "CPUs" # pylint: disable=consider-using-f-string
    text += """ The list can include individual CPU numbers and CPU number ranges. For example,
               '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special
               keyword 'all' to specify all CPUs. If the CPUs/cores/packages were not specified,
               all CPUs will be used as the default value."""
    subpars.add_argument("--cpus", help=text)

    text = fmt % "cores" # pylint: disable=consider-using-f-string
    text += """ The list can include individual core numbers and core number ranges. For example,
               '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special
               keyword 'all' to specify all cores."""
    subpars.add_argument("--cores", help=text)

    text = fmt % "packages" # pylint: disable=consider-using-f-string
    text += """ The list can include individual package numbers and package number ranges. For
               example, '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and 3.
               Use the special keyword 'all' to specify all packages."""
    subpars.add_argument("--packages", help=text)

    text = fmt % "core sibling indices" # pylint: disable=consider-using-f-string
    text += """ The list can include individual core sibling indices or index ranges. For example,
               core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean CPU 4. This
               option can only be used to reference online CPUs, because Linux does not provide
               topology information for offline CPUs. In the previous example if CPU 3 was offline,
               then '0' would mean CPU 4."""
    subpars.add_argument("--core-siblings", help=text)

def build_arguments_parser():
    """A helper function which parses the input arguments."""

    text = "pepc - Power, Energy, and Performance Configuration tool for Linux."
    parser = PepcArgsParser(description=text, prog=_OWN_NAME, ver=_VERSION)

    ArgParse.add_ssh_options(parser)
    parser.add_dataset_options()

    text = "Force coloring of the text output."
    parser.add_argument("--force-color", action="store_true", help=text)
    subparsers = parser.add_subparsers(title="commands", dest="a command")
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

    text = """List of CPUs to online. The list can include individual CPU numbers and CPU number
              ranges. For example, '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12.
              Use the special keyword 'all' to specify all CPUs."""
    subpars2.add_argument("--cpus", help=text)
    subpars2.add_argument("--cores", help=argparse.SUPPRESS)
    subpars2.add_argument("--packages", help=argparse.SUPPRESS)
    subpars2.add_argument("--core-siblings", help=argparse.SUPPRESS)

    #
    # Create parser for the 'cpu-hotplug offline' command.
    #
    text = """Bring CPUs offline."""
    subpars2 = subparsers2.add_parser("offline", help=text, description=text)
    subpars2.set_defaults(func=cpu_hotplug_offline_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to offline.")

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

    _add_cpu_subset_arguments(subpars2, "List of %s to get information about.")

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    text = f"""Comma-separated list of C-states to get information about (all C-states by default).
               {cst_list_text}."""
    subpars2.add_argument("--cstates", dest="csnames", metavar="CATATES", nargs="?", help=text,
                          default="default")

    for name, pinfo in CStates.PROPS.items():
        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Get current setting for "
        else:
            text = "Get "

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]} This option has {pinfo["sname"]} scope."""

        subpars2.add_argument(option, action="store_true", help=text)

    #
    # Create parser for the 'cstates config' command.
    #
    text = "Configure C-states."
    descr = """Configure C-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=cstates_config_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to configure.")

    text = f"""Comma-separated list of C-states to enable. {cst_list_text}."""
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
        text += f"""{name}. {pinfo["help"]}{choices} This option has {pinfo["sname"]} scope."""

        kwargs["help"] = text
        kwargs["action"] = ArgParse.OrderedArg
        subpars2.add_argument(option, **kwargs)

    #
    # Create parser for the 'cstates save' command.
    #
    text = "Save C-states settings."
    descr = f"""Save all the modifiable C-state settings into a file. This file can later be used
                for restoring C-state settings with the '{_OWN_NAME} cstates restore' command."""
    subpars2 = subparsers2.add_parser("save", help=text, description=descr)
    subpars2.set_defaults(func=cstates_save_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to save C-state information about.")

    text = "Name of the file to save the settings to."
    subpars2.add_argument("-o", "--outfile", help=text)

    #
    # Create parser for the 'cstates restore' command.
    #
    text = "Restore C-states settings."
    descr = f"""Restore C-state settings from a file previously created with the
               '{_OWN_NAME} cstates save' command."""
    subpars2 = subparsers2.add_parser("restore", help=text, description=descr)
    subpars2.set_defaults(func=cstates_restore_command)

    text = """Name of the file restore the settings from (use "-" to read from the standard
              output."""
    subpars2.add_argument("-f", "--from", dest="infile", help=text)

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

    _add_cpu_subset_arguments(subpars2, "List of %s to get information about.")

    text = """Print information in YAML format."""
    subpars2.add_argument("--yaml", action="store_true", help=text)

    for name, pinfo in PStates.PROPS.items():
        if pinfo["type"] == "bool":
            # This is a binary "on/off" type of features.
            text = "Get current setting for "
        else:
            text = "Get "

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]} This option has {pinfo["sname"]} scope."""

        subpars2.add_argument(option, action="store_true", help=text)

    #
    # Create parser for the 'pstates config' command.
    #
    text = """Configure P-states."""
    descr = """Configure P-states on specified CPUs. All options can be used without a parameter,
               in which case the currently configured value(s) will be printed."""
    subpars2 = subparsers2.add_parser("config", help=text, description=descr)
    subpars2.set_defaults(func=pstates_config_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to configure P-States on.")

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

        option = f"--{name.replace('_', '-')}"
        name = Human.untitle(pinfo["name"])
        text += f"""{name}. {pinfo["help"]}{choices} This option has {pinfo["sname"]}
                    scope."""

        kwargs["help"] = text
        kwargs["action"] = ArgParse.OrderedArg
        subpars2.add_argument(option, **kwargs)

    #
    # Create parser for the 'pstates save' command.
    #
    text = "Save P-states settings."
    descr = f"""Save all the modifiable P-state settings into a file. This file can later be used
                for restoring P-state settings with the '{_OWN_NAME} pstates restore' command."""
    subpars2 = subparsers2.add_parser("save", help=text, description=descr)
    subpars2.set_defaults(func=pstates_save_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to save P-state information about.")

    text = "Name of the file to save the settings to (printed to standard output by default)."
    subpars2.add_argument("-o", "--outfile", help=text, default="-")

    #
    # Create parser for the 'pstates restore' command.
    #
    text = "Restore P-states settings."
    descr = f"""Restore P-state settings from a file previously created with the
               '{_OWN_NAME} pstates save' command."""
    subpars2 = subparsers2.add_parser("restore", help=text, description=descr)
    subpars2.set_defaults(func=pstates_restore_command)

    text = """Name of the file restore the settings from (use "-" to read from the standard
              output."""
    subpars2.add_argument("-f", "--from", dest="infile", help=text)

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

    #
    # Create parser for the 'topology' command.
    #
    text = "CPU topology commands."
    descr = """Various commands related to CPU topology."""
    subpars = subparsers.add_parser("topology", help=text, description=descr)
    subparsers2 = subpars.add_subparsers(title="further sub-commands")
    subparsers2.required = True

    text = "Print CPU topology."
    descr = """Print CPU topology information. Note, the topology information for some offline CPUs
               may be unavailable, in these cases the number will be substituted with "?"."""
    subpars2 = subparsers2.add_parser("info", help=text, description=descr)
    subpars2.set_defaults(func=topology_info_command)

    _add_cpu_subset_arguments(subpars2, "List of %s to print topology information for.")

    orders = ", ".join([lvl.lower() for lvl in CPUInfo.LEVELS])
    text = f"""By default, the topology table is printed in CPU number order. Use this option to
               print it in a different order (e.g., core or package number order). Here are the
               supported order names: {orders}."""
    subpars2.add_argument("--order", help=text, default="CPU")

    text = """Include only online CPUs. By default offline and online CPUs are included."""
    subpars2.add_argument("--online-only", action='store_true', help=text)

    columns = ", ".join(CPUInfo.LEVELS)
    text = f"""By default, the topology columns are {columns}, "die" and "module" columns are not
               printed if there is only one die per package and no modules. Use this option to
               select topology columns names and order (e.g. '--columns Package,Core,CPU')."""
    subpars2.add_argument("--columns", help=text, default=None)

    if argcomplete:
        argcomplete.autocomplete(parser)

    return parser

def parse_arguments():
    """Parse input arguments."""

    parser = build_arguments_parser()
    args = parser.parse_args()

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
        base = ProjectFiles.find_project_data(_OWN_NAME, "tests/data", what=f"{_OWN_NAME} datasets")
        for name in os.listdir(base):
            _LOG.info("\n======= emulation:%s =======", name)
            yield Path(f"{base}/{name}")
    else:
        base = ProjectFiles.find_project_data(_OWN_NAME, "tests/data", what=f"{_OWN_NAME} datasets")
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

    for module in modules:
        pman.init_testdata(module, path)

    return pman

def main():
    """Script entry point."""

    try:
        args = parse_arguments()

        if not getattr(args, "func", None):
            _LOG.error("please, run '%s -h' for help", _OWN_NAME)
            return -1

        # pylint: disable=no-member
        if args.hostname == "localhost":
            args.username = args.privkey = args.timeout = None

        if args.dataset:
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
