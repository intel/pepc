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
This module provides a capability of reading and changing uncore frequency on Intel CPUs.

On older platforms, such as Skylake Xeon and Sapphire Rapids Xeon, the uncore frequency is
controlled via an MSR. Linux kernel has the 'intel_uncore_frequency' driver that exposes the sysfs
interface, which programs the MSR under the hood. The sysfs interface is per-die. For example,
package 0, die 1 uncore frequency is controlled via sysfs files under the "package_01_die_00" sysfs
sub-directory.

This sysfs interface is referred to as the legacy interface.

On newer platforms, such as Granite Rapids Xeon, the uncore frequency is controlled via TPMI, and
Linux kernel has the 'intel_uncore_frequency_tpmi' driver that exposes the sysfs interface. The TPMI
driver has two sysfs interfaces, though: the legacy interface and the new interface. The legacy
interface is limited, and the new interface is preferable.

The new interface works in terms of "uncore frequency domains". However, uncore domain IDs are the
same as die IDs, and in this project uncore domains are referred to as "dies".

At this point this module uses the legacy sysfs interface even when the new interface is available.
"""

import logging
import re
from pathlib import Path
from pepclibs import CPUInfo, _SysfsIO
from pepclibs.msr import UncoreRatioLimit
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, KernelModule, FSHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

_LOG = logging.getLogger()

class UncoreFreq(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing uncore frequency on Intel CPUs. This
    class is considered to be an internal "companion" class for other classes, so it does not
    validate the input arguments, assuming the user does the validation.

    Public methods overview.

    1. Get/set uncore frequency via Linux sysfs interfaces:
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'
    2. Get uncore frequency limits via Linux sysfs interfaces:
       * 'get_min_freq_limit()'
       * 'get_max_freq_limit()'
    3. Get dies information dictionary:
       * 'get_dies_info()'

    Note, class methods do not validate the 'cpus' argument. The caller is assumed to have done the
    validation. The input CPU numbers should exist and should be online.
    """

    def _get_sysfs_base_lsdir(self):
        """
        Return the list of files and directories in the uncore frequency driver's base sysfs
        directory.
        """

        if self._sysfs_base_lsdir is not None:
            return self._sysfs_base_lsdir

        self._sysfs_base_lsdir = []
        for dirname, _, _ in self._pman.lsdir(self._sysfs_base):
            self._sysfs_base_lsdir.append(dirname)

        return self._sysfs_base_lsdir

    def _use_new_sysfs_api(self):
        """Return 'True' if the new uncore frequency driver interface is available."""

        if self._has_sysfs_new_api is not None:
            return self._has_sysfs_new_api

        self._has_sysfs_new_api = False
        for dirname in self._get_sysfs_base_lsdir():
            if dirname.startswith("uncore"):
                self._has_sysfs_new_api = True
                break

        return self._has_sysfs_new_api

    def _get_sysfs_path(self, key, cpu, limit=False):
        """Return the sysfs file path for an uncore frequency read or write operation."""

        levels = self._cpuinfo.get_cpu_levels(cpu, levels=("package", "die"))
        package = levels["package"]
        die = levels["die"]

        prefix = "initial_" if limit else ""
        fname = prefix + key + "_freq_khz"

        if self._die_id_quirk:
            die = 0

        path = self._sysfs_base / f"package_{package:02d}_die_{die:02d}" / fname
        if not self._die_id_quirk and not self._pman.exists(path) and die > 0:
            # If path does not exist, try to fallback to die 0 as temporary band-aid for some of the
            # newer platforms. Please note that on newer platforms the legacy path controls every
            # die (uncore frequency domain) under it via the kernel driver support.
            path = self._sysfs_base / f"package_{package:02d}_die_00" / fname
            self._die_id_quirk = True
            _LOG.debug("die ID quirk applied, falling back to die 0 from die %d", die)

        return path

    def _get_freq(self, key, cpus, limit=False):
        """Yield uncore frequency by reading from the corresponding sysfs file."""

        what = f"{key}. uncore frequency"
        if limit:
            what += " limit"

        for cpu in cpus:
            path = self._get_sysfs_path(key, cpu, limit=limit)
            freq = self._sysfs_io.read_int(path, what=what)
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_min_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum uncore
        frequency for the die (uncore frequency domain) corresponding to CPU 'cpu'. The arguments
        are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequencies for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq("min", cpus)

    def get_max_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum uncore
        frequency for the die (uncore frequency domain) corresponding to CPU 'cpu'. The arguments
        are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequencies for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq("max", cpus)

    def get_min_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum uncore
        frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq("min", cpus, limit=True)

    def get_max_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum uncore
        frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq("max", cpus, limit=True)

    def _set_freq(self, freq, key, cpus):
        """
        For every CPU in 'cpus', set uncore frequency by writing to the corresponding sysfs file.
        """

        what = f"{key}. uncore frequency"

        for cpu in cpus:
            path = self._get_sysfs_path(key, cpu)
            try:
                self._sysfs_io.write_verify(path, str(freq // 1000), what=what)
            except ErrorVerifyFailed as err:
                setattr(err, "cpu", cpu)
                raise err

    def set_min_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', set the minimum uncore frequency for corresponding die die (uncore
        frequency domain) corresponding. The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * cpus - a collection of integer CPU numbers to set the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the minimum uncore frequency.
        """

        self._set_freq(freq, "min", cpus)

    def set_max_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', set the maximum uncore frequency for corresponding die die (uncore
        frequency domain) corresponding. The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * cpus - a collection of integer CPU numbers to set the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the maximum uncore frequency.
        """

        self._set_freq(freq, "max", cpus)

    def _add_die(self, package, die):
        """Add die 'die' for package 'packet' to the dies information dictionary."""

        if package not in self._dies_info:
            self._dies_info[package] = []

        self._dies_info[package].append(die)

    def _build_dies_info(self):
        """Build dies information dictionary."""

        self._dies_info = {}
        sysfs_base_lsdir = self._get_sysfs_base_lsdir()

        if self._use_new_sysfs_api():
            for dirname in sysfs_base_lsdir:
                match = re.match(r"^uncore(\d+)$", dirname)
                if not match:
                    continue

                path = self._sysfs_base / dirname
                with self._pman.open(path / "package_id", "r") as fobj:
                    package = Trivial.str_to_int(fobj.read(), what="package ID")

                with self._pman.open(path / "domain_id", "r") as fobj:
                    die = Trivial.str_to_int(fobj.read(), what="uncore frequency domain ID")

                self._add_die(package, die)
        else:
            for dirname in sysfs_base_lsdir:
                match = re.match(r"package_(\d+)_die_(\d+)", dirname)
                if match:
                    package = int(match.group(1))
                    die = int(match.group(2))
                    self._add_die(package, die)

    def get_dies_info(self):
        """
        Return the dies information dictionary, which maps package numbers to die numbers. Die
        numbers match the uncore frequency domain ID numbers. The returned dictionary has the
        following format.

            {package0: [ die0, die1, ... ], package1: [ die0, die1, ... ]}

        In other words, it is a dictionary with keys being package numbers and values being lists of
        die numbers.  For example, with a system with 2 packages and 3 dies per package, the dies
        information dictionary would be as follows.

            {0: [0, 1, 2], 1: [0, 1, 2]}
        """

        if not self._dies_info:
            self._build_dies_info()

        return self._dies_info.copy()

    def _probe_driver(self):
        """
        Attempt to determine the required kernel module for uncore frequency support, and probe it.
        Raise 'ErrorNotSupported' if the uncore frequency driver fails to load.
        """

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
                  f"implementing uncore frequency support via MSR {msr_addr:#x}."
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
                  f"with the '{kopt}' option."

        try:
            self._drv = KernelModule.KernelModule(drvname, pman=self._pman)
            loaded = self._drv.is_loaded()
        except Error as err:
            _LOG.debug("%s\n%s.", err, msg)
            errmsg = msg
            loaded = False

        if loaded:
            # The sysfs directories do not exist, but the driver is loaded.
            _LOG.debug("the uncore frequency driver '%s' is loaded, but the sysfs directory '%s' "
                       "does not exist\n%s.", drvname, self._sysfs_base, msg)
            errmsg = msg
        else:
            try:
                self._drv.load()
                self._unload_drv = True
                FSHelpers.wait_for_a_file(self._sysfs_base, timeout=1, pman=self._pman)
            except Error as err:
                _LOG.debug("%s\n%s.", err, msg)
                errmsg = msg

        if errmsg:
            raise ErrorNotSupported(errmsg)

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to control uncore frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._dies_info = None

        self._drv = None
        self._unload_drv = False

        self._sysfs_io = None
        self._sysfs_base = Path("/sys/devices/system/cpu/intel_uncore_frequency")

        # List of directory names in 'self._sysfs_base'.
        self._sysfs_base_lsdir = None
        # The new sysfs API is available if 'True'.
        self._has_sysfs_new_api = None

        self._die_id_quirk = False

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        vendor = self._cpuinfo.info["vendor"]
        if vendor != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported CPU vendor '{vendor}'{pman.hostmsg}\nOnly"
                                    f"Intel CPU uncore frequency control is currently supported")

        if not self._pman.exists(self._sysfs_base):
            self._probe_driver()

        self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        if self._unload_drv:
            self._drv.unload()

        close_attrs = ("_sysfs_io", "_drv", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
