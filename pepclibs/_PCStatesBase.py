# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides the base class for 'PState' and 'CState' classes.
"""

import copy
import logging
from pepclibs.helperlibs import ClassHelpers, LocalProcessManager, Human, Trivial
from pepclibs import CPUInfo
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, Error

_LOG = logging.getLogger()

class PCStatesBase(ClassHelpers.SimpleCloseContext):
    """
    This is a base class for the 'PState' and 'CState' classes.
    """

    def _check_prop(self, pname):
        """Raise an error if a property 'pname' is not supported."""

        if pname not in self._props:
            pnames_str = ", ".join(set(self._props))
            raise ErrorNotSupported(f"property '{pname}' is not supported{self._pman.hostmsg}, use "
                                    f"one of the following: {pnames_str}")

    def _normalize_inprops(self, inprops):
        """Normalize the 'inprops' argument of the 'set_props()' method and return the result."""

        def _add_prop(pname, val):
            """Add property 'pname' to the 'result' dictionary."""

            self._check_prop(pname)

            if not self.props[pname]["writable"]:
                name = Human.untitle(self.props[pname]["name"])
                raise Error(f"{name} is read-only and can not be modified{self._pman.hostmsg}")

            if pname in result:
                _LOG.warning("duplicate property '%s': dropping value '%s', keeping '%s'",
                             pname, result[pname], val)
            result[pname] = val

        result = {}
        if hasattr(inprops, "items"):
            for pname, val in inprops.items():
                _add_prop(pname, val)
        else:
            for pname, val in inprops:
                _add_prop(pname, val)

        return result

    def _read_prop_value_from_sysfs(self, prop, path):
        """
        Read CPU 'cpu' property described by 'prop' from sysfs, and return its value.
        '"""

        val = self._pman.read(path).strip()

        if prop["type"] == "int":
            val = int(val)
            if not Trivial.is_int(val):
                raise Error(f"read an unexpected non-integer value from '{path}'"
                            f"{self._pman.hostmsg}")
            if prop.get("unit") == "Hz":
                # Sysfs files have the numbers in kHz, convert to Hz.
                val *= 1000

        if prop["type"] == "list[str]":
            val = val.split()

        return val

    def _init_props_dict(self, props):
        """Initialize the 'props' dictionary."""

        self.props = copy.deepcopy(props)

        for prop in self.props.values():
            # Every features should include the 'subprops' sub-dictionary.
            if "subprops" not in prop:
                prop["subprops"] = {}
            else:
                # Propagate the "scope" key to sub-properties.
                for subprop in prop["subprops"].values():
                    if "scope" not in subprop:
                        subprop["scope"] = prop["scope"]

        self._props = copy.deepcopy(self.props)

    def _get_cpu_subprop(self, pname, subpname, cpu):
        """Returns sup-property 'subpname' of property 'pname' for CPU 'cpu'."""

        subprop = self._props[pname]["subprops"][subpname]
        return self._get_cpu_prop_value(subpname, cpu, prop=subprop) # pylint: disable=no-member

    def _get_cpu_prop(self, pname, cpu):
        """Returns property 'pname' for CPU 'cpu'."""

        return self._get_cpu_prop_value(pname, cpu) # pylint: disable=no-member

    def _get_cpu_props(self, pnames, cpu):
        """Returns all properties in 'pnames' for CPU 'cpu'."""

        pinfo = {}

        for pname in pnames:
            pinfo[pname] = {}

            # Get the 'pname' property.
            pinfo[pname][pname] = self._get_cpu_prop(pname, cpu)
            if pinfo[pname][pname] is None:
                _LOG.debug("CPU %d: %s is not supported", cpu, pname)
                continue
            _LOG.debug("CPU %d: %s = %s", cpu, pname, pinfo[pname][pname])

            # Get all the sub-properties.
            for subpname in self._props[pname]["subprops"]:
                if pinfo[pname][pname] is not None:
                    # Get the 'subpname' sub-property.
                    pinfo[pname][subpname] = self._get_cpu_subprop(pname, subpname, cpu)
                else:
                    # The property is not supported, so all sub-properties are not supported either.
                    pinfo[pname][subpname] = None
                _LOG.debug("CPU %d: %s = %s", cpu, subpname, pinfo[pname][subpname])

        return pinfo

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for _, pinfo in self.get_props(pnames, cpus=(cpu,)): # pylint: disable=no-member
            pass
        return pinfo

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_props()', but for a single CPU and a single property."""

        pinfo = None
        for _, pinfo in self.get_props((pname,), cpus=(cpu,)): # pylint: disable=no-member
            pass
        return pinfo

    def set_prop(self, pname, val, cpus):
        """Same as 'set_props()', but for a single property."""

        self.set_props(((pname, val),), cpus=cpus) # pylint: disable=no-member

    def set_cpu_props(self, inprops, cpu):
        """Same as 'set_props()', but for a single CPU."""

        self.set_props(inprops, cpus=(cpu,)) # pylint: disable=no-member

    def set_cpu_prop(self, pname, val, cpu):
        """Same as 'set_props()', but for a single CPU and a single property."""

        self.set_props(((pname, val),), cpus=(cpu,)) # pylint: disable=no-member

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target system..
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self.props = None
        # Internal version of 'self.props'. Contains some data which we don't want to expose to the
        # user.
        self._props = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
