# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of retrieving and setting S-state related properties.
"""

# TODO: finish annotating and modernizing this module.
from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import _PropsClassBase, CPUIdle
from pepclibs.CStatesVars import PROPS
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.msr import PowerCtl, PCStateConfigCtl

# pylint: disable=unused-import
from pepclibs.CPUIdle import ReqCStateInfoTypedDict, ReqCStateInfoValuesType, ReqCStateInfoKeysType
from pepclibs._PropsClassBase import ErrorUsePerCPU, ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Generator, Literal, Iterable
    from pepclibs.CPUInfoTypes import AbsNumsType

class CStates(_PropsClassBase.PropsClassBase):
    """
    This class provides C-state management API.

    Public methods overview.
    1. All the get/set property methods defined by the '_PropsClassBase.PropsClassBase' base class
       (refer to its docstring for more information).
    2. Enable or disable multiple C-states for multiple CPUs via Linux sysfs interfaces:
       'enable_cstates()', 'disable_cstates()'.
    3. Get C-state(s) information.
       * For multiple CPUs and multiple C-states: get_cstates_info().
       * For single CPU and multiple C-states: 'get_cpu_cstates_info()'.
       * For single CPU and a single C-state:  'get_cpu_cstate_info()'.
    """

    def _get_cpuidle(self):
        """Returns a 'CPUIdle()' object."""

        if not self._cpuidle:
            self._cpuidle = CPUIdle.CPUIdle(self._pman, cpuinfo=self._cpuinfo,
                                            enable_cache=self._enable_cache)
        return self._cpuidle

    def _get_powerctl(self):
        """Return an instance of 'PowerCtl' class."""

        if not self._powerctl:
            msr = self._get_msr()
            self._powerctl = PowerCtl.PowerCtl(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)
        return self._powerctl

    def _get_pcstatectl(self):
        """Return an instance of 'PCStateConfigCtl' class."""

        if not self._pcstatectl:
            msr = self._get_msr()
            self._pcstatectl = PCStateConfigCtl.PCStateConfigCtl(pman=self._pman,
                                                                 cpuinfo=self._cpuinfo, msr=msr)
        return self._pcstatectl

    def get_cstates_info(self,
                         cpus: AbsNumsType | Literal["all"] = "all",
                         csnames: Iterable[str] | Literal["all"] = "all") -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """Same as 'CPUIdle.get_cstates_info()'."""

        yield from self._get_cpuidle().get_cstates_info(cpus=cpus, csnames=csnames)

    def get_cpu_cstates_info(self, cpu, csnames="all"):
        """Same as 'CPUIdle.get_cpu_cstates_info()'."""

        return self._get_cpuidle().get_cpu_cstates_info(cpu, csnames=csnames)

    def get_cpu_cstate_info(self, cpu, csname):
        """Same as 'CPUIdle.get_cpu_cstate_info()'."""

        return self._get_cpuidle().get_cpu_cstate_info(cpu, csname)

    def enable_cstates(self, csnames="all", cpus="all", mnames=None):
        """
        Same as 'CPUIdle.enable_cstates()', except for the 'mnames' argument, which is has no
        effect, only checked to to be 'sysfs' on 'None.
        """

        mnames = self._normalize_mnames(mnames, allow_readonly=False)
        if "sysfs" not in mnames:
            mnames = ", ".join(mnames)
            raise ErrorNotSupported(f"cannot disable C-states, unsupported methods: {mnames}.\n"
                                    f"Use the 'sysfs' method instead.")

        return self._get_cpuidle().enable_cstates(csnames=csnames, cpus=cpus)

    def disable_cstates(self, csnames="all", cpus="all", mnames=None):
        """
        Same as 'CPUIdle.disable_cstates()', except for the 'mnames' argument, which is has no
        effect, only checked to to be 'sysfs' on 'None.
        """

        mnames = self._normalize_mnames(mnames, allow_readonly=False)
        if "sysfs" not in mnames:
            mnames = ", ".join(mnames)
            raise ErrorNotSupported(f"cannot disable C-states, unsupported methods: {mnames}.\n"
                                    f"Use the 'sysfs' method instead.")

        return self._get_cpuidle().disable_cstates(csnames=csnames, cpus=cpus)

    def get_prop_from_msr(self, pname, cpus):
        """
        For every CPU in 'cpus', yield '(cpu, val)' pairs, where 'val' is value of property 'pname',
        provided by 'MSR_POWER_CTL' or 'MSR_PKG_CST_CONFIG_CONTROL'.
        """

        if pname in PowerCtl.FEATURES:
            module = self._get_powerctl()
        else:
            module = self._get_pcstatectl()

        yield from module.read_feature(pname, cpus=cpus)

    def _get_pkg_cstate_limit(self, pname, cpus):
        """
        For every CPU in 'cpus', yield '(cpu, val)' pairs, where 'val' is the 'pkg_cstate_limit' or
        a related property value.
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
                yield cpu, limits

    def _get_cpuidle_prop(self, pname, cpus):
        """
        For every CPU in 'cpus', yield '(cpu, val)' pairs, where 'val' is value of property 'pname',
        provided by the 'CPUIdle' module.
        """

        if pname == "idle_driver":
            val = self._get_cpuidle().get_idle_driver()
        elif pname == "governor":
            val = self._get_cpuidle().get_current_governor()
        else:
            val = self._get_cpuidle().get_available_governors()

        # All the properties are global, sor read only once and yield the same value for all CPUs.
        for cpu in cpus:
            yield (cpu, val)

    def _get_prop_cpus(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, 'val' is property 'pname' value for CPU
        'cpu'. Use mechanism 'mname'.
        """

        if pname.startswith("pkg_cstate_"):
            yield from self._get_pkg_cstate_limit(pname, cpus)
        elif pname in ("idle_driver", "governor", "governors"):
            yield from self._get_cpuidle_prop(pname, cpus)
        elif mname == "msr":
            yield from self.get_prop_from_msr(pname, cpus)
        else:
            raise Error(f"BUG: unsupported property '{pname}'")

    def _set_prop_cpus(self, pname, val, cpus, mname):
        """Set property 'pname' to value 'val' for CPUs in 'cpus'. Use mechanism 'mname'."""

        if mname == "msr":
            if pname in PowerCtl.FEATURES:
                self._get_powerctl().write_feature(pname, val, cpus=cpus)
                return
            if pname in PCStateConfigCtl.FEATURES:
                self._get_pcstatectl().write_feature(pname, val, cpus=cpus)
                return

        if mname == "sysfs":
            if pname == "governor":
                self._get_cpuidle().set_current_governor(val)
                return

        raise Error(f"BUG: unsupported property '{pname}'")

    def _set_sname(self, pname):
        """Set scope name for property 'pname'."""

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

    def __init__(self, pman=None, cpuinfo=None, cpuidle=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * cpuidle - a 'CPUIdle.CPUIdle()' object which should be used for reading and setting
                      requestable C-state properties.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._cpuidle = cpuidle
        self._close_cpuidle = cpuidle is None

        self._powerctl = None
        self._pcstatectl = None

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcstatectl", "_powerctl", "_cpuidle")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
