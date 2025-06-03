# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide API for onlining and offlining CPUs.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import Iterable, Literal
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs import CPUInfo

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUOnline(ClassHelpers.SimpleCloseContext):
    """
    Provides API for onlining and offlining CPUs.
    """

    def __init__(self,
                 loglevel: int | None = None,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None):
        """
        Initialize a class instance.

        Args:
            progress: Set logging level for progress messages. Defaults to 'DEBUG'.
            pman: The process manager object for the host to online/offline CPUs. If not provided,
                  a 'LocalProcessManager.LocalProcessManager()' object is created.
            cpuinfo: An instance of 'CPUInfo.CPUInfo()' to use. If not provided, a new instance is
                     created.
        """

        if loglevel is None:
            self._loglevel = Logging.DEBUG
        else:
            self._loglevel = loglevel

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_cpuinfo", "_pman",))

    def _get_cpuinfo(self) -> CPUInfo.CPUInfo:
        """
        Return a 'CPUInfo' object.

        Returns:
            CPUInfo: A 'CPUInfo' object describing the target host CPU.
        """

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        return self._cpuinfo

    def _verify_path(self, cpu: int, path: Path):
        """
        Check if the 'online' sysfs path exists for the given CPU.

        Args:
            cpu: The CPU number to verify the path for.
            path: Path to the 'online' sysfs file for the CPU.

        Raises:
            ErrorNotSupported: If the path does not exist, which means that the CPU does not support
                               onlining/offlining.
        """

        if not self._pman.is_file(path):
            if self._pman.is_dir(path.parent):
                raise ErrorNotSupported(f"CPU {cpu} does not support onlining/offlining"
                                        f"{self._pman.hostmsg}")
            raise Error(f"CPU {cpu} does not exist{self._pman.hostmsg}")

    def _validate_hotplugged_cpus(self, cpus: list[int], state: bool):
        """
        Validate that the specified CPUs are in the expected online or offline state.

        Args:
            cpus: List of CPU numbers to validate.
            state: The expected state of the CPUs: True for online, False for offline.
        """

        cpuinfo = self._get_cpuinfo()

        if state:
            valid = set(cpuinfo.get_cpus())
        else:
            valid = set(cpuinfo.get_offline_cpus())

        for cpu in cpus:
            if cpu not in valid:
                state_str = "online" if state else "offline"
                raise Error(f"Failed to {state_str} CPU{cpu}")

    def _get_online(self, path: Path) -> str:
        """
        Read the 'online' sysfs file at the given path.

        Args:
            path: Path to the 'online' sysfs file.

        Returns:
            The online state as a string ("0" or "1").
        """

        with self._pman.open(path, "r") as fobj:
            state = fobj.read().strip()

        if state in ("0", "1"):
            return state

        raise Error(f"Unexpected value '{state}' in '{path}'{self._pman.hostmsg}")

    def _get_path(self, cpu: int) -> Path:
        """
        Construct and return the sysfs path to the 'online' file for the specified CPU.

        Args:
            cpu: CPU number for which to build the sysfs path.

        Returns:
            Path to the 'online' sysfs file for the given CPU.
        """

        return self._sysfs_base / f"cpu{cpu}" / "online"

    def _toggle(self, cpus: Iterable[int] | Literal["all"], online: bool, skip_unsupported: bool):
        """
        Toggle the online or offline state of specified CPUs.

        Args:
            cpus: CPU numbers to toggle. Special value 'all' means "all CPUs".
            online: If True, bring CPUs online; if False, take CPUs offline.
            skip_unsupported: If True, skip CPUs that do not support hotplugging.

        Raises:
            ErrorNotSupported: If a CPU does not support hotplugging and skip_unsupported is False.
        """

        cpuinfo = self._get_cpuinfo()
        cpuinfo.cpus_hotplugged()

        if online:
            data = "1"
            state_str = "online"
            action_str = "Onlining"
            ready_cpus = set(cpuinfo.get_cpus())
        else:
            data = "0"
            state_str = "offline"
            action_str = "Offlining"
            ready_cpus = set(cpuinfo.get_offline_cpus())

        if cpus == "all":
            skip_unsupported = True
            if online:
                cpus = cpuinfo.get_offline_cpus()
            else:
                cpus = cpuinfo.get_cpus()

            if not cpus:
                _LOG.log(self._loglevel, "All CPUs are already %s", state_str)
                return
        else:
            cpus = cpuinfo.normalize_cpus(cpus, offline_ok=True)

        _LOG.debug("CPUs to %s: %s", state_str, ", ".join([str(cpu) for cpu in cpus]))

        toggled = []
        for cpu in cpus:
            if cpu in ready_cpus:
                _LOG.log(self._loglevel, "CPU%d is already %s, skipping", cpu, state_str)
                continue

            path = self._get_path(cpu)
            try:
                self._verify_path(cpu, path)
            except ErrorNotSupported as err:
                if not skip_unsupported:
                    raise
                _LOG.info(err)
                continue

            _LOG.log(self._loglevel, "%s CPU%d", action_str, cpu)

            try:
                with self._pman.open(path, "r+") as fobj:
                    fobj.write(data)
            except Error as err:
                raise Error(f"Failed to {state_str} CPU{cpu}:\n{err.indent(2)}") from err
            toggled.append(cpu)

        if toggled:
            cpuinfo.cpus_hotplugged()
            self._validate_hotplugged_cpus(toggled, online)

    def online(self, cpus: Iterable[int] | Literal["all"] = "all", skip_unsupported: bool = False):
        """
        Bring the specified CPUs online.

        Args:
            cpus: CPU numbers to bring online. Special value 'all' means "all CPUs".
            skip_unsupported: Skip CPUs that do not support onlining if True; otherwise, raise an
                              exception.

        Raises:
            ErrorNotSupported: If a CPU does not support onlining/offlining and 'skip_unsupported'
                               is False.
        """

        self._toggle(cpus, True, skip_unsupported)

    def offline(self, cpus: Iterable[int] | Literal["all"] = "all", skip_unsupported: bool = False):
        """
        Set specified CPUs offline.

        Args:
            cpus: CPU numbers to set offline. Special value 'all' means "all CPUs".
            skip_unsupported: Skip CPUs that do not support onlining if True; otherwise, raise an
                              exception.

        Raises:
            Exception: If a CPU does not support onlining/offlining and 'skip_unsupported'
                       is False.
        """

        self._toggle(cpus, False, skip_unsupported)

    def is_online(self, cpu: int) -> bool:
        """
        Check if the specified CPU is online.

        Args:
            cpu: CPU number to check.

        Returns:
            True if the CPU is online, False otherwise.

        Raises:
            ErrorNotFound: If the CPU path does not exist and is not due to hotplug being disabled.

        Note:
            If the hotplug subsystem is disabled and the "online" file is missing, assume the CPU is
            online.
        """

        path = self._get_path(cpu)
        try:
            return self._get_online(path) == "1"
        except ErrorNotFound:
            if not self._pman.is_dir(path.parent):
                raise
            # Hotplug sub-system might be disabled, in that case there is no "online" file and the
            # CPU is online.
            return True
