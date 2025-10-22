# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Helpful classes extending 'argparse.ArgumentParser' class functionality.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import types
import typing
import argparse
from pathlib import Path

try:
    import argcomplete
    _ARGCOMPLETE_AVAILABLE = True
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    _ARGCOMPLETE_AVAILABLE = False

from pepclibs.helperlibs import DamerauLevenshtein, Trivial, Logging
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import TypedDict, Iterable, Any, Sequence

    # The class type returned by the 'add_subparsers()' method of the arguments classes. Even though
    # the class is private, it is documented and will unlikely to change.
    SubParsersType = argparse._SubParsersAction # pylint: disable=protected-access

    class ArgKwargsTypedDict(TypedDict, total=False):
        """
        The type of the "kwargs" sub-dictionary of the 'ArgDictType' dictionary type. It defines the
        supported keyword arguments that are ultimately passed to the 'argparse.add_argument()'
        method.

        Attributes:
            dest: The 'argparse' attribute name where the command line argument will be stored.
            default: The default value for the argument.
            nargs: The number of command line arguments that should be consumed.
            metavar: The name of the argument in the help text.
            action: The 'argparse' action to use for the argument. For example, 'store_true' or
                    'store_const'.
            help: A brief description of the argument.
        """

        dest: str
        default: str | int
        nargs: str | int
        metavar: str
        action: str | type[argparse.Action]
        help: str

    class ArgTypedDict(TypedDict, total=False):
        """
        A dictionary type the options definitions dictionary.

        Attributes:
            short: The short option name.
            long: The long option name.
            argcomplete: The 'argcomplete' class name to use for tab completion of the option.
            kwargs: Additional keyword arguments for 'argparse.add_argument()'.
        """

        short: str | None
        long: str
        argcomplete: str | None
        kwargs: ArgKwargsTypedDict

    class CommonArgsTypedDict(TypedDict, total=False):
        """
        The common command-line arguments.

        Attributes:
            quiet: Suppress non-essential output (-q option). False by default.
            force_color: Force colorized output even if the output stream is not a terminal
                        (--force-color option). False by default.
            debug: Enable debugging output (-d option). False by default.
            debug_modules: Comma-separated list modules for which to enable debugging output
                           (--debug-modules option). None by default (enable debugging for all
                           modules).
        """

        quiet: bool
        force_color: bool
        debug: bool
        debug_modules: list[str] | None

    class SSHArgsTypedDict(TypedDict, total=False):
        """
        The SSH-related command-line arguments after they have been processed and validated.

        Attributes:
            hostname: The remote host name or IP address (-H option). Default is "localhost".
            username: The user name for logging into the remote host (-U option). Default is "root"
                      in case of a remote host and "" (empty string) for the local host.
            privkey: The path to the private SSH key (-K option). Default is an empty string (no
                     private SSH key).
            timeout: The timeout for establishing an SSH connection in seconds (-T option). Default
                     is 8 seconds for remote hosts and None for the local host.
        """

        hostname: str
        username: str
        privkey: str | Path
        timeout: int | float | None

SSH_OPTIONS: list[ArgTypedDict] = [
    {
        "short" : "-H",
        "long" : "--host",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "hostname",
            "default" : "localhost",
            "help" : "Host name or IP address of the remote host to connect to over SSH and run "
                     "the command on. Run the command on the local host if not specified."
        },
    },
    {
        "short" : "-U",
        "long" : "--username",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "username",
            "default" : "",
            "help" : "Name of the user to use for logging into the remote host over SSH. The "
                     "default user name is 'root'."
        },
    },
    {
        "short" : "-K",
        "long" : "--priv-key",
        "argcomplete" : "FilesCompleter",
        "kwargs" : {
            "dest" : "privkey",
            "default" : "",
            "help" : "Path to the private SSH key for logging into the remote host. Defaults to "
                     "keys in standard paths like '$HOME/.ssh'."
        },
    },
    {
        "short" : "-T",
        "long" : "--timeout",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "timeout",
            "default" : "",
            "help" : "Timeout for establishing an SSH connection in seconds. Defaults to 8."
        },
    },
]

def add_options(parser: argparse.ArgumentParser | ArgsParser, options: Iterable[ArgTypedDict]):
    """
    Add command line options to the given parser.

    Args:
        parser: The argument parser object to which options will be added.
        options: An iterable collection of option definition dictionaries.
    """

    for opt in options:
        args: tuple[str, ...]

        if opt["short"] is None:
            args = (opt["long"], )
        else:
            args = (opt["short"], opt["long"])

        arg = parser.add_argument(*args, **opt["kwargs"])
        if opt["argcomplete"] and _ARGCOMPLETE_AVAILABLE:
            setattr(arg, "completer", getattr(argcomplete.completers, opt["argcomplete"]))

def add_ssh_options(parser: argparse.ArgumentParser | ArgsParser):
    """
    Add SSH-related command-line options to the given argument parser.

    Args:
        parser: The argument parser object to which SSH options will be added.
    """

    add_options(parser, SSH_OPTIONS)

def format_common_args(args: argparse.Namespace) -> CommonArgsTypedDict:
    """
    Verify common command-line arguments and return them as a dictionary.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A dictionary containing the common options.
    """

    cmdl: CommonArgsTypedDict = {}

    cmdl["quiet"] = getattr(args, "quiet", False)
    cmdl["debug"] = getattr(args, "debug", False)
    if cmdl["quiet"] and cmdl["debug"]:
        raise Error("The '-q' and '-d' options cannot be used together")

    debug_modules: str | None = getattr(args, "debug_modules", None)
    if debug_modules:
        if cmdl["quiet"]:
            raise Error("The '-q' and '--debug-modules' options cannot be used together")
        if not cmdl["debug"]:
            raise Error("The '--debug-modules' option requires the '-d' option to be used")
        cmdl["debug_modules"] = Trivial.split_csv_line(debug_modules)
    else:
        cmdl["debug_modules"] = None

    cmdl["force_color"] = getattr(args, "force_color", False)
    if cmdl["force_color"]:
        try:
            # pylint: disable-next=unused-import,import-outside-toplevel
            import colorama
        except ImportError as err:
            raise Error("The '--force-color' option requires the 'colorama' python package to be "
                        "installed") from err
    return cmdl

def format_ssh_args(args: argparse.Namespace) -> SSHArgsTypedDict:
    """
    Verify SSH-related command-line arguments and return them as a dictionary.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A dictionary containing the SSH-related options.
    """

    hostname: str = getattr(args, "hostname", "localhost")
    username: str = getattr(args, "username", "")
    privkey: str | Path = getattr(args, "privkey", "")
    timeout: int | float | None = getattr(args, "timeout", None)

    if hostname == "localhost":
        if username:
            raise Error("The '--username' option requires the '--host' option")
        if privkey:
            raise Error("The '--priv-key' option requires the '--host' option")
        if timeout:
            raise Error("The '--timeout' option requires the '--host' option")
    else:
        if not username:
            username = "root"
        if timeout:
            timeout = Trivial.str_to_num(getattr(args, "timeout"), what="--timeout option value")
        else:
            timeout = 8

    cmdl: SSHArgsTypedDict = {"hostname": hostname,
                              "username": username,
                              "privkey": privkey,
                              "timeout": timeout}
    return cmdl

class OrderedArg(argparse.Action):
    """
    Implement an argparse action to preserve the order of command-line arguments.

    This action stores arguments and their values in the 'oargs' attribute of the namespace,
    maintaining the order in which arguments are parsed. Use this when the order of arguments
    matters.

    Example:
        parser.add_argument("--foo", action=OrderedArg)
        parser.add_argument("--bar", action=OrderedArg)
        args = parser.parse_args()
        print(args.oargs)  # {'foo': 'foo_value', 'bar': 'bar_value'}
    """

    def __call__(self,
                 parser: argparse.ArgumentParser,
                 namespace: argparse.Namespace,
                 values: str | Sequence[Any] | None,
                 option_string: str | None = None):
        """Append the ordered argument to the 'oargs' attribute."""

        oargs: dict[str, Any]
        if not hasattr(namespace, "oargs"):
            oargs = {}
            setattr(namespace, "oargs", oargs)
        else:
            oargs = getattr(namespace, "oargs")

        oargs[self.dest] = values

        # Also add the standard attribute for compatibility.
        setattr(namespace, self.dest, values)

def _add_parser(subparsers: SubParsersType, *args: Any, **kwargs: Any) -> argparse.ArgumentParser:
    """
    Override the 'add_parser()' method of a subparsers object to mangle the 'description' argument.

    This function removes all newlines and extra whitespace from the 'description' keyword argument
    before calling the original 'add_parser()' method. Unfortunately, a monkey-patch is has to be
    used to override the 'add_parser()' method of the 'subparsers' object.

    Example:
        subparsers = parser.add_subparsers()
        descr = "Long description\n   With newlines and white-spaces and possibly tabs."
        subparsers.add_parser("subcommand", help="help", description=descr)

        Without this function, the 'description' would be displayed with newlines and extra spaces.
        This function ensures that the 'description' is formatted correctly for display in help
        text.

    Args:
        subparsers: The subparsers action object returned by 'add_subparsers()'.
        *args: Positional arguments to pass to the original 'add_parser()' method.
        **kwargs: Keyword arguments to pass to the original 'add_parser()' method.

    Returns:
        The 'ArgumentParser' instance created by the original 'add_parser()' method.
    """

    if "description" in kwargs:
        kwargs["description"] = " ".join(kwargs["description"].split())

    orig_add_parser = getattr(subparsers, "__orig_add_parser")
    return orig_add_parser(*args, **kwargs)

class ArgsParser(argparse.ArgumentParser):
    """
    Enhance 'argparse.ArgumentParser' with standard options and improved usability.
      - Add and validate standard options, such  as '-h' and '-q'.
      - Remove extra whitespace and newlines from 'description' in 'add_parser()'.
      - Override 'error()' to always suggest using '-h' for help and provide typo suggestions.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        """
        We assume all tools using this module support the '-q' and '-d' options. This helper adds
        them to the 'parser' argument parser object.
        """

        if "ver" in kwargs:
            version = kwargs["ver"]
            del kwargs["ver"]
        else:
            version = None

        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)

        text = "Show this help message and exit."
        self.add_argument("-h", "--help", dest="help", action="help", help=text)

        text = "Be quiet (print only improtant messages like warnings)."
        self.add_argument("-q", "--quiet", dest="quiet", action="store_true", help=text)

        text = """Force colorized output even if the output stream is not a terminal (adds ANSI
                  escape codes)."""
        self.add_argument("--force-color", action="store_true", help=text)

        text = "Print debugging information."
        self.add_argument("-d", "--debug", dest="debug", action="store_true", help=text)

        text = "Print debugging information only from the specified modules."
        self.add_argument("--debug-modules", action="store", metavar="MODNAME[,MODNAME1,...]",
                          help=text)

        if version:
            text = "Print the version number and exit."
            self.add_argument("--version", action="version", help=text, version=version)

    def parse_args(self, *args: Any, **kwargs: Any) -> argparse.Namespace: # type: ignore[override]
        """
        Parse command line arguments and configure debug logging.

        Args:
            *args: Positional arguments for 'ArgumentParser.parse_args()'.
            **kwargs: Keyword arguments for 'ArgumentParser.parse_args()'.
        """

        _args = super().parse_args(*args, **kwargs)

        cmdl = format_common_args(_args)
        if cmdl["debug_modules"] is not None:
            Logging.DEBUG_MODULE_NAMES = set(cmdl["debug_modules"])

        return _args

    def add_subparsers(self, *args: Any, **kwargs: Any) -> SubParsersType:
        """
        Create subparsers with a customized 'add_parser()' method.

        Args:
            *args: Positional arguments for 'add_subparsers'.
            **kwargs: Keyword arguments for 'add_subparsers'.

        Returns:
            The subparsers action object.
        """

        subparsers = super().add_subparsers(*args, **kwargs)
        setattr(subparsers, "__orig_add_parser", subparsers.add_parser)
        setattr(subparsers, "add_parser", types.MethodType(_add_parser, subparsers))

        return subparsers

    def error(self, message: str):
        """
        Improve error messages from 'argparse.ArgumentParser'.

        Args:
            message: The original error message.
        """

        if "invalid choice: " not in message:
            message += "\nUse -h for help."
        else:
            offending, opts = message.split(" (choose from ")
            offending = offending.split("invalid choice: ")[1].strip("'")
            options = [opt.strip(")'") for opt in opts.split(", ")]
            suggestion = DamerauLevenshtein.closest_match(offending, options)
            if suggestion:
                message = f"bad argument '{offending}', use '{self.prog} -h'.\n\nThe most " \
                          f"similar argument is\n  {suggestion}"

        # Raise an error instead of calling the superclass method, because it exits the program.
        # super().error(message)
        raise Error(message)
