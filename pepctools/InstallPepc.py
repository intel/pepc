# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'install-pepc' tool and provide a public 'install_pepc()' API.

The 'install_pepc()' function can be imported by other projects that depend on 'pepc' (e.g.
'stats-collect') to install 'pepc' as part of their own installation flow.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import types
import typing
from pathlib import Path

try:
    argcomplete: types.ModuleType | None
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs.helperlibs import ProcessManager, ArgParse, Logging
from pepclibs.helperlibs.Exceptions import Error
from pepctools import PythonPrjInstaller

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final
    from pepclibs.helperlibs.ArgParse import SSHArgsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepctools.PythonPrjInstaller import SudoAliasStyle

    class _CmdlineArgsTypedDict(SSHArgsTypedDict, total=False):
        """
        A typed dictionary for command-line arguments of this tool. Includes all attributes from
        'SSHArgsTypedDict', plus the following:

        Attributes:
            install_path: The path to install 'pepc' to.
            src_path: The path to install 'pepc' from (a filesystem path or a Git URL).
            no_pkg_install: Do not install missing OS packages.
            no_rcfile: Do not modify the user's shell RC file (e.g. '.bashrc').
            force_sudo_alias: Force adding the 'sudo' alias, skipping the automatic privilege
                              checks.
            no_sudo_alias: Prevent adding the 'sudo' alias, skipping the automatic privilege
                           checks.
            sudo_alias_style: The style of the 'sudo' alias to add. One of 'refresh' or 'wrap'.
        """

        install_path: Path
        src_path: str
        no_pkg_install: bool
        no_rcfile: bool
        force_sudo_alias: bool
        no_sudo_alias: bool
        sudo_alias_style: SudoAliasStyle

_VERSION: Final[str] = "0.1"
_TOOLNAME: Final[str] = "install-pepc"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

# The upstream 'pepc' project Git URL and branch.
PEPC_GIT_INSTALL_SRC: Final[str] = "git+https://github.com/intel/pepc.git@release"

# The tools pepc relies on to be installed and to operate.
PEPC_DEPENDENCIES: Final[tuple[str, ...]] = (
    "virtualenv",
    "pip3",
    "cat",
    "dmesg",
    "id",
    "uname",
    "modprobe")

# Directories and files to exclude when copying pepc project sources to a remote host.
PEPC_COPY_EXCLUDE: Final[tuple[str, ...]] = ("/tests", "/docs", "**/*.md", ".*")

def _build_arguments_parser() -> ArgParse.ArgsParser:
    """
    Build and return the command-line arguments parser.

    Returns:
        An initialized command-line arguments parser object.
    """

    text = f"""{_TOOLNAME} - install 'pepc' on the local or a remote host into a Python virtual
               environment."""
    parser = ArgParse.ArgsParser(description=text, prog=_TOOLNAME, ver=_VERSION)
    ArgParse.add_ssh_options(parser)

    text = f"""Installation directory on the target host
               (default: '{PythonPrjInstaller.DEFAULT_INSTALL_PATH}')."""
    parser.add_argument("-p", "--install-path", type=Path, help=text)

    text = f"""Installation source: a local directory path or a Git URL
               (default: '{PEPC_GIT_INSTALL_SRC}')."""
    parser.add_argument("-s", "--src-path", help=text)

    text = """Do not install missing OS packages required for 'pepc' to work."""
    parser.add_argument("--no-pkg-install", action="store_true", help=text)

    text = """Do not modify the user's shell RC file (e.g. '.bashrc'). By default, the installer
              adds a line to the shell RC file to set up the 'pepc' environment."""
    parser.add_argument("--no-rcfile", action="store_true", help=text)

    text = """By default, the installer checks whether a 'sudo' alias is needed: if the target
              host is accessible with 'root' privileges or passwordless 'sudo', no alias is added
              (pepc handles privilege escalation internally). Otherwise, 'alias pepc="sudo pepc"'
              is added to the shell RC file so that 'pepc' commands always run with the required
              privileges."""
    text_on = f"""{text} Use this option to force adding the alias, skipping the automatic
                  checks."""
    parser.add_argument("--force-sudo-alias", action="store_true", help=text_on)

    text_off = f"""{text} Use this option to prevent adding the alias, skipping the automatic
                   checks."""
    parser.add_argument("--no-sudo-alias", action="store_true", help=text_off)

    text = """The style of the 'sudo' alias to add when one is needed. 'refresh' pre-authorizes
              'sudo' credentials before each invocation and lets 'pepc' escalate privileges
              internally as needed ('alias pepc="sudo -v && pepc"'). 'wrap' runs the entire
              'pepc' process under 'sudo' ('alias pepc="sudo ... pepc"'). This requires virtual
              environment configuration to be preserved across 'sudo'. Default: 'refresh'."""
    parser.add_argument("--sudo-alias-style", choices=["refresh", "wrap"], default="",
                        help=text)

    if argcomplete is not None:
        getattr(argcomplete, "autocomplete")(parser)

    return parser

def _parse_arguments() -> argparse.Namespace:
    """
    Parse the command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """

    parser = _build_arguments_parser()
    args = parser.parse_args()

    return args

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _CmdlineArgsTypedDict = {**ArgParse.format_ssh_args(args)}

    install_path = args.install_path
    cmdl["install_path"] = install_path if install_path else PythonPrjInstaller.DEFAULT_INSTALL_PATH

    src_path = args.src_path
    cmdl["src_path"] = src_path if src_path else PEPC_GIT_INSTALL_SRC

    cmdl["no_pkg_install"] = args.no_pkg_install
    cmdl["no_rcfile"] = args.no_rcfile
    cmdl["force_sudo_alias"] = args.force_sudo_alias
    cmdl["no_sudo_alias"] = args.no_sudo_alias

    sudo_alias_style = args.sudo_alias_style
    if sudo_alias_style and cmdl["no_sudo_alias"]:
        raise Error("The '--no-sudo-alias' and '--sudo-alias-style' options are mutually "
                    "exclusive")

    for optname in ("force_sudo_alias", "no_sudo_alias"):
        if cmdl["no_rcfile"] and cmdl[optname]:
            raise Error(f"The '--{optname.replace('_', '-')}' and '--no-rcfile' options are "
                        f"mutually exclusive")

    if cmdl["force_sudo_alias"] and cmdl["no_sudo_alias"]:
        raise Error("The '--force-sudo-alias' and '--no-sudo-alias' options are mutually "
                    "exclusive")

    cmdl["sudo_alias_style"] = sudo_alias_style or "refresh"

    return cmdl

def install_pepc(pman: ProcessManagerType,
                 src: str,
                 install_path: Path = PythonPrjInstaller.DEFAULT_INSTALL_PATH,
                 no_pkg_install: bool = False,
                 no_rcfile: bool = False,
                 force_sudo_alias: bool = False,
                 no_sudo_alias: bool = False,
                 sudo_alias_style: SudoAliasStyle = "refresh") -> None:
    """
    Install 'pepc' on the target host into a Python virtual environment.

    Args:
        pman: The process manager object that defines the target host.
        src: Installation source: a local directory path or a Git URL.
        install_path: Installation directory on the target host.
        no_pkg_install: Do not install missing OS packages.
        no_rcfile: Do not modify the user's shell RC file.
        force_sudo_alias: Force adding a 'sudo' alias to the RC file.
        no_sudo_alias: Prevent adding a 'sudo' alias to the RC file.
        sudo_alias_style: The style of the 'sudo' alias ('refresh' or 'wrap').
    """

    installer = PythonPrjInstaller.PythonPrjInstaller("pepc", src, pman=pman,
                                                      install_path=install_path, logging=True)
    if not no_pkg_install:
        installer.install_dependencies(PEPC_DEPENDENCIES)

    installer.install(exclude=PEPC_COPY_EXCLUDE)

    if not no_rcfile and not no_sudo_alias:
        if force_sudo_alias:
            installer.add_sudo_aliases(("pepc",), style=sudo_alias_style)
        elif not pman.is_superuser() and not pman.has_passwdless_sudo():
            installer.add_sudo_aliases(("pepc",), style=sudo_alias_style)

    if not no_rcfile:
        installer.hookup_rc_file()
    else:
        _LOG.info("Skipping shell RC file hookup%s, run '. %s' to configure "
                  "the 'pepc' environment manually.", pman.hostmsg, installer.rcfile_path)

def _main(pman: ProcessManagerType, cmdl: _CmdlineArgsTypedDict):
    """
    The main body of the tool.

    Args:
        pman: The process manager object that defines the target host.
        cmdl: The command-line arguments description dictionary.
    """

    install_pepc(pman, cmdl["src_path"], install_path=cmdl["install_path"],
                 no_pkg_install=cmdl["no_pkg_install"],
                 no_rcfile=cmdl["no_rcfile"],
                 force_sudo_alias=cmdl["force_sudo_alias"],
                 no_sudo_alias=cmdl["no_sudo_alias"],
                 sudo_alias_style=cmdl["sudo_alias_style"])

def main():
    """
    The 'install-pepc' tool entry point. Parse command-line arguments and install 'pepc'.

    Returns:
        The program exit code.
    """

    try:
        args = _parse_arguments()
        cmdl = _get_cmdline_args(args)

        with ProcessManager.get_pman(cmdl["hostname"], username=cmdl["username"],
                                     privkeypath=cmdl["privkey"]) as pman:
            _main(pman, cmdl)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
    except Error as err:
        _LOG.error_out(str(err))

    return 0
