# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
make-standalone - create a standalone 'pepc' zipapp that can be run without installation.
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

from pepclibs.helperlibs import LocalProcessManager, ArgParse, Logging
from pepclibs.helperlibs.Exceptions import Error
from pepctools import PythonPrjInstaller, InstallPepc

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final
    from pepclibs.helperlibs.ArgParse import SSHArgsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _CmdlineArgsTypedDict(SSHArgsTypedDict, total=False):
        """
        A typed dictionary for command-line arguments of this tool. Includes all attributes from
        'SSHArgsTypedDict', plus the following:

        Attributes:
            output: The path to the output standalone version of 'pepc'.
            src_path: The path to install 'pepc' from (a filesystem path or a Git URL).
            no_pkg_install: Do not install missing OS packages.
        """

        output: Path
        src_path: str
        no_pkg_install: bool

_VERSION: Final[str] = "0.1"
_TOOLNAME: Final[str] = "make-standalone"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

_DEFAULT_PEPC_STANDALONE_NAME: Final[str] = "pepc-standalone"

def _build_arguments_parser() -> ArgParse.ArgsParser:
    """
    Build and return the command-line arguments parser.

    Returns:
        An initialized command-line arguments parser object.
    """

    text = f"""{_TOOLNAME} - create a standalone 'pepc' zipapp that can be run without
               installation."""
    parser = ArgParse.ArgsParser(description=text, prog=_TOOLNAME, ver=_VERSION)

    text = f"""Path to the output standalone 'pepc' zipapp (default is
               './{_DEFAULT_PEPC_STANDALONE_NAME}')."""
    parser.add_argument("-o", "--output", type=Path, help=text)

    text = f"""Installation source: a local directory path or a Git URL
               (default: '{InstallPepc.PEPC_GIT_INSTALL_SRC}')."""
    parser.add_argument("-s", "--src-path", help=text)

    text = """Do not install missing OS packages required for 'pepc' to work."""
    parser.add_argument("--no-pkg-install", action="store_true", help=text)

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

    output = getattr(args, "output")
    cmdl["output"] = output if output else Path(f"./{_DEFAULT_PEPC_STANDALONE_NAME}")

    src_path = getattr(args, "src_path")
    cmdl["src_path"] = src_path if src_path else InstallPepc.PEPC_GIT_INSTALL_SRC

    cmdl["no_pkg_install"] = getattr(args, "no_pkg_install")

    return cmdl

def _main(lpman: LocalProcessManager.LocalProcessManager,
          cmdl: _CmdlineArgsTypedDict,
          tmpdir: Path):
    """
    The main body of the tool.

    Args:
        lpman: A local process manager object to use for running commands on the local host.
        cmdl: The command-line arguments description dictionary.
        tmpdir: Path to a temporary directory to use for intermediate operations.
    """

    installer = PythonPrjInstaller.PythonPrjInstaller("pepc", cmdl["src_path"], pman=lpman,
                                                      install_path=tmpdir / "pepc", logging=True)

    if not cmdl["no_pkg_install"]:
        installer.install_dependencies(InstallPepc.PEPC_DEPENDENCIES)

    # Install the project to the temporary directory.
    installer.install(exclude=InstallPepc.PEPC_COPY_EXCLUDE)

    # Create the standalone executable from the installed project.
    installer.create_standalone("pepc", cmdl["output"])

def main():
    """
    The entry point of the tool.

    Returns:
        The program exit code.
    """

    try:
        args = _parse_arguments()
        cmdl = _get_cmdline_args(args)

        with LocalProcessManager.LocalProcessManager() as lpman, \
             lpman.mkdtemp_ctx(prefix=f"{_TOOLNAME}-") as tmpdir:
            _main(lpman, cmdl, tmpdir)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
    except Error as err:
        _LOG.error_out(str(err))

    return 0
