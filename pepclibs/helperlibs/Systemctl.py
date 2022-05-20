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

from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

class Systemctl(ClassHelpers.SimpleCloseContext):
    """This module provides python API to the systemctl tool."""

    def _start(self, units, start):
        """Start or stop the 'units' systemd units."""

        if start:
            action = "start"
        else:
            action = "stop"

        if not Trivial.is_iterable(units):
            units = [units]

        for unit in units:
            self._pman.run_verify(f"systemctl {action} -- '{unit}'")
            if self.is_active(unit) != start:
                status = None
                try:
                    status, _ = self._pman.run_verify(f"systemctl status -- '{unit}'")
                except Error:
                    pass

                msg = f"failed to {action} systemd unit '{unit}'"
                if status:
                    msg += f", here is its current status:\n{status}"
                raise Error(msg)

    def _is_smth(self, unit, what):
        """Check if a unit is active/failed or not."""

        output, _, _ = self._pman.run(f"systemctl is-{what} -- '{unit}'")
        output = output.strip()
        return output == what

    def start(self, units):
        """Start systemd unit(s) 'units'."""
        self._start(units, True)

    def stop(self, units):
        """Stop a systemd unit(s) 'units'."""
        self._start(units, False)

    def is_active(self, unit):
        """Returns 'True' if a systemd 'unit' is active (started) and 'False' otherwise."""
        return self._is_smth(unit, "active")

    def is_failed(self, unit):
        """Returns 'True' if a systemd 'unit' is in the "failed" state and 'False' otherwise."""
        return self._is_smth(unit, "failed")

    def stop_ntp(self):
        """Stop NPT services. The services can later be re-enabled with 'restore_ntp()'."""

        services = ("ntpd", "ntpdate", "sntp", "systemd-timesyncd", "chronyd")
        self._saved_ntp_services = []

        for service in services:
            if self.is_active(service):
                self._start(service, False)
                self._saved_ntp_services.append(service)

    def restore_ntp(self):
        """Restore NTP services to the state they had been before 'stop_ntp()' was called."""

        if self._saved_ntp_services:
            self._start(self._saved_ntp_services, True)
        self._saved_ntp_services = None

    def stop_timers(self):
        """
        Stop all systemd timers. The timers can later be re-started with 'restore_timers()'. Returns
        the list of timers that were stopped.
        """

        cmd = "systemctl list-timers"
        timers = [part for part in self._pman.run_verify(cmd)[0].split() if part.endswith(".timer")]
        if timers:
            self._start(timers, False)

        self._saved_timers = timers
        return timers

    def restore_timers(self):
        """Restore systemd timers to the state they had been before 'stop_timers()' was called."""

        if self._saved_timers:
            self._start(self._saved_timers, True)
        self._saved_timers = None

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
       """

        self._pman = pman
        self._close_pman = pman is None

        self._saved_timers = None
        self._saved_ntp_services = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))
