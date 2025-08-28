# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>

"""
Provide API for changing properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import TypedDict, Sequence, cast, Iterable, Literal, Union
from pepctool import _PepcCommon
from pepctool import _OpTarget, _PepcPrinter
from pepclibs import CPUInfo, _SysfsIO, CStates, PStates, PMQoS
from pepclibs.helperlibs import ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder
from pepclibs.msr import MSR

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._PropsClassBaseTypes import MechanismNameType, PropertyValueType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

    _PropsClassType = Union[PStates.PStates, CStates.CStates, PMQoS.PMQoS]
    _PepcPrinterClassType = Union[_PepcPrinter.CStatesPrinter, _PepcPrinter.PStatesPrinter,
                                  _PepcPrinter.PMQoSPrinter]

    class PropSetInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary for property settings.

        Attributes:
            val: The value to assign to the property.
            default_unit: The default unit of the property.
        """

        val: str
        default_unit: str

class _PropsSetter(ClassHelpers.SimpleCloseContext):
    """Base class for pepc property setter classes."""

    def __init__(self,
                 pman: ProcessManagerType,
                 pobj: _PropsClassType,
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

        mname = _PepcCommon.set_prop_sname(self._pobj, pname, optar, spinfo[pname]["val"],
                                           mnames=mnames)
        del spinfo[pname]
        mnames_info[pname] = mname

    @staticmethod
    def _set_prop(pobj: _PropsClassType,
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
            pobj.set_prop_cpus(pname, val, cast(AbsNumsType, nums))
        elif sname == "die":
            pobj.set_prop_dies(pname, val, cast(RelNumsType, nums))
        elif sname == "package":
            pobj.set_prop_packages(pname, val, cast(AbsNumsType, nums))
        else:
            raise Error(f"BUG: Unsupported scope name '{sname}' for property '{pname}'")

    def set_props(self,
                  spinfo: dict[str, PropSetInfoTypedDict],
                  optar: _OpTarget.OpTarget,
                  mnames: Sequence[MechanismNameType] = ()):
        """
        Set properties specified CPUs, cores, modules, or other targets.

        Args:
            spinfo: Dictionary mapping property names to their information, such as the value to
                    set.
            optar: The operation target object defining the processor topology entities (CPUs,
                   cores, etc) to set properties for.
            mnames: Mechanism names allowed for setting properties. An empty sequence (default)
                    means that all mechanisms are allowed.
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
            self._set_prop_sname(spinfo_copy, pname, optar, mnames, mnames_info)

        if self._msr:
            self._msr.commit_transaction()
        if self._sysfs_io:
            self._sysfs_io.commit_transaction()

        if self._pprinter:
            for pname in spinfo:
                mnames = (mnames_info[pname], )
                self._pprinter.print_props((pname,), optar, mnames=mnames, skip_ro=True,
                                           skip_unsupported=False, action="set to")

class PStatesSetter(_PropsSetter):
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
            if pname not in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
                raise

            # Setting frequencies may be tricky because of the ordering constraints. Here is an
            # example illustrating why order matters. Suppose current min. and max. frequencies and
            # new min. and max. frequencies are as follows:
            #  ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #
            # Where the dotted line represents the horizontal frequency axis. Setting min. frequency
            # before max. frequency leads to a failure (more precisely, the 'ErrorBadOrder'
            # exception). Indeed, at step #2 below, current minimum frequency would be set to a
            # value higher that current maximum frequency.
            #  1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #  2. ----------------- Cur. Max -------- Cur. Min -- New Max ----------> FAIL!
            #
            # To handle this situation, max. frequency should be set first.
            #  1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #  2. ---- Cur. Min --------------------- New Min --- Cur. Max --------->
            #  3. ----------------------------------- Cur. Min -- Cur. Max --------->
            #
            # Therefore, if both min. and max. frequencies should be changed, try changing them in
            # different order.

            freq_pname = pname
            if pname.startswith("min"):
                # Trying to set minimum frequency to a value higher than currently configured
                # maximum frequency.
                other_freq_pname = pname.replace("min", "max")
            elif pname.startswith("max"):
                other_freq_pname = pname.replace("max", "min")
            else:
                raise Error(f"BUG: Unexpected property {pname}") from err

            if other_freq_pname not in spinfo:
                raise

            for pnm in (other_freq_pname, freq_pname):
                mname = _PepcCommon.set_prop_sname(self._pobj, pnm, optar, spinfo[pnm]["val"],
                                                   mnames=mnames)
                del spinfo[pnm]
                mnames_info[pnm] = mname

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

        self._pprinter.print_cstates(csnames=csnames, cpus=cpus, mnames=mnames, skip_ro=True,
                               action="set to")
