# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides python API to the systemctl tool.
"""

from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class Systemctl(ClassHelpers.SimpleCloseContext):
    """This module provides python API to the systemctl tool."""

    def _run_action(self, units, action, save=False):
        """Run action 'action' for systemd unit 'units'."""

        if not Trivial.is_iterable(units):
            units = [units]

        for unit in units:
            self._pman.run_verify(f"{self._systemctl_path} {action} -- '{unit}'")

            started = action in ("start", "restart")
            if self.is_active(unit) == started:
                if save:
                    if unit not in self._saved_units:
                        self._saved_units[unit] = action
                    elif self._saved_units[unit] != action:
                        _LOG.warning("systemd unit '%s' state is already saved as '%s'",
                                     unit, self._saved_units[unit])
                continue

            # The error path: unit state did not change.
            status = None
            try:
                status, _ = self._pman.run_verify_join(f"{self._systemctl_path} status -- '{unit}'")
            except Error:
                pass

            msg = f"failed to {action} systemd unit '{unit}'"
            if status:
                msg += f", here is its current status:\n{status}"

            raise Error(msg)

    def _is_smth(self, unit, what):
        """Check if a unit is active/failed or not."""

        output, _, _ = self._pman.run(f"{self._systemctl_path} is-{what} -- '{unit}'")
        output = output.strip()
        return output == what

    def start(self, units, save=False):
        """
        Start systemd unit(s). The arguments are as follows.
          * units - unit name or a collection of unit names to start.
          * save - if 'True', save the process state and restore it in the 'restore()' method.
        """

        self._run_action(units, "start", save=save)

    def stop(self, units, save=False):
        """
        Stop systemd unit(s). The arguments are as follows.
          * units - unit name or a collection of unit names to stop.
          * save - if 'True', save the process state and restore it in the 'restore()' method.
        """

        self._run_action(units, "stop", save=save)

    def restart(self, units):
        """
        Restart systemd unit(s). The arguments are as follows.
          * units - unit name or a collection of unit names to restart.
        """

        self._run_action(units, "restart", save=False)

    def restore(self):
        """Restore saved units' state."""

        if not self._saved_units:
            _LOG.debug("nothing to restore")
            return

        for unit, action in self._saved_units.items():
            if action == "stop":
                self.start(unit)
            else:
                self.stop(unit)

    def is_active(self, unit):
        """Returns 'True' if a systemd 'unit' is active (started) and 'False' otherwise."""
        return self._is_smth(unit, "active")

    def is_failed(self, unit):
        """Returns 'True' if a systemd 'unit' is in the "failed" state and 'False' otherwise."""
        return self._is_smth(unit, "failed")

    def stop_ntp(self):
        """
        Stop NPT services and return the list of stopped services' names. The services can later be
        re-enabled with 'restore_ntp()'.
        """

        services = ("ntpd", "ntpdate", "sntp", "systemd-timesyncd", "chronyd")
        self._saved_ntp_services = []

        for service in services:
            if self.is_active(service):
                self.stop(service)
                self._saved_ntp_services.append(service)

        return self._saved_ntp_services

    def restore_ntp(self):
        """
        Restore NTP services to the state they had been before 'stop_ntp()' was called. Returns the
        list of restored services' names.
        """

        if self._saved_ntp_services:
            self.start(self._saved_ntp_services)

        restored_ntp_services = self._saved_ntp_services
        self._saved_ntp_services = None
        return restored_ntp_services

    def stop_timers(self):
        """
        Stop all systemd timers. The timers can later be re-started with 'restore_timers()'. Returns
        the list of timers that were stopped.
        """

        cmd = f"{self._systemctl_path} list-timers"
        timers = []
        for part in self._pman.run_verify_nojoin(cmd)[0].split():
            if part.endswith(".timer"):
                timers.append(part)
        if timers:
            self.stop(timers)

        self._saved_timers = timers
        return timers

    def restore_timers(self):
        """Restore systemd timers to the state they had been before 'stop_timers()' was called."""

        if self._saved_timers:
            self.start(self._saved_timers)
        self._saved_timers = None

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
       """

        self._pman = pman
        self._close_pman = pman is None
        self._systemctl_path = None

        self._saved_timers = None
        self._saved_ntp_services = None
        self._saved_units = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        self._systemctl_path = self._pman.which("systemctl")

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
