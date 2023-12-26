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
This module provides C-state management API.
"""

from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import _PCStatesBase, CPUIdle
from pepclibs.msr import PowerCtl, PCStateConfigCtl

# Make the exception class be available for users.
from pepclibs._PropsClassBase import ErrorUsePerCPU # pylint: disable=unused-import

# This dictionary describes the C-state properties this module supports. Many of the properties are
# just features controlled by an MSR, such as "c1e_autopromote" from 'PowerCtl.FEATURES'.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'CStates' objects. Use the full dictionary via
# 'CStates.props'.
#
# Some properties have scope name set to 'None' because the scope may be different for different
# systems. In such cases, the scope can be obtained via 'CStates.get_sname()'.
PROPS = {
    "pkg_cstate_limit" : {
        "name" : "Package C-state limit",
        "type" : "str",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : True,
        "subprops" : ("pkg_cstate_limit_lock", "pkg_cstate_limits", "pkg_cstate_limit_aliases"),
    },
    "pkg_cstate_limit_lock" : {
        "name" : "Package C-state limit lock",
        "type" : "bool",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "pkg_cstate_limits" : {
        "name" : "Available package C-state limits",
        "type" : "list[str]",
        # Conceptually this is per-package, but in practice it is global on all current platforms.
        "sname": "global",
        "mnames" : ("doc", ),
        "writable" : False,
    },
    "pkg_cstate_limit_aliases" : {
        "name" : "Package C-state limit aliases",
        "type" : "dict[str,str]",
        # Conceptually this is per-package, but in practice it is global on all current platforms.
        "sname": "global",
        "mnames" : ("doc", ),
        "writable" : False,
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "type" : "bool",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "type" : "bool",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "c1e_autopromote" : {
        "name" : "C1E autopromote",
        "type" : "bool",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "cstate_prewake" : {
        "name" : "C-state prewake",
        "type" : "bool",
        "sname": None,
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "idle_driver" : {
        "name" : "Idle driver",
        "type" : "str",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "governor" : {
        "name" : "Idle governor",
        "type" : "str",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : True,
    },
    "governors" : {
        "name" : "Available idle governors",
        "type" : "list[str]",
        "sname": "global",
        "mnames" : ("sysfs", ),
        "writable" : False,
    },
    "pch_negotiation" : {
        "name" : "PCH negotiation",
        "type" : "bool",
        "sname": None,
        "writable" : True,
        "mnames" : ("msr", ),
    },
}

class CStates(_PCStatesBase.PCStatesBase):
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

    def get_cstates_info(self, cpus="all", csnames="all"):
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

    def _read_prop_from_msr(self, pname, cpu):
        """
        Read property 'pname' from the corresponding MSR register on CPU 'cpu' and return its value.
        """

        try:
            if pname in PowerCtl.FEATURES:
                module = self._get_powerctl()
            else:
                module = self._get_pcstatectl()

            return module.read_cpu_feature(pname, cpu)
        except ErrorNotSupported:
            return None

    def _get_pkg_cstate_limit(self, pname, cpu):
        """
        Return the 'pkg_cstate_limit' or a related property value.
        Return 'None' if 'pname' is not related to 'pkg_cstate_limit'.
        """

        if pname == "pkg_cstate_limit_lock":
            return self._read_prop_from_msr(pname, cpu)

        try:
            pcstatectl = self._get_pcstatectl()
            pkg_cstate_limit_props = pcstatectl.read_cpu_feature("pkg_cstate_limit", cpu)
        except ErrorNotSupported:
            return None

        return pkg_cstate_limit_props[pname]

    def _get_cpuidle_prop(self, pname, cpu):
        """Return value for a property provided by the 'CPUIdle' class."""

        if pname == "idle_driver":
            return self._get_cpuidle().get_idle_driver()
        if pname == "governor":
            return self._get_cpuidle().get_current_governor()
        if pname == "governors":
            return self._get_cpuidle().get_available_governors()
        return None

    def _get_cpu_prop(self, pname, cpu, mname):
        """Return 'pname' property value for CPU 'cpu', using mechanism 'mname'."""

        if pname.startswith("pkg_cstate_"):
            return self._get_pkg_cstate_limit(pname, cpu)

        if pname in ("idle_driver","governor", "governors"):
            return self._get_cpuidle_prop(pname, cpu)

        if mname == "msr":
            return self._read_prop_from_msr(pname, cpu)

        raise Error(f"BUG: unsupported property '{pname}'")

    def _set_prop_cpus(self, pname, val, cpus, mnames=None):
        """Refer to '_PropsClassBase.PropsClassBase.set_prop_cpus()'."""

        if pname in PowerCtl.FEATURES:
            self._get_powerctl().write_feature(pname, val, cpus=cpus)
            return "msr"

        if pname in PCStateConfigCtl.FEATURES:
            self._get_pcstatectl().write_feature(pname, val, cpus=cpus)
            return "msr"

        if pname == "governor":
            self._get_cpuidle().set_current_governor(val)
            return "sysfs"

        raise Error(f"BUG: undefined property '{pname}'")

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

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # The Package C-state limit feature has "package" scope, but the underlying MSR register may
        # have "core" I/O scope.
        try:
            pcstatectl = self._get_pcstatectl()
        except ErrorNotSupported:
            pass
        else:
            self._props["iosname"] = pcstatectl.features["pkg_cstate_limit"]["iosname"]

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

        self._init_props_dict()

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcstatectl", "_powerctl", "_cpuidle")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
