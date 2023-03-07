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

def run_tool(tool, arguments, pman, exp_exc=None, warn_only=None):
    """
    Run pepc command and verify the outcome. The arguments are as follows.
    * tool - the main Python module of the tool to run.
    * arguments - the arguments to run the command with, e.g. 'pstate info --cpus 0-43'.
    * pman - the process manager object that defines the host to run the measurements on.
    * exp_exc - the expected exception, by default, any exception is considered to be a failure.
                But when set if the command did not raise the expected exception then the test is
                considered to be a failure.
    * warn_only - a map of error type and command argument strings to look for in case of error. For
                  matching exceptions print warning instead of asserting.
    """

    if not warn_only:
        warn_only = {}

    cmd = f"{tool.__file__} {arguments}"
    _LOG.debug("running: %s", cmd)
    sys.argv = cmd.split()
    try:
        args = tool.parse_arguments()
        ret = args.func(args, pman)
    except Exception as err: # pylint: disable=broad-except
        if exp_exc is None:
            err_type = type(err)
            errmsg = f"command '{tool.TOOLNAME} {arguments}' raised the following exception:\n" \
                     f"- {type(err).__name__}({err})"

            if pman.is_remote and err_type in warn_only and warn_only[err_type] in arguments:
                _LOG.warning(errmsg)
                return None

            assert False, errmsg

        if isinstance(err, exp_exc):
            return None

        assert False, f"command '{tool.TOOLNAME} {arguments}' raised the following exception:\n" \
                      f"- {type(err).__name__}({err})\nbut it was expected to raise the following" \
                      f"exception:\n- {exp_exc.__name__}"

    if exp_exc is not None:
        assert False, f"command '{tool.TOOLNAME} {arguments}' did not raise the following " \
                      f"exception type:\n- {exp_exc.__name__}"

    return ret
