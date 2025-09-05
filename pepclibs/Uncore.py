# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide a capability of retrieving and setting uncore-related properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import statistics
from pepclibs import _PropsClassBase
from pepclibs.UncoreVars import PROPS
from pepclibs.helperlibs import ClassHelpers, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

# pylint: disable-next=unused-import
from pepclibs._PropsClassBase import ErrorTryAnotherMechanism, ErrorUsePerCPU

if typing.TYPE_CHECKING:
    from typing import Any, Generator, Union
    from pepclibs import _SysfsIO, _UncoreFreqSysfs, _UncoreFreqTpmi
    from pepclibs.CPUInfo import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.PropsTypes import PropertyValueType, MechanismNameType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class Uncore(_PropsClassBase.PropsClassBase):
    """
    This class provides API for managing platform settings related to uncore properties. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo | None = None,
                 msr: Any = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()'). If not provided, one is
                     created.
            msr: Not used, ignored.
            sysfs_io: The sysfs access object ('_SysfsIO.SysfsIO()'). If not provided, one is
                      created.
            enable_cache: Enable property caching if True.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._uncfreq_sysfs_obj: _UncoreFreqSysfs.UncoreFreqSysfs | None = None
        self._uncfreq_sysfs_err: str | None = None

        self._uncfreq_tpmi_obj: _UncoreFreqTpmi.UncoreFreqTpmi | None = None
        self._uncfreq_tpmi_err: str | None = None

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_uncfreq_sysfs_obj", "_uncfreq_tpmi_obj")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()

    def _get_uncfreq_sysfs_obj(self) -> _UncoreFreqSysfs.UncoreFreqSysfs:
        """
        Get an 'UncoreFreqSysfs' object.

        Returns:
            An instance of '_UncoreFreqSysfs.UncoreFreqSysfs'.
        """

        if self._uncfreq_sysfs_err:
            raise ErrorNotSupported(self._uncfreq_sysfs_err)

        if not self._uncfreq_sysfs_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _UncoreFreqSysfs

            sysfs_io = self._get_sysfs_io()
            try:
                obj = _UncoreFreqSysfs.UncoreFreqSysfs(self._cpuinfo, pman=self._pman,
                                                       sysfs_io=sysfs_io,
                                                       enable_cache=self._enable_cache)
                self._uncfreq_sysfs_obj = obj
            except ErrorNotSupported as err:
                self._uncfreq_sysfs_err = str(err)
                raise

        return self._uncfreq_sysfs_obj

    def _get_uncfreq_tpmi_obj(self) -> _UncoreFreqTpmi.UncoreFreqTpmi:
        """
        Get an 'UncoreFreqTpmi' object.

        Returns:
            An instance of '_UncoreFreqTpmi.UncoreFreqTpmi'.
        """

        if self._uncfreq_tpmi_err:
            raise ErrorNotSupported(self._uncfreq_tpmi_err)

        if not self._uncfreq_tpmi_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _UncoreFreqTpmi

            try:
                obj = _UncoreFreqTpmi.UncoreFreqTpmi(self._cpuinfo, pman=self._pman)
                self._uncfreq_tpmi_obj = obj
            except ErrorNotSupported as err:
                self._uncfreq_tpmi_err = str(err)
                raise

        return self._uncfreq_tpmi_obj

    def _get_freq_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield uncore frequency values for the specified CPUs.

        Args:
            pname: Name of the uncore frequency property to retrieve. Supported values are
                   "min_freq", "max_freq", "min_freq_limit", and "max_freq_limit".
            cpus: CPU numbers to retrieve uncore frequency values for.
            mname: Name of the mechanism to use for retrieving the uncore frequency values.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its uncore frequency in
            Hz.
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "min_freq":
            yield from uncfreq_obj.get_min_freq_cpus(cpus)
            return
        if pname == "max_freq":
            yield from uncfreq_obj.get_max_freq_cpus(cpus)
            return

        if mname == "sysfs":
            uncfreq_sysfs_obj = self._get_uncfreq_sysfs_obj()
            if pname == "min_freq_limit":
                yield from uncfreq_sysfs_obj.get_min_freq_limit_cpus(cpus)
                return
            if pname == "max_freq_limit":
                yield from uncfreq_sysfs_obj.get_max_freq_limit_cpus(cpus)
                return

        raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _get_elc_threshold_cpus(self,
                                pname: str,
                                cpus: AbsNumsType,
                                mname: MechanismNameType) -> Generator[tuple[int, int | bool],
                                                                       None, None]:
        """
        Retrieve and yield ELC threshold values for the specified CPUs (either a percentage or a
        boolean indicating enabled/disabled status).

        Args:
            pname: Name of the ELC threshold property to retrieve.
            cpus: CPU numbers to retrieve ELC threshold values for.
            mname: Name of the mechanism to use for retrieving the ELC threshold values.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its ELC threshold
            value (either a percentage or a boolean indicating enabled/disabled status).
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "elc_low_threshold":
            yield from uncfreq_obj.get_elc_low_threshold_cpus(cpus)
        elif pname == "elc_high_threshold":
            yield from uncfreq_obj.get_elc_high_threshold_cpus(cpus)
        elif pname == "elc_high_threshold_status":
            yield from uncfreq_obj.get_elc_high_threshold_status_cpus(cpus)
        elif pname == "elc_low_zone_min_freq":
            yield from uncfreq_obj.get_elc_low_zone_min_freq_cpus(cpus)
        elif pname == "elc_mid_zone_min_freq":
            yield from uncfreq_obj.get_elc_mid_zone_min_freq_cpus(cpus)
        else:
            raise Error(f"BUG: Unexpected ELC threshold property {pname}")

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, PropertyValueType],
                                                                    None, None]:
        """Refer to '_PropsClassBase._get_prop_cpus()'."""

        _LOG.debug("Getting property '%s' using mechanism '%s', cpus: %s",
                   pname, mname, self._cpuinfo.cpus_to_str(cpus))

        if pname in {"min_freq", "max_freq", "min_freq_limit", "max_freq_limit"}:
            yield from self._get_freq_cpus(pname, cpus, mname)
        elif pname in {"elc_low_threshold", "elc_high_threshold", "elc_high_threshold_status",
                       "elc_low_zone_min_freq", "elc_mid_zone_min_freq"}:
            yield from self._get_elc_threshold_cpus(pname, cpus, mname)
        else:
            raise Error(f"BUG: Unknown property '{pname}'")

    def _get_freq_dies(self,
                       pname: str,
                       dies: RelNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield uncore frequency values for the specified dies.

        Args:
            pname: Name of the uncore frequency property to retrieve (e.g., "min_freq").
            dies: Dictionary mapping package numbers to collections of die numbers.
            mname: Name of the mechanism to use for property retrieval.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the uncore frequency or limit.
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "min_freq":
            yield from uncfreq_obj.get_min_freq_dies(dies)
        elif pname == "max_freq":
            yield from uncfreq_obj.get_max_freq_dies(dies)
        elif pname == "elc_low_zone_min_freq":
            yield from uncfreq_obj.get_elc_low_zone_min_freq_dies(dies)
        elif pname == "elc_mid_zone_min_freq":
            yield from uncfreq_obj.get_elc_mid_zone_min_freq_dies(dies)
        elif mname == "sysfs":
            uncfreq_sysfs_obj = self._get_uncfreq_sysfs_obj()
            if pname == "min_freq_limit":
                yield from uncfreq_sysfs_obj.get_min_freq_limit_dies(dies)
            elif pname == "max_freq_limit":
                yield from uncfreq_sysfs_obj.get_max_freq_limit_dies(dies)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property '{pname}'")

    def _get_elc_threshold_dies(self,
                                pname: str,
                                dies: RelNumsType,
                                mname: MechanismNameType) -> Generator[tuple[int, int, int | bool],
                                                                       None, None]:
        """
        Retrieve and yield ELC threshold values for the specified dies (either a percentage or a
        boolean indicating enabled/disabled status).

        Args:
            pname: Name of the ELC threshold property to retrieve.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mname: Name of the mechanism to use for property retrieval.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the ELC threshold value (either a percentage or a boolean
            indicating enabled/disabled status).
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "elc_low_threshold":
            yield from uncfreq_obj.get_elc_low_threshold_dies(dies)
        elif pname == "elc_high_threshold":
            yield from uncfreq_obj.get_elc_high_threshold_dies(dies)
        elif pname == "elc_high_threshold_status":
            yield from uncfreq_obj.get_elc_high_threshold_status_dies(dies)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _get_prop_dies(self,
                       pname: str,
                       dies: RelNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int, PropertyValueType],
                                                              None, None]:
        """Refer to '_PropsClassBase._get_prop_dies()'."""

        _LOG.debug("Getting property '%s' using mechanism '%s', packages/dies: %s",
                   pname, mname, dies)

        # In case of uncore properties, there may be I/O dies, which have no CPUs, so implement
        # per-die access.
        if pname in {"min_freq", "max_freq", "min_freq_limit", "max_freq_limit",
                     "elc_low_zone_min_freq", "elc_mid_zone_min_freq"}:
            yield from self._get_freq_dies(pname, dies, mname)
        elif pname in {"elc_low_threshold", "elc_high_threshold", "elc_high_threshold_status"}:
            yield from self._get_elc_threshold_dies(pname, dies, mname)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _set_prop_cpus(self,
                       pname: str,
                       val: PropertyValueType,
                       cpus: AbsNumsType,
                       mname: MechanismNameType):
        """Refer to '_PropsClassBase._set_prop_cpus()'."""

        # TODO: implement by translating CPU numbers to die num
        raise Error(f"BUG: Unsupported property '{pname}'")

    def _set_numeric_freq_dies(self,
                               pname: str,
                               freq: int,
                               dies: RelNumsType,
                               mname: MechanismNameType):
        """
        Set the minimum or maximum uncore frequency for specified dies.

        Args:
            pname: The property name (e.g., "min_freq").
            freq: The frequency value to set.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mname: Name of the mechanism to use for setting the property.
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "min_freq":
            uncfreq_obj.set_min_freq_dies(freq, dies)
        elif pname == "max_freq":
            uncfreq_obj.set_max_freq_dies(freq, dies)
        elif pname == "elc_low_zone_min_freq":
            uncfreq_obj.set_elc_low_zone_min_freq_dies(freq, dies)
        elif pname == "elc_mid_zone_min_freq":
            uncfreq_obj.set_elc_mid_zone_min_freq_dies(freq, dies)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property {pname}")

    def _get_numeric_freq(self,
                          freq: str | int,
                          dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Convert a user-provided uncore frequency value to its numeric representation in Hz for each
        die.

        Args:
            freq: The frequency value to convert. Can be a numeric value or a special string
                  ("min", "max", "mdl").
            dies: A dictionary mapping package numbers to collections of die numbers.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the resolved frequency in Hz.
        """

        if freq == "min":
            _iterator = self._get_prop_dies_mnames("min_freq_limit", dies, ("sysfs",))
            if typing.TYPE_CHECKING:
                iterator_min = cast(Generator[tuple[int, int, int], None, None], _iterator)
            else:
                iterator_min = _iterator
            yield from iterator_min
        elif freq == "max":
            _iterator = self._get_prop_dies_mnames("max_freq_limit", dies, ("sysfs",))
            if typing.TYPE_CHECKING:
                iterator_max = cast(Generator[tuple[int, int, int], None, None], _iterator)
            else:
                iterator_max = _iterator
            yield from iterator_max
        elif freq == "mdl":
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _UncoreFreqTpmi

            min_limit_iter = self._get_prop_dies_mnames("min_freq_limit", dies, ("sysfs",))
            max_limit_iter = self._get_prop_dies_mnames("max_freq_limit", dies, ("sysfs",))
            iter_zip = zip(min_limit_iter, max_limit_iter)
            if typing.TYPE_CHECKING:
                iterator_mdl = cast(Generator[tuple[tuple[int, int, int], tuple[int, int, int]],
                                              None, None], iter_zip)
            else:
                iterator_mdl = iter_zip
            ratio = _UncoreFreqTpmi.RATIO_MULTIPLIER
            for (package, die, min_limit), (_, _, max_limit) in iterator_mdl:
                yield package, die, ratio * round(statistics.mean([min_limit, max_limit]) / ratio)
        elif isinstance(freq, int):
            for package, pkg_dies in dies.items():
                for die in pkg_dies:
                    yield package, die, freq
        else:
            raise Error(f"BUG: Unexpected non-integer uncore frequency value '{freq}'")

    def _set_freq_dies(self,
                       pname: str,
                       val: str | int,
                       dies: RelNumsType,
                       mname: MechanismNameType):
        """
        Set the uncore frequency property for specified dies using a given method. Handle
        non-numeric values.

        Args:
            pname: Name of the uncore frequency property to set (e.g., 'min_freq').
            val: The value to set for the property. Can be a numeric value or a special string
                 (e.g., 'min', 'max', 'mdl').
            dies: Mapping of package numbers to collections of die numbers.
            mname: Name of the mechanism to use for setting the property.
        """

        freq2dies: dict[int, dict[int, list[int]]] = {}
        for (package, die, new_freq) in self._get_numeric_freq(val, dies):
            if new_freq not in freq2dies:
                freq2dies[new_freq] = {}
            if package not in freq2dies[new_freq]:
                freq2dies[new_freq][package] = []
            freq2dies[new_freq][package].append(die)

        for new_freq, freq_dies in freq2dies.items():
            self._set_numeric_freq_dies(pname, new_freq, freq_dies, mname)

    def _set_elc_threshold_dies(self,
                                pname: str,
                                val: int | bool,
                                dies: RelNumsType,
                                mname: MechanismNameType):
        """
        Enable/disable the an ELC threshold or set and ELC threshold value for specified dies

        Args:
            pname: The property name.
            val: The ELC threshold value (either a percentage or a boolean to enable/disable the
                 threshold).
            dies: Dictionary mapping package numbers to collections of die numbers.
            mname: Name of the mechanism to use for setting the property.
        """

        uncfreq_obj: Union[_UncoreFreqSysfs.UncoreFreqSysfs, _UncoreFreqTpmi.UncoreFreqTpmi]
        if mname == "sysfs":
            uncfreq_obj = self._get_uncfreq_sysfs_obj()
        elif mname == "tpmi":
            uncfreq_obj = self._get_uncfreq_tpmi_obj()
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        if pname == "elc_low_threshold":
            uncfreq_obj.set_elc_low_threshold_dies(cast(int, val), dies)
        elif pname == "elc_high_threshold":
            uncfreq_obj.set_elc_high_threshold_dies(cast(int, val), dies)
        elif pname == "elc_high_threshold_status":
            uncfreq_obj.set_elc_high_threshold_status_dies(cast(bool, val), dies)
        else:
            raise Error(f"BUG: Unexpected uncore ELC threshold property {pname}")

    def _set_prop_dies(self,
                       pname: str,
                       val: PropertyValueType,
                       dies: RelNumsType,
                       mname: MechanismNameType):
        """Refer to '_PropsClassBase._set_prop_dies()'."""

        _LOG.debug("Setting property '%s' to value '%s' using mechanism '%s', packages/dies: %s",
                   pname, val, mname, dies)

        if pname in {"min_freq", "max_freq", "elc_low_zone_min_freq", "elc_mid_zone_min_freq"}:
            if typing.TYPE_CHECKING:
                _val = cast(Union[str, int], val)
            else:
                _val = val
            self._set_freq_dies(pname, _val, dies, mname)
        elif pname in {"elc_low_threshold", "elc_high_threshold", "elc_high_threshold_status"}:
            if typing.TYPE_CHECKING:
                _val = cast(Union[int, bool], val)
            else:
                _val = val
            self._set_elc_threshold_dies(pname, _val, dies, mname)
        else:
            raise Error(f"BUG: Unexpected uncore frequency property {pname}")
