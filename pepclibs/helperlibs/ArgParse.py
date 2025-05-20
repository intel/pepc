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

# TODO: finish adding type hints to this module.
from __future__ import annotations # Remove when switching to Python 3.10+.

import types
from typing import TypedDict
import argparse

try:
    import argcomplete
    argcomplete_imported = True
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete_imported = False

from pepclibs.helperlibs import DamerauLevenshtein, Trivial, Logging
from pepclibs.helperlibs.Exceptions import Error # pylint: disable=unused-import

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
            "help" : "User name for SSH login to the remote host. Defaults to 'root."
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

def add_options(parser: argparse.ArgumentParser | ArgsParser, options: list[ArgTypedDict]):
    """
    Add the '--host', '--timeout' and other SSH-related options to argument parser object 'parser'.
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
    Add the '--host', '--timeout' and other SSH-related options to argument parser object 'parser'.
    """

    # Add the SSH options to the parser.
    add_options(parser, SSH_OPTIONS)

class OrderedArg(argparse.Action):
    """
    This action implements ordered arguments support. Sometimes the command line arguments order
    matter, and this action can be used to preserve the order. It simply stores all the ordered
    arguments in the 'oargs' attribute, which is a dictionary with keys being option names and
    values being the option values.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        """Append the ordered argument to the 'oargs' attribute."""

        if not getattr(namespace, "oargs", None):
            setattr(namespace, "oargs", {})

        # Also add the standard attribute for compatibility.
        setattr(namespace, self.dest, values)

        namespace.oargs[self.dest] = values

def _add_parser(subparsers, *args, **kwargs):
    """
    This function overrides the 'add_parser()' method of the 'subparsers' object. The 'subparsers'
    object the action object returned by 'add_subparsers()'. The goal of this function is to remove
    all newlines and extra white-spaces from the "description" keyword argument. Here is an example.

    descr = "Long description\n   With newlines and white-spaces and possibly tabs."
    subpars = subparsers.add_parser("subcommand", help="help", description=descr)

    By default 'argparse' removes those newlines when the help is displayed. However, for some
    reason when we generate man pages out of help text using the 'argparse-manpage' tool, the
    newlines are not removed and the man page looks untidy.

    So basically this is a workaround for that problem. We just override the 'add_parser()' method,
    remove newlines and extra spaces from the description, and call the original 'add_parser()'
    method.
    """

    if "description" in kwargs:
        kwargs["description"] = " ".join(kwargs["description"].split())
    return subparsers.__orig_add_parser(*args, **kwargs) # pylint: disable=protected-access

class ArgsParser(argparse.ArgumentParser):
    """
    This class re-defines the 'error()' method of the 'argparse.ArgumentParser' class in order to
    make it always print a hint about the '-h' option. It also overrides the 'add_argument()' method
    to include the standard options like '-q' and '-d'.
    """

    def __init__(self, *args, **kwargs):
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

    def _check_arguments(self, args):
        """
        Check validity of common arguments.
        """

        if args.quiet and args.debug:
            raise Error("-q and -d cannot be used together")

        if args.quiet and args.debug_modules:
            raise Error("-q and --debug_modules cannot be used together")

        if args.debug_modules and not args.debug:
            raise Error("--debug_modules requires -d to be used")

    def _configure_debug_logging(self, args):
        """
        Handle the '--debug-modules' argument, which includes a comma-separated list of module names
        to allow debugging messages from.
        """

        if args.debug_modules:
            modnames = Trivial.split_csv_line(args.debug_modules)
            Logging.DEBUG_MODULE_NAMES = set(modnames)

    def parse_args(self, *args, **kwargs): # pylint: disable=signature-differs
        """Verify that '-d' and '-q' are not used at the same time."""

        args = super().parse_args(*args, **kwargs)
        self._check_arguments(args)
        self._configure_debug_logging(args)
        return args

    def add_subparsers(self, *args, **kwargs):
        """
        Create and return the subparsers action object with a customized 'add_parser()' method.
        Refer to '_add_parser()' for details.
        """

        subparsers = super().add_subparsers(*args, **kwargs)
        setattr(subparsers, "__orig_add_parser", subparsers.add_parser)
        setattr(subparsers, "add_parser", types.MethodType(_add_parser, subparsers))

        return subparsers

    def error(self, message):
        """
        Print the error message and exit. The arguments are as follows.
          * message - the error message to print.
        """

        # Check if the user only made a minor typo, and improve the message if they did.
        if "invalid choice: " not in message:
            message += "\nUse -h for help."
        else:
            offending, opts = message.split(" (choose from ")
            offending = offending.split("invalid choice: ")[1].strip("'")
            opts = [opt.strip(")'") for opt in opts.split(", ")]
            suggestion = DamerauLevenshtein.closest_match(offending, opts)
            if suggestion:
                message = f"bad argument '{offending}', use '{self.prog} -h'.\n\nThe most " \
                          f"similar argument is\n        {suggestion}"

        super().error(message)
