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
 * pvinfo - the property value dictionary, returned by 'get_prop_cpus()' and 'get_cpu_prop()'.
            Includes property value and CPU number. Refer to 'PropsClassBase.get_prop_cpus()' for
            more information.
 * pname - name of a property.
 * sname - functional scope name of the property, i.e., whether the property is per-CPU (affects a
           single CPU), per-core, per-package, etc. Scope names have the same values in
           'CPUInfo.LEVELS': CPU, core, package, etc.
 * core siblings - all CPUs sharing the same core. For example, "CPU6 core siblings" are all CPUs
                   sharing the same core as CPU 6.
 * module siblings - all CPUs sharing the same module.
 * die siblings - all CPUs sharing the same die.
 * package siblings - all CPUs sharing the same package.
"""

import copy
import logging
import contextlib
from pepclibs import CPUInfo, _PropsCache
from pepclibs.helperlibs import Trivial, Human, ClassHelpers, LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = logging.getLogger()

MECHANISMS = {
    "sysfs" : {
        "short": "sysfs",
        "long":  "Linux sysfs file-system",
        "writable": True,
    },
    "msr" : {
        "short": "MSR",
        "long":  "Model Specific Register (MSR)",
        "writable": True,
    },
    "cppc" : {
        "short": "ACPI CPPC",
        "long":  "ACPI Colalborative Processor Performance Control (CPPC)",
        "writable": False,
    },
    "doc" : {
        "short": "Cocumentation",
        "long":  "Hardware documentation",
        "writable": False,
    }
}

def _bug_method_not_defined(method_name):
    """Raise an error if the child class did not define the 'method_name' mandatory method."""

    raise Error(f"BUG: '{method_name}()' was not defined by the child class")

class PropsClassBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for higher level classes implementing properties (e.g. 'CStates' or 'PStates').

    Public methods overview.

    1. Per-CPU methods.
       * 'get_prop_cpus()' - get a property for multiple CPUs.
       * 'get_cpu_prop()' - get a property for a single CPU.
       * 'set_prop_cpus()' - set a property for multiple CPUs.
       * 'set_cpu_prop()' - set a property for a single CPU.
       * 'prop_is_supported_cpu()' - check if a property is supported for a single CPU.
    2. Per-die methods.
       * 'get_prop_dies()' - get a property for multiple dies.
       * 'get_die_prop()' - get a property for a single die.
       * 'set_prop_dies()' - set a property for multiple dies.
       * 'set_die_prop()' - set a property for a single die.
       * 'prop_is_supported_die()' - check if a property is supported for a single die.
    3. Per-package methods.
       * 'get_prop_packages()' - get a property for multiple packages.
       * 'get_package_prop()' - get a property for a single package.
       * 'set_prop_packages()' - set a property for multiple packages.
       * 'set_package_prop()' - set a property for a single package.
       * 'prop_is_supported_package()' - check if a property is supported for a single package.
    4. Misc. methods.
       * 'get_sname()' - get property scope name.
       * 'get_mechanism_descr()' - get a mechanism description string.
    """

    def get_mechanism_descr(self, mname):
        """
        Get a string describing a property mechanism 'mname'. See the 'MECHANISMS' dictionary for
        more information.
        """

        try:
            return self.mechanisms[mname]["long"]
        except KeyError:
            raise Error(f"BUG: missing mechanism description for '{mname}'") from None

    def _validate_mname(self, mname, pname=None, allow_readonly=True):
        """
        Validate if mechanism 'mname'. The arguments are as follwos.
          * mname - name of the mechanism to validate.
          * pname - if provided, ensure that 'mname' is supported by property 'pname'.
          * allow_readonly - if 'True', allow both read-only and read-write mechanisms, otherwise
                             allow only read-write mechanisms.
        """

        if pname:
            all_mnames = self._props[pname]["mnames"]
        else:
            all_mnames = self.mechanisms

        if mname not in all_mnames:
            mnames = ", ".join(all_mnames)
            if pname:
                name = self._props[pname]["name"]
                raise ErrorNotSupported(f"cannot access {name} ({pname}) using the '{mname}' "
                                        f"mechanism{self._pman.hostmsg}.\n"
                                        f"Use one the following mechanism(s) instead: {mnames}.",
                                        mname=mname)
            raise ErrorNotSupported(f"unsupported mechanism '{mname}', supported mechanisms are: "
                                    f"{mnames}.", mname=mname)

        if not allow_readonly and not self.mechanisms[mname]["writable"]:
            if pname:
                name = self._props[pname]["name"]
                raise Error(f"can't use read-only mechanism '{mname}' for modifying "
                            f"{name} ({pname})\n")
            raise Error(f"can't use read-only mechanism '{mname}'")

    def _normalize_mnames(self, mnames, pname=None, allow_readonly=True):
        """Validate and normalize mechanism names in 'mnames'."""

        if mnames is None:
            if pname:
                mnames = self._props[pname]["mnames"]
            else:
                mnames = self.mechanisms
            return list(mnames)

        for mname in mnames:
            self._validate_mname(mname, pname=pname, allow_readonly=allow_readonly)

        return Trivial.list_dedup(mnames)

    def _set_sname(self, pname):
        """
        Set scope name for property 'pname'. Some properties have platform-dependent scope, and this
        method exists for assigning scope name depending on the platform.
        """

        if self._props[pname]["sname"]:
            return

        _bug_method_not_defined("PropsClassBase._set_sname")

    def get_sname(self, pname):
        """
        Return scope name for the 'pname' property. May return 'None' if the property is not
        supported, but this is not guaranteed.

        If the property is not supported by the platform, this method does not guarantee that 'None'
        is returned. Depending on the property and platform, this method may return a valid scope
        name even if the property is not actually supported.
        """

        try:
            if not self._props[pname]["sname"]:
                try:
                    self._set_sname(pname)
                except ErrorNotSupported:
                    return None

            return self._props[pname]["sname"]
        except KeyError as err:
            raise Error(f"property '{pname}' does not exist") from err

    @staticmethod
    def _normalize_bool_type_value(pname, val):
        """
        Normalize and validate value 'val' of a boolean-type property 'pname'. Returns the boolean
        value corresponding to 'val'.
        """

        if val in (True, False):
            return val

        val = val.lower()
        if val in ("on", "enable"):
            return True

        if val in ("off", "disable"):
            return False

        name = Human.uncapitalize(pname)
        raise Error(f"bad value '{val}' for {name}, use one of: True, False, on, off, enable, "
                    f"disable")

    def _validate_pname(self, pname):
        """Raise an exception if property 'pname' is unknown."""

        if pname not in self._props:
            pnames_str = ", ".join(set(self._props))
            raise Error(f"unknown property name '{pname}', known properties are: {pnames_str}")

    def _validate_cpus_vs_scope(self, pname, cpus):
        """Make sure that CPUs in 'cpus' match the scope of a property 'pname'."""

        sname = self._props[pname]["sname"]
        name = Human.uncapitalize(self._props[pname]["name"])

        if sname not in {"global", "package", "die", "core", "CPU"}:
            raise Error(f"BUG: unsupported scope name \"{sname}\"")

        if sname == "CPU":
            return

        if sname == "global":
            all_cpus = set(self._cpuinfo.get_cpus())

            if all_cpus.issubset(cpus):
                return

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

    def _validate_prop_vs_scope(self, pname, sname):
        """
        Validate that 'pname' is suitable for accessing on per-die or per-package bases (the scope
        is defined by 'sname').
        """

        if sname == "die":
            ok_scopes = set(("die", "package", "global"))
        elif sname == "package":
            ok_scopes = set(("package", "global"))
        else:
            raise Error(f"BUG: support for scope {sname} is not implemented")

        # If there is only one die per package, assume that "package" and "die" scopes are the same
        # thing and allow for setting per-die features using per-package interface and vice-versa.
        if len(self._cpuinfo.get_dies(package=0)) == 1:
            ok_scopes.add("die")

        prop = self._props[pname]

        if prop["sname"] not in ok_scopes:
            name = prop["name"]
            snames = ", ".join(ok_scopes)
            raise Error(f"cannot access {name} on per-{sname} basis, because it has "
                        f"{prop['sname']} scope{self._pman.hostmsg}.\nPer-{sname} access is only "
                        f"allowed for properties with the following scopes: {snames}")

    @staticmethod
    def _construct_pvinfo(pname, cpu, mname, val):
        """Construct and return the property value dictionary."""

        if isinstance(val, bool):
            val = "on" if val is True else "off"
        return {"cpu": cpu, "pname": pname, "val": val, "mname": mname}

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

        return self._msr

    def _get_cpu_prop_pvinfo(self, pname, cpu, mnames=None):
        """
        This method should be implemented by the sub-class. The arguments and the same as in
        'get_prop_cpus()'. Returns the property value dictionary.
        """

        # pylint: disable=unused-argument
        return _bug_method_not_defined("PropsClassBase._get_cpu_prop")

    def _get_cpu_prop(self, pname, cpu, mnames=None):
        """Read property 'pname' and return the value."""

        return self._get_cpu_prop_pvinfo(pname, cpu, mnames=mnames)["val"]

    def get_prop_cpus(self, pname, cpus="all", mnames=None):
        """
        Read property 'pname' for CPUs in 'cpus', and for every CPU yield the property value
        dictionary. The arguments are as follows.
          * pname - name of the property to read and yield the values for. The property will be read
                    for every CPU in 'cpus'.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for getting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                     property will be tried.

        The property value dictionary has the following format:
            { "cpu": CPU number,
              "val": value of property 'pname' on the given CPU,
              "mname" : name of the mechanism that was used for getting the property }

        If a property is not supported, the 'val' and 'mname' keys will contain 'None'.

        Properties of "bool" type use the following values:
           * "on" if the feature is enabled.
           * "off" if the feature is disabled.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        with contextlib.suppress(ErrorNotSupported):
            self._set_sname(pname)

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            pvinfo = self._get_cpu_prop_pvinfo(pname, cpu, mnames)
            _LOG.debug("'%s' is '%s' for CPU %d using mechanism '%s'%s",
                    pname, pvinfo["val"], cpu, pvinfo["mname"], self._pman.hostmsg)
            yield pvinfo

    def get_cpu_prop(self, pname, cpu, mnames=None):
        """
        Similar to 'get_prop_cpus()', but for a single CPU and a single property. The arguments are
        as follows:
          * pname - name of the property to get.
          * cpu - CPU number to get the property for.
          * mnames - same as in 'get_prop_cpus()'.
        """

        for pvinfo in self.get_prop_cpus(pname, cpus=(cpu,), mnames=mnames):
            return pvinfo

    def prop_is_supported_cpu(self, pname, cpu):
        """
        Return 'True' if property 'pname' is supported by CPU 'cpu, otherwise return 'False'. The
        arguments are as follows:
          * pname - property name to check.
          * cpu - CPU number to check the property for.
        """

        return self.get_cpu_prop(pname, cpu)["val"] is not None

    def get_prop_dies(self, pname, dies="all", mnames=None):
        """
        Read property 'pname' for dies in 'dies'. For every die, yield the property value
        dictionary. This is similar to 'get_prop_cpus()', but works on per-die basis.

        The arguments are as follows.
          * pname - name of the property to read and yield the values for. The property will be read
                    for every die in 'dies'.
          * dies - a dictionary with keys being integer package numbers and values being a
                   collection of integer die numbers in the package. Special value 'all' means "all
                   dies in all packages".
          * mnames - list of mechanisms to use for getting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                     property will be tried.

        Unlike CPU numbers, die numbers are relative to package numbers. For example, on a two
        socket system there may be die 0 in both packages 0 and 1. Therefore, the 'dies' argument is
        a dictionary, not just a list of integer die numbers.

        The property value dictionary has the following format:
            { "die": die number within the package,
              "package": package number,
              "val": value of property 'pname' for the given package and die,
              "mname" : name of the mechanism that was used for getting the property }

        Otherwise the same as 'get_prop_cpus()'.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        with contextlib.suppress(ErrorNotSupported):
            self._set_sname(pname)

        self._validate_prop_vs_scope(pname, "die")

        # Emulate using the per-CPU interface so far (temporary solution).
        for package in self._cpuinfo.normalize_packages(dies):
            for die in self._cpuinfo.normalize_dies(dies[package], package=package):
                cpu = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))[0]
                pvinfo = self.get_cpu_prop(pname, cpu, mnames=mnames)

                die_pvinfo = {}
                die_pvinfo["die"] = die
                die_pvinfo["package"] = package
                die_pvinfo["val"] = pvinfo["val"]
                die_pvinfo["mname"] = pvinfo["mname"]

                yield die_pvinfo

    def get_die_prop(self, pname, die, package, mnames=None):
        """
        Similar to 'get_prop_dies()', but for a single die and a single property. The arguments are
        as follows:
          * pname - name of the property to get.
          * die - die number to get the property for.
          * package - package number for die 'die'.
          * mnames - same as in 'get_prop_dies()'.
        """

        for pvinfo in self.get_prop_dies(pname, dies={package: (die,)}, mnames=mnames):
            return pvinfo

    def prop_is_supported_die(self, pname, die, package):
        """
        Return 'True' if property 'pname' is supported by die 'die' on package 'package', otherwise
        return 'False'. The arguments are as follows:
          * pname - property name to check.
          * die - die number to check the property for.
          * package - package number for die 'die'.
        """

        return self.get_die_prop(pname, die, package)["val"] is not None

    def get_prop_packages(self, pname, packages="all", mnames=None):
        """
        Read property 'pname' for packages in 'packages', and for every package yield the property
        value dictionary. This is similar to 'get_prop_cpus()', but works on per-package basis. The
        arguments are as follows.
          * pname - name of the property to read and yield the values for. The property will be read
                    for every package in 'packages'.
          * packages - collection of integer package numbers. Special value 'all' means "all
                       packages".
          * mnames - list of mechanisms to use for getting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                     property will be tried.

        The property value dictionary has the following format:
            { "package": package number,
              "val": value of property 'pname' for the given package,
              "mname" : name of the mechanism that was used for getting the property }

        Otherwise the same as 'get_prop_cpus()'.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        with contextlib.suppress(ErrorNotSupported):
            self._set_sname(pname)

        self._validate_prop_vs_scope(pname, "package")

        # Emulate using the per-CPU interface so far (temporary solution).
        for package in self._cpuinfo.normalize_packages(packages):
            cpu = self._cpuinfo.package_to_cpus(package)[0]
            pvinfo = self.get_cpu_prop(pname, cpu, mnames=mnames)

            pkg_pvinfo = {}
            pkg_pvinfo["package"] = package
            pkg_pvinfo["val"] = pvinfo["val"]
            pkg_pvinfo["mname"] = pvinfo["mname"]

            yield pkg_pvinfo

    def get_package_prop(self, pname, package, mnames=None):
        """
        Similar to 'get_prop_packages()', but for a single package and a single property. The
        arguments are as follows:
          * pname - name of the property to get.
          * package - package number to get the property for.
          * mnames - same as in 'get_prop_packages()'.
        """

        for pvinfo in self.get_prop_packages(pname, packages=(package,), mnames=mnames):
            return pvinfo

    def prop_is_supported_package(self, pname, package):
        """
        Return 'True' if property 'pname' is supported by package 'package, otherwise return
        'False'. The arguments are as follows:
          * pname - property name to check.
          * package - package number to check the property for.
        """

        return self.get_package_prop(pname, package)["val"] is not None

    def _normalize_inprop(self, pname, val):
        """Normalize and return the input property value."""

        self._validate_pname(pname)

        prop = self._props[pname]
        if not prop["writable"]:
            name = Human.uncapitalize(pname)
            raise Error(f"{name} is read-only and can not be modified{self._pman.hostmsg}")

        if prop.get("type") == "bool":
            val = self._normalize_bool_type_value(pname, val)

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

    def _set_prop_cpus(self, pname, val, cpus, mnames=None):
        """Implements 'set_prop_cpus()'. The arguments are as the same as in 'set_prop_cpus()'."""

        # pylint: disable=unused-argument
        return _bug_method_not_defined("PropsClassBase.set_prop_cpus")

    def set_prop_cpus(self, pname, val, cpus, mnames=None):
        """
        Set property 'pname' to value 'val' for CPUs in 'cpus'. The arguments are as follows.
          * pname - name of the property to set.
          * val - value to set the property to.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for setting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. Any mechanism is allowed by default.

        Properties of "bool" type have the following values:
           * True, "on", "enable" for enabling the feature.
           * False, "off", "disable" for disabling the feature.

        Returns name of the mechanism that was used for setting the property.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)
        cpus = self._cpuinfo.normalize_cpus(cpus)

        self._set_sname(pname)
        self._validate_cpus_vs_scope(pname, cpus)

        return self._set_prop_cpus(pname, val, cpus, mnames=mnames)

    def set_cpu_prop(self, pname, val, cpu, mnames=None):
        """
        Similar to 'set_prop_cpus()', but for a single CPU and a single property. The arguments are
        as follows:
          * pname - name of the property to set.
          * val - the value to set the property to.
          * cpu - CPU number to set the property for.
          * mnames - same as in 'set_prop_cpus()'.
        """

        return self.set_prop_cpus(pname, val, (cpu,), mnames=mnames)

    def set_prop_dies(self, pname, val, dies, mnames=None):
        """
        Set property 'pname' to value 'val' for dies in 'dies'. The arguments are as follows.
          * pname - name of the property to set.
          * val - value to set the property to.
          * dies - a dictionary with keys being integer package numbers and values being a
                   collection of integer die numbers in the package. Special value 'all' means "all
                   dies in all packages".
          * mnames - list of mechanisms to use for setting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. Any mechanism is allowed by default.

        Otherwise the same as 'set_prop_cpus()'.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "die")

        # Emulate using the per-CPU interface so far (temporary solution).
        cpus = []
        for package in self._cpuinfo.normalize_packages(dies):
            for die in self._cpuinfo.normalize_dies(dies[package], package=package):
                die_cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                cpus += die_cpus

        return self._set_prop_cpus(pname, val, cpus, mnames=mnames)

    def set_die_prop(self, pname, val, die, package, mnames=None):
        """
        Similar to 'set_prop_dies()', but for a single die and a single property. The arguments are
        as follows:
          * pname - name of the property to set.
          * val - the value to set the property to.
          * die - die number to set the property for.
          * package - package number for die 'die'.
          * mnames - same as in 'set_prop_dies()'.
        """

        return self.set_prop_dies(pname, val, {package: (die,)}, mnames=mnames)

    def set_prop_packages(self, pname, val, packages, mnames=None):
        """
        Set property 'pname' to value 'val' for packages in 'packages'. The arguments are as
        follows.
          * pname - name of the property to set.
          * val - value to set the property to.
          * packages - collection of integer package numbers. Special value 'all' means "all CPUs".
          * mnames - list of mechanisms to use for setting the property (see
                     '_PropsClassBase.MECHANISMS'). The mechanisms will be tried in the order
                     specified in 'mnames'. Any mechanism is allowed by default.

        Otherwise the same as 'set_prop_cpus()'.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "package")

        # Emulate using the per-CPU interface so far (temporary solution).
        cpus = []
        for package in self._cpuinfo.normalize_packages(packages):
            cpu = self._cpuinfo.package_to_cpus(package)[0]
            cpus.append(cpu)

        return self._set_prop_cpus(pname, val, cpus, mnames=mnames)

    def set_package_prop(self, pname, val, package, mnames=None):
        """
        Similar to 'set_prop_packages()', but for a single package and a single property. The
        arguments are as follows:
          * pname - name of the property to set.
          * val - the value to set the property to.
          * package - package number to set the property for.
          * mnames - same as in 'set_prop_packages()'.
        """

        return self.set_prop_packages(pname, val, (package,), mnames=mnames)

    def _init_props_dict(self, props):
        """Initialize the 'props' and 'mechanisms' dictionaries."""

        self._props = copy.deepcopy(props)
        self.props = props

        # Initialize the 'mechanisms' dictionary, which includes the mechanisms supported by the
        # subclass.
        seen = set()
        for prop in self._props.values():
            seen.update(prop["mnames"])

        self.mechanisms = {}
        for mname, minfo in MECHANISMS.items():
            if mname in seen:
                self.mechanisms[mname] = minfo

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target system..
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - enable properties caching if 'True'.
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
        # Dictionary describing all supported mechanisms. Same as 'MECHANISMS', but includes only
        # the mechanisms that at least one property supports.
        self.mechanisms = None

        # The write-through per-CPU properties cache. The properties that are backed by MSR/EPP/EPB
        # are not cached, because they implement their own caching.
        self._enable_cache = enable_cache
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=self._enable_cache)

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_pcache", "_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
