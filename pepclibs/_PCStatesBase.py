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

def _bug_method_not_defined(method_name):
    """
    Raise an error if the child class did not define the 'method_name' mandatory method.
    """

    raise Error(f"BUG: '{method_name}()' was not defined by the child class")

class PCStatesBase(ClassHelpers.SimpleCloseContext):
    """
    This is a base class for the 'PState' and 'CState' classes.
    """

    @staticmethod
    def _validate_bool_type_value(prop, val):
        """Validate value 'val' of a boolean-type property 'prop'."""

        vals = {True, False, "on", "off", "enable", "disable"}
        if val not in vals:
            name = Human.untitle(prop["name"])
            use = ", ".join([str(val1) for val1 in vals])
            raise Error(f"bad value '{val}' for {name}, use one of: {use}")

    def _validate_governor_name(self, name):
        """Validate P-state or C-state governor name 'name'."""

        # Get the list of governors to validate 'name' against. Note, the list of governors is the
        # same for all CPUs (global scope).
        governors = self._get_cpu_subprop_value("governor", "governors", 0)
        if name not in governors:
            governors = ", ".join(governors)
            raise Error(f"bad governor name '{name}', use one of: {governors}")

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
        """Read property described by 'prop' from sysfs, and return its value."""

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

    def _write_prop_value_to_sysfs(self, prop, path, val):
        """Write property value 'val' to a sysfs file at path 'path'."""

        if prop["type"] == "int":
            val = int(val)
            if not Trivial.is_int(val):
                raise Error(f"received an unexpected non-integer value from '{prop['name']}'"
                            f"{self._pman.hostmsg}")
            if prop.get("unit") == "Hz":
                # Sysfs files have the numbers in kHz, convert to Hz.
                val //= 1000

        if prop["type"] == "list[str]":
            val = ' '.join(val)

        self._pman.write(path, str(val))

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

    def _get_cpu_prop_value(self, pname, cpu, prop=None):
        """Returns property value for 'pname' in 'prop' for CPU 'cpu'."""

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("PCStatesBase._get_cpu_prop_value")

    def _get_cpu_subprop_value(self, pname, subpname, cpu):
        """Returns sup-property 'subpname' of property 'pname' for CPU 'cpu'."""

        subprop = self._props[pname]["subprops"][subpname]
        return self._get_cpu_prop_value(subpname, cpu, prop=subprop)

    def _get_cpu_props(self, pnames, cpu):
        """Returns all properties in 'pnames' for CPU 'cpu'."""

        pinfo = {}

        for pname in pnames:
            pinfo[pname] = {}

            # Get the 'pname' property.
            pinfo[pname][pname] = self._get_cpu_prop_value(pname, cpu)
            if pinfo[pname][pname] is None:
                _LOG.debug("CPU %d: %s is not supported", cpu, pname)
                continue
            _LOG.debug("CPU %d: %s = %s", cpu, pname, pinfo[pname][pname])

            # Get all the sub-properties.
            for subpname in self._props[pname]["subprops"]:
                if pinfo[pname][pname] is not None:
                    # Get the 'subpname' sub-property.
                    pinfo[pname][subpname] = self._get_cpu_subprop_value(pname, subpname, cpu)
                else:
                    # The property is not supported, so all sub-properties are not supported either.
                    pinfo[pname][subpname] = None
                _LOG.debug("CPU %d: %s = %s", cpu, subpname, pinfo[pname][subpname])

        return pinfo

    def get_props(self, pnames, cpus="all"):
        """
        Read all properties specified in the 'pnames' list for CPUs in 'cpus', and for every CPU
        yield a ('cpu', 'pinfo') tuple, where 'pinfo' is dictionary containing the read values of
        all the properties. The arguments are as follows.
          * pnames - list or an iterable collection of properties to read and yield the values for.
                     These properties will be read for every CPU in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. Value 'all' mean "all CPUs" (default).

        The yielded 'pinfo' dictionaries have the following format.

        { property1_name: { property1_name : property1_value,
                            subprop1_key : subprop1_value,
                            subprop2_key : subprop2_value,
                            ... etc for every key ...},
          property2_name: { property2_name : property2_value,
                            subprop1_key : subprop2_value,
                            ... etc ...},
          ... etc ... }

        So each property has the (main) value, and possibly sub-properties, which provide additional
        read-only information related to the property. For example, the 'epp_policy' property comes
        with the 'epp_policies' sub-property. Most properties have no sub-properties.

        If a property is not supported, its value will be 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        for pname in pnames:
            self._check_prop(pname)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, self._get_cpu_props(pnames, cpu)

    def get_cpu_props(self, pnames, cpu):
        """Same as 'get_props()', but for a single CPU."""

        pinfo = None
        for _, pinfo in self.get_props(pnames, cpus=(cpu,)):
            pass
        return pinfo

    def get_cpu_prop(self, pname, cpu):
        """Same as 'get_props()', but for a single CPU and a single property."""

        pinfo = None
        for _, pinfo in self.get_props((pname,), cpus=(cpu,)):
            pass
        return pinfo

    def set_props(self, inprops, cpus="all"):
        """
        Set multiple properties described by 'inprops' to values also provided in 'inprops'.
          * inprops - an iterable collection of property names and values.
          * cpus - same as in 'get_props()'.

        This method accepts two 'inprops' formats.

        1. An iterable collection (e.g., list or a tuple) of ('pname', 'val') pairs. For example:
           * [(property1_name, property1_value), (property2_name, property2_value)]
        2. A dictionary with property names as keys. For example:
           * {property1_name : property1_value, property2_name : property2_value}

        Properties of "bool" type accept the following values:
           * True, "on", "enable" for enabling the feature.
           * False, "off", "disable" for disabling the feature.
        """

        # pylint: disable=unused-argument,no-self-use
        return _bug_method_not_defined("PCStatesBase.set_props")

    def set_prop(self, pname, val, cpus):
        """Same as 'set_props()', but for a single property."""

        self.set_props(((pname, val),), cpus=cpus)

    def set_cpu_props(self, inprops, cpu):
        """Same as 'set_props()', but for a single CPU."""

        self.set_props(inprops, cpus=(cpu,))

    def set_cpu_prop(self, pname, val, cpu):
        """Same as 'set_props()', but for a single CPU and a single property."""

        self.set_props(((pname, val),), cpus=(cpu,))

    def _validate_prop_scope(self, prop, cpus):
        """
        Make sure that CPUs in 'cpus' match the scope of a property described by 'prop'. For
        example, if the property has "package" scope, 'cpus' should include all CPUs in one or more
        packages.
        """

        scope = prop["scope"]

        if scope not in {"global", "package", "die", "core", "CPU"}:
            raise Error(f"BUG: unsupported scope \"{scope}\"")

        if scope == "CPU":
            return

        if scope == "global":
            all_cpus = set(self._cpuinfo.get_cpus())

            if all_cpus.issubset(cpus):
                return

            name = Human.untitle(prop["name"])
            missing_cpus = all_cpus - set(cpus)
            raise Error(f"{name} has {scope} scope, so the list of CPUs must include all CPUs.\n"
                        f"However, the following CPUs are missing from the list: {missing_cpus}")

        _, rem_cpus = getattr(self._cpuinfo, f"cpus_div_{scope}s")(cpus)
        if not rem_cpus:
            return

        mapping = ""
        for pkg in self._cpuinfo.get_packages():
            pkg_cpus = self._cpuinfo.package_to_cpus(pkg)
            pkg_cpus_str = Human.rangify(pkg_cpus)
            mapping += f"\n  * package {pkg}: CPUs: {pkg_cpus_str}"

            if scope in {"core", "die"}:
                # Build the cores or dies to packages map, in order to make the error message more
                # helpful. We use "core" in variable names, but in case of the "die" scope, they
                # actually mean "die".

                pkg_cores = getattr(self._cpuinfo, f"package_to_{scope}s")(pkg)
                pkg_cores_str = Human.rangify(pkg_cores)
                mapping += f"\n               {scope}s: {pkg_cores_str}"

                # Build the cores to CPUs mapping string.
                clist = []
                for core in pkg_cores:
                    if scope == "core":
                        cpus = self._cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))
                    else:
                        cpus = self._cpuinfo.dies_to_cpus(dies=(core,), packages=(pkg,))
                    cpus_str = Human.rangify(cpus)
                    clist.append(f"{core}:{cpus_str}")

                # The core/die->CPU mapping may be very long, wrap it to 100 symbols.
                import textwrap # pylint: disable=import-outside-toplevel

                prefix = f"               {scope}s to CPUs: "
                indent = " " * len(prefix)
                clist_wrapped = textwrap.wrap(", ".join(clist), width=100,
                                              initial_indent=prefix, subsequent_indent=indent)
                clist_str = "\n".join(clist_wrapped)

                mapping += f"\n{clist_str}"

        name = Human.untitle(prop["name"])
        rem_cpus_str = Human.rangify(rem_cpus)

        if scope == "core":
            mapping_name = "relation between CPUs, cores, and packages"
        elif scope == "die":
            mapping_name = "relation between CPUs, dies, and packages"
        else:
            mapping_name = "relation between CPUs and packages"

        errmsg = f"{name} has {scope} scope, so the list of CPUs must include all CPUs " \
                f"in one or multiple {scope}s.\n" \
                f"However, the following CPUs do not comprise full {scope}(s): {rem_cpus_str}\n" \
                f"Here is the {mapping_name}{self._pman.hostmsg}:{mapping}"

        raise Error(errmsg)

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
