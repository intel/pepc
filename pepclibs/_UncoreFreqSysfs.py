# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
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

On even newer Intel server platforms, that do not support the uncore MSR, the legacy sysfs interface
is not available.

The new sysfs interface uses 'uncoreXX' directories, where XX is a sequence number starting from 0.
The kernel driver assigns these numbers as it enumerates TPMI UFS devices in order of PCI addresses
(lowest to highest), and within each PCI device, it enumerates all UFS feature instances and
clusters. This module maps 'uncoreXX' directories to dies by relying on this enumeration order,
which matches the order of dies from die information (see '_build_dies_info()' for the mapping
implementation).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import math
import typing
from pathlib import Path

from pepclibs import _SysfsIO, _UncoreFreqBase, CPUModels, CPUInfo
from pepclibs.msr import UncoreRatioLimit
from pepclibs.helperlibs import Logging, ClassHelpers, KernelModule, FSHelpers
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, Literal, Sequence
    from pepclibs.PropsTypes import MechanismNameType
    from pepclibs._UncoreFreqBase import ELCThresholdType as _ELCThresholdType
    from pepclibs._UncoreFreqBase import ELCZoneType as _ELCZoneType
    from pepclibs._UncoreFreqBase import FreqValueType as _FreqValueType
    from pepclibs._UncoreFreqBase import UncoreDieInfoTypedDict
    from pepclibs.CPUInfoTypes import RelNumsType, DieInfoTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    # Type for the uncore frequency driver sysfs paths cache. The indexing goes as follows.
    #
    #   ftype[_FreqValueType]: Whether the sysfs path is for a minimum, maximum or current uncore
    #                          frequency file.
    #   package[int] - The package number the sysfs path belongs to.
    #   die[int] - The die number the sysfs path belongs to.
    #   limit[bool] - If 'True', path is about an uncore frequency limit, otherwise the path is
    #                 about the current uncore frequency.
    #
    # Example:
    # {'max': {0: {0: {
    #      False: '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/max_freq_khz',
    #      True:  '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_max_freq_khz'
    #                 },
    #              1: {
    #      False: '/sys/devices/system/cpu/intel_uncore_frequency/uncore01/max_freq_khz',
    #      True:  '/sys/devices/system/cpu/intel_uncore_frequency/uncore01/initial_max_freq_khz'
    #                 },
    #               ... and so on for all dies of package 0 ...
    #          1: {0: {
    #      False: '/sys/devices/system/cpu/intel_uncore_frequency/uncore04/max_freq_khz',
    #      True:  '/sys/devices/system/cpu/intel_uncore_frequency/uncore04/initial_max_freq_khz'
    #                 },
    #               ... and so on for all dies of package 1 ...
    #  'min': {0: {0: {
    #      False: '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/min_freq_khz',
    #      True:  '/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_min_freq_khz'
    #                 },
    #               ... and so on for all packages and dies ...
    _SysfsPathCacheType = dict[_FreqValueType, dict[int, dict[int, dict[bool, Path]]]]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class UncoreFreqSysfs(_UncoreFreqBase.UncoreFreqBase):
    """
    Provide functionality for reading and modifying uncore frequency on Intel CPUs via sysfs.

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

        # The packages->dies mapping.
        self._pkg2dies: dict[int, list[int]] = {}

        # The dictionary that maps package and die numbers to their corresponding sysfs
        # sub-directory names. Example:
        # {0: {0: 'uncore00', 1: 'uncore01', 3: 'uncore02', 4: 'uncore03'},
        #  1: {0: 'uncore04', 1: 'uncore05', 3: 'uncore06', 4: 'uncore07'}}
        self._dirmap: dict[int, dict[int, str]] = {}

        # List of directory names in 'self._sysfs_base'.
        self._lsdir_sysfs_base_cache: list[str] = []

        # The new/legacy sysfs APIs are available if 'True', 'False' if they are not, and 'None' if
        # it is unknown
        self._has_sysfs_new_api: bool | None = None
        self._has_sysfs_legacy_api: bool | None = None

        # 'True' if the uncore frequency was "unlocked" via the legacy sysfs API before starting to
        # use the new sysfs API.
        self._new_sysfs_api_unlocked = False
        # 'True' if ELC sysfs files are present.
        self._elc_supported: bool | None = None

        self._sysfs_io: _SysfsIO.SysfsIO
        if not sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)
        else:
            self._sysfs_io = sysfs_io

        proc_cpuinfo = self._cpuinfo.get_proc_cpuinfo()
        if not CPUModels.is_intel(proc_cpuinfo["vendor"]):
            raise ErrorNotSupported(f"Unsupported CPU model '{self._cpuinfo.cpudescr}'"
                                    f"{self._pman.hostmsg}\nOnly Intel CPU uncore frequency "
                                    f"control is currently supported")

        if not self._pman.exists(self._sysfs_base):
            _LOG.debug("The uncore frequency sysfs directory '%s' does not exist%s.",
                       self._sysfs_base, self._pman.hostmsg)
            self._probe_driver()

    def close(self):
        """Uninitialize the class instance."""

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
        self._has_sysfs_legacy_api = False

        for dirname in self._lsdir_sysfs_base():
            if dirname.startswith("uncore"):
                self._has_sysfs_new_api = True
            if dirname.startswith("package_"):
                self._has_sysfs_legacy_api = True

        _LOG.debug("New sysfs API available: %s, legacy sysfs API available: %s",
                   self._has_sysfs_new_api, self._has_sysfs_legacy_api)

        return self._has_sysfs_new_api

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

    def _read_agent_types(self, path: Path) -> Sequence[str]:
        """
        Read the agent types supported by the die corresponding to the provided uncore frequency
        sysfs sub-directory.

        Args:
            path: The uncore frequency sysfs sub-directory path.

        Returns:
            A collection of agent types supported by the die.

        Raises:
            ErrorNotFound: If the 'agent_types' sysfs file does not exist.
        """

        path = path / "agent_types"
        with self._pman.open(path, "r") as fobj:
            agent_types_str: str = fobj.read()
            agent_types = [atype.strip() for atype in agent_types_str.strip().split(" ")]
            for agent_type in agent_types:
                if agent_type not in CPUInfo.AGENT_TYPES:
                    raise Error(f"Unexpected agent type '{agent_type}' read from {path}"
                                f"{self._pman.hostmsg}, expected one of: "
                                f"{', '.join(CPUInfo.AGENT_TYPES)}")

        return agent_types

    def _build_dies_info(self):
        """
        Build the dies information dictionary that maps package and die numbers to corresponding
        uncore frequency driver sysfs sub-directory names.
        """

        self._dirmap = {}
        sysfs_base_lsdir = self._lsdir_sysfs_base()

        if not self._use_new_sysfs_api():
            for dirname in sysfs_base_lsdir:
                match = re.match(r"package_(\d+)_die_(\d+)", dirname)
                if match:
                    package = int(match.group(1))
                    die = int(match.group(2))
                    self._add_die(package, die, dirname)
            return

        dies_info = self._cpuinfo.get_all_dies_info()

        # Build sorted dictionary for die TPMI information:
        # {addr, {instance: {cluster: tuple[package, die]}}}
        topo_unsorted: dict[str, dict[int, dict[int, tuple[int, int]]]] = {}

        for package, pkg_dies in dies_info.items():
            for die, die_info in pkg_dies.items():
                addr = die_info["addr"]
                instance = die_info["instance"]
                cluster = die_info["cluster"]
                if not addr:
                    raise Error(f"BUG: The new sysfs API is in use{self._pman.hostmsg}, but die "
                                f"{die} in package {package} has no TPMI information")
                topo_unsorted.setdefault(addr, {}).setdefault(instance, {})
                topo_unsorted[addr][instance][cluster] = (package, die)

        # Sort the topology information.
        topo_sorted = {addr: topo_unsorted[addr] for addr in sorted(topo_unsorted)}
        for addr, insts in topo_sorted.items():
            topo_sorted[addr] = {inst: insts[inst] for inst in sorted(insts)}
            for inst, clusters in topo_sorted[addr].items():
                topo_sorted[addr][inst] = {clust: clusters[clust] for clust in sorted(clusters)}

        # Use the fact that the driver enumerates the TPMI devices in the order of TPMI device PCI
        # addresses, which start from package 0 / TPMI partition 0 (see 'tpmi_info', the 'PARTITION'
        # field), then package 0 / TPMI partition 1, etc. Therefore, the order of the 'uncoreXX'
        # directories corresponds to package and die numbers.

        # {dirname: tuple[package, die, die_info]}
        dirname2die_info: dict[str, tuple[int, int, DieInfoTypedDict]] = {}

        dirname_seqnum = 0
        for addr, insts in topo_sorted.items():
            for inst, clusters in insts.items():
                for cluster, (package, die) in clusters.items():
                    die_info = dies_info[package][die]
                    dirname = f"uncore{dirname_seqnum:02d}"
                    dirname2die_info[dirname] = (package, die, die_info)
                    dirname_seqnum += 1

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            # pylint: disable-next=import-outside-toplevel
            import pprint

            _LOG.debug("The sorted topology:\n%s", pprint.pformat(topo_sorted, sort_dicts=False))
            _LOG.debug("The directory to die info mapping:\n%s",
                       pprint.pformat(dirname2die_info, sort_dicts=False))

        index = -1
        for dirname in sorted(sysfs_base_lsdir):
            match = re.match(r"^uncore(\d+)$", dirname)
            if not match:
                continue

            idx = Trivial.str_to_int(match.group(1), base=10,
                                     what=f"'{dirname}' uncore directory index")

            path = self._sysfs_base / dirname

            if idx != index + 1:
                raise Error(f"Unexpected uncore frequency sysfs directory '{path}' found"
                            f"{self._pman.hostmsg}:\nExpected index {index + 1}, got {idx}")
            index = idx

            if dirname not in dirname2die_info:
                raise Error(f"Unexpected uncore frequency sysfs directory '{path}' found"
                            f"{self._pman.hostmsg}")

            with self._pman.open(path / "package_id", "r") as fobj:
                pkg_sysfs_str = fobj.read().strip()
                pkg_sysfs = Trivial.str_to_int(pkg_sysfs_str, base=10,
                                               what=f"package ID from '{dirname}'")

            package, die , die_info = dirname2die_info[dirname]
            if package != pkg_sysfs:
                raise Error(f"Package ID {pkg_sysfs} read from '{path}/package_id' does not match "
                            f"the expected package ID {package}{self._pman.hostmsg}")

            # Detect die type corresponding to this uncore directory.
            try:
                agent_types_sysfs = self._read_agent_types(path)
            except ErrorNotFound:
                # The kernel is probably old and does not provide the 'agent_types' sysfs file.
                # Skip this sanity check.
                pass
            else:
                agent_types = die_info["agent_types"]
                if set(agent_types_sysfs) != set(agent_types):
                    raise Error(f"Agent types read from '{path}/agent_types' do not match the "
                                f"expected agent types for package {package} die {die}"
                                f"{self._pman.hostmsg}:\nExpected: {', '.join(agent_types)}\n"
                                f"Got: {', '.join(agent_types_sysfs)}")

            self._add_die(package, die, dirname)

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
            limit: If True, retrieve the path for a frequency limit file. If False,
                   retrieve the path for a current frequency value file.

        Returns:
            The sysfs file path for the specified sysfs file type, package, die, and limit.
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
                _LOG.debug("Package %d die %d %s is %d Hz, read file '%s'",
                            package, die, what, freq * 1000, path)
                # The frequency value is in kHz in sysfs.
                yield package, die, freq * 1000

    def _construct_elc_zone_freq_path_die(self,
                                          ztype: _ELCZoneType,
                                          ftype: _FreqValueType,
                                          package: int,
                                          die: int) -> Path:
        """
        Retrieve the sysfs file path for an ELC zone frequency.

        Args:
            ztype: The type of ELC zone (e.g., "low").
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: The package number.
            die: The die number within the package.

        Returns:
            The sysfs file path for the specified ELC zone frequency.
        """

        if ftype != "min" or ztype != "low":
            raise ErrorNotSupported(f"ELC {ztype} zone {ftype} uncore frequency is not available")

        return self._sysfs_base / self._get_dirmap()[package][die] / "elc_floor_freq_khz"

    def _check_elc_is_supported(self) -> bool:
        """
        Check if the ELC feature is supported on the current system.

        Returns:
            True if ELC is supported, False otherwise.
        """

        if self._elc_supported is not None:
            return self._elc_supported

        dirmap = self._get_dirmap()
        package = die = -1
        for package, dies in dirmap.items():
            for die in dies:
                break
            break

        if package == -1 or die == -1:
            self._elc_supported = False
        else:
            path = self._construct_elc_zone_freq_path_die("low", "min", package, die)
            self._elc_supported = self._pman.exists(path)

        return self._elc_supported

    def _get_elc_zone_freq_dies(self,
                                ztype: _ELCZoneType,
                                ftype: _FreqValueType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_elc_zone_freq_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {ztype} zone {ftype} uncore frequency"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_elc_zone_freq_path_die(ztype, ftype, package, die)
                freq = self._sysfs_io.read_int(path, what=what)
                _LOG.debug("Package %d die %d %s is %d Hz, read file '%s'",
                           package, die, what, freq * 1000, path)
                # The frequency value is in kHz in sysfs.
                yield package, die, freq * 1000

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

        if not self._has_sysfs_legacy_api:
            return
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

    def _validate_freq(self,
                       freq: int,
                       package: int,
                       die: int,
                       ftype: _FreqValueType,
                       ztype: _ELCZoneType | None = None):
        """
        Validate that a frequency value is within the acceptable range.

        Args:
            freq: The uncore frequency value to validate, in Hz.
            ftype: The uncore frequency value type (e.g., "min" for the minimum frequency).
            package: Package number to validate the frequency for.
            die: Die number to validate the frequency for.
            ztype: The uncore frequency ELC zone type (e.g., "low" for the low zone). The default
                   None value means that this is not an ELC zone frequency.

        Raises:
            ErrorOutOfRange: If the uncore frequency value is outside the allowed range.
            ErrorBadOrder: If min. uncore frequency is greater than max. uncore frequency.
        """

        if ztype:
            zname = f"ELC {ztype} zone "
        else:
            zname = ""

        path = self._construct_freq_path_die("min", package, die, limit=True)
        what = f"{zname}min uncore frequency limit for package {package} die {die}"
        min_freq_limit = self._sysfs_io.read_int(path, what=what) * 1000

        path = self._construct_freq_path_die("max", package, die, limit=True)
        what = f"{zname}max uncore frequency limit for package {package} die {die}"
        max_freq_limit = self._sysfs_io.read_int(path, what=what) * 1000

        min_freq: int | None = None
        max_freq: int | None = None

        if ftype == "min":
            path = self._construct_freq_path_die("max", package, die)
            what = f"{zname}max package {package} die {die} uncore frequency"
            max_freq = self._sysfs_io.read_int(path, what=what) * 1000
        else:
            path = self._construct_freq_path_die("min", package, die)
            what = f"{zname}min package {package} die {die} uncore frequency"
            min_freq = self._sysfs_io.read_int(path, what=what) * 1000

        self._validate_frequency(freq, ftype, package, die, min_freq_limit, max_freq_limit,
                                 min_freq=min_freq, max_freq=max_freq, zname=zname)

    def _set_freq_dies(self, freq: int, ftype: _FreqValueType, dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_freq_dies()'."""

        if self._use_new_sysfs_api():
            self._unlock_new_sysfs_api()

        what = f"{ftype} uncore frequency"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                self._validate_freq(freq, package, die, ftype)
                path = self._construct_freq_path_die(ftype, package, die)
                self._sysfs_io.write_int(path, freq // 1000, what=what)
                _LOG.debug("Set package %d die %d %s to %d Hz, wrote file '%s'",
                           package, die, what, freq, path)

    def _set_elc_zone_freq_dies(self,
                                freq: int,
                                ztype: _ELCZoneType,
                                ftype: _FreqValueType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_zone_freq_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {ztype} zone {ftype} uncore frequency"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                self._validate_freq(freq, package, die, ftype, ztype=ztype)
                path = self._construct_elc_zone_freq_path_die(ztype, ftype, package, die)
                self._sysfs_io.write_int(path, freq // 1000, what=what)
                _LOG.debug("Set package %d die %d %s to %d Hz, wrote file '%s'",
                           package, die, what, freq, path)

    def _probe_driver(self):
        """
        Attempt to determine and load the required kernel module for uncore frequency support.
        """

        proc_cpuinfo = self._cpuinfo.get_proc_cpuinfo()
        vfm = proc_cpuinfo["vfm"]
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
                                          die: int,
                                          suffix: Literal["percent", "enable"] = "percent") -> Path:
        """
        Construct and return the sysfs file path for an ELC threshold read or write operation.

        Args:
            thrtype: The type of ELC threshold ("low" or "high").
            package: The package number to construct the path for.
            die: The die number within the package to construct the path for.
            suffix: The sysfs file suffix, defaults to "percent", which corresponds to the ELC
                    threshold percent sysfs file.

        Returns:
            Path to the requested uncore frequency sysfs file.
        """

        fname = f"elc_{thrtype}_threshold_{suffix}"
        return self._sysfs_base / self._get_dirmap()[package][die] / fname

    def _get_elc_threshold_dies(self,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """Refer to '_UncoreFreqBase._get_elc_threshold_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {thrtype} threshold"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_elc_threshold_path_die(thrtype, package, die)
                threshold = self._sysfs_io.read_int(path, what=what)
                _LOG.debug("Package %d die %d %s is %d%%, read file '%s'",
                           package, die, what, threshold, path)
                yield package, die, threshold

    def _get_elc_threshold_status_dies(self,
                                       thrtype: _ELCThresholdType,
                                       dies: RelNumsType) -> Generator[tuple[int, int, bool],
                                                                       None, None]:
        """Refer to '_UncoreFreqBase._get_elc_threshold_status_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {thrtype} threshold enabled/disabled status"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_elc_threshold_path_die(thrtype, package, die,
                                                              suffix="enable")
                status = self._sysfs_io.read_int(path, what=what)
                _LOG.debug("Package %d die %d %s is %s, read file '%s'",
                           package, die, what, status, path)
                yield package, die, bool(status)

    def _set_elc_threshold_dies(self,
                                threshold: int,
                                thrtype: _ELCThresholdType,
                                dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {thrtype} threshold"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                self._validate_elc_threshold(threshold, thrtype, package, die)
                path = self._construct_elc_threshold_path_die(thrtype, package, die)
                # Round the threshold up, following the kernel driver approach.
                _LOG.debug("Setting package %d die %d %s to %d%% via file '%s'",
                           package, die, what, threshold, path)
                self._sysfs_io.write_int(path, math.ceil(threshold), what=what)

    def _set_elc_threshold_status_dies(self,
                                       status: bool,
                                       thrtype: _ELCThresholdType,
                                       dies: RelNumsType):
        """Refer to '_UncoreFreqBase._set_elc_threshold_status_dies()'."""

        if not self._check_elc_is_supported():
            raise ErrorNotSupported("ELC is not supported on this system")

        what = f"ELC {thrtype} threshold enabled/disabled status"

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                path = self._construct_elc_threshold_path_die(thrtype, package, die,
                                                              suffix="enable")
                _LOG.debug("Setting package %d die %d %s to %s via file '%s'",
                           package, die, what, status, path)
                self._sysfs_io.write_int(path, int(status), what=what)

    def _fill_dies_info(self, dies_info: dict[int, dict[int, UncoreDieInfoTypedDict]]):
        """
        Fill in the dies information dictionary.

        Args:
            dies_info: The dies information dictionary to fill in.
        """

        for package, pkg_dies in dies_info.items():
            for die, die_info in pkg_dies.items():
                path = self._sysfs_base / self._get_dirmap()[package][die]
                die_info["path"] = path
