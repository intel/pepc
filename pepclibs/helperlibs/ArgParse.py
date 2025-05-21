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
from typing import TypedDict, Iterable, Any, Sequence, cast
from dataclasses import dataclass
import argparse

try:
    import argcomplete
    argcomplete_imported = True
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete_imported = False

from pepclibs.helperlibs import DamerauLevenshtein, Trivial, Logging
from pepclibs.helperlibs.Exceptions import Error

# The class type returned by the 'add_subparsers()' method of the arguments classes. Even though the
# class is private, it is documented and will unlikely to change.
SubParsersType = argparse._SubParsersAction # pylint: disable=protected-access

class ArgKwargsTypedDict(TypedDict, total=False):
    """
    The type of the "kwargs" sub-dictionary of the 'ArgDictType' dictionary type. It defines the
    supported keyword arguments that are ultimately passed to the 'argparse.add_argument()' method.

    Attributes:
        dest: The 'argparse' attribute name where the command line argument will be stored.
        default: The default value for the argument.
        metavar: The name of the argument in the help text.
        action: The 'argparse' action to use for the argument. For example, 'store_true' or
                'store_const'.
        help: A brief description of the argument.
    """

    dest: str
    default: str | int
    metavar: str
    action: str
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
            "default" : "root",
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
            "default" : 8,
            "help" : "Timeout for establishing an SSH connection in seconds. Defaults to 8."
        },
    },
]

@dataclass
class _CommonArgumentsType:
    """
    The common command-line arguments.

    Attributes:
        quiet: Suppress non-essential output (-q option).
        debug: Enable debugging output (-d option).
        debug_modules: Comma-separated list modules for which to enable debugging output, or None
                       to enable debugging for all modules (--debug-modules option).
    """

    quiet: bool
    debug: bool
    debug_modules: str | None

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
        if opt["argcomplete"] and argcomplete_imported:
            setattr(arg, "completer", getattr(argcomplete.completers, opt["argcomplete"]))

def add_ssh_options(parser: argparse.ArgumentParser | ArgsParser):
    """
    Add SSH-related command-line options to the given argument parser.

    Args:
        parser: The argument parser object to which SSH options will be added.
    """

    add_options(parser, SSH_OPTIONS)

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
        self.add_argument("-h", dest="help", action="help", help=text)

        text = "Be quiet (print only improtant messages like warnings)."
        self.add_argument("-q", dest="quiet", action="store_true", help=text)

        text = "Print debugging information."
        self.add_argument("-d", dest="debug", action="store_true", help=text)

        text = "Print debugging information only from the specified modules."
        self.add_argument("--debug-modules", action="store", metavar="MODNAME[,MODNAME1,...]",
                          help=text)

        if version:
            text = "Print the version number and exit."
            self.add_argument("--version", action="version", help=text, version=version)

    def _check_arguments(self, args: _CommonArgumentsType):
        """
        Validate the common command-line arguments.

        Args:
            args: The parsed command-line arguments.

        Raises:
            Error: If an invalid argument combination is detected.
        """

        if args.quiet and args.debug:
            raise Error("-q and -d cannot be used together")

        if args.quiet and args.debug_modules:
            raise Error("-q and --debug_modules cannot be used together")

        if args.debug_modules and not args.debug:
            raise Error("--debug-modules requires -d to be used")

    def _configure_debug_logging(self, args: _CommonArgumentsType):
        """
        Parse the '--debug-modules' argument and enable debug logging for the specified modules.

        Args:
            args: The parsed command-line arguments.
        """

        if args.debug_modules:
            modnames = Trivial.split_csv_line(args.debug_modules)
            Logging.DEBUG_MODULE_NAMES = set(modnames)

    def parse_args(self, *args: Any, **kwargs: Any) -> argparse.Namespace: # type: ignore[override]
        """Verify that '-d' and '-q' are not used at the same time."""

        arguments = super().parse_args(*args, **kwargs)

        args_dc = cast(_CommonArgumentsType, arguments)
        self._check_arguments(args_dc)
        self._configure_debug_logging(args_dc)

        return arguments

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

        super().error(message)
