# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of retrieving and setting S-state related properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
from pepclibs import _PropsClassBase, CPUIdle
from pepclibs.CStatesVars import PROPS
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs.msr import PowerCtl, PCStateConfigCtl

# pylint: disable=unused-import
from pepclibs._PropsClassBase import ErrorUsePerCPU, ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Generator, Literal, Iterable, Sequence, Union
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR
    from pepclibs.msr._FeaturedMSR import FeatureValueType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUIdle import ReqCStateInfoTypedDict, ReqCStateInfoValuesType
    from pepclibs.CPUIdle import ReqCStateInfoKeysType, ReqCStateToggleResultType
    from pepclibs.PropsTypes import PropertyValueType, MechanismNameType
    from pepclibs.CPUInfoTypes import AbsNumsType

class CStates(_PropsClassBase.PropsClassBase):
    """
    Provide API for managing platform settings related to C-states.

    Public methods overview.
    1. All the get/set property methods defined by the '_PropsClassBase.PropsClassBase' base class
       (refer to its docstring for more information).
    2. Enable or disable multiple C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    3. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For single CPU and multiple C-states: 'get_cpu_cstates_info()'.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 cpuidle: CPUIdle.CPUIdle | None = None,
                 msr: MSR.MSR | None = None,
                 enable_cache: bool = True):
        """Refer to 'PropsClassBase.__init__()'."""

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._cpuidle = cpuidle
        self._close_cpuidle = cpuidle is None

        self._powerctl: PowerCtl.PowerCtl | None = None
        self._pcstatectl: PCStateConfigCtl.PCStateConfigCtl | None = None

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcstatectl", "_powerctl", "_cpuidle")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()

    def _get_cpuidle(self) -> CPUIdle.CPUIdle:
        """
        Return a 'CPUIdle' object.

        Returns:
            An instance of the 'CPUIdle' class.
        """

        if not self._cpuidle:
            self._cpuidle = CPUIdle.CPUIdle(self._pman, cpuinfo=self._cpuinfo,
                                            enable_cache=self._enable_cache)
        return self._cpuidle

    def _get_powerctl(self) -> PowerCtl.PowerCtl:
        """
        Return a 'PowerCtl' object.

        Returns:
            An instance of the 'PowerCtl' class.
        """

        if not self._powerctl:
            msr = self._get_msr()
            self._powerctl = PowerCtl.PowerCtl(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._powerctl

    def _get_pcstatectl(self) -> PCStateConfigCtl.PCStateConfigCtl:
        """
        Return a 'PCStateConfigCtl' object.

        Returns:
            An instance of the 'PCStateConfigCtl' class.
        """

        if not self._pcstatectl:
            msr = self._get_msr()
            self._pcstatectl = PCStateConfigCtl.PCStateConfigCtl(pman=self._pman,
                                                                 cpuinfo=self._cpuinfo, msr=msr)
        return self._pcstatectl

    def get_cstates_info(self,
                         csnames: Iterable[str] | Literal["all"] = "all",
                         cpus: AbsNumsType | Literal["all"] = "all") -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """Refer to 'CPUIdle.get_cstates_info()'."""

        yield from self._get_cpuidle().get_cstates_info(csnames=csnames, cpus=cpus)

    def get_cpu_cstates_info(self,
                             cpu: int,
                             csnames: Iterable[str] | Literal["all"] = "all") -> \
                                                                dict[str, ReqCStateInfoTypedDict]:
        """Refer to 'CPUIdle.get_cpu_cstates_info()'."""

        return self._get_cpuidle().get_cpu_cstates_info(cpu, csnames=csnames)

    def enable_cstates(self,
                       csnames: Iterable[str] | Literal["all"] = "all",
                       cpus: AbsNumsType | Literal["all"] = "all",
                       mnames: Sequence[MechanismNameType] = ()) -> ReqCStateToggleResultType:
        """
        Enable specified C-states on selected CPUs using the specified mechanisms.

        Args:
            csnames: C-state names to enable, or "all" to enable all available C-states.
            cpus: CPU numbers to enable C-states on, or "all" for all CPUs.
            mnames: Mechanism names to use for enabling C-states. If empty, use all available
                    mechanisms.

        Returns:
            A dictionary providing a list of enabled C-state names for every CPU number.

        Raises:
            ErrorTryAnotherMechanism: If none of the provided mechanisms support enabling C-states.
            ErrorNotSupported: If one or more of the specified C-states are not supported.
        """

        mnames = self._normalize_mnames(mnames, allow_readonly=False)
        if "sysfs" not in mnames:
            raise ErrorTryAnotherMechanism("Use the 'sysfs' mechanism to enable C-states")

        return self._get_cpuidle().enable_cstates(csnames=csnames, cpus=cpus)

    def disable_cstates(self,
                        csnames: Iterable[str] | Literal["all"] = "all",
                        cpus: AbsNumsType | Literal["all"] = "all",
                        mnames: Sequence[MechanismNameType] = ()) -> dict:
        """Same as 'enable_cstates()', but disable specified C-states."""

        mnames = self._normalize_mnames(mnames, allow_readonly=False)
        if "sysfs" not in mnames:
            raise ErrorTryAnotherMechanism("Use the 'sysfs' mechanism to disable C-states")

        try:
            return self._get_cpuidle().disable_cstates(csnames=csnames, cpus=cpus)
        except ErrorNotFound as err:
            raise ErrorNotSupported(str(err)) from err

    def _get_prop_from_msr(self,
                           pname: str,
                           cpus: AbsNumsType) -> Generator[tuple[int, PropertyValueType],
                                                           None, None]:
        """
        Retrieve and yield property 'pname' value for CPUs in 'cpus'.

        Args:
            pname: The name of the property to retrieve the value for.
            cpus: The CPU numbers to retrieve the property value for.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the property value.
        """

        _featured_msr_obj: Union[PowerCtl.PowerCtl, PCStateConfigCtl.PCStateConfigCtl]
        if pname in PowerCtl.FEATURES:
            _featured_msr_obj = self._get_powerctl()
        else:
            _featured_msr_obj = self._get_pcstatectl()

        yield from _featured_msr_obj.read_feature(pname, cpus=cpus)

    def _get_pkg_cstate_limit(self,
                              pname: str,
                              cpus: AbsNumsType) -> Generator[tuple[int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield package C-state property 'pname' value for CPUs in 'cpus'.

        Args:
            pname: Name of the package C-state property to retrieve.
            cpus: The CPU numbers to retrieve the property value for.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the property value.
        """

        pcstatectl = self._get_pcstatectl()

        if pname == "pkg_cstate_limit_lock":
            yield from pcstatectl.read_feature(pname, cpus=cpus)
        elif pname == "pkg_cstate_limit":
            for cpu, features in pcstatectl.read_feature("pkg_cstate_limit", cpus=cpus):
                yield cpu, features
        elif pname == "pkg_cstate_limits":
            pcstatectl.validate_feature_supported("pkg_cstate_limit", cpus=cpus)
            # The "vals" attribute contains a dictionary with keys being the limit names and
            # values being the limit values.
            limits = list(pcstatectl.features["pkg_cstate_limit"]["vals"])
            for cpu in cpus:
                yield cpu, cast(list[str], limits)

    def _get_cpuidle_prop(self,
                          pname: str,
                          cpus: AbsNumsType) -> Generator[tuple[int, PropertyValueType],
                                                          None, None]:
        """
        Retrieve and yield CPU idle property 'pname' value for CPUs in 'cpus'.

        Args:
            pname: Name of the CPU idle property to retrieve.
            cpus: The CPU numbers to retrieve the property value for.

        Yields:
            Tuples of (cpu, value), where 'cpu' is the CPU number and 'value' is the property value.
        """

        val: PropertyValueType
        if pname == "idle_driver":
            val = self._get_cpuidle().get_idle_driver()
        elif pname == "governor":
            val = self._get_cpuidle().get_current_governor()
        else:
            val = self._get_cpuidle().get_available_governors()

        # All the properties are global, so read only once and yield the same value for all CPUs.
        for cpu in cpus:
            yield cpu, val

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """Refer to 'PropsClassBase._get_prop_cpus()'."""

        if pname.startswith("pkg_cstate_"):
            yield from self._get_pkg_cstate_limit(pname, cpus)
        elif pname in ("idle_driver", "governor", "governors"):
            yield from self._get_cpuidle_prop(pname, cpus)
        elif mname == "msr":
            yield from self._get_prop_from_msr(pname, cpus)
        else:
            raise Error(f"BUG: Unsupported property '{pname}'")

    def _set_prop_cpus(self,
                       pname: str,
                       val: PropertyValueType,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]):
        """Refer to 'PropsClassBase._set_prop_cpus()'."""

        if typing.TYPE_CHECKING:
            _val = cast(FeatureValueType, val)
        else:
            _val = val

        if mname == "msr":
            if pname in PowerCtl.FEATURES:
                self._get_powerctl().write_feature(pname, _val, cpus=cpus)
                return
            if pname in PCStateConfigCtl.FEATURES:
                self._get_pcstatectl().write_feature(pname, _val, cpus=cpus)
                return

        if mname == "sysfs":
            if pname == "governor":
                self._get_cpuidle().set_current_governor(cast(str, val))
                return

        raise Error(f"BUG: Unsupported property '{pname}'")

    def _set_sname(self, pname: str):
        """
        Set the scope name ('sname') for the specified property.

        Args:
            pname: The name of the property for which to set the scope name.
        """

        prop = self._props[pname]
        if prop["sname"]:
            return

        finfo = None
        if pname in PCStateConfigCtl.FEATURES:
            finfo = self._get_pcstatectl().features
        elif pname in PowerCtl.FEATURES:
            finfo = self._get_powerctl().features

        if finfo:
            prop["sname"] = finfo[pname]["sname"]
            prop["iosname"] = finfo[pname]["iosname"]
            self.props[pname]["sname"] = prop["sname"]
        else:
            raise Error(f"BUG: unexpected property \"{pname}\"")
