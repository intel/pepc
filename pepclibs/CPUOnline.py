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
from pepclibs.helperlibs import FSHelpers, LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo

_LOG = logging.getLogger()

class CPUOnline:
    """This class provides API for onlining and offlining CPUs."""

    def _get_cpuinfo(self):
        """Returns a 'CPUInfo.CPUInfo()' object."""

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        return self._cpuinfo

    def _verify_path(self, cpu, path):
        """Verify if path 'path' exists."""

        if not FSHelpers.isfile(path, pman=self._pman):
            if FSHelpers.isdir(path.parent, pman=self._pman):
                raise ErrorNotSupported(f"CPU '{cpu}' on host {self._pman.hostname}' does not "
                                        f"support onlining/offlining")
            raise Error(f"CPU '{cpu}' does not exist on host '{self._pman.hostname}'")

    def _get_online(self, path):
        """Read the 'online' sysfs file at 'path'."""

        with self._pman.open(path, "r") as fobj:
            state = fobj.read().strip()
        if state in ("0", "1"):
            return state
        raise Error("unexpected value '{state}' in '{path}' on host '{self._pman.hostname}'")

    def _get_path(self, cpu):
        """Build and return path to the 'online' sysfs file for CPU number 'cpu'."""

        return self._sysfs_base / f"cpu{cpu}" / "online"

    def _toggle(self, cpus, online, skip_unsupported):
        """Implements onlining and offlining."""

        cpuinfo = self._get_cpuinfo()

        if online:
            data = "1"
            state_str = "online"
            action_str = "Onlining"
        else:
            data = "0"
            state_str = "offline"
            action_str = "Offlining"

        if cpus == "all":
            skip_unsupported = True
            if online:
                cpus = cpuinfo.get_offline_cpus()
            else:
                cpus = cpuinfo.get_cpus()
        else:
            cpus = cpuinfo.normalize_cpus(cpus, offlined_ok=True)

        _LOG.debug("CPUs to %s: %s", state_str, ", ".join([str(cpu) for cpu in cpus]))

        for cpu in cpus:
            path = self._get_path(cpu)

            try:
                self._verify_path(cpu, path)
            except ErrorNotSupported as err:
                if not skip_unsupported:
                    raise
                _LOG.info(err)
                continue

            state = self._get_online(path)
            if data == state:
                msg = f"CPU{cpu} is already {state_str}, skipping"
            else:
                msg = f"{action_str} CPU{cpu}"
            _LOG.log(self._loglevel, msg)

            try:
                with self._pman.open(path, "w") as fobj:
                    fobj.write(data)
            except Error as err:
                raise Error(f"failed to {state_str} CPU{cpu}:\n{err}") from err

            if self._get_online(path) != data:
                raise Error(f"failed to {state_str} CPU{cpu}")

            self._save([cpu], state == "1")

    def online(self, cpus="all", skip_unsupported=False):
        """
        Bring CPUs in 'cpus' online. The arguments are as follows.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs".
          * skip_unsupported - by default, if a CPU in 'cpus' does not support onlining/offlining,
                               this method raises 'ErrorNotSupported()'. If 'skip_unsupported' is
                               'True', the CPU is just skipped without raising an exception.
        """

        self._toggle(cpus, True, skip_unsupported)

    def offline(self, cpus="all", skip_unsupported=False):
        """The opposite to 'online()'."""

        self._toggle(cpus, False, skip_unsupported)

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
            self._toggle([cpu], state, False)

    def __init__(self, progress=None, pman=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * progress - controls the logging level for the progress messages. The default logging
                       level is 'DEBUG'.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - A 'CPUInfo.CPUInfo()' object.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._loglevel = progress
        self._saved_states = {}
        self._sysfs_base = Path("/sys/devices/system/cpu")
        self.restore_on_close = False

        if progress is None:
            progress = logging.DEBUG

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_pman", None):
            if getattr(self, "restore_on_close", None) and \
               getattr(self, "_saved_states", None):
                self.restore()

        for attr in ("_cpuinfo", "_pman"):
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
