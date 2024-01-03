# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This module contains helper functions for test runners."""

import logging
import sys

logging.basicConfig(level=logging.DEBUG)
_LOG = logging.getLogger()

def run_tool(tool, toolname, arguments, pman=None, exp_exc=None, ignore=None):
    """
    Run pepc command and verify the outcome. The arguments are as follows.
    * tool - the main Python module of the tool to run.
    * toolname - the name of the tool to run, used in error messages.
    * arguments - the arguments to run the command with, e.g. 'pstate info --cpus 0-43'.
    * pman - optionally provide a process manager object to pass to the tool and tell it which host
             to run the tests on.
    * exp_exc - the expected exception, by default, any exception is considered to be a failure.
                But when set if the command did not raise the expected exception then the test is
                considered to be a failure.
    * ignore - a map of error type and command argument strings to look for in case of errors.
               Ignore matching exceptions.
    """

    if not ignore:
        ignore = {}

    cmd = f"{tool.__file__} {arguments}"
    _LOG.debug("running: %s", cmd)
    sys.argv = cmd.split()
    try:
        args = tool.parse_arguments()
        if pman:
            ret = args.func(args, pman)
        else:
            ret = args.func(args)
    except Exception as err: # pylint: disable=broad-except
        if exp_exc is None:
            err_type = type(err)
            msg = f"command '{toolname} {arguments}' raised the following exception:\n" \
                  f"- {type(err).__name__}({err})"
            if err_type in ignore and (ignore[err_type] is None or ignore[err_type] in arguments):
                _LOG.debug(msg)
                return None
            assert False, msg

        if isinstance(err, exp_exc):
            return None

        assert False, f"command '{toolname} {arguments}' raised the following exception:\n" \
                      f"- {type(err).__name__}({err})\nbut it was expected to raise the following" \
                      f"exception:\n- {exp_exc.__name__}"

    if exp_exc is not None:
        assert False, f"command '{toolname} {arguments}' did not raise the following " \
                      f"exception type:\n- {exp_exc.__name__}"

    return ret
