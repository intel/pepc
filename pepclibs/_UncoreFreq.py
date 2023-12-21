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

The new interface works in terms of "uncore domains". However, uncore domain IDs are the same as die
IDs, and in this project uncore domains are also referred to as "dies".

At this point this module uses the legacy sysfs interface even when the new interface is available.
"""

import logging
import re
import contextlib
from pathlib import Path
from pepclibs import CPUInfo, _PerCPUCache
from pepclibs.msr import UncoreRatioLimit
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, KernelModule, FSHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
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
    3. Get uncore domain ID numbers (same as die numbers) per package:
       * 'get_domain_ids()'
    4. Get number of uncore domains:
       * 'get_domains_count()'
    """

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
            # uncore domain under it via the kernel driver support.
            path = self._sysfs_base / f"package_{package:02d}_die_00" / fname
            self._die_id_quirk = True
            _LOG.debug("die ID quirk applied, falling back to die 0 from die %d", die)

        return path

    def _get_freq(self, key, cpu, limit=False):
        """Set uncore frequency by reading from the corresponding sysfs file."""

        path = self._get_sysfs_path(key, cpu, limit=limit)

        with contextlib.suppress(ErrorNotFound):
            return self._cache.get(path, cpu)

        try:
            with self._pman.open(path, "r") as fobj:
                freq = Trivial.str_to_int(fobj.read(), what=f"{key}. uncore frequency")
        except ErrorNotFound:
            return self._cache.add(path, cpu, None, sname="die")
        except Error as err:
            raise Error(f"failed to read {key}. uncore frequency for CPU{cpu} from '{path}'"
                        f"{self._pman.hostmsg}\n{err.indent(2)}") from err

        # The frequency value is in kHz in sysfs.
        freq *= 1000
        return self._cache.add(path, cpu, freq, sname="die")

    def get_min_freq(self, cpu):
        """
        Get minimum uncore frequency for the die (uncore frequency domain) corresponding to CPU
        'cpu'. The arguments are as follows.
          * cpu - CPU number to get the uncore frequency for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency in Hz or 'None' if the uncore frequency sysfs file does not exist.

        Note, the CPU number is not validated and the caller is assumed to have done the validation.
        CPU 'cpu' should exist and should be online.
        """

        return self._get_freq("min", cpu)

    def get_max_freq(self, cpu):
        """Same as 'get_min_freq()', but for the maximum uncore frequency."""

        return self._get_freq("max", cpu)

    def get_min_freq_limit(self, cpu):
        """
        Get minimum uncore frequency limit for the die (uncore frequency domain) corresponding to
        CPU 'cpu'. The arguments are as follows.
          * cpu - CPU number to get the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency limit in Hz or 'None' if the uncore frequency sysfs file does not exist.

        Note, the CPU number is not validated and the caller is assumed to have done the validation.
        CPU 'cpu' should exist and should be online.
        """
        return self._get_freq("min", cpu, limit=True)

    def get_max_freq_limit(self, cpu):
        """Same as 'get_min_freq_limit()', but for the maximum uncore frequency limit."""

        return self._get_freq("max", cpu, limit=True)

    def _set_freq(self, freq, key, cpu):
        """Set uncore frequency by writing to the corresponding sysfs file."""

        path = self._get_sysfs_path(key, cpu)

        self._cache.remove(path, cpu, sname="die")

        try:
            with self._pman.open(path, "r+") as fobj:
                # Note, the frequency value is in kHz in sysfs.
                fobj.write(str(freq // 1000))
        except Error as err:
            raise Error(f"failed to write {key}. uncore frequency value '{freq}' for CPU{cpu} to "
                        f"'{path}'{self._pman.hostmsg}:\n{err.indent(2)}") from err

        # Read uncore frequency back and verify that it was set correctly.
        try:
            with self._pman.open(path, "r") as fobj:
                new_freq = Trivial.str_to_int(fobj.read(), what=f"{key}. uncore frequency") * 1000
        except Error as err:
            raise Error(f"failed to read {key}. uncore frequency for CPU{cpu}{self._pman.hostmsg} "
                        f"from '{path}'\n{err.indent(2)}") from err

        if freq == new_freq:
            return self._cache.add(path, cpu, freq, sname="die")

        raise ErrorVerifyFailed(f"failed to set {key}. uncore frequency to {freq} for CPU{cpu}"
                                f"{self._pman.hostmsg}: wrote '{freq // 1000}' to '{path}', but "
                                f"read '{new_freq // 1000}' back",
                                cpu=cpu, expected=freq, actual=new_freq, path=path)

    def set_min_freq(self, freq, cpu):
        """
        Set minimum uncore frequency for the die (uncore frequency domain) corresponding to CPU
        'cpu'. The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * cpu - CPU number to set the uncore frequency for.

        Use the Linux uncore frequency driver sysfs interface set the minimum uncore frequency.

        Note, the CPU number is not validated and the caller is assumed to have done the validation.
        CPU 'cpu' should exist and should be online.
        """

        self._set_freq(freq, "min", cpu)

    def set_max_freq(self, freq, cpu):
        """Same as 'set_min_freq()', but for the maximum uncore frequency."""

        self._set_freq(freq, "max", cpu)

    def _add_domain(self, package, domain):
        """Add mapping for a single uncore 'domain' under 'package'."""

        if package not in self._domains_info:
            self._domains_info[package] = []

        self._domains_info[package].append(domain)
        self._domains_cnt += 1

    def _build_domains_info(self):
        """Build domain info for available uncore domains."""

        self._domains_info = {}

        if self._pman.is_dir(self._sysfs_base / "uncore00"):
            for dirname, path, _ in self._pman.lsdir(self._sysfs_base):
                match = re.match(r"^uncore(\d+)$", dirname)
                if not match:
                    continue

                with self._pman.open(path / "package_id", "r") as fobj:
                    package = Trivial.str_to_int(fobj.read(), what="package ID")

                with self._pman.open(path / "domain_id", "r") as fobj:
                    domain = Trivial.str_to_int(fobj.read(), what="uncore domain ID")

                self._add_domain(package, domain)
        else:
            for dirname, path, _ in self._pman.lsdir(self._sysfs_base):
                match = re.match(r"package_(\d+)_die_(\d+)", dirname)
                if match:
                    package = int(match.group(1))
                    domain = int(match.group(2))
                    self._add_domain(package, domain)

    def get_domain_ids(self):
        """
        Return the domain ID dictionary, which maps package numbers to domain ID numbers, and has
        the following format.

        domain_ids = { <package-id-0>: [ <domain-id-0>, <domain-id-1> ... <domain-id-n> ],
                       <package-id-n>: [ <domain-id-0>, <domain-id-1> ... <domain-id-n> ] }

        For example, with a system with 2 packages and 3 domains under each package the domain ids
        would be:

        domain_ids = { 0: [0, 1, 2],
                       1: [0, 1, 2] }
        """

        if not self._domains_info:
            self._build_domains_info()

        return self._domains_info

    def get_domains_count(self):
        """Get total number of uncore domains for system."""

        if not self._domains_info:
            self._build_domains_info()

        return self._domains_cnt

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
          * pman - the process manager object that defines the host to control uncore frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._domains_info = None
        self._domains_cnt = 0

        self._drv = None
        self._unload_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu/intel_uncore_frequency")

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

        self._cache = _PerCPUCache.PerCPUCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                               enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        if self._unload_drv:
            self._drv.unload()

        close_attrs = ("_cache", "_drv", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
