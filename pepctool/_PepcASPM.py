# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc aspm' command.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import ASPM

_LOG = logging.getLogger()

def _print_l1_aspm_state(args, aspm):
    """
    Print the L1 ASPM status for the device specified via the '--device' option.
    """

    state = "enabled" if aspm.is_l1_aspm_enabled(args.device) else "disabled"
    _LOG.info("L1 ASPM: %s for device '%s'", state, args.device)

def aspm_info_command(args, pman):
    """
    Implement the 'aspm info' command. The arguments are as follows.
      * args - the command line arguments.
      * pman - the process manager object that defines the host to get ASPM info for.
    """

    opt = []
    if hasattr(args, "oargs"):
        opt = args.oargs

    with ASPM.ASPM(pman=pman) as aspm:
        if "l1_aspm" in opt or args.device:
            if args.device:
                _print_l1_aspm_state(args, aspm)
            else:
                raise Error("please, provide a valid PCI device using the '--device' option")

        if "policy" in opt or not opt:
            cur_policy = aspm.get_policy()
            _LOG.info("ASPM policy: %s", cur_policy)

        if "policies" in opt or not opt:
            available_policies = ", ".join(aspm.get_policies())
            _LOG.info("Available policies: %s", available_policies)

def _handle_policy_option(args, aspm, pman, name):
    """Handle the '--policy' option of the "config" command."""

    opts = getattr(args, "oargs", {})
    opts_copy = opts.copy()
    opts_copy.pop("policy")

    if args.device and not bool(opts_copy):
        raise Error("'--device' option is not applicable to the --policy option")

    cur_policy = aspm.get_policy()
    if name:
        aspm.set_policy(name)
        new_policy = aspm.get_policy()
        if name != new_policy:
            raise Error(f"ASPM policy{pman.hostmsg} was set to '{name}', but it became "
                        f"'{new_policy}' instead")
        if name != cur_policy:
            _LOG.info("Changed ASPM policy from '%s' to '%s'%s", cur_policy, name, pman.hostmsg)
        else:
            _LOG.info("ASPM policy was '%s', set it to '%s' again%s", name, name, pman.hostmsg)
    else:
        _LOG.info("ASPM policy: '%s'%s", cur_policy, pman.hostmsg)

def _handle_1l_aspm_options(args, aspm, pman, state):
    """Handle the '--l1-aspm' option for the "config" command."""

    device = args.device
    if not device:
        raise Error("please, provide a valid PCI device using the '--device' option")

    if not state:
        _print_l1_aspm_state(args, aspm)
        return

    state = state.lower()
    valid_vals = ["false", "true", "off", "on", "disable", "enable"]
    if state not in valid_vals:
        valid_vals = ", ".join(valid_vals)
        raise Error(f"bad L1 ASPM state value '{state}', use one of: {valid_vals}")

    enable = state in ["true", "on", "enable"]
    aspm.toggle_l1_aspm_state(device, enable)
    _LOG.info("Changed L1 ASPM to '%s'%s for device '%s'", state, pman.hostmsg, device)

def aspm_config_command(args, pman):
    """
    Implement the 'aspm config' command. The arguments are as follows.
      * args - the command line arguments.
      * pman - the process manager object that defines the host to configure ASPM info for.
    """

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    with ASPM.ASPM(pman=pman) as aspm:
        opts = getattr(args, "oargs", {})
        if "policy" in opts:
            _handle_policy_option(args, aspm, pman, opts["policy"])
        if "l1_aspm" in opts:
            _handle_1l_aspm_options(args, aspm, pman, opts["l1_aspm"])
