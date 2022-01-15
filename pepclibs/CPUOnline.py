# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides an API for onlining and offlining CPUs.
"""

import logging
from pathlib import Path
from pepclibs.helperlibs import ArgParse, FSHelpers, Procs, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

_LOG = logging.getLogger()

class CPUOnline:
    """This class provides API for onlining and offlining CPUs."""

    def _verify_path(self, cpu, path):
        """Verify if path 'path' exists."""

        if not FSHelpers.isfile(path, proc=self._proc):
            if FSHelpers.isdir(path.parent, proc=self._proc):
                msg = f"CPU '{cpu}' on host {self._proc.hostname}' does not support " \
                      f"onlining/offlining"
            else:
                msg = f"CPU '{cpu}' does not exist on host '{self._proc.hostname}'"
            raise Error(msg)

    def _get_online(self, path):
        """Read the 'online' sysfs file at 'path'."""

        with self._proc.open(path, "r") as fobj:
            state = fobj.read().strip()
        if state in ("0", "1"):
            return state
        raise Error("unexpected value '{state}' in '{path}' on host '{self._proc.hostname}'")

    def _get_path(self, cpu):
        """Build and return path to the 'online' sysfs file for CPU number 'cpu'."""

        return self._sysfs_base / f"cpu{cpu}" / "online"

    def _normalize_cpus(self, cpus, online):
        """
        Some methods accept the list of CPUs on input. The list may be a string of comma-separated
        numbers, or a list. It may contain CPU ranges. This function normalizes user input and turns
        it into a list of integer CPU numbers.
        """

        if cpus == "all":
            cpus = None

        if cpus is None or isinstance(cpus, str):
            if cpus is None:
                if online:
                    cpugeom_key = "offline_cpus"
                else:
                    cpugeom_key = "nums"

                if not self._cpuinfo:
                    self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)
                cpugeom = self._cpuinfo.get_cpu_geometry()
                cpus = cpugeom["CPU"][cpugeom_key]
            else:
                cpus = ArgParse.parse_int_list(cpus, ints=True, dedup=True, sort=True)
        else:
            for cpu in cpus:
                if not Trivial.is_int(cpu):
                    raise Error(f"bad CPU number '{cpu}'")

        return cpus

    def _toggle(self, cpus, online):
        """Implements onlining and offlining."""

        if cpus == "all":
            cpus = None

        if online:
            data = "1"
            state_str = "online"
            action_str = "Onlining"
        else:
            data = "0"
            state_str = "offline"
            action_str = "Offlining"

        skip_cpu0 = cpus is None
        cpus = self._normalize_cpus(cpus, online)

        _LOG.debug("CPUs to %s: %s", state_str, ", ".join([str(cpu) for cpu in cpus]))

        for cpu in cpus:
            if cpu == 0:
                if skip_cpu0:
                    continue
                raise Error("CPU0 is special in Linux and does not support onlining/offlining")

            path = self._get_path(cpu)
            self._verify_path(cpu, path)
            state = self._get_online(path)
            if data == state:
                msg = f"CPU{cpu} is already {state_str}, skipping"
            else:
                msg = f"{action_str} CPU{cpu}"
            _LOG.log(self._loglevel, msg)

            try:
                with self._proc.open(path, "w") as fobj:
                    fobj.write(data)
            except Error as err:
                raise Error(f"failed to {state_str} CPU{cpu}:\n{err}") from err

            if self._get_online(path) != data:
                raise Error(f"failed to {state_str} CPU{cpu}")

            self._save([cpu], state == "1")

    def online(self, cpus=None):
        """
        Bring CPUs in 'cpus' online. The 'cpus' argument may be a list of CPUs or a string
        containing a comma-separated list of CPUs and CPU ranges. For example, '0-4,7,8,10-12' would
        mean CPUs 0 to 4, CPUs 7, 8, and 10 to 12. If 'cpus' is 'all' or 'None', then all CPUs are
        onlined (default).
        """

        self._toggle(cpus, True)

    def offline(self, cpus=None):
        """
        The opposite to 'online()'.
        """

        self._toggle(cpus, False)

    def is_online(self, cpu):
        """Returns 'True' if CPU number 'cpu' is online and 'False' otherwise."""

        path = self._get_path(cpu)
        return self._get_online(path) == "1"

    def _save(self, cpus, state):
        """Update saved online/offline state 'state' on CPUs 'cpus'."""

        for cpu in cpus:
            self._saved_states[int(cpu)] = state

    def restore(self):
        """Restore the original CPU states."""

        for cpu, state in reversed(self._saved_states.items()):
            self._toggle([cpu], state)

    def __init__(self, progress=None, proc=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * progress - controls the logging level for the progress messages. The default logging
                       level is 'DEBUG'.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - A 'CPUInfo.CPUInfo()' object.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None

        self._loglevel = progress
        self._saved_states = {}
        self._sysfs_base = Path("/sys/devices/system/cpu")
        self.restore_on_close = False

        if progress is None:
            progress = logging.DEBUG

        if not self._proc:
            self._proc = Procs.Proc()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_proc", None):
            if getattr(self, "restore_on_close", None) and \
               getattr(self, "_saved_states", None):
                self.restore()

        for attr in ("_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
