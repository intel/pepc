# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides the base class for classes implementing properties, such as 'PState' and
'CState' classes.

Terminology.
 * sub-property - a property related to another (main) property so that the sub-property exists or
                  makes sense only when the main property is supported by the platform.
                  Sub-properties have to be read-only.

Naming conventions.
 * props - dictionary describing the properties. As an example, check 'PROPS' in 'PStates' and
           'CStates'.
 * pinfo - a properties dictionary in the format returned described in 'PropsClassBase.get_props()'.
 * pname - name of a property.
 * sname - name of a scope from the allowed list of scope names in 'CPUInfo.LEVELS'.
 * <sname> siblings - all CPUs sharing the same <sname>. E.g. "package siblings" means all CPUs
                      sharing the same package, "CPU 6 core siblings" means all CPUs sharing the
                      same core as CPU 6.
"""

import copy
import logging
from pepclibs import CPUInfo
from pepclibs.helperlibs import Trivial, Human, ClassHelpers, LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

MECHANISMS = {
    "sysfs" : {
        "short" : "sysfs",
        "long"  : "Linux sysfs file-system",
    },
    "msr" : {
        "short" : "MSR",
        "long"  : "Model Specific Register (MSR)",
    },
    "eds" : {
        "short" : "EDS",
        "long"  : "External Design Specification (EDS)",
    }
}

def _bug_method_not_defined(method_name):
    """Raise an error if the child class did not define the 'method_name' mandatory method."""

    raise Error(f"BUG: '{method_name}()' was not defined by the child class")

class PropsClassBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for higher level classes implementing properties (e.g. 'CStates' or 'PStates').
    """

    @staticmethod
    def get_mechanism_descr(mname):
        """
        Get a string describing a property mechanism 'nname'. See the 'MECHANISMS' dictionary for
        more information.
        """

        try:
            return MECHANISMS[mname]["long"]
        except KeyError:
            raise Error(f"BUG: missing mechanism description for '{mname}'") from None

    def _set_sname(self, pname):
        """
        Set scope "sname" for property 'pname'. This method is useful in cases where property scope
        depends on the platform.
        """

        if self._props[pname]["sname"]:
            return

        _bug_method_not_defined("PropsClassBase._set_sname")

    def get_sname(self, pname):
        """Get scope "sname" for property 'pname'."""

        try:
            if not self._props[pname]["sname"]:
                self._set_sname(pname)

            return self._props[pname]["sname"]
        except KeyError as err:
            raise Error(f"property '{pname}' does not exist") from err

    @staticmethod
    def _normalize_bool_type_value(prop, val):
        """
        Normalize and validate value 'val' of a boolean-type property 'prop'. Returns the boolean
        value corresponding to 'val'.
        """

        if val in (True, False):
            return val

        val = val.lower()
        if val in ("on", "enable"):
            return True

        if val in ("off", "disable"):
            return False

        name = Human.uncapitalize(prop["name"])
        raise Error(f"bad value '{val}' for {name}, use one of: True, False, on, off, enable, "
                    f"disable")

    def _validate_pname(self, pname):
        """Raise an exception if property 'pname' is unknown."""

        if pname not in self._props:
            pnames_str = ", ".join(set(self._props))
            raise Error(f"unknown property name '{pname}', known properties are: {pnames_str}")

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("PropsClassBase._get_cpu_prop_value")

    def _get_cpu_props(self, pnames, cpu):
        """Returns all properties in 'pnames' for CPU 'cpu'."""

        pinfo = {}

        for pname in pnames:
            # Get the 'pname' property.
            pinfo[pname] = self._get_cpu_prop_value(pname, cpu)
            if pinfo[pname] is None:
                _LOG.debug("CPU %d: %s is not supported", cpu, pname)
                continue
            _LOG.debug("CPU %d: %s = %s", cpu, pname, pinfo[pname])

        return pinfo

    def get_props(self, pnames, cpus="all"):
        """
        Read all properties specified in the 'pnames' list for CPUs in 'cpus', and for every CPU
        yield a ('cpu', 'pinfo') tuple, where 'pinfo' is dictionary containing the read values of
        all the properties. The arguments are as follows.
          * pnames - list or an iterable collection of properties to read and yield the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".

        The yielded 'pinfo' dictionaries have the following format.

        { property1_name : property1_value,
          property2_name : property2_value,
          ... etc ... }

        If a property is not supported, its value will be 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        for pname in pnames:
            self._validate_pname(pname)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, self._get_cpu_props(pnames, cpu)

    def get_prop(self, pname, cpus="all"):
        """
        Read property 'pnames' for CPUs in 'cpus', and for every CPU yield a ('cpu', 'val') tuple,
        where 'val' is property value. The arguments are as follows.
          * pname - name of the property to read and yield the values for. The property will be read
                    for every CPU in 'cpus'.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".

        If a property is not supported, its value will be 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        for cpu, pinfo in self.get_props((pname, ), cpus=cpus):
            yield (cpu, pinfo[pname])

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for _, pinfo in self.get_props(pnames, cpus=(cpu,)):
            pass
        return pinfo

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_prop()', but for a single CPU and a single property."""

        pinfo = None
        for _, pinfo in self.get_props((pname,), cpus=(cpu,)):
            pass
        return pinfo[pname]

    def _normalize_inprop(self, pname, val):
        """Normalize and return the input property value."""

        self._validate_pname(pname)

        prop = self._props[pname]
        if not prop["writable"]:
            name = Human.uncapitalize(prop["name"])
            raise Error(f"{name} is read-only and can not be modified{self._pman.hostmsg}")

        if prop.get("type") == "bool":
            val = self._normalize_bool_type_value(prop, val)

        if "unit" not in prop:
            return val

        if Trivial.is_num(val):
            if prop["type"] == "int":
                val = Trivial.str_to_int(val)
            else:
                val = float(val)
        else:
            special_vals = prop.get("special_vals", {})
            if val not in special_vals:
                # This property has a unit, and the value is not a number, nor it is one of the
                # special values. Presumably this is a value with a unit, such as "100MHz" or
                # something like that.
                is_integer = prop["type"] == "int"
                name = Human.uncapitalize(prop["name"])
                val = Human.parse_human(val, unit=prop["unit"], integer=is_integer, name=name)

        return val

    def _validate_cpus_vs_scope(self, prop, cpus):
        """Make sure that CPUs in 'cpus' match the scope of a property described by 'prop'."""

        sname = prop["sname"]

        if sname not in {"global", "package", "die", "core", "CPU"}:
            raise Error(f"BUG: unsupported scope name \"{sname}\"")

        if sname == "CPU":
            return

        if sname == "global":
            all_cpus = set(self._cpuinfo.get_cpus())

            if all_cpus.issubset(cpus):
                return

            name = Human.uncapitalize(prop["name"])
            missing_cpus = all_cpus - set(cpus)
            raise Error(f"{name} has {sname} scope, so the list of CPUs must include all CPUs.\n"
                        f"However, the following CPUs are missing from the list: {missing_cpus}")

        _, rem_cpus = getattr(self._cpuinfo, f"cpus_div_{sname}s")(cpus)
        if not rem_cpus:
            return

        mapping = ""
        for pkg in self._cpuinfo.get_packages():
            pkg_cpus = self._cpuinfo.package_to_cpus(pkg)
            pkg_cpus_str = Human.rangify(pkg_cpus)
            mapping += f"\n  * package {pkg}: CPUs: {pkg_cpus_str}"

            if sname in {"core", "die"}:
                # Build the cores or dies to packages map, in order to make the error message more
                # helpful. We use "core" in variable names, but in case of the "die" scope name,
                # they actually mean "die".

                pkg_cores = getattr(self._cpuinfo, f"package_to_{sname}s")(pkg)
                pkg_cores_str = Human.rangify(pkg_cores)
                mapping += f"\n               {sname}s: {pkg_cores_str}"

                # Build the cores to CPUs mapping string.
                clist = []
                for core in pkg_cores:
                    if sname == "core":
                        cpus = self._cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))
                    else:
                        cpus = self._cpuinfo.dies_to_cpus(dies=(core,), packages=(pkg,))
                    cpus_str = Human.rangify(cpus)
                    clist.append(f"{core}:{cpus_str}")

                # The core/die->CPU mapping may be very long, wrap it to 100 symbols.
                import textwrap # pylint: disable=import-outside-toplevel

                prefix = f"               {sname}s to CPUs: "
                indent = " " * len(prefix)
                clist_wrapped = textwrap.wrap(", ".join(clist), width=100,
                                              initial_indent=prefix, subsequent_indent=indent)
                clist_str = "\n".join(clist_wrapped)

                mapping += f"\n{clist_str}"

        name = Human.uncapitalize(prop["name"])
        rem_cpus_str = Human.rangify(rem_cpus)

        if sname == "core":
            mapping_name = "relation between CPUs, cores, and packages"
        elif sname == "die":
            mapping_name = "relation between CPUs, dies, and packages"
        else:
            mapping_name = "relation between CPUs and packages"

        errmsg = f"{name} has {sname} scope, so the list of CPUs must include all CPUs " \
                 f"in one or multiple {sname}s.\n" \
                 f"However, the following CPUs do not comprise full {sname}(s): {rem_cpus_str}\n" \
                 f"Here is the {mapping_name}{self._pman.hostmsg}:{mapping}"

        raise Error(errmsg)

    def _set_prop(self, pname, val, cpus):
        """Implements 'set_prop()'. The arguments are as the same as in 'set_prop()'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("PropsClassBase.set_prop")

    def set_prop(self, pname, val, cpus):
        """
        Set property 'pname' to value 'val' for CPUs in 'cpus'. The arguments are as follows.
          * pname - name of the property to set.
          * val - value to set the property to.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".

        Properties of "bool" type have the following values:
           * True, "on", "enable" for enabling the feature.
           * False, "off", "disable" for disabling the feature.
        """

        val = self._normalize_inprop(pname, val)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        self._set_sname(pname)
        self._validate_cpus_vs_scope(self._props[pname], cpus)

        self._set_prop(pname, val, cpus)

    def set_cpu_prop(self, pname, val, cpu):
        """Same as 'set_prop()', but for a single CPU and a single property."""

        self.set_prop(pname, val, (cpu,))

    def _init_props_dict(self, props):
        """Initialize the 'props' dictionary."""

        self._props = copy.deepcopy(props)
        self.props = props

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
