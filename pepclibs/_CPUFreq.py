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

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency via Linux "cpufreq"
    subsystem sysfs interfaces.

    Public methods overview.

    1. Get/set CPU frequency via Linux "cpufreq" sysfs interfaces:
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'
    2. Get CPU frequency limits via Linux "cpufreq" sysfs interfaces:
       * 'get_min_freq_limit()'
       * 'get_max_freq_limit()'
    3. Get avalilable CPU frequencies list:
       * 'get_available_frequencies()'

    Note, class methods do not validate the CPU number argument. The caller is assumed to have done
    the validation. The input CPU number should exist and should be online.
    """

    def _get_sysfs_path(self, cpu, fname):
        """Construct and return Linux "cpufreq" sysfs path for file 'fname'."""

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / fname

    def _get_cpu_freq_sysfs_path(self, key, cpu, limit=False):
        """Get the sysfs file path for a CPU frequency read of write operation."""

        fname = "scaling_" + key + "_freq"
        prefix = "cpuinfo_" if limit else "scaling_"
        fname = prefix + key + "_freq"
        return self._get_sysfs_path(cpu, fname)

    def _read_sysfs_file(self, path, what):
        """
        Read a sysfs file at 'path' and return its contents. Return 'None' if the file does not
        exist.
        """

        try:
            with self._pman.open(path, "r") as fobj:
                try:
                    val = fobj.read().strip()
                except Error as err:
                    raise Error(f"failed to read {what} from '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err
        except ErrorNotFound:
            return None

        return val

    def _read_sysfs_file_int(self, path, what):
        """
        Read a sysfs file at 'path', verify that it contains an integer value and return the value
        as 'int'. Return 'None' if the file does not exist.
        """

        val = self._read_sysfs_file(path, what)
        if val is None:
            return None

        try:
            return Trivial.str_to_int(val, what="CPU valuency value")
        except Error as err:
            raise Error(f"bad contents of file '{path}'{self._pman.hostmsg}\n{err.indent(2)}") \
                        from err

    def _get_freq_sysfs(self, key, cpu, limit=False):
        """Get CPU frequency from the Linux "cpufreq" sysfs file."""

        path = self._get_cpu_freq_sysfs_path(key, cpu, limit=limit)

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get(path, cpu)

        _LOG.debug("reading %s CPU frequency for CPU%d from '%s'%s",
                   key, cpu, path, self._pman.hostmsg)

        freq = self._read_sysfs_file_int(path, f"{key}. frequency for CPU {cpu}")
        if freq is None:
            return None

        # Sysfs files use kHz.
        freq *= 1000
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

    def get_min_freq_limit(self, cpu):
        """
        Get minimum CPU frequency limit via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the frequency for.

        Return the minimum CPU frequency limit in Hz or 'None' if the CPU frequency sysfs file does
        not exist.
        """

        return self._get_freq_sysfs("min", cpu, limit=True)

    def get_max_freq_limit(self, cpu):
        """Same as 'get_min_freq_sysfs()', but for the maximum CPU frequency."""

        return self._get_freq_sysfs("max", cpu, limit=True)

    def _set_freq_sysfs(self, freq, key, cpu):
        """Set CPU frequency by writing to the Linux "cpufreq" sysfs file."""

        path = self._get_cpu_freq_sysfs_path(key, cpu)

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

    def get_available_frequencies(self, cpu):
        """
        Get the list of available CPU frequency values. The arguments are as follows.
          * cpu - CPU number to get the list of available frequencies for.

        Return the list of available frequencies Hz or 'None' if the frequencies sysfs file does not
        exist. The sysfs file provided by the 'acpi-cpufreq' driver. but 'intel_idle' driver does
        not provide it.
        """

        path = self._get_sysfs_path(cpu, "scaling_available_frequencies")

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get(path, cpu)

        val = self._read_sysfs_file(path, "available CPU frequencies")
        if val is None:
            return self._cache.add(path, cpu, None, sname="CPU")

        freqs = []
        for freq in val.split():
            try:
                freq = Trivial.str_to_int(freq, what="CPU frequency value")
                freqs.append(freq * 1000)
            except Error as err:
                raise Error(f"bad contents of file '{path}'{self._pman.hostmsg}\n{err.indent(2)}") \
                            from err

        freqs = sorted(freqs)
        return self._cache.add(path, cpu, freqs, sname="CPU")

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

class CPUFreqMSR(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency for Intel platforms
    supporting thie 'MSR_HWP_REQUEST' model-specific register (MSR).

    Public methods overview.

    1. Get/set CPU frequency via an MSR (Intel CPUs only):
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'

    Note, class methods do not validate the CPU number argument. The caller is assumed to have done
    the validation. The input CPU number should exist and should be online.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

        return self._msr

    def _get_fsbfreq(self):
        """Discover bus clock speed."""

        if not self._fsbfreq:
            from pepclibs.msr import FSBFreq # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_bclk(self, cpu, not_supported_ok=True):
        """
        Return bus clock speed in Hz. Return 'None' if bus clock is not supported by the platform.
        """

        try:
            bclk = self._get_fsbfreq().read_cpu_feature("fsb", cpu)
        except ErrorNotSupported:
            # Fall back to 100MHz clock speed.
            if self._cpuinfo.info["vendor"] == "GenuineIntel":
                return 100000000
            if not_supported_ok:
                return None
            raise

        # Convert MHz to Hz.
        return int(bclk * 1000000)

    def _get_hwpreq(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            from pepclibs.msr import HWPRequest # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            from pepclibs.msr import HWPRequestPkg # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_freq_msr(self, key, cpu):
        """Read and return the minimum or maximum CPU frequency from 'MSR_HWP_REQUEST'."""

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{key}_perf"

        bclk = self._get_bclk(cpu, not_supported_ok=True)
        if not bclk:
            return None

        try:
            hwpreq = self._get_hwpreq()
            if hwpreq.is_cpu_feature_pkg_controlled(feature_name, cpu):
                hwpreq = self._get_hwpreq_pkg()
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return None

        try:
            perf = hwpreq.read_cpu_feature(feature_name, cpu)
        except ErrorNotSupported:
            _LOG.debug("CPU %d: HWP %s performance is not supported", cpu, key)
            return None

        freq = None
        if self._cpuinfo.info["hybrid"]:
            pcore_cpus = set(self._cpuinfo.get_hybrid_cpu_topology()["pcore"])
            # In HWP mode, the Linux 'intel_pstate' driver changes CPU frequency by programming
            # 'MSR_HWP_REQUEST'.
            # On many Intel platforms,the MSR is programmed in terms of frequency ratio (frequency
            # divided by 100MHz). But on hybrid Intel platform (e.g., Alder Lake), the MSR works in
            # terms of platform-dependent abstract performance units on P-cores. Convert the
            # performance units to CPU frequency in Hz.
            if cpu in pcore_cpus:
                freq = perf * self._perf_to_freq_factor
                # Round the frequency down to bus clock.
                # * Why rounding? CPU frequency changes in bus-clock increments.
                # * Why rounding down? Following how Linux 'intel_pstate' driver example.
                return freq - (freq % bclk)

        return perf * bclk

    def get_min_freq(self, cpu):
        """
        Get minimum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * cpu - CPU number to get the frequency for.

        Return the minimum CPU frequency in Hz or 'None' if 'MSR_HWP_REQUEST' is not supported.
        """

        return self._get_freq_msr("min", cpu)

    def get_max_freq(self, cpu):
        """Same as 'get_min_freq()', but for the maximum CPU frequency."""

        return self._get_freq_msr("max", cpu)

    def _set_freq_msr(self, freq, key, cpu):
        """Set CPU frequency by writing to 'MSR_HWP_REQUEST'."""

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{key}_perf"

        perf = None
        if self._cpuinfo.info["hybrid"]:
            pcore_cpus = set(self._cpuinfo.get_hybrid_cpu_topology()["pcore"])
            if cpu in pcore_cpus:
                perf = int((freq + self._perf_to_freq_factor - 1) / self._perf_to_freq_factor)

        if perf is None:
            bclk = self._get_bclk(cpu, not_supported_ok=False)
            perf = freq // bclk

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control(feature_name, cpu)
        hwpreq.write_cpu_feature(feature_name, perf, cpu)

    def set_min_freq(self, freq, cpu):
        """
        Set minimum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * freq - the minimum frequency value to set, hertz.
          * cpu - CPU number to set the frequency for.
        """

        self._set_freq_msr(freq, "min", cpu)

    def set_max_freq(self, freq, cpu):
        """Same as 'set_min_freq()', but for the maximum CPU frequency."""

        self._set_freq_msr(freq, "max", cpu)

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to control CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._fsbfreq = None
        self._hwpreq = None
        self._hwpreq_pkg = None

        # Performance to frequency factor.
        self._perf_to_freq_factor = 78740157

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_fsbfreq", "_hwpreq", "_hwpreq_pkg", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
