# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides a capability of reading and changing the uncore frequencies on Intel CPUs.
"""

import logging
import contextlib
from pathlib import Path
from pepclibs import CPUInfo, _PropsCache
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, KernelModule, FSHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

_LOG = logging.getLogger()

class UncoreFreq(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing the uncore frequencies on Intel CPUs.
    This class is considered to be an internal "companion" class for other classes, so it does not
    validate the input arguments, assuming the user does the validation.

    Public methods overview.

    1. Get/set uncore frequency via Linux sysfs interfaces:
       'get_min_freq()', 'get_max_freq()', 'set_min_freq()', 'set_max_freq()'.
    2. Get uncore frequency limits via Linux sysfs interfaces:
       'get_min_freq_limit()', 'get_max_freq_limit()'.
    """

    def _get_filename_from_key(self, key, limit=False, write=False):
        """
        Verify the validity of 'key', and return the corresponding sysfs file name. Raise an
        exception if 'key' is invalid.
        """

        if key not in ("min", "max"):
            if write:
                msg = "writing"
            else:
                msg = "reading"
            raise Error(f"BUG: bad uncore frequency key for {msg}: '{key}', only 'min', 'max' "
                        "supported.")

        prefix = "initial_" if limit else ""

        return prefix + key + "_freq_khz"

    def _get_sysfs_path(self, key, cpu, limit=False, write=False):
        """Get the sysfs file path for the given uncore frequency parameter."""

        levels = self._cpuinfo.get_cpu_levels(cpu, levels=("package", "die"))
        package = levels["package"]
        die = levels["die"]

        name = self._get_filename_from_key(key, limit=limit, write=write)
        return self._sysfs_base / f"package_{package:02d}_die_{die:02d}" / name

    def _get_freq(self, key, cpu, limit=False):
        """
        Get uncore frequency from sysfs. The arguments are as follows.
          * key - name identifier of the frequency to read.
          * cpu - CPU number to read the frequency for.
          * limit - if 'True', reads the limit value. Otherwise reads the current setting.
        """

        path = self._get_sysfs_path(key, cpu, limit=limit)

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get(path, cpu, "sysfs")

        try:
            with self._pman.open(path, "r") as fobj:
                freq = Trivial.str_to_int(fobj.read(), what=f"{key} uncore frequency") * 1000
        except Error as err:
            raise Error(f"failed to read {key} uncore frequency for CPU{cpu}{self._pman.hostmsg} "
                        f"from '{path}'\n{err.indent(2)}")

        return self._pcache.add(path, cpu, freq, "sysfs", sname="die")

    def get_min_freq(self, cpu):
        """Get minimum uncore frequency from sysfs for CPU 'cpu'."""
        return self._get_freq("min", cpu)

    def get_max_freq(self, cpu):
        """Get maximum uncore frequency from sysfs for CPU 'cpu'."""
        return self._get_freq("max", cpu)

    def get_min_freq_limit(self, cpu):
        """Get minimum uncore frequency limit from sysfs for CPU 'cpu'."""
        return self._get_freq("min", cpu, limit=True)

    def get_max_freq_limit(self, cpu):
        """Get maximum uncore frequency limit from sysfs for CPU 'cpu'."""
        return self._get_freq("max", cpu, limit=True)

    def _set_freq(self, freq, key, cpu):
        """
        Write uncore frequency to sysfs. The arguments are as follows.
          * freq - frequency to write to sysfs, in Hz.
          * key - name identifier of the frequency to write.
          * cpu - CPU number to write the frequency for.
        """

        path = self._get_sysfs_path(key, cpu, write=True)

        try:
            with self._pman.open(path, "r+") as fobj:
                fobj.write(str(freq // 1000))

            with self._pman.open(path, "r") as fobj:
                new_freq = Trivial.str_to_int(fobj.read(), what=f"{key} uncore frequency") * 1000
        except Error as err:
            errmsg = f"failed to set {key} uncore frequency to {freq} for CPU{cpu}" \
                     f"{self._pman.hostmsg}:\n{err.indent(2)}"
            raise Error(errmsg)

        if freq != new_freq:
            errmsg = f"failed to set {key} uncore frequency to {freq} for CPU{cpu}" \
                     f"{self._pman.hostmsg}: wrote '{freq // 1000}' to '{path}' but read" \
                     f"'{new_freq}' back."
            raise ErrorVerifyFailed(errmsg)

        return self._pcache.add(path, cpu, freq, "sysfs", sname="die")

    def set_min_freq(self, freq, cpu):
        """Set minimum uncore frequency for CPU 'cpu' to 'freq'."""
        self._set_freq(freq, "min", cpu)

    def set_max_freq(self, freq, cpu):
        """Set maximum uncore frequency for CPU 'cpu' to 'freq'."""
        self._set_freq(freq, "max", cpu)

    def _probe_driver(self):
        """
        Attempt to determine the required kernel module for uncore support, and probe it. Will
        raise an ErrorNotSupported if fails.
        """

        from pepclibs.msr import UncoreRatioLimit # pylint: disable=import-outside-toplevel

        cpumodel = self._cpuinfo.info["model"]

        errmsg = None

        # If the CPU supports MSR_UNCORE_RATIO_LIMIT, the uncore frequency driver is
        # "intel_uncore_frequency".
        if cpumodel in UncoreRatioLimit.FEATURES["max_ratio"]["cpumodels"]:
            drvname = "intel_uncore_frequency"
            kopt = "CONFIG_INTEL_UNCORE_FREQ_CONTROL"
            msr_addr = UncoreRatioLimit.MSR_UNCORE_RATIO_LIMIT

            msg = f"Uncore frequency operations are not supported{self._pman.hostmsg}. Here are " \
                  f"the possible reasons:\n" \
                  f" 1. the '{drvname}' driver is not enabled. Try to compile the kernel " \
                  f"with the '{kopt}' option.\n" \
                  f" 2. the kernel is old and does not have the '{drvname}' driver.\n" \
                  f"Address these issues or contact project maintainers and request" \
                  f"implementing uncore frequency support via MSR {msr_addr:#x}"
        else:
            drvname = "intel_uncore_frequency_tpmi"
            kopt = "CONFIG_INTEL_UNCORE_FREQ_CONTROL_TPMI"

            msg = f"Uncore frequency operations are not supported{self._pman.hostmsg}. Here are " \
                  f"the possible reasons:\n" \
                  f" 1. the hardware does not support uncore frequency management.\n" \
                  f" 2. the '{drvname}' driver does not support this hardware.\n" \
                  f" 3. the kernel is old and does not have the '{drvname}' driver. This driver " \
                  f"is supported since kernel version 6.5.\n" \
                  f" 4. the '{drvname}' driver is not enabled. Try to compile the kernel " \
                  f"with the '{kopt}' option"

        try:
            self._drv = KernelModule.KernelModule(drvname, pman=self._pman)
            loaded = self._drv.is_loaded()
        except Error as err:
            _LOG.debug("%s\n%s", err, msg)
            errmsg = msg
            loaded = False

        if loaded:
            # The sysfs directories do not exist, but the driver is loaded.
            _LOG.debug("the uncore frequency driver '%s' is loaded, but the sysfs directory '%s' "
                       "does not exist.\n%s", drvname, self._sysfs_base, msg)
            errmsg = msg
        else:
            try:
                self._drv.load()
                self._unload_drv = True
                FSHelpers.wait_for_a_file(self._sysfs_base, timeout=1, pman=self._pman)
            except Error as err:
                _LOG.debug("%s\n%s", err, msg)
                errmsg = msg

        if errmsg:
            raise ErrorNotSupported(errmsg)

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._drv = None
        self._unload_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu/intel_uncore_frequency")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        if not self._pman.exists(self._sysfs_base):
            self._probe_driver()

        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        if self._unload_drv:
            self._drv.unload()

        close_attrs = ("_pcache", "_drv", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
