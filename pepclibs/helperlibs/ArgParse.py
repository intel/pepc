# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains helpers related to parsing command-line arguments.
"""

import sys
import types
import argparse

try:
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs.helperlibs import DamerauLevenshtein
from pepclibs.helperlibs.Exceptions import Error # pylint: disable=unused-import

SSH_OPTIONS = [
    {
        "short" : "-H",
        "long" : "--host",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "hostname",
            "default" : "localhost",
            "help" : "Name of the host to run the command on."
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
            "help" : "Path to the private SSH key that should be used for logging into the remote "
                     "host. By default the key is automatically found from standard paths like "
                     "'~/.ssh'."
        },
    },
    {
        "short" : "-T",
        "long" : "--timeout",
        "argcomplete" : None,
        "kwargs" : {
            "dest" : "timeout",
            "default" : 8,
            "help" : "SSH connect timeout in seconds, default is 8."
        },
    },
]

def add_ssh_options(parser):
    """
    Add the '--host', '--timeout' and other SSH-related options to argument parser object 'parser'.
    """

    for opt in SSH_OPTIONS:
        arg = parser.add_argument(opt["short"], opt["long"], **opt["kwargs"])
        if opt["argcomplete"] and argcomplete:
            setattr(arg, "completer", getattr(argcomplete.completers, opt["argcomplete"]))

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
        text = "Be quiet."
        self.add_argument("-q", dest="quiet", action="store_true", help=text)
        text = "Print debugging information."
        self.add_argument("-d", dest="debug", action="store_true", help=text)
        if version:
            text = "Print version and exit."
            self.add_argument("--version", action="version", help=text, version=version)

    def parse_args(self, *args, **kwargs): # pylint: disable=signature-differs
        """Verify that '-d' and '-q' are not used at the same time."""

        args = super().parse_args(*args, **kwargs)

        if args.quiet and args.debug:
            raise Error("-q and -d cannot be used together")

        return args

    def add_subparsers(self, *args, **kwargs):
        """
        Create and return the subparsers action object with a customized 'add_parser()' method.
        Refer to '_add_parser()' for details.
        """

        subparsers = super().add_subparsers(*args, **kwargs)
        setattr(subparsers, "__orig_add_parser", subparsers.add_parser)
        subparsers.add_parser = types.MethodType(_add_parser, subparsers)

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

class SSHOptsAwareArgsParser(ArgsParser):
    """
    This class defines a parser that improves SSH options (see 'SSH_OPTIONS') handling by allowing
    them to be used before and after sub-commands. Here is the usage scenario. A command has
    sub-commands, and some of them support SSH options. For example, "toolname info -H my_host". But
    it is convenient that the following works as well: "toolname -H my_host info". This class makes
    makes it possible.
    """

    def parse_args(self, args=None, **kwargs): # pylint: disable=signature-differs, arguments-differ
        """
        Re-structure the input arguments ('args') so that SSH options always go after the
        subcommand.
        """

        if args is None:
            args = sys.argv[1:]
        else:
            args = list(args)

        ssh_opts = set()
        for opt in SSH_OPTIONS:
            if "short" in opt:
                ssh_opts.add(opt["short"])
            if "long" in opt:
                ssh_opts.add(opt["long"])

        ssh_arg_idx = -1
        ssh_args = []
        non_ssh_args = []
        # Find SSH and non-SSH arguments before sub-command and save them in separate lists.
        for idx, arg in enumerate(args):
            if arg in ssh_opts:
                ssh_arg_idx = idx + 1
                ssh_args.append(arg)
                continue
            # We assume that every SSH option has an argument.
            if ssh_arg_idx == idx:
                ssh_args.append(arg)
                continue

            non_ssh_args.append(arg)

        args_new = non_ssh_args + ssh_args
        return super().parse_args(args=args_new, **kwargs)
