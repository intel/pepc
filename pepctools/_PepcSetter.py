# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>

"""
Provide API for changing properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
from pepctools import _PepcCommon
from pepctools._OpTarget import ErrorNoCPUTarget
from pepclibs.helperlibs import ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder
from pepclibs.msr import MSR

if typing.TYPE_CHECKING:
    from typing import TypedDict, Sequence, Iterable, Literal, Union
    from pepctools import _OpTarget, _PepcPrinter
    from pepclibs import CPUInfo, _SysfsIO, PStates, CStates, Uncore, PMQoS
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.PropsTypes import MechanismNameType, PropertyValueType, PropsClassType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

    _PepcPrinterClassType = Union[_PepcPrinter.CStatesPrinter, _PepcPrinter.PStatesPrinter,
                                  _PepcPrinter.UncorePrinter, _PepcPrinter.PMQoSPrinter]

    class PropSetInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary describing a property to be set to a value.

        Attributes:
            val: The value to assign to the property.
            default_unit: The default unit of the property.
            mnames: Mechanism names to use for setting the property.
        """

        val: str
        default_unit: str
        mnames: Sequence[MechanismNameType]

class _PropsSetter(ClassHelpers.SimpleCloseContext):
    """Base class for pepc property setter classes."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: PropsClassType,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinterClassType,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """
        Initialize a class instance.

        Args:
            pman: Process manager object for the target host.
            pobj: The properties object (e.g., 'PStates') to print the properties for.
            cpuinfo: The 'CPUInfo' object for to the host from which properties are read.
            pprinter: The property printer object for and printing properties after they are set.
            msr: Optional MSR object for an MSR transaction.
            sysfs_io: Optional SysfsIO object for a file I/O transaction.
        """

        self._pman = pman
        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._pprinter = pprinter
        self._msr = msr
        self._sysfs_io = sysfs_io

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, unref_attrs=("_sysfs_io", "_msr", "_pprinter", "_cpuinfo", "_pobj",
                                              "_pman"))

    def _do_set_prop_sname(self,
                           pname: str,
                           optar: _OpTarget.OpTarget,
                           val: PropertyValueType,
                           mnames: Sequence[MechanismNameType]) -> MechanismNameType:
        """
        Set a property to a value, accounting for its scope.

        Args:
            pname: Name of the property to set.
            optar: Operation target object specifying CPUs, packages, etc.
            val: The value to set the property to.
            mnames: Mechanism names to use for setting the property.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNoCPUTarget: If no valid CPUs/dies/packages can be determined for the operation.
        """

        try:
            sname, nums = _PepcCommon.get_sname_and_nums(self._pobj, pname, optar)
        except ErrorNoCPUTarget as err:
            name = self._pobj.props[pname]["name"]
            raise ErrorNoCPUTarget(f"Impossible to set {name}:\n{err.indent(2)}") from err

        if sname == "die":
            if typing.TYPE_CHECKING:
                nums = cast(RelNumsType, nums)
            return self._pobj.set_prop_dies(pname, val, nums, mnames=mnames)

        if typing.TYPE_CHECKING:
            nums = cast(AbsNumsType, nums)

        if sname == "CPU":
            return self._pobj.set_prop_cpus(pname, val, nums, mnames=mnames)

        return self._pobj.set_prop_packages(pname, val, nums, mnames=mnames)

    def _set_prop_sname(self,
                        spinfo: dict[str, PropSetInfoTypedDict],
                        pname: str,
                        optar: _OpTarget.OpTarget,
                        mnames: Sequence[MechanismNameType],
                        mnames_info: dict[str, MechanismNameType]):
        """
        Set the property.

        Args:
            spinfo: Dictionary mapping property names to their information, such as the value to
                    set.
            pname: The name of the property to set.
            optar: The operation target object defining the processor topology entities (CPUs,
                   cores, etc) to set property for.
            mnames: Mechanism names allowed for setting the property. An empty sequence (default)
                    means that all mechanisms are allowed.
            mname_info: A dictionary where the mechanism used for setting the property is stored.
        """

        if pname not in spinfo:
            return

        mname = self._do_set_prop_sname(pname, optar, spinfo[pname]["val"], mnames=mnames)
        del spinfo[pname]
        mnames_info[pname] = mname

    @staticmethod
    def _set_prop(pobj: PropsClassType,
                  pname: str,
                  sname: ScopeNameType,
                  val: PropertyValueType,
                  nums: AbsNumsType | RelNumsType):
        """
        Set a property for a given scope using the appropriate method.

        Args:
            pobj: The properties object that manages properties and provides methods for setting
                  them.
            pname: The name of the property to set.
            sname: The scope name where to set the property (e.g., "CPU", "die", package)".
            val: The value to assign to the property.
            nums: The identifiers (absolute or relative) specifying the targets within the scope.
        """

        if sname == "CPU":
            if typing.TYPE_CHECKING:
                nums = cast(AbsNumsType, nums)
            pobj.set_prop_cpus(pname, val, nums)
        elif sname == "die":
            if typing.TYPE_CHECKING:
                nums = cast(RelNumsType, nums)
            pobj.set_prop_dies(pname, val, cast(RelNumsType, nums))
        elif sname == "package":
            if typing.TYPE_CHECKING:
                nums = cast(AbsNumsType, nums)
            pobj.set_prop_packages(pname, val, nums)
        else:
            raise Error(f"BUG: Unsupported scope name '{sname}' for property '{pname}'")

    def set_props(self,
                  spinfo: dict[str, PropSetInfoTypedDict],
                  optar: _OpTarget.OpTarget):
        """
        Set properties specified CPUs, cores, modules, or other targets.

        Args:
            spinfo: Dictionary mapping property names to their information, such as the value to
                    set.
            optar: The operation target object defining the processor topology entities (CPUs,
                   cores, etc) to set properties for.
        """

        # Remember the mechanism used for every option.
        mnames_info: dict[str, MechanismNameType] = {}

        # '_set_props()' needs to modify the 'spinfo' dictionary, so create a copy.
        spinfo_copy = spinfo.copy()

        # Translate values without unit to the default units.
        for pname, pname_info in spinfo.items():
            if "default_unit" not in pname_info:
                continue

            try:
                val = Trivial.str_to_num(pname_info["val"])
            except Error:
                # Not a number, which means there is a unit specified.
                continue

            # Append the default unit.
            spinfo_copy[pname]["val"] = str(val) + pname_info["default_unit"]

        if self._sysfs_io:
            self._sysfs_io.start_transaction()
        if self._msr:
            self._msr.start_transaction()

        for pname in list(spinfo):
            mnames = spinfo[pname]["mnames"]
            self._set_prop_sname(spinfo_copy, pname, optar, mnames, mnames_info)

        if self._msr:
            self._msr.commit_transaction()
        if self._sysfs_io:
            self._sysfs_io.commit_transaction()

        if self._pprinter:
            for pname in spinfo:
                mnames = (mnames_info[pname], )
                self._pprinter.print_props((pname,), optar, mnames=mnames, skip_ro_props=True,
                                           action="set to")

class _PStatesUncoreSetter(_PropsSetter):
    """Base class for the P-state and Uncore property setters."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: PStates.PStates | Uncore.Uncore,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinter.PStatesPrinter | _PepcPrinter.UncorePrinter,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """Refer to '_PropsSetter.__init__()'."""

        super().__init__(pman, pobj, cpuinfo, pprinter, msr=msr, sysfs_io=sysfs_io)

        self._order_pnames: set[str] = set()

    def _set_prop_sname(self,
                        spinfo: dict[str, PropSetInfoTypedDict],
                        pname: str,
                        optar: _OpTarget.OpTarget,
                        mnames: Sequence[MechanismNameType],
                        mnames_info: dict[str, MechanismNameType]):
        """
        Set property the property and handle frequency properties ordering.

        The arguments are the same as in '_PropsSetter._set_prop_sname()'.
        """

        try:
            super()._set_prop_sname(spinfo, pname, optar, mnames, mnames_info)
            return
        except ErrorBadOrder as err:
            if pname not in self._order_pnames:
                raise

            # Setting frequency or ELC threshold values requires careful handling due to ordering
            # constraints. For example, consider the case of updating minimum and maximum
            # frequencies:
            #
            #  ---- Current Min --- Current Max -------- New Min --- New Max ---------->
            #
            # The dotted line represents the frequency axis. If the minimum frequency is set before
            # the maximum frequency, an 'ErrorBadOrder' exception could be raised because the new
            # minimum could exceed the current maximum. For instance:
            #  1. ---- Current Min --- Current Max -------- New Min --- New Max ---------->
            #  2. ----------------- Current Max -------- Current Min -- New Max ----------> FAIL!
            #
            # To avoid this, the maximum frequency should be set first:
            #  1. ---- Current Min --- Current Max -------- New Min --- New Max ---------->
            #  2. ---- Current Min --------------------- New Min --- Current Max --------->
            #  3. ----------------------------------- Current Min -- Current Max --------->
            #
            # Therefore, if both minimum and maximum frequencies (or ELC thresholds) need to be
            # changed, attempt to set them in the correct order to satisfy the constraints.

            if "min_" in pname:
                # Trying to set minimum frequency to a value higher than currently configured
                # maximum frequency.
                other_pname = pname.replace("min_", "max_")
            elif "low_" in pname:
                # Trying to set ELC low threshold to a value higher than currently configured
                # high threshold.
                other_pname = pname.replace("low_", "high_")
            elif "max_" in pname:
                other_pname = pname.replace("max_", "min_")
            elif "high_" in pname:
                other_pname = pname.replace("high_", "low_")
            else:
                raise Error(f"BUG: Unexpected property {pname}") from err

            if other_pname not in spinfo:
                raise

            for pnm in (other_pname, pname):
                mname = self._do_set_prop_sname(pnm, optar, spinfo[pnm]["val"], mnames=mnames)
                del spinfo[pnm]
                mnames_info[pnm] = mname

class PStatesSetter(_PStatesUncoreSetter):
    """Provide API for changing P-state properties."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: PStates.PStates,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinter.PStatesPrinter,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """Refer to '_PropsSetter.__init__()'."""

        super().__init__(pman, pobj, cpuinfo, pprinter, msr=msr, sysfs_io=sysfs_io)

        self._pobj: PStates.PStates
        self._pprinter: _PepcPrinter.PStatesPrinter
        self._order_pnames = {"min_freq", "max_freq"}

class UncoreSetter(_PStatesUncoreSetter):
    """Provide API for changing uncore properties."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: Uncore.Uncore,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinter.UncorePrinter,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """Refer to '_PropsSetter.__init__()'."""

        super().__init__(pman, pobj, cpuinfo, pprinter, msr=msr, sysfs_io=sysfs_io)

        self._pobj: Uncore.Uncore
        self._pprinter: _PepcPrinter.UncorePrinter

        self._order_pnames = {"min_freq", "max_freq", "elc_low_threshold", "elc_high_threshold"}

class PMQoSSetter(_PropsSetter):
    """Provide API for changing PM QoS properties."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: PMQoS.PMQoS,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinter.PMQoSPrinter,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """Refer to '_PropsSetter.__init__()'."""

        super().__init__(pman, pobj, cpuinfo, pprinter, msr=msr, sysfs_io=sysfs_io)

        self._pobj: PMQoS.PMQoS
        self._pprinter: _PepcPrinter.PMQoSPrinter

class CStatesSetter(_PropsSetter):
    """Provide API for changing C-state properties."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: CStates.CStates,
                 cpuinfo: CPUInfo.CPUInfo,
                 pprinter: _PepcPrinter.CStatesPrinter,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None):
        """Refer to '_PropsSetter.__init__()'."""

        super().__init__(pman, pobj, cpuinfo, pprinter, msr=msr, sysfs_io=sysfs_io)

        self._pobj: CStates.CStates
        self._pprinter: _PepcPrinter.CStatesPrinter

    def set_cstates(self,
                    csnames: Iterable[str] | Literal["all"] = "all",
                    cpus: AbsNumsType | Literal["all"] = "all",
                    enable: bool = True,
                    mnames: Sequence[MechanismNameType] = ()):
        """
        Enable or disable C-states for specified CPUs.

        Args:
            csnames: C-state names to enable or disable, or "all" to select all C-states.
            cpus: CPU numbers to apply the operation to, or "all" for all CPUs.
            enable: If True, enable the specified C-states, if False, disable them.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.
        """

        if enable:
            self._pobj.enable_cstates(csnames=csnames, cpus=cpus)
        else:
            self._pobj.disable_cstates(csnames=csnames, cpus=cpus)

        self._pprinter.print_cstates(csnames=csnames, cpus=cpus, mnames=mnames, skip_ro_props=True,
                               action="set to")
