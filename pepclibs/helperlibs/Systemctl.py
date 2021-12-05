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

from pepclibs.helperlibs import FSHelpers, Procs, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

class Systemctl:
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
            self._proc.run_verify(f"systemctl {action} -- '{unit}'")
            if self.is_active(unit) != start:
                status = None
                try:
                    status, _ = self._proc.run_verify(f"systemctl status -- '{unit}'")
                except Error:
                    pass

                msg = f"failed to {action} systemd unit '{unit}'"
                if status:
                    msg += f", here is its current status:\n{status}"
                raise Error(msg)

    def _is_smth(self, unit, what):
        """Check if a unit is active/failed or not."""

        output, _, _ = self._proc.run(f"systemctl is-{what} -- '{unit}'")
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
        timers = [part for part in self._proc.run_verify(cmd)[0].split() if part.endswith(".timer")]
        if timers:
            self._start(timers, False)

        self._saved_timers = timers
        return timers

    def restore_timers(self):
        """Restore systemd timers to the state they had been before 'stop_timers()' was called."""

        if self._saved_timers:
            self._start(self._saved_timers, True)
        self._saved_timers = None

    def __init__(self, proc=None):
        """
        Initialize a class instance for the host associated with the 'proc' object. By default it is
        going to be the local host, but 'proc' can be used to pass a connected 'SSH' object, in
        which case all operation will be done on the remote host. This object will keep a 'proc'
        reference and use it in various methods.
       """

        if not proc:
            proc = Procs.Proc()

        self._proc = proc
        self._saved_timers = None
        self._saved_ntp_services = None

        if not FSHelpers.which("systemctl", default=None, proc=proc):
            raise ErrorNotSupported(f"the 'systemctl' tool is not installed{proc.hostmsg}")

    def close(self):
        """Uninitialize the class object."""
        if getattr(self, "_proc", None):
            self._proc = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
