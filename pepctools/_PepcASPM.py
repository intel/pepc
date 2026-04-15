# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc aspm' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import ASPM

if typing.TYPE_CHECKING:
    import argparse
    from typing import TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _CmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc aspm info' and 'pepc aspm
        config' commands.

        Attributes:
            device: PCI device address (e.g., '0000:00:02.0'), or 'None' if not specified.
            oargs: Ordered command-line arguments dictionary. Keys are option names, values are
                   the option values, or 'None' for options that take no value.
        """

        device: str | None
        oargs: dict[str, str | None]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format 'pepc aspm' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _CmdlineArgsTypedDict = {}
    cmdl["device"] = getattr(args, "device", None)
    cmdl["oargs"] = getattr(args, "oargs", {})

    return cmdl

def _print_l1_state(device: str, aspm: ASPM.ASPM):
    """
    Print the L1 ASPM status for the specified PCI device.

    Args:
        device: PCI device address.
        aspm: ASPM object.
    """

    state = "enabled" if aspm.is_l1_enabled(device) else "disabled"
    _LOG.info("L1 ASPM: %s for device '%s'", state, device)

def _handle_policy_option(cmdl: _CmdlineArgsTypedDict,
                          aspm: ASPM.ASPM,
                          pman: ProcessManagerType,
                          name: str | None):
    """
    Handle the '--policy' option of the 'pepc aspm config' command.

    Args:
        cmdl: Parsed command-line arguments dictionary.
        aspm: ASPM object.
        pman: Process manager object for the target host.
        name: Policy name to set, or 'None' to only display the current policy.
    """

    opts = cmdl.get("oargs", {})
    opts_copy = opts.copy()
    opts_copy.pop("policy", None)

    if cmdl.get("device") and not opts_copy:
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

def _handle_l1_aspm_option(cmdl: _CmdlineArgsTypedDict,
                            aspm: ASPM.ASPM,
                            pman: ProcessManagerType,
                            state: str | None):
    """
    Handle the '--l1-aspm' option of the 'pepc aspm config' command.

    Args:
        cmdl: Parsed command-line arguments dictionary.
        aspm: ASPM object.
        pman: Process manager object for the target host.
        state: L1 ASPM state to set (e.g., 'on', 'off'), or 'None' to only display the state.
    """

    device = cmdl.get("device")
    if not device:
        raise Error("Please, provide a valid PCI device using the '--device' option")

    if not state:
        _print_l1_state(device, aspm)
        return

    state = state.lower()
    valid_vals = ("false", "true", "off", "on", "disable", "enable")
    if state not in valid_vals:
        vals_str = ", ".join(valid_vals)
        raise Error(f"Bad L1 ASPM state value '{state}', use one of: {vals_str}")

    enable = state in ("true", "on", "enable")
    aspm.toggle_l1_state(device, enable)
    _LOG.info("Changed L1 ASPM to '%s'%s for device '%s'", state, pman.hostmsg, device)

def aspm_info_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pepc aspm info' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)
    oargs = cmdl.get("oargs", {})
    device = cmdl.get("device")

    with ASPM.ASPM(pman=pman) as aspm:
        if "l1_aspm" in oargs or device:
            if device:
                _print_l1_state(device, aspm)
            else:
                raise Error("Please, provide a valid PCI device using the '--device' option")

        if "policy" in oargs or not oargs:
            cur_policy = aspm.get_policy()
            _LOG.info("ASPM policy: %s", cur_policy)

        if "policies" in oargs or not oargs:
            available_policies = ", ".join(aspm.get_policies())
            _LOG.info("Available policies: %s", available_policies)

def aspm_config_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pepc aspm config' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_cmdline_args(args)
    oargs = cmdl.get("oargs", {})

    if not oargs:
        raise Error("Please, provide a configuration option")

    with ASPM.ASPM(pman=pman) as aspm:
        if "policy" in oargs:
            _handle_policy_option(cmdl, aspm, pman, oargs.get("policy"))
        if "l1_aspm" in oargs:
            _handle_l1_aspm_option(cmdl, aspm, pman, oargs.get("l1_aspm"))
