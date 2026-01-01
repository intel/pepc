# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This module contains helper functions for test runners."""

# TODO: annotate and modernize this module.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import typing
from pepclibs.helperlibs import Logging

if typing.TYPE_CHECKING:
    from types import ModuleType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def run_tool(tool: ModuleType,
             toolname: str,
             arguments: str,
             pman: ProcessManagerType | None = None,
             exp_exc: type[Exception] | None = None,
             ignore: dict[type[Exception], str] | None = None):
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
    _LOG.debug("Running: %s", cmd)
    sys.argv = cmd.split()
    try:
        ret = tool.do_main(pman=pman)
    except Exception as err: # pylint: disable=broad-except
        err_type = type(err)
        msg = f"Command '{toolname} {arguments}' raised the following exception:\n" \
              f"- {type(err).__name__}({err})"
        if err_type in ignore and (not ignore[err_type] or ignore[err_type] in arguments):
            _LOG.debug(msg)
            return None

        if exp_exc is None:
            assert False, msg

        if isinstance(err, exp_exc):
            return None

        assert False, f"Command '{toolname} {arguments}' raised the following exception:\n" \
                      f"- {type(err).__name__}({err})\nbut it was expected to raise the following" \
                      f"exception:\n- {exp_exc.__name__}"

    if exp_exc is not None:
        assert False, f"Command '{toolname} {arguments}' did not raise the following " \
                      f"exception type:\n- {exp_exc.__name__}"

    return ret
