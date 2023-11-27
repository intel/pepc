# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "aspm" 'pepc' command implementation.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import ASPM

_LOG = logging.getLogger()

def aspm_info_command(args, pman):
    """Implements the 'aspm info' command."""

    opt = []
    if hasattr(args, "oargs"):
        opt = args.oargs

    with ASPM.ASPM(pman=pman) as aspm:
        if "policy" in opt or not opt:
            cur_policy = aspm.get_policy()
            _LOG.info("ASPM policy: %s", cur_policy)
        if "policies" in opt or not opt:
            available_policies = ", ".join(aspm.get_policies())
            _LOG.info("Available policies: %s", available_policies)

def _handle_policy_option(pman, aspm, name):
    """Handle the '--policy' option of the "config" command."""

    cur_policy = aspm.get_policy()
    if name:
        aspm.set_policy(name)
        new_policy = aspm.get_policy()
        if name != new_policy:
            raise Error(f"ASPM policy{pman.hostmsg} was set to '{name}', but it became "
                        f"'{new_policy}' instead")
        if name != cur_policy:
            _LOG.info("ASPM policy%s was changed from '%s' to '%s'", pman.hostmsg, cur_policy, name)
        else:
            _LOG.info("ASPM policy%s was '%s', set it to '%s' again", pman.hostmsg, name, name)
    else:
        _LOG.info("ASPM policy%s: %s", pman.hostmsg, cur_policy)

def aspm_config_command(args, pman):
    """Implements the 'aspm config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    with ASPM.ASPM(pman=pman) as aspm:
        opts = getattr(args, "oargs", {})
        if "policy" in opts:
            name = opts["policy"]
            _handle_policy_option(pman, aspm, name)
