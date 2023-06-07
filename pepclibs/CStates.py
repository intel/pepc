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

import logging
from pathlib import Path
from pepclibs import _PropsCache
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs import _PCStatesBase, CPUIdle
from pepclibs.msr import MSR, PowerCtl, PCStateConfigCtl

_LOG = logging.getLogger()

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
        "writable" : True,
        "mechanisms" : ("msr", ),
        "subprops" : {
            "pkg_cstate_limit_locked" : {
                "name" : "Package C-state limit lock",
                "type" : "bool",
                "sname": "package",
                "writable" : False,
            },
            "pkg_cstate_limits" : {
                "name" : "Available package C-state limits",
                "type" : "list[str]",
                "sname": "package",
                "writable" : False,
            },
            "pkg_cstate_limit_aliases" : {
                "name" : "Package C-state limit aliases",
                "type" : "dict[str,str]",
                "sname": "package",
                "writable" : False,
            },
        },
    },
    "c1_demotion" : {
        "name" : "C1 demotion",
        "type" : "bool",
        "sname": None,
        "writable" : True,
        "mechanisms" : ("msr", ),
    },
    "c1_undemotion" : {
        "name" : "C1 undemotion",
        "type" : "bool",
        "sname": None,
        "writable" : True,
        "mechanisms" : ("msr", ),
    },
    "c1e_autopromote" : {
        "name" : "C1E autopromote",
        "type" : "bool",
        "sname": None,
        "writable" : True,
        "mechanisms" : ("msr", ),
    },
    "cstate_prewake" : {
        "name" : "C-state prewake",
        "type" : "bool",
        "sname": None,
        "writable" : True,
        "mechanisms" : ("msr", ),
    },
    "idle_driver" : {
        "name" : "Idle driver",
        "type" : "str",
        "sname": "global",
        "writable" : False,
        "mechanisms" : ("sysfs", ),
    },
    "governor" : {
        "name" : "Idle governor",
        "type" : "str",
        "sname": "global",
        "writable" : True,
        "mechanisms" : ("sysfs", ),
        "subprops" : {
            "governors" : {
                "name" : "Available idle governors",
                "type" : "list[str]",
                "sname": "global",
                "writable" : False,
            },
        },
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
            self._cpuidle = CPUIdle.CPUIdle(self._pman, cpuinfo=self._cpuinfo)
        return self._cpuidle

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

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

    def enable_cstates(self, csnames="all", cpus="all"):
        """Same as 'CPUIdle.enable_cstates()'."""

        return self._get_cpuidle().enable_cstates(csnames=csnames, cpus=cpus)

    def disable_cstates(self, csnames="all", cpus="all"):
        """Same as 'CPUIdle.disable_cstates()'."""

        return self._get_cpuidle().disable_cstates(csnames=csnames, cpus=cpus)

    def _get_pkg_cstate_limit(self, pname, cpu):
        """Return the 'pname' sub-property for the 'pkg_cstate_limit' property."""

        try:
            pcstatectl = self._get_pcstatectl()
            pkg_cstate_limit_props = pcstatectl.read_cpu_feature("pkg_cstate_limit", cpu)
        except ErrorNotSupported:
            return None

        return pkg_cstate_limit_props[pname]

    def _read_prop_value_from_msr(self, pname, cpu):
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

    def _get_cpu_prop_value_sysfs(self, prop):
        """
        This is a helper for '_get_cpu_prop_value()' which handles the properties backed by a sysfs
        file.
        """

        path = self._sysfs_cpuidle / prop["fname"]

        try:
            return self._read_prop_value_from_sysfs(prop, path)
        except ErrorNotFound:
            _LOG.debug("can't read value of property '%s', path '%s' missing", prop["name"], path)
            return None

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """"Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        if prop is None:
            prop = self._props[pname]

        _LOG.debug("getting '%s' (%s) for CPU %d%s", pname, prop["name"], cpu, self._pman.hostmsg)

        if pname == "idle_driver":
            return self._get_cpuidle().get_idle_driver()

        if pname in {"pkg_cstate_limit", "pkg_cstate_limits", "pkg_cstate_limit_aliases"}:
            return self._get_pkg_cstate_limit(pname, cpu)

        if pname == "pkg_cstate_limit_locked":
            return self._read_prop_value_from_msr("locked", cpu)

        if prop["mechanisms"][0] == "msr":
            return self._read_prop_value_from_msr(pname, cpu)

        if self._pcache.is_cached(pname, cpu):
            return self._pcache.get(pname, cpu)

        if "fname" in prop:
            val = self._get_cpu_prop_value_sysfs(prop)
        else:
            raise Error(f"BUG: unsupported property '{pname}'")

        self._pcache.add(pname, cpu, val, sname=prop["sname"])
        return val

    def _set_prop_value(self, pname, val, cpus):
        """Sets user-provided property 'pname' to value 'val' for CPUs 'cpus'."""

        if pname in PowerCtl.FEATURES:
            self._get_powerctl().write_feature(pname, val, cpus=cpus)
            return

        if pname in PCStateConfigCtl.FEATURES:
            self._get_pcstatectl().write_feature(pname, val, cpus=cpus)
            return

        # Removing 'cpus' from the cache will make sure the following '_pcache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_pcache.add()'
        # method.
        for cpu in cpus:
            self._pcache.remove(pname, cpu)

        prop = self._props[pname]

        for cpu in cpus:
            if self._pcache.is_cached(pname, cpu):
                if prop["sname"] == "global":
                    break
                continue

            if "fname" in prop:
                path = self._sysfs_cpuidle / prop["fname"]
                self._write_prop_value_to_sysfs(prop, path, val)

                # Note, below 'add()' call is scope-aware. It will cache 'val' not only for CPU
                # number 'cpu', but also for all the 'sname' siblings. For example, if property
                # scope name is "package", 'val' will be cached for all CPUs in the package that
                # contains CPU number 'cpu'.
                self._pcache.add(pname, cpu, val, sname=prop["sname"])
            else:
                raise Error(f"BUG: undefined property '{pname}'")

    def _set_props(self, inprops, cpus):
        """Refer to '_PropsClassBase.PropsClassBase._set_props()'."""

        if "governor" in inprops:
            self._validate_governor_name(inprops["governor"])

        for pname, val in inprops.items():
            self._set_prop_value(pname, val, cpus)

    def _set_sname(self, pname):
        """Set scope "sname" for property 'pname'."""

        if self._props[pname]["sname"]:
            return

        if pname in PCStateConfigCtl.FEATURES:
            finfo = self._get_pcstatectl().features
            self._props["c1_demotion"]["sname"] = finfo["c1_demotion"]["sname"]
            self._props["c1_undemotion"]["sname"] = finfo["c1_undemotion"]["sname"]

            self._props["pkg_cstate_limit"]["sname"] = finfo["pkg_cstate_limit"]["sname"]
            subprops = self._props["pkg_cstate_limit"]["subprops"]
            subprops["pkg_cstate_limits"]["sname"] = finfo["pkg_cstate_limit"]["sname"]
            subprops["pkg_cstate_limit_aliases"]["sname"] = finfo["pkg_cstate_limit"]["sname"]
            subprops["pkg_cstate_limit_locked"]["sname"] = finfo["locked"]["sname"]
        elif pname in PowerCtl.FEATURES:
            finfo = self._get_powerctl().features
            self._props["c1e_autopromote"]["sname"] = finfo["c1e_autopromote"]["sname"]
            self._props["cstate_prewake"]["sname"] = finfo["cstate_prewake"]["sname"]
        else:
            raise Error(f"BUG: could not get scope for property '{pname}'")

    def _init_props_dict(self): # pylint: disable=arguments-differ
        """Initialize the 'props' dictionary."""

        super()._init_props_dict(PROPS)

        # These properties are backed by a sysfs file.
        self._props["governor"]["fname"] = "current_governor"
        self._props["governor"]["subprops"]["governors"]["fname"] = "available_governors"

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

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

        self._cpuidle = cpuidle
        self._close_cpuidle = cpuidle is None

        self._powerctl = None
        self._pcstatectl = None

        self._init_props_dict()

        self._sysfs_cpuidle = Path("/sys/devices/system/cpu/cpuidle")

        # The write-through per-CPU properties cache. The properties that are backed by an MSR are
        # not cached, because the MSR layer implements its own caching.
        self._enable_cache = enable_cache
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=self._enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcstatectl", "_powerctl", "_cpuidle", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()
