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
interface is limited, so this module uses the new interface instead.

The new interface works in terms of "uncore frequency domains". However, uncore domain IDs are the
same as die IDs, and in this project uncore domains are referred to as "dies".
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
       * On per-die (uncore frequency domain) basis:
           - 'get_min_freq_dies()'
           - 'get_max_freq_dies()'
           - 'set_min_freq_dies()'
           - 'set_max_freq_dies()'
       * On per-CPU basis:
           - 'get_min_freq_cpus()'
           - 'get_max_freq_cpus()'
           - 'set_min_freq_cpus()'
           - 'set_max_freq_cpus()'
    2. Get uncore frequency limits via Linux sysfs interfaces:
       * On per-die (uncore frequency domain) basis:
           - 'get_min_freq_limit_dies()'
           - 'get_max_freq_limit_dies()'
       * On per-CPU basis:
           - 'get_min_freq_limit_cpus()'
           - 'get_max_freq_limit_cpus()'
    3. Get dies information dictionary:
       * 'get_dies_info()'

    Note, class methods do not validate the 'cpus' and 'dies' arguments. The caller is assumed to
    have done the validation. The input package, die, and CPU numbers should exist, the CPUs should
    be online.
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

    def _get_dies_info(self):
        """Return the dies information dictionary."""

        if self._dies_info is None:
            self._build_dies_info()
        return self._dies_info

    def _get_dirmap(self):
        """Return the sysfs directory map."""

        if self._dirmap is None:
            self._build_dies_info()
        return self._dirmap

    def _get_new_sysfs_api_path(self, key, package, die, limit=False):
        """Return the new sysfs API file path for an uncore frequency read or write operation."""

        prefix = "initial_" if limit else ""
        fname = prefix + key + "_freq_khz"
        return self._sysfs_base / self._get_dirmap()[package][die] / fname

    def _get_legacy_sysfs_api_path(self, key, package, die, limit=False):
        """Return the legacy sysfs API file path for a uncore frequency read or write operation."""

        prefix = "initial_" if limit else ""
        fname = prefix + key + "_freq_khz"
        return self._sysfs_base / f"package_{package:02d}_die_{die:02d}" / fname

    def _get_sysfs_path_dies(self, key, package, die, limit=False):
        """Get the sysfs file path for an uncore frequency read or write operation."""

        if self._use_new_sysfs_api():
            return self._get_new_sysfs_api_path(key, package, die, limit=limit)
        return self._get_legacy_sysfs_api_path(key, package, die, limit=limit)

    def _get_freq_dies(self, key, dies, limit=False):
        """
        For every die in the 'dies' dictionary, yield a '(package, die, val)' tuple, where 'val' is
        the min. or max. uncore frequency or frequency limit for the die 'die' in package 'package'.
        The arguments are as follows.
        """

        what = f"{key}. uncore frequency"
        if limit:
            what += " limit"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._get_sysfs_path_dies(key, package, die, limit=limit)
                freq = self._sysfs_io.read_int(path, what=what)
                # The frequency value is in kHz in sysfs.
                yield package, die, freq * 1000

    def get_min_freq_dies(self, dies):
        """
        For every die in the 'dies' dictionary, yield a '(package, die, val)' tuple, where 'val' is
        the minimum uncore frequency for the die 'die' in package 'package'. The arguments are as
        follows.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_dies("min", dies)

    def get_max_freq_dies(self, dies):
        """
        For every die in the 'dies' dictionary, yield a '(package, die, val)' tuple, where 'val' is
        the maximum uncore frequency for the die 'die' in package 'package'. The arguments are as
        follows.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_dies("max", dies)

    def get_min_freq_limit_dies(self, dies):
        """
        For every die in the 'dies' dictionary, yield a '(package, die, val)' tuple, where 'val' is
        the minimum uncore frequency limit for the die 'die' in package 'package'. The arguments are
        as follows.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency limit sysfs file
        does not exist.
        """

        yield from self._get_freq_dies("min", dies, limit=True)

    def get_max_freq_limit_dies(self, dies):
        """
        For every die in the 'dies' dictionary, yield a '(package, die, val)' tuple, where 'val' is
        the maximum uncore frequency limit for the die 'die' in package 'package'. The arguments are
        as follows.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency limit sysfs file
        does not exist.
        """

        yield from self._get_freq_dies("max", dies, limit=True)

    def _unlock_new_sysfs_api(self):
        """
        The "intel_uncore_frequency_tpmi" kernel driver has an unintuitive behavior: the min./max.
        frequency configured via the legacy sysfs API limits the range of available uncore
        frequencies configurable via the new sysfs API.

        For example, if max. uncore frequency limit is 2GHz, but max. uncore frequency was set to
        1GHz via the legacy API, it is impossible to set it to anything greater than 1GHz via the
        new API.

        The method is essentially a quirk to work around the driver behavior: "unlock" the new sysfs
        API by removing the floor/ceiling potentially configured via the legacy sysfs API.
        """

        if self._new_sysfs_api_unlocked:
            return

        # When the new sysfs API is available, the legacy sysfs API exposes sysfs files only for die
        # 0, which actually controls all dies in the package. Therefore, iterate only the packages,
        # but not dies.
        for package in self._get_dies_info():
            for key in "min", "max":
                path = self._get_sysfs_path_dies(key, package, 0, limit=True)
                what = f"{key}. uncore frequency limit"
                limit = self._sysfs_io.read_int(path, what=what)

                path = self._get_sysfs_path_dies(key, package, 0, limit=False)
                self._sysfs_io.write_verify(path, str(limit), what=what)

    def _set_freq_dies(self, freq, key, dies):
        """For every die in 'dies', set the min. or max. uncore frequency for the die."""

        self._unlock_new_sysfs_api()

        what = f"{key}. uncore frequency"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._get_sysfs_path_dies(key, package, die)
                try:
                    self._sysfs_io.write_verify(path, str(freq // 1000), what=what)
                except ErrorVerifyFailed as err:
                    setattr(err, "package", package)
                    setattr(err, "die", die)
                    raise err

    def set_min_freq_dies(self, freq, dies):
        """
        For every die in 'dies', set the minimum uncore frequency for the die (uncore frequency
        domain). The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the minimum uncore frequency.
        Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not exist.
        """

        self._set_freq_dies(freq, "min", dies)

    def set_max_freq_dies(self, freq, dies):
        """
        For every die in 'dies', set the maximum uncore frequency for the die (uncore frequency
        domain). The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * dies - a dictionary indexed by the package numbers with values being lists of die
                   numbers to get the frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the maximum uncore frequency.
        Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not exist.
        """

        self._set_freq_dies(freq, "max", dies)

    def _get_sysfs_path_cpu(self, key, cpu, limit=False):
        """Return the sysfs file path for a CPU-based uncore frequency read or write operation."""

        levels = self._cpuinfo.get_cpu_levels(cpu, levels=("package", "die"))
        package = levels["package"]
        die = levels["die"]

        if self._use_new_sysfs_api():
            return self._get_new_sysfs_api_path(key, package, die, limit=limit)
        return self._get_legacy_sysfs_api_path(key, package, die, limit=limit)

    def _get_freq_cpus(self, key, cpus, limit=False):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the min. or max. uncore
        frequency or frequency limit for the die (uncore frequency domain) corresponding to CPU
        'cpu'.
        """

        what = f"{key}. uncore frequency"
        if limit:
            what += " limit"

        for cpu in cpus:
            path = self._get_sysfs_path_cpu(key, cpu, limit=limit)
            freq = self._sysfs_io.read_int(path, what=what)
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_min_freq_cpus(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum uncore
        frequency for the die (uncore frequency domain) corresponding to CPU 'cpu'. The arguments
        are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequencies for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_cpus("min", cpus)

    def get_max_freq_cpus(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum uncore
        frequency for the die (uncore frequency domain) corresponding to CPU 'cpu'. The arguments
        are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequencies for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_cpus("max", cpus)

    def get_min_freq_limit_cpus(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum uncore
        frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the minimum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_cpus("min", cpus, limit=True)

    def get_max_freq_limit_cpus(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum uncore
        frequency limit for the die (uncore frequency domain) corresponding to CPU 'cpu'. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface to get and return the maximum uncore
        frequency limit in Hz. Raise 'ErrorNotSupported' if the uncore frequency sysfs file does not
        exist.
        """

        yield from self._get_freq_cpus("max", cpus, limit=True)

    def _set_freq_cpus(self, freq, key, cpus):
        """
        For every CPU in 'cpus', set the min. or max. uncore frequency for the die (uncore frequency
        domain) corresponding to the CPU. The arguments are as follows.
        """

        what = f"{key}. uncore frequency"

        for cpu in cpus:
            path = self._get_sysfs_path_cpu(key, cpu)
            try:
                self._sysfs_io.write_verify(path, str(freq // 1000), what=what)
            except ErrorVerifyFailed as err:
                setattr(err, "cpu", cpu)
                raise err

    def set_min_freq_cpus(self, freq, cpus):
        """
        For every CPU in 'cpus', set the minimum uncore frequency for the die (uncore frequency
        domain) corresponding the CPU. The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * cpus - a collection of integer CPU numbers to set the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the minimum uncore frequency.
        """

        self._set_freq_cpus(freq, "min", cpus)

    def set_max_freq_cpus(self, freq, cpus):
        """
        For every CPU in 'cpus', set the maximum uncore frequency for the die (uncore frequency
        domain) corresponding the CPU. The arguments are as follows.
          * freq - the frequency to set, in Hz.
          * cpus - a collection of integer CPU numbers to set the uncore frequency limit for.

        Use the Linux uncore frequency driver sysfs interface set the maximum uncore frequency.
        """

        self._set_freq_cpus(freq, "max", cpus)

    def _add_die(self, package, die, dirname):
        """
        Add package and die numbers to the dies information dictionary. Add the sysfs directory name
        to the sysfs directories map.
        """

        if package not in self._dies_info:
            self._dies_info[package] = []
        self._dies_info[package].append(die)

        if package not in self._dirmap:
            self._dirmap[package] = {}
        self._dirmap[package][die] = dirname

    def _build_dies_info(self):
        """Build the dies information dictionary and the sysfs directories map."""

        self._dies_info = {}
        self._dirmap = {}
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

                self._add_die(package, die, dirname)
        else:
            for dirname in sysfs_base_lsdir:
                match = re.match(r"package_(\d+)_die_(\d+)", dirname)
                if match:
                    package = int(match.group(1))
                    die = int(match.group(2))
                    self._add_die(package, die, dirname)

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

        return self._get_dies_info().copy()

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

    def __init__(self, pman=None, cpuinfo=None, sysfs_io=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to control uncore frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * sysfs_io - an '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                       files.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._sysfs_io = sysfs_io

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_sysfs_io = sysfs_io is None

        self._drv = None
        self._unload_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu/intel_uncore_frequency")

        # List of directory names in 'self._sysfs_base'.
        self._sysfs_base_lsdir = None
        # The new sysfs API is available if 'True'.
        self._has_sysfs_new_api = None

        # The package -> die numbers map.
        self._dies_info = None
        # The sysfs directories map, translating package/die number to the corresponding sysfs
        # directory name. Helps to quickly determine sysfs path in case of the new sysfs API.
        self._dirmap = None
        # 'True' if the uncore frequency was "unlocked" via the legacy sysfs API before starting to
        # use the new sysfs API.
        self._new_sysfs_api_unlocked = False

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        if not self._sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, cpuinfo=cpuinfo, enable_cache=enable_cache)

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
