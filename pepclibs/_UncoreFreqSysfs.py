# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Tero Kristo <tero.kristo@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide functionality for reading and modifying uncore frequency on Intel CPUs via sysfs.

On older Intel server platforms, such as Skylake Xeon and Sapphire Rapids Xeon, uncore frequency is
managed via an MSR. The Linux kernel 'intel_uncore_frequency' driver exposes a sysfs interface that
programs the MSR behind the scenes. This sysfs interface operates on a per-die basis. For example,
the uncore frequency for package 0, die 1 is controlled through sysfs files located in the
"package_01_die_00" sub-directory. This sysfs interface is referred to as the legacy interface in
this python module.

On newer Intel server platforms, such as Granite Rapids Xeon, uncore frequency is managed via TPMI,
and the Linux kernel provides the 'intel_uncore_frequency_tpmi' driver. The TPMI driver exposes both
the legacy and a new sysfs interfaces. The legacy interface is limited, so this module uses the new
interface when available.

The new sysfs interface operates in terms of "uncore frequency domains". On current Intel server
platforms the uncore domain IDs correspond to die IDs, and this project refers to uncore domains as
"dies".
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import math
from typing import Generator
from pathlib import Path
from pepclibs import _SysfsIO, CPUInfo, _UncoreFreqBase
from pepclibs._PropsClassBaseTypes import MechanismNameType
from pepclibs._UncoreFreqBase import FreqValueType as _FreqValueType
from pepclibs._UncoreFreqBase import ELCThresholdType as _ELCThresholdType
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.CPUInfoTypes import RelNumsType, AbsNumsType
from pepclibs.msr import UncoreRatioLimit
from pepclibs.helperlibs import Logging, ClassHelpers, KernelModule, FSHelpers
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Type for the uncore frequency driver sysfs paths cache. The indexing goes as follows.
#
#   ftype[_FreqValueType]: Whether the sysfs path is for a minimum, maximum or current uncore
#                          frequency file.
#   package[int] - The package number the sysfs path belongs to.
#   die[int] - The die number the sysfs path belongs to.
#   limit[bool] - If 'True', path is about an uncore frequency limit, otherwise the path is about
#                  the current uncore frequency.
#
# Example:
# {'max': {0: {0: {False:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/max_freq_khz',
#                  True:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_max_freq_khz'},
#              1: {False:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore01/max_freq_khz',
#                  True:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore01/initial_max_freq_khz'},
#
#               ... and so on for all dies of package 0 ...
#
#          1: {0: {False:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore04/max_freq_khz',
#                  True:
#                  '/sys/devices/system/cpu/intel_uncore_frequency/uncore04/initial_max_freq_khz'},
#
#               ... and so on for all dies of package 1 ...
#
#  'min': {0: {0: {False:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/min_freq_khz',
#                  True:
#                   '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_min_freq_khz'},
#
#               ... and so on for all packages and dies ...
_SysfsPathCacheType = dict[_FreqValueType, dict[int, dict[int, dict[bool, Path]]]]

class UncoreFreqSysfs(_UncoreFreqBase.UncoreFreqBase):
    """
    Provide functionality for reading and modifying uncore frequency on Intel CPUs via sysfs.

    Overview of public methods:

    1. Get or set uncore frequency via Linux sysfs interface:
        * Per-die:
            - get_min_freq_dies()
            - get_max_freq_dies()
            - set_min_freq_dies()
            - set_max_freq_dies()
            - get_cur_freq_dies()
        * Per-CPU:
            - get_min_freq_cpus()
            - get_max_freq_cpus()
            - set_min_freq_cpus()
            - set_max_freq_cpus()
            - get_cur_freq_cpus()
    2. Retrieve uncore frequency limits via Linux sysfs interfaces:
        * Per-die:
            - 'get_min_freq_limit_dies()'
            - 'get_max_freq_limit_dies()'
        * Per-CPU:
            - 'get_min_freq_limit_cpus()'
            - 'get_max_freq_limit_cpus()'
    3. Get or set ELC thresholds.
        * Per-die:
            - get_elc_low_threshold_dies()
            - get_elc_high_threshold_dies()
            - set_elc_low_threshold_dies()
            - set_elc_high_threshold_dies()
        * Per-CPU:
            - get_elc_low_threshold_cpus()
            - get_elc_high_threshold_cpus()
            - set_elc_low_threshold_cpus()
            - set_elc_high_threshold_cpus()

    Note: Methods of this class do not validate the 'cpus' and 'dies' arguments. The caller is
    responsible for ensuring that the provided package, die, and CPU numbers exist and that CPUs are
    online.
    """

    mname: MechanismNameType = "sysfs"

    def __init__(self,
                 cpuinfo: CPUInfo.CPUInfo,
                 pman: ProcessManagerType | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()').
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            sysfs_io: The sysfs access object ('_SysfsIO.SysfsIO()'). If not provided, one is
                      created.
            enable_cache: Enable caching if True. Used only if 'sysfs_io' is not provided.
        """

        super().__init__(cpuinfo, pman, enable_cache=enable_cache)

        self._close_sysfs_io = sysfs_io is None

        self._drv: KernelModule.KernelModule | None = None
        self._unload_drv = False

        self._sysfs_base = Path("/sys/devices/system/cpu/intel_uncore_frequency")
        self._path_cache: _SysfsPathCacheType = {}

        # The package -> die numbers map.
        self._pkg2dies: dict[int, list[int]]= {}

        # The dictionary that maps package and die numbers to their corresponding sysfs
        # sub-directory names. Example:
        # {0: {0: 'uncore00', 1: 'uncore01', 3: 'uncore02', 4: 'uncore03'},
        #  1: {0: 'uncore04', 1: 'uncore05', 3: 'uncore06', 4: 'uncore07'}}
        self._dirmap: dict[int, dict[int, str]] = {}

        # List of directory names in 'self._sysfs_base'.
        self._lsdir_sysfs_base_cache: list[str] = []

        # The new sysfs API is available if 'True', 'False' if it is not, and 'None' if it is
        # unknown.
        self._has_sysfs_new_api: bool | None = None
        # 'True' if the uncore frequency was "unlocked" via the legacy sysfs API before starting to
        # use the new sysfs API.
        self._new_sysfs_api_unlocked = False

        self._sysfs_io: _SysfsIO.SysfsIO
        if not sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)
        else:
            self._sysfs_io = sysfs_io

        vendor = self._cpuinfo.info["vendor"]
        if vendor != "GenuineIntel":
            raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor}'{self._pman.hostmsg}\nOnly"
                                    f"Intel CPU uncore frequency control is currently supported")

        if not self._pman.exists(self._sysfs_base):
            _LOG.debug("The uncore frequency sysfs directory '%s' does not exist%s.",
                       self._sysfs_base, self._pman.hostmsg)
            self._probe_driver()

    def close(self):
        """Uninitialize the class object."""

        if self._unload_drv:
            assert self._drv is not None
            self._drv.unload()

        close_attrs = ("_sysfs_io", "_drv")
        ClassHelpers.close(self, close_attrs=close_attrs)

        self._path_cache = {}
        self._dirmap = {}
        self._pkg2dies = {}
        self._lsdir_sysfs_base_cache = []

        super().close()

    def _lsdir_sysfs_base(self) -> list[str]:
        """
        List files and directories in the uncore frequency driver's base sysfs directory.

        Returns:
            Names of files and directories in the uncore frequency driver's base sysfs directory.
        """

        if self._lsdir_sysfs_base_cache:
            return self._lsdir_sysfs_base_cache

        for entry in self._pman.lsdir(self._sysfs_base):
            self._lsdir_sysfs_base_cache.append(entry["name"])

        return self._lsdir_sysfs_base_cache

    def _use_new_sysfs_api(self) -> bool:
        """
        Determine if the new uncore frequency driver sysfs interface is available.

        Returns:
            True if the new uncore frequency driver sysfs interface is available, False otherwise.
        """

        if self._has_sysfs_new_api is not None:
            return self._has_sysfs_new_api

        self._has_sysfs_new_api = False
        for dirname in self._lsdir_sysfs_base():
            if dirname.startswith("uncore"):
                self._has_sysfs_new_api = True
                break

        _LOG.debug("Using the %s uncore frequency sysfs interface",
                   "new" if self._has_sysfs_new_api else "old")
        return self._has_sysfs_new_api

    def _get_dies_info(self) -> RelNumsType:
        """
        Retrieve the dies information dictionary.

        Returns:
            The dies information dictionary, mapping package numbers to their corresponding die
            numbers.
        """

        if not self._pkg2dies:
            self._build_dies_info()
        return self._pkg2dies

    def _get_dirmap(self) -> dict[int, dict[int, str]]:
        """
        Retrieve the sysfs directory map for uncore frequency control.

        Returns:
            A mapping of package and die numbers to their corresponding uncore frequency driver
            sysfs sub-directory names.
        """

        if not self._dirmap:
            self._build_dies_info()
        return self._dirmap

    def _construct_new_freq_path(self,
                                 ftype: _FreqValueType,
                                 package: int,
                                 die: int,
                                 limit: bool = False) -> Path:
        """
        Construct and return the new sysfs API file path for uncore frequency read or write
        operations.

        Args:
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: The package number to construct the path for.
            die: The die number within the package to construct the path for.
            limit: If True, construct the path for an uncore frequency limit sysfs file.

        Returns:
            Path to the requested uncore frequency sysfs file.
        """

        prefix = "initial_" if limit else ""
        fname = prefix + ftype + "_freq_khz"
        return self._sysfs_base / self._get_dirmap()[package][die] / fname

    def _construct_legacy_freq_path(self,
                                    ftype: _FreqValueType,
                                    package: int,
                                    die: int,
                                    limit: bool = False) -> Path:
        """
        Construct and return the legacy sysfs API file path for uncore frequency read or write
        operations.

        Args:
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: The package number to construct the path for.
            die: The die number within the package to construct the path for.
            limit: If True, construct the path for an uncore frequency limit sysfs file.

        Returns:
            Path to the requested uncore frequency sysfs file.
        """

        prefix = "initial_" if limit else ""
        fname = prefix + ftype + "_freq_khz"
        return self._sysfs_base / f"package_{package:02d}_die_{die:02d}" / fname

    def _construct_freq_path_die(self,
                                 ftype: _FreqValueType,
                                 package: int,
                                 die: int,
                                 limit: bool = False) -> Path:
        """
        Retrieve the sysfs file path for an uncore frequency read or write operation.

        Args:
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: The package number.
            die: The die number within the package.
            limit: if True, retrieve the path for a frequency limit file. If False,
                   retrieve the path for a current frequency value file.

        Returns:
            The sysfs file path as a string for the specified sysfs file type, package, die, and
            limit.
        """

        if ftype not in self._path_cache:
            self._path_cache[ftype] = {}
        if package not in self._path_cache[ftype]:
            self._path_cache[ftype][package] = {}
        if die not in self._path_cache[ftype][package]:
            self._path_cache[ftype][package][die] = {}

        cached_path = self._path_cache[ftype][package][die].get(limit)
        if cached_path:
            return cached_path

        if self._use_new_sysfs_api():
            path = self._construct_new_freq_path(ftype, package, die, limit=limit)
        else:
            path = self._construct_legacy_freq_path(ftype, package, die, limit=limit)

        self._path_cache[ftype][package][die][limit] = path
        return path

    def _get_freq_dies(self,
                       ftype: _FreqValueType,
                       dies: RelNumsType,
                       limit: bool = False) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_freq_dies()'."""

        what = f"{ftype} uncore frequency"
        if limit:
            what += " limit"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_freq_path_die(ftype, package, die, limit=limit)
                freq = self._sysfs_io.read_int(path, what=what)
                # The frequency value is in kHz in sysfs.
                yield package, die, freq * 1000

    def get_min_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the minimum uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the minimum uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the minimum uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
        """

        yield from self._get_freq_dies("min", dies)

    def get_max_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the maximum uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the maximum uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the maximum uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
        """

        yield from self._get_freq_dies("max", dies)

    def get_min_freq_limit_dies(self,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the minimum uncore frequency limit for each die in the provided
        package->die mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the minimum uncore frequency limit.

        Yields:
            Tuples of (package, die, value), where 'value' is the minimum uncore frequency limit for
            the specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency limit sysfs file does not exist.
        """

        yield from self._get_freq_dies("min", dies, limit=True)

    def get_max_freq_limit_dies(self,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the maximum uncore frequency limit for each die in the provided
        package->die mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the maximum uncore frequency limit.

        Yields:
            Tuples of (package, die, value), where 'value' is the maximum uncore frequency limit for
            the specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency limit sysfs file does not exist.
        """

        yield from self._get_freq_dies("max", dies, limit=True)

    def get_cur_freq_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield the current uncore frequency for each die in the provided packages->dies
        mapping.

        Args:
            dies: Dictionary mapping package numbers to sequences of die numbers for which to yield
                  the current uncore frequency.

        Yields:
            Tuples of (package, die, value), where 'value' is the current uncore frequency for the
            specified die in the specified package, in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
        """

        yield from self._get_freq_dies("current", dies)

    def _unlock_new_sysfs_api(self):
        """
        Unlock the new sysfs API for uncore frequency control by removing limits set via the legacy
        sysfs API.

        The "intel_uncore_frequency_tpmi" kernel driver has unintuitive behavior: minimum and
        maximum uncore frequencies configured through the legacy sysfs API restrict the range of
        frequencies that can be set using the new sysfs API. For example, if the maximum uncore
        frequency limit is 2 GHz, but the maximum frequency was set to 1 GHz via the legacy API,
        you cannot set it above 1 GHz using the new API.

        This method works around this strange driver behavior by restoring the legacy min/max
        frequency values to their limit values, effectively "unlocking" the new sysfs API and
        allowing the full frequency range to be configured.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs files do not exist.
        """

        if self._new_sysfs_api_unlocked:
            return

        # When the new sysfs API is available, the legacy sysfs API exposes sysfs files only for die
        # 0, which actually controls all dies in the package. Therefore, iterate only the packages,
        # but not dies.
        for package, dies in self._get_dies_info().items():
            for ftype in "min", "max":
                # Get the frequency limit value via the legacy API.
                path_legacy_limit = self._construct_legacy_freq_path(ftype, package, 0, limit=True)
                what_limit = f"{ftype} uncore frequency limit"
                freq_limit_legacy = self._sysfs_io.read_int(path_legacy_limit, what=what_limit)

                # Get min. or max. frequency value via the legacy API.
                path_legacy = self._construct_legacy_freq_path(ftype, package, 0, limit=False)
                what = f"{ftype} uncore frequency"
                freq_legacy = self._sysfs_io.read_int(path_legacy, what=what)
                if freq_legacy == freq_limit_legacy:
                    # Nothing to do, the legacy API won't be a limiting factor, because the min.
                    # or max. frequency is already at its limit value.
                    continue

                # Get the current min. or max. frequency values via the new API, in order to restore
                # them later.
                paths_new = {}
                freqs_new = {}
                for die in dies:
                    paths_new[die] = self._construct_new_freq_path(ftype, package, die,
                                                                    limit=False)
                    freqs_new[die] = self._sysfs_io.read_int(paths_new[die], what=what)

                # Set min. or max. frequency limit via the legacy interface. This should "unlock"
                # the new sysfs API.
                self._sysfs_io.write_int(path_legacy, freq_limit_legacy, what=what)

                # Restore the current min. or max. frequency values via the new API.
                for die in dies:
                    self._sysfs_io.write_int(paths_new[die], freqs_new[die], what=what)

        self._new_sysfs_api_unlocked = True

    def _validate_freq(self, freq: int, ftype: _FreqValueType, package: int, die: int):
        """
        Validate that a frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        path = self._construct_freq_path_die("min", package, die, limit=True)
        what = f"min uncore frequency limit for package {package} die {die}"
        min_freq_limit = self._sysfs_io.read_int(path, what=what) * 1000

        path = self._construct_freq_path_die("max", package, die, limit=True)
        what = f"max uncore frequency limit for package {package} die {die}"
        max_freq_limit = self._sysfs_io.read_int(path, what=what) * 1000

        min_freq: int | None = None
        max_freq: int | None = None

        if ftype == "min":
            path = self._construct_freq_path_die("max", package, die)
            what = f"max package {package} die {die} uncore frequency"
            max_freq = self._sysfs_io.read_int(path, what=what) * 1000
        else:
            path = self._construct_freq_path_die("min", package, die)
            what = f"min package {package} die {die} uncore frequency"
            min_freq = self._sysfs_io.read_int(path, what=what) * 1000

        self._validate_frequency(freq, ftype, package, die, min_freq_limit, max_freq_limit,
                                 min_freq=min_freq, max_freq=max_freq)

    def _set_freq_dies(self, freq: int, ftype: _FreqValueType, dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_freq_dies()'."""

        if self._use_new_sysfs_api():
            self._unlock_new_sysfs_api()

        what = f"{ftype} uncore frequency"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                self._validate_freq(freq, ftype, package, die)
                path = self._construct_freq_path_die(ftype, package, die)
                self._sysfs_io.write_int(path, freq // 1000, what=what)

    def set_uncore_low_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set the minimum uncore frequency for each die in the provided packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        self._set_freq_dies(freq, "min", dies)

    def set_max_freq_dies(self, freq: int, dies: RelNumsType):
        """
        Set the maximum uncore frequency for each die in the provided packages->dies mapping.

        Args:
            freq: The frequency value to set, in Hz.
            dies: Dictionary mapping package numbers to die numbers.

        Raises:
            ErrorNotSupported: If the uncore frequency sysfs file does not exist.
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency and vice
                           versa.
        """

        self._set_freq_dies(freq, "max", dies)

    def get_min_freq_limit_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the minimum uncore frequency limit for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the minimum uncore frequency limit
                  for.

        Yields:
            Tuple (cpu, value), where 'value' is the minimum uncore frequency limit for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency limit sysfs file does not exist.
        """

        yield from self._get_freq_cpus("min", cpus, limit=True)

    def get_max_freq_limit_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield the maximum uncore frequency limit for each CPU in 'cpus'.

        Args:
            cpus: A collection of integer CPU numbers to retrieve the maximum uncore frequency limit
                  for.

        Yields:
            Tuple (cpu, value), where 'value' is the maximum uncore frequency limit for the die
            corresponding to 'cpu', in Hz.

        Raises:
            ErrorNotSupported: If the uncore frequency limit sysfs file does not exist.
        """

        yield from self._get_freq_cpus("max", cpus, limit=True)

    def _add_die(self, package: int, die: int, dirname: str):
        """
        Add package, die and sysfs sub-directory name information to the 'self._pkg2dies' and
        'self._dirmap' caches.

        Args:
            package: Package number to add.
            die: Die number to add.
            dirname: Sysfs subdirectory name to add.
        """

        if package not in self._pkg2dies:
            self._pkg2dies[package] = []
        self._pkg2dies[package].append(die)

        if package not in self._dirmap:
            self._dirmap[package] = {}
        self._dirmap[package][die] = dirname

    def _build_dies_info(self):
        """
        Build the dies information dictionary that maps package and die numbers to corresponding
        uncore frequency driver sysfs sub-directory names.
        """

        self._dirmap = {}
        sysfs_base_lsdir = self._lsdir_sysfs_base()

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

    def _probe_driver(self):
        """
        Attempt to determine and load the required kernel module for uncore frequency support.
        """

        vfm = self._cpuinfo.info["vfm"]
        errmsg = ""

        # If the CPU supports MSR_UNCORE_RATIO_LIMIT, the uncore frequency driver is
        # "intel_uncore_frequency".
        if vfm in UncoreRatioLimit.FEATURES["max_ratio"]["vfms"]:
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
            _LOG.debug("The uncore frequency driver '%s' is loaded, but the sysfs directory '%s' "
                       "does not exist\n%s.", drvname, self._sysfs_base, msg)
            errmsg = msg
        else:
            try:
                assert self._drv is not None
                self._drv.load()
                self._unload_drv = True
                FSHelpers.wait_for_a_file(self._sysfs_base, timeout=1, pman=self._pman)
            except Error as err:
                _LOG.debug("%s\n%s.", err, msg)
                errmsg = msg

        if errmsg:
            raise ErrorNotSupported(errmsg)

    def _construct_elc_threshold_path_die(self,
                                          thrtype: _ELCThresholdType,
                                          package: int,
                                          die: int) -> Path:
        """
        Construct and return the sysfs file path for an ELC threshold read or write operation.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            package: The package number to construct the path for.
            die: The die number within the package to construct the path for.

        Returns:
            Path to the requested uncore frequency sysfs file.
        """

        fname = f"elc_{thrtype}_threshold_percent"
        return self._sysfs_base / self._get_dirmap()[package][die] / fname

    def _get_elc_threshold_dies(self,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_elc_threshold_dies()'."""

        what = f"ELC {thrtype} threshold"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_elc_threshold_path_die(thrtype, package, die)
                threshold = self._sysfs_io.read_int(path, what=what)
                yield package, die, int(threshold)

    def _set_elc_threshold_dies(self,
                                threshold: int,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_dies()'."""

        what = f"ELC {thrtype} threshold"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                self._validate_elc_threshold(threshold, thrtype, package, die)
                path = self._construct_elc_threshold_path_die(thrtype, package, die)
                # Round the threshold up, following the kernel driver approach.
                self._sysfs_io.write_int(path, math.ceil(threshold), what=what)
