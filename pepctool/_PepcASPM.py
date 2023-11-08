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
        if "l1_aspm" in opt or args.device:
            if args.device:
                state = "enabled" if aspm.read_l1_aspm_state(args.device) else "disabled"
                _LOG.info("L1 ASPM is %s for the '%s' device", state, args.device)
            else:
                raise Error("please, provide a valid PCI device using the '--device' option")
            if args.device and not opt:
                return
        if "policy" in opt or not opt:
            cur_policy = aspm.get_policy()
            _LOG.info("ASPM policy: %s", cur_policy)
        if "policies" in opt or not opt:
            available_policies = ", ".join(aspm.get_policies())
            _LOG.info("Available policies: %s", available_policies)

def _handle_policy_option(pman, aspm, name, args):
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

def _handle_1l_aspm_options(pman, aspm, name, args):
    """Handle the '--li-aspm' option for the "config" command."""

    device = args.device
    if device and not name:
        state = "enabled" if aspm.read_l1_aspm_state(device) else "disabled"
        _LOG.info("L1 ASPM is %s for the '%s' device", state, device)
    elif device:
        aspm.write_l1_aspm_state(device, name)
        _LOG.info("Changed L1 ASPM to '%s'%s succeeded for the '%s' device",
                  name, pman.hostmsg, device)
    else:
        raise Error("please, provide a valid PCI device, using the '--device' option")

def aspm_config_command(args, pman):
    """Implements the 'aspm config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    with ASPM.ASPM(pman=pman) as aspm:
        opts = getattr(args, "oargs", {})
        if "policy" in opts:
            name = opts["policy"]
            _handle_policy_option(pman, aspm, name, args)
        if "l1_aspm" in opts:
            name = opts["l1_aspm"]
            _handle_1l_aspm_options(pman, aspm, name, args)
