# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide python API to the systemctl tool.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Iterable, Literal
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    _UnitActions = Literal["start", "stop", "restart"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class Systemctl(ClassHelpers.SimpleCloseContext):
    """Provide python API to the systemctl tool."""

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. Use a local process
                  manager if not provided.
        """

        self._close_pman = pman is None

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        path = self._pman.which("systemctl", must_find=True)
        self._systemctl_path: Path = cast(Path, path)

        self._saved_timers: list[str] = []
        self._saved_ntp_services: list[str] = []
        self._saved_units: dict[str, str] = {}

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_pman",))

    def _run_action(self, units: str | Iterable[str], action: _UnitActions, save: bool = False):
        """
        Run a specified action on one or more systemd units.

        Args:
            units: A single systemd unit name or an iterable of unit names to run the action on.
            action: The action to ron on the unit(s), such as 'start', 'stop', or 'restart'.
            save: Whether to save the action run for each unit.
        """

        unit_names: Iterable[str]
        if not Trivial.is_iterable(units):
            if typing.TYPE_CHECKING:
                unit_names = cast(Iterable[str], [units])
            else:
                unit_names = [units]
        else:
            unit_names = units

        for unit in unit_names:
            self._pman.run_verify(f"{self._systemctl_path} {action} -- '{unit}'")

            started = action in ("start", "restart")
            if self.is_active(unit) == started:
                if save:
                    if unit not in self._saved_units:
                        self._saved_units[unit] = action
                    elif self._saved_units[unit] != action:
                        _LOG.warning("Systemd unit '%s' state is already saved as '%s'",
                                     unit, self._saved_units[unit])
                continue

            # The error path: unit state did not change.
            status = ""
            try:
                status, _ = self._pman.run_verify_join(f"{self._systemctl_path} status -- '{unit}'")
            except Error:
                pass

            msg = f"Failed to {action} systemd unit '{unit}'"
            if status:
                msg += f", current status:\n{status}"
            raise Error(msg)

    def start(self, units: str | Iterable[str], save: bool = False):
        """
        Start one or more systemd units.

        Args:
            units: Name or collection of names of systemd units to start.
            save: If True, save the current units state for later restoration via the 'restore()'
                  method.
        """

        self._run_action(units, "start", save=save)

    def stop(self, units: str | Iterable[str], save: bool = False):
        """
        Stop one or more systemd units.

        Args:
            units: Name or collection of names of systemd units to stop.
            save: If True, save the current units state for later restoration via the 'restore()'
                  method.
        """

        self._run_action(units, "stop", save=save)

    def restart(self, units: str | Iterable[str]):
        """
        Restart one or more systemd units.

        Args:
            units: Name or collection of names of systemd units to restart.
        """

        self._run_action(units, "restart", save=False)

    def restore(self):
        """
        Restore the previously saved state of systemd units.
        """

        if not self._saved_units:
            _LOG.debug("Nothing to restore")
            return

        for unit, action in self._saved_units.items():
            if action == "stop":
                self.start(unit)
            else:
                self.stop(unit)

    def _is_in_state(self, unit: str, what: str) -> bool:
        """
        Check if a systemd unit matches a specific state.

        Args:
            unit: Name of the systemd unit to check.
            what: The state to check for (e.g., 'active', 'failed').

        Returns:
            True if the unit's state matches the specified state, False otherwise.
        """

        output, _, _ = self._pman.run(f"{self._systemctl_path} is-{what} -- '{unit}'")
        output = cast(str, output).strip()

        return output == what

    def is_active(self, unit: str) -> bool:
        """
        Check if a systemd unit is currently active.

        Args:
            unit: Name of the systemd unit to check.

        Returns:
            True if the unit is active (started), False otherwise.
        """

        return self._is_in_state(unit, "active")

    def is_failed(self, unit: str) -> bool:
        """
        Check if a systemd unit is currently in the failed state.

        Args:
            unit: Name of the systemd unit to check.

        Returns:
            True if the unit is in the failed state, False otherwise.
        """

        return self._is_in_state(unit, "failed")

    def stop_ntp(self) -> list[str]:
        """
        Stop NTP services and return the list of stopped services names. The services can later be
        re-started with 'restore_ntp()'.

        Returns:
            List of names of NTP services that were stopped.
        """

        services = ("ntpd", "ntpdate", "sntp", "systemd-timesyncd", "chronyd")
        self._saved_ntp_services = []

        for service in services:
            if self.is_active(service):
                self.stop(service)
                self._saved_ntp_services.append(service)

        return self._saved_ntp_services

    def restore_ntp(self) -> list[str]:
        """
        Restore NTP services to their previous state before 'stop_ntp()' was called.

        Returns:
            List of restored NTP service names, or an empty list if no services were saved.
        """

        if self._saved_ntp_services:
            self.start(self._saved_ntp_services)

        restored_ntp_services = self._saved_ntp_services
        self._saved_ntp_services = []
        return restored_ntp_services

    def stop_timers(self) -> list[str]:
        """
        Stop all systemd timers. The timers can later be re-started with 'restore_timers()'.

        Returns:
            List of timer names that were stopped.
        """

        cmd = f"{self._systemctl_path} list-timers"
        timers = []
        for part in self._pman.run_verify_join(cmd)[0].split():
            if part.endswith(".timer"):
                timers.append(part)
        if timers:
            self.stop(timers)

        self._saved_timers = timers
        return timers

    def restore_timers(self) -> list[str]:
        """
        Restore systemd timers to their previous state before 'stop_timers()' was called.

        Returns:
            List of restored timer names, or an empty list if no timers were saved.
        """

        if self._saved_timers:
            self.start(self._saved_timers)
        saved_timers = self._saved_timers
        self._saved_timers = []
        return saved_timers
