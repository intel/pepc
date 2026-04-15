# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Implement the 'pepc cpu-hotplug' command.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo, CPUOnline
from pepctools import _OpTarget

if typing.TYPE_CHECKING:
    import argparse
    from typing import Literal, TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class _OnlineCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc cpu-hotplug online' command.

        Attributes:
            cpus: CPU numbers to online, or 'None' if not specified.
        """

        cpus: str | None

    class _OfflineCmdlineArgsTypedDict(TypedDict, total=False):
        """
        A typed dictionary for command-line arguments of the 'pepc cpu-hotplug offline' command.

        Attributes:
            cpus: CPU numbers to offline, or 'None' if not specified.
            cores: Core numbers to offline, or 'None' if not specified.
            modules: Module numbers to offline, or 'None' if not specified.
            dies: Die numbers to offline, or 'None' if not specified.
            packages: Package numbers to offline, or 'None' if not specified.
            core_siblings: Core sibling indices to offline, or 'None' if not specified.
            module_siblings: Module sibling indices to offline, or 'None' if not specified.
        """

        cpus: str | None
        cores: str | None
        modules: str | None
        dies: str | None
        packages: str | None
        core_siblings: str | None
        module_siblings: str | None

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _get_online_cmdline_args(args: argparse.Namespace) -> _OnlineCmdlineArgsTypedDict:
    """
    Format 'pepc cpu-hotplug online' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _OnlineCmdlineArgsTypedDict = {}
    cmdl["cpus"] = getattr(args, "cpus", None)

    return cmdl

def _get_offline_cmdline_args(args: argparse.Namespace) -> _OfflineCmdlineArgsTypedDict:
    """
    Format 'pepc cpu-hotplug offline' command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _OfflineCmdlineArgsTypedDict = {}
    cmdl["cpus"] = getattr(args, "cpus", None)
    cmdl["cores"] = getattr(args, "cores", None)
    cmdl["modules"] = getattr(args, "modules", None)
    cmdl["dies"] = getattr(args, "dies", None)
    cmdl["packages"] = getattr(args, "packages", None)
    cmdl["core_siblings"] = getattr(args, "core_siblings", None)
    cmdl["module_siblings"] = getattr(args, "module_siblings", None)

    return cmdl

def cpu_hotplug_info_command(_: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pepc cpu-hotplug info' command.

    Args:
        _: Parsed command-line arguments (unused).
        pman: Process manager object for the target host.
    """

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        for func, word in (("get_cpus", "online"), ("get_offline_cpus", "offline")):
            cpus = getattr(cpuinfo, func)()
            if cpus:
                _LOG.info("The following CPUs are %s%s: %s",
                          word, pman.hostmsg, Trivial.rangify(cpus))
            else:
                _LOG.info("No %s CPUs%s", word, pman.hostmsg)

def cpu_hotplug_online_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pepc cpu-hotplug online' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_online_cmdline_args(args)

    cpus_str = cmdl.get("cpus")
    if not cpus_str:
        raise Error("Please, specify the CPUs to online")

    cpus: list[int] | Literal["all"]
    if cpus_str == "all":
        cpus = "all"
    else:
        cpus = Trivial.parse_int_list(cpus_str, dedup=True, what="CPU numbers")

    with CPUOnline.CPUOnline(loglevel=Logging.INFO, pman=pman) as onl:
        onl.online(cpus=cpus)

def cpu_hotplug_offline_command(args: argparse.Namespace, pman: ProcessManagerType):
    """
    Implement the 'pepc cpu-hotplug offline' command.

    Args:
        args: Parsed command-line arguments.
        pman: Process manager object for the target host.
    """

    cmdl = _get_offline_cmdline_args(args)

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(loglevel=Logging.INFO, pman=pman, cpuinfo=cpuinfo) as onl:

        # Some CPUs may not support offlining. Suppose it is CPU 0. If CPU 0 is in the 'cpus' list,
        # 'onl.offline()' will error out. This is expected when the user explicitly specified CPU 0
        # (e.g., via '--cpus 0'), but not when CPU 0 was included indirectly via '--cpus all' or
        # '--packages 0'.
        skip_unsupported = cmdl.get("cpus") in ("all", None)

        optar = _OpTarget.OpTarget(pman=pman, cpuinfo=cpuinfo,
                                   cpus=cmdl.get("cpus") or (),
                                   cores=cmdl.get("cores") or (),
                                   modules=cmdl.get("modules") or (),
                                   dies=cmdl.get("dies") or (),
                                   packages=cmdl.get("packages") or (),
                                   core_siblings=cmdl.get("core_siblings") or (),
                                   module_siblings=cmdl.get("module_siblings") or ())

        onl.offline(cpus=optar.get_cpus(), skip_unsupported=skip_unsupported)
