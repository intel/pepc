# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides a capability of reading and changing CPU frequency.
"""

import time
import logging
import contextlib
from pathlib import Path
from pepclibs import CPUInfo, _PerCPUCache
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

_LOG = logging.getLogger()

class CPUFreq(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency.

    Public methods overview.

    1. Set CPU frequency via Linux "cpufreq" sysfs interfaces:
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'

    Note, class methods do not validate the CPU number argument. The caller is assumed to have done
    the validation. The input CPU number should exist and should be online.
    """

    def _get_sysfs_path(self, key, cpu):
        """Get the sysfs file path for a CPU frequency read of write operation."""

        fname = "scaling_" + key + "_freq"
        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / fname

    def _get_freq_sysfs(self, key, cpu):
        """Get CPU frequency from the Linux "cpufreq" sysfs file."""

        path = self._get_sysfs_path(key, cpu)

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get(path, cpu)

        _LOG.debug("reading %s CPU frequency for CPU%d from '%s'%s",
                   key, cpu, path, self._pman.hostmsg)

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    freq = Trivial.str_to_int(fobj.read(), what=f"{key} CPU frequency") * 1000
                except Error as err:
                    raise Error(f"failed to read {key} CPU frequency for CPU{cpu} from '{path}'"
                                f"{self._pman.hostmsg}\n{err.indent(2)}") from err
        except ErrorNotFound as err:
            return self._cache.add(path, cpu, None, sname="CPU")

        return self._cache.add(path, cpu, freq, sname="CPU")

    def get_min_freq(self, cpu):
        """
        Get minimum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the frequency for.

        Return the minimum CPU frequency in Hz or 'None' if the CPU frequency sysfs file does not
        exist.
        """

        return self._get_freq_sysfs("min", cpu)

    def get_max_freq(self, cpu):
        """Same as 'get_min_freq()', but for the maximum CPU frequency."""

        return self._get_freq_sysfs("max", cpu)

    def _set_freq_sysfs(self, freq, key, cpu):
        """Set CPU frequency by writing to the Linux "cpufreq" sysfs file."""

        path = self._get_sysfs_path(key, cpu)

        _LOG.debug("writing %s CPU frequency value '%d' for CPU%d to '%s'%s",
                   key, freq // 1000, cpu, path, self._pman.hostmsg)

        self._cache.remove(path, cpu, sname="CPU")

        try:
            with self._pman.open(path, "r+") as fobj:
                # Sysfs files use kHz.
                fobj.write(str(freq // 1000))
        except Error as err:
            raise Error(f"failed to write {key}. CPU frequency value '{freq}' for CPU{cpu} to "
                        f"'{path}'{self._pman.hostmsg}:\n{err.indent(2)}") from err

        count = 3
        while count > 0:
            # Read CPU frequency back and verify that it was set correctly.
            try:
                with self._pman.open(path, "r") as fobj:
                    new_freq = Trivial.str_to_int(fobj.read(), what=f"{key}. CPU frequency") * 1000
            except Error as err:
                raise Error(f"failed to read {key}. CPU frequency for CPU{cpu}{self._pman.hostmsg} "
                            f"from '{path}'\n{err.indent(2)}") from err

            if freq == new_freq:
                return self._cache.add(path, cpu, freq, sname="CPU")

            # Sometimes the update does not happen immediately. For example, we observed this on
            # Intel systems with HWP enabled. Wait a little bit and try again.
            time.sleep(0.1)
            count -= 1

        raise ErrorVerifyFailed(f"failed to set {key}. CPU frequency to {freq} for CPU{cpu}"
                                f"{self._pman.hostmsg}: wrote '{freq // 1000}' to '{path}', but "
                                f"read '{new_freq // 1000}' back",
                                cpu=cpu, expected=freq, actual=new_freq, path=path)

    def set_min_freq(self, freq, cpu):
        """
        Set minimum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * freq - the minimum frequency value to set, hertz.
          * cpu - CPU number to set the frequency for.
        """

        self._set_freq_sysfs(freq, "min", cpu)

    def set_max_freq(self, freq, cpu):
        """Same as 'set_min_freq()', but for the maximum CPU frequency."""

        self._set_freq_sysfs(freq, "max", cpu)

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to control CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        self._cache = _PerCPUCache.PerCPUCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                               enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_cache", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
