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

from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs import CPUInfo

_LOG = Logging.getLogger(f"pepc.{__name__}")

class CPUOnline(ClassHelpers.SimpleCloseContext):
    """
    This class provides API for onlining and offlining CPUs.

    Public methods overview.
      * 'online()'
      * 'offline()'
      * 'is_online()'
    """

    def _get_cpuinfo(self):
        """Returns a 'CPUInfo.CPUInfo()' object."""

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        return self._cpuinfo

    def _verify_path(self, cpu, path):
        """Verify if path 'path' exists."""

        if not self._pman.is_file(path):
            if self._pman.is_dir(path.parent):
                raise ErrorNotSupported(f"CPU {cpu} does not support onlining/offlining"
                                        f"{self._pman.hostmsg}")
            raise Error(f"CPU {cpu} does not exist{self._pman.hostmsg}")

    def _validate_hotplugged_cpus(self, cpus, state):
        """Validate that CPUs 'cpus' state is the same in sysfs."""

        if state:
            valid = set(self._cpuinfo.get_cpus())
        else:
            valid = set(self._cpuinfo.get_offline_cpus())

        for cpu in cpus:
            if cpu not in valid:
                state_str = "online" if state else "offline"
                raise Error(f"failed to {state_str} CPU{cpu}")

    def _get_online(self, path):
        """Read the 'online' sysfs file at 'path'."""

        with self._pman.open(path, "r") as fobj:
            state = fobj.read().strip()
        if state in ("0", "1"):
            return state
        raise Error(f"unexpected value '{state}' in '{path}'{self._pman.hostmsg}")

    def _get_path(self, cpu):
        """Build and return path to the 'online' sysfs file for CPU number 'cpu'."""

        return self._sysfs_base / f"cpu{cpu}" / "online"

    def _toggle(self, cpus, online, skip_unsupported):
        """Implements onlining and offlining."""

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
                raise Error(f"failed to {state_str} CPU{cpu}:\n{err.indent(2)}") from err
            toggled.append(cpu)

        if toggled:
            cpuinfo.cpus_hotplugged()
            self._validate_hotplugged_cpus(toggled, online)

    def online(self, cpus="all", skip_unsupported=False):
        """
        Bring CPUs in 'cpus' online. The arguments are as follows.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
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
        try:
            return self._get_online(path) == "1"
        except ErrorNotFound:
            if not self._pman.is_dir(path.parent):
                raise
            # Hotplug sub-system might be disabled, in that case there is no "online" file and the
            # CPU is online.
            return True

    def __init__(self, progress=None, pman=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * progress - controls the logging level for the progress messages. The default logging
                       level is 'DEBUG'.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - a 'CPUInfo.CPUInfo()' object.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        if progress is None:
            progress = Logging.DEBUG

        self._loglevel = progress
        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_cpuinfo", "_pman",))
