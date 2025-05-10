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

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
from typing import TypedDict

from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, Trivial, Human, ClassHelpers, LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class MechanismsTypedDict(TypedDict):
    """
    Dictionary describing a mechanism for getting or setting a property.

    Attributes:
        short: A short name or identifier for the mechanism.
        long: A more descriptive name for the mechanism (but still a one-liner).
        writable: Whether the mechanism property is writable.
    """

    short: str
    long: str
    writable: bool

MECHANISMS: dict[str, MechanismsTypedDict] = {
    "sysfs" : {
        "short": "sysfs",
        "long":  "Linux sysfs file-system",
        "writable": True,
    },
    "cdev" : {
        "short": "cdev",
        "long":  "Linux character device node",
        "writable": True,
    },
    "msr" : {
        "short": "MSR",
        "long":  "Model Specific Register (MSR)",
        "writable": True,
    },
    "cppc" : {
        "short": "ACPI CPPC",
        "long":  "ACPI Collaborative Processor Performance Control (CPPC)",
        "writable": False,
    },
    "doc" : {
        "short": "Documentation",
        "long":  "Hardware documentation",
        "writable": False,
    }
}

class ErrorUsePerCPU(Error):
    """
    Raise when a per-die or per-package property "get" method cannot provide a reliable result due to
    sibling CPUs having different property values.

    Use the per-CPU 'get_prop_cpus()' method instead. This situation can occur when a property's
    scope differs from its I/O scope, resulting in inconsistent values among sibling CPUs.
    """

class ErrorTryAnotherMechanism(Error):
    """
    Raise when a property is unsupported by the current mechanism but may be available via others.

    This exception indicates that the requested property cannot be retrieved using the specified
    mechanism. However, alternative mechanisms may support this property.
    """

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
        Validate if mechanism 'mname'. The arguments are as follows.
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
                name = Human.uncapitalize(self._props[pname]["name"])
                raise ErrorNotSupported(f"{name} is not available via the '{mname}' mechanism"
                                        f"{self._pman.hostmsg}.\nUse one the following "
                                        f"mechanism(s) instead: {mnames}.", mname=mname)
            raise ErrorNotSupported(f"unsupported mechanism '{mname}', supported mechanisms are: "
                                    f"{mnames}.", mname=mname)

        if not allow_readonly and not self.mechanisms[mname]["writable"]:
            if pname:
                name = Human.uncapitalize(self._props[pname]["name"])
                raise Error(f"can't use read-only mechanism '{mname}' for modifying {name}\n")
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

        raise ErrorNotSupported("PropsClassBase._set_sname")

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

    def _normalize_bool_type_value(self, pname, val):
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

        name = Human.uncapitalize(self._props[pname]["name"])
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

        if sname not in {"global", "package", "die", "core", "CPU"}:
            raise Error(f"BUG: unsupported scope name \"{sname}\"")

        if sname == "CPU":
            return

        if sname == "global":
            all_cpus = set(self._cpuinfo.get_cpus())

            if all_cpus.issubset(cpus):
                return

            missing_cpus = all_cpus - set(cpus)
            name = Human.uncapitalize(self._props[pname]["name"])
            raise Error(f"{name} has {sname} scope, so the list of CPUs must include all CPUs.\n"
                        f"However, the following CPUs are missing from the list: {missing_cpus}")

        _, rem_cpus = getattr(self._cpuinfo, f"cpus_div_{sname}s")(cpus)
        if not rem_cpus:
            return

        mapping = ""
        for pkg in self._cpuinfo.get_packages():
            pkg_cpus = self._cpuinfo.package_to_cpus(pkg)
            pkg_cpus_str = Trivial.rangify(pkg_cpus)
            mapping += f"\n  * package {pkg}: CPUs: {pkg_cpus_str}"

            if sname in {"core", "die"}:
                # Build the cores or dies to packages map, in order to make the error message more
                # helpful. We use "core" in variable names, but in case of the "die" scope name,
                # they actually mean "die".

                pkg_cores = getattr(self._cpuinfo, f"package_to_{sname}s")(pkg)
                pkg_cores_str = Trivial.rangify(pkg_cores)
                mapping += f"\n               {sname}s: {pkg_cores_str}"

                # Build the cores to CPUs mapping string.
                clist = []
                for core in pkg_cores:
                    if sname == "core":
                        cpus = self._cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))
                    else:
                        cpus = self._cpuinfo.dies_to_cpus(dies=(core,), packages=(pkg,))
                    cpus_str = Trivial.rangify(cpus)
                    clist.append(f"{core}:{cpus_str}")

                # The core/die->CPU mapping may be very long, wrap it to 100 symbols.
                import textwrap # pylint: disable=import-outside-toplevel

                prefix = f"               {sname}s to CPUs: "
                indent = " " * len(prefix)
                clist_wrapped = textwrap.wrap(", ".join(clist), width=100,
                                              initial_indent=prefix, subsequent_indent=indent)
                clist_str = "\n".join(clist_wrapped)

                mapping += f"\n{clist_str}"

        rem_cpus_str = Trivial.rangify(rem_cpus)

        if sname == "core":
            mapping_name = "relation between CPUs, cores, and packages"
        elif sname == "die":
            mapping_name = "relation between CPUs, dies, and packages"
        else:
            mapping_name = "relation between CPUs and packages"

        name = Human.uncapitalize(self._props[pname]["name"])
        errmsg = f"{name} ({pname}) has {sname} scope, so the list of CPUs must include all CPUs " \
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

        prop = self._props[pname]

        if prop["sname"] not in ok_scopes:
            name = Human.uncapitalize(prop["name"])
            snames = ", ".join(ok_scopes)
            raise Error(f"cannot access {name} on per-{sname} basis, because it has "
                        f"{prop['sname']} scope{self._pman.hostmsg}.\nPer-{sname} access is only "
                        f"allowed for properties with the following scopes: {snames}")

    def _validate_prop_vs_ioscope(self, pname, cpus, mnames=None, **kwargs):
        """
        Verify the property 'pname' has the same value on all CPUs in 'cpus'.

        This method should only be used for properties that have different scope and I/O scope.
        Please, refer to 'FeatruedMSR' module docstring for information about "scope" vs "I/O
        scope".

        Example of a situation this method helps catching.

        This "Package C-state Limit" property has package scope, but the corresponding MSR has core
        scope on many Intel platforms. This means, that the MSR may have different value on
        different cores, and it is impossible to tell what is the actual package C-state limit
        value.
        """

        same = True
        prev_cpu = None
        disagreed_pvinfos = None
        pvinfos = {}

        for pvinfo in self._get_prop_pvinfo_cpus(pname, cpus, mnames=mnames,
                                                 raise_not_supported=False):
            cpu = pvinfo["cpu"]
            pvinfos[cpu] = pvinfo
            if not same:
                continue

            if prev_cpu is None:
                prev_cpu = cpu
                continue

            if pvinfo["val"] != pvinfos[prev_cpu]["val"]:
                disagreed_pvinfos = (pvinfos[prev_cpu], pvinfo)
                same = False

        if same:
            return

        if "die" in kwargs:
            op_sname = "die"
            for_what = f" for package {kwargs['package']}, die {kwargs['die']}"
        elif "package" in kwargs:
            op_sname = "package"
            for_what = f" for package {kwargs['package']}"
        else:
            raise Error("BUG: unsupported scope")

        cpu1 = disagreed_pvinfos[0]["cpu"]
        val1 = disagreed_pvinfos[0]["val"]
        cpu2 = disagreed_pvinfos[1]["cpu"]
        val2 = disagreed_pvinfos[1]["val"]

        prop = self._props[pname]
        sname = prop["sname"]
        iosname = prop["iosname"]
        name = Human.uncapitalize(prop["name"])

        raise ErrorUsePerCPU(f"cannot determine {name} {for_what}{self._pman.hostmsg}:\n"
                             f"  CPU {cpu1} has value '{val1}', but CPU {cpu2} has value '{val2}', "
                             f"even though they are in the same {op_sname}.\n"
                             f"  This situation is possible because {name} has '{sname}' "
                             f"scope, but '{iosname}' I/O scope.", pvinfos=pvinfos)

    @staticmethod
    def _construct_cpu_pvinfo(pname, cpu, mname, val):
        """Construct and return the property value dictionary for CPU 'cpu'."""

        if isinstance(val, bool):
            val = "on" if val is True else "off"
        return {"cpu": cpu, "pname": pname, "val": val, "mname": mname}

    @staticmethod
    def _construct_die_pvinfo(pname, package, die, mname, val):
        """Construct and return the property value dictionary for die 'die' of package 'package'."""

        if isinstance(val, bool):
            val = "on" if val is True else "off"
        return {"package": package, "die" : die, "pname": pname, "val": val, "mname": mname}

    @staticmethod
    def _construct_package_pvinfo(pname, package, mname, val):
        """Construct and return the property value dictionary for package 'package'."""

        if isinstance(val, bool):
            val = "on" if val is True else "off"
        return {"package": package, "pname": pname, "val": val, "mname": mname}

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_sysfs_io(self):
        """Returns a '_SysfsIO.SysfsIO()' object."""

        if not self._sysfs_io:
            from pepclibs import _SysfsIO # pylint: disable=import-outside-toplevel

            self._sysfs_io = _SysfsIO.SysfsIO(self._pman, enable_cache=self._enable_cache)

        return self._sysfs_io

    def _do_prop_not_supported(self, pname, nums_str, mnames, action, exceptions=None):
        """
        Rase 'ErrorNotSupported' or print a debug message if a property "get" or "set" method
        failed.
        """

        if len(mnames) > 2:
            mnames_quoted = [f"'{mname}'" for mname in mnames]
            mnames_str = f"using {', '.join(mnames_quoted[:-1])} and {mnames_quoted[-1]} methods"
        elif len(mnames) == 2:
            mnames_str = f"using '{mnames[0]}' and '{mnames[1]}' methods"
        else:
            mnames_str = f"using the '{mnames[0]}' method"

        if exceptions:
            errmsgs = Trivial.list_dedup([str(err) for err in exceptions])
            errmsgs = "\n" + "\n".join([Error(errmsg).indent(2) for errmsg in errmsgs])
        else:
            errmsgs = ""

        what = Human.uncapitalize(self._props[pname]["name"])
        msg = f"cannot {action} {what} {mnames_str} for {nums_str}{errmsgs}"
        if exceptions:
            raise ErrorNotSupported(msg)
        _LOG.debug(msg)

    def _prop_not_supported_cpus(self, pname, cpus, mnames, action, exceptions=None):
        """
        Rase 'ErrorNotSupported' or print a debug message if property "get" or "set" method failed
        to get or set a property for CPUs in 'cpus' using mechanisms in 'mnames'.
        """

        if len(cpus) > 1:
            cpus_str = f"the following CPUs: {Trivial.rangify(cpus)}"
        else:
            cpus_str = f"CPU {cpus[0]}"

        self._do_prop_not_supported(pname, cpus_str, mnames, action, exceptions=exceptions)

    def _prop_not_supported_dies(self, pname, dies, mnames, action, exceptions=None):
        """
        Rase 'ErrorNotSupported' or print a debug message if property "get" or "set" method failed
        to get or set a property for dies in 'dies' using mechanisms in 'mnames'.
        """

        dies_str = self._cpuinfo.dies_to_str(dies)
        self._do_prop_not_supported(pname, dies_str, mnames, action, exceptions=exceptions)

    def _prop_not_supported_packages(self, pname, packages, mnames, action, exceptions=None):
        """
        Rase 'ErrorNotSupported' or print a debug message if property "get" or "set" method failed
        to get or set a property for packages in 'packages' using mechanisms in 'mnames'.
        """

        if len(packages) > 1:
            packages_str = f"the following packages: {Trivial.rangify(packages)}"
        else:
            packages_str = f"CPU {packages[0]}"

        self._do_prop_not_supported(pname, packages_str, mnames, action, exceptions=exceptions)

    def _get_prop_cpus(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, 'val' is property 'pname' value for CPU
        'cpu'. Use mechanism 'mname'. If the property is not supported for a CPU, yield 'None' for
        'val'. If the property is not supported for any CPU, raise 'ErrorNotSupported'.

        This method should be implemented by the sub-class.
        """

        raise ErrorNotSupported("PropsClassBase._get_cpu_prop")

    def _get_prop_pvinfo_cpus(self, pname, cpus, mnames=None, raise_not_supported=True):
        """
        For every CPU in 'cpus', yield the property value dictionary ('pvinfo') of property 'pname'.
        Use mechanisms in 'mnames'.
        """

        prop = self._props[pname]
        if not mnames:
            mnames = prop["mnames"]

        exceptions = []

        for mname in mnames:
            cpu = None
            try:
                for cpu, val in self._get_prop_cpus(pname, cpus, mname):
                    _LOG.debug("'%s' is '%s' for CPU %d using mechanism '%s'%s",
                               pname, val, cpu, mname, self._pman.hostmsg)
                    pvinfo = self._construct_cpu_pvinfo(pname, cpu, mname, val)
                    yield pvinfo
                # Yielded a 'pvinfo' for every CPU.
                return
            except ErrorNotSupported as err:
                exceptions.append(err)
                # If something was yielded already, this is an error condition. Otherwise, try the
                # next mechanism.
                if cpu is not None:
                    name = self._props[pname]["name"]
                    raise Error(f"failed to get {name} using the '{mname}' mechanism:\n"
                                f"{err.indent(2)}\nSucceeded getting it for for some CPUs"
                                f"(e.g., CPU {cpu}), but not for all the requested "
                                f"CPUs") from err

        # None of the methods succeeded.
        if raise_not_supported:
            # The below will raise an exception and won't return.
            self._prop_not_supported_cpus(pname, cpus, mnames, "get", exceptions=exceptions)
        else:
            self._prop_not_supported_cpus(pname, cpus, mnames, "get")

        for cpu in cpus:
            yield self._construct_cpu_pvinfo(pname, cpu, mnames[-1], None)

    def _get_prop_cpus_mnames(self, pname, cpus, mnames=None):
        """
        For every CPU in 'cpus', yield '(cpu, val)' tuples, where 'val' is the 'pname' property
        value for CPU 'cpu'. Try mechanisms in 'mnames'.

        This method is similar to the API 'get_prop_cpus()' method, but it does not validate input
        arguments.
        """

        for pvinfo in self._get_prop_pvinfo_cpus(pname, cpus, mnames):
            yield (pvinfo["cpu"], pvinfo["val"])

    def _get_cpu_prop_mnames(self, pname, cpu, mnames=None):
        """
        Read property 'pname' and return the value, try mechanisms in 'mnames'. This method is
        similar to the API method 'get_cpu_prop()', but it does not verify input arguments.
        """

        pvinfo = next(self._get_prop_pvinfo_cpus(pname, (cpu,), mnames))
        return pvinfo["val"]

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

        cpus = self._cpuinfo.normalize_cpus(cpus)
        if len(cpus) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for cpu in cpus:
                yield self._construct_cpu_pvinfo(pname, cpu, mnames[-1], None)
            return

        yield from self._get_prop_pvinfo_cpus(pname, cpus, mnames=mnames, raise_not_supported=False)

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

    def _get_prop_dies(self, pname, dies, mname):
        """
        For every die in 'dies', yield a '(package, die, val)' tuple, where 'val' is property
        'pname' value for die 'die' of package 'package'. Use mechanisms in 'mnames'. If the
        property is not supported for a die, yield 'None' for 'val'. If the property is not
        supported for any die, raise 'ErrorNotSupported'.

        This is the default implementation of the method, which is based on per-CPU access.
        Subclasses may choose to override this default implementation.
        """

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                val = self._get_cpu_prop_mnames(pname, cpus[0], mnames=(mname,))
                yield package, die, val

    def _get_prop_pvinfo_dies(self, pname, dies, mnames=None, raise_not_supported=True):
        """
        For every die in 'dies', yield the property value dictionary ('pvinfo') of property 'pname'.
        Use mechanisms in 'mnames'.
        """

        prop = self._props[pname]
        if not mnames:
            mnames = prop["mnames"]

        exceptions = []

        for mname in mnames:
            pvinfo = None
            try:
                for package, die, val in self._get_prop_dies(pname, dies, mname):
                    _LOG.debug("'%s' is '%s' for package %d, die %d, using mechanism '%s'%s",
                               pname, val, package, die, mname, self._pman.hostmsg)
                    pvinfo = self._construct_die_pvinfo(pname, package, die, mname, val)
                    yield pvinfo
                # Yielded a 'pvinfo' for every die.
                return
            except ErrorNotSupported as err:
                exceptions.append(err)
                # If something was yielded already, this is an error condition. Otherwise, try the
                # next mechanism.
                if pvinfo is not None:
                    name = self._props[pname]["name"]
                    got_pkg = pvinfo["package"]
                    got_die = pvinfo["die"]
                    raise Error(f"failed to get {name} using the '{mname}' mechanism:\n"
                                f"{err.indent(2)}\nSucceeded getting it for for some dies (e.g., "
                                f"package {got_pkg}, die {got_die}), but not for all the requested "
                                f"dies") from err

        # None of the methods succeeded.
        if raise_not_supported:
            # The below will raise an exception and won't return.
            self._prop_not_supported_dies(pname, dies, mnames, "get", exceptions=exceptions)
        else:
            self._prop_not_supported_dies(pname, dies, mnames, "get")

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                yield self._construct_die_pvinfo(pname, package, die, mnames[-1], None)

    def _get_prop_dies_mnames(self, pname, dies, mnames=None):
        """
        For every die in 'dies', yield '(package, die, val)' tuples, where 'val' is the 'pname'
        property value for die 'die' in package 'package'. Try mechanisms in 'mnames'.

        This method is similar to the API 'get_prop_cpus()' method, but it does not validate input
        arguments.
        """

        for pvinfo in self._get_prop_pvinfo_dies(pname, dies, mnames):
            yield (pvinfo["package"], pvinfo["die"], pvinfo["val"])

    def _get_die_prop_mnames(self, pname, package, die, mnames=None):
        """
        Read property 'pname' and return the value, try mechanisms in 'mnames'. This method is
        similar to the API method 'get_die_prop()', but it does not verify input arguments.
        """

        pvinfo = next(self._get_prop_pvinfo_dies(pname, {package: [die]}, mnames))
        return pvinfo["val"]

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

        Unlike CPU numbers, die numbers are may be relative to package numbers (depending on the
        system and kernel version - on some systems they are globally unique). For example, on a two
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

        normalized_dies = {}
        for package in self._cpuinfo.normalize_packages(dies):
            normalized_dies[package] = []
            for die in self._cpuinfo.normalize_dies(dies[package], package=package):
                normalized_dies[package].append(die)

        # Get rid of empty die lists.
        for package, pkg_dies in dies.copy().items():
            if len(pkg_dies) == 0:
                del dies[package]

        if len(dies) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for package, pkg_dies in normalized_dies.items():
                for die in pkg_dies:
                    yield self._construct_die_pvinfo(package, package, die, mnames[-1], None)
            return

        self._validate_prop_vs_scope(pname, "die")

        for package, pkg_dies in normalized_dies.items():
            for die in pkg_dies:
                if self._props[pname]["sname"] == self._props[pname]["iosname"]:
                    continue
                cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                self._validate_prop_vs_ioscope(pname, cpus, mnames=mnames, package=package, die=die)

        yield from self._get_prop_pvinfo_dies(pname, normalized_dies, mnames=mnames,
                                              raise_not_supported=False)

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

    def _get_prop_packages(self, pname, packages, mname):
        """
        For every package in 'packages', yield a '(package, val)' tuple, where 'val' is property
        'pname' value for package 'package'. Use mechanisms in 'mnames'. If the
        property is not supported for a package, yield 'None' for 'val'. If the property is not
        supported for any package, raise 'ErrorNotSupported'.

        This is the default implementation of the method, which is based on per-CPU access.
        Subclasses may choose to override this default implementation.
        """

        for package in packages:
            cpus = self._cpuinfo.package_to_cpus(package)
            val = self._get_cpu_prop_mnames(pname, cpus[0], mnames=(mname,))
            yield package, val

    def _get_prop_pvinfo_packages(self, pname, packages, mnames=None, raise_not_supported=True):
        """
        For every package in 'packages', yield the property value dictionary ('pvinfo') of property
        'pname'.  Use mechanisms in 'mnames'.
        """

        prop = self._props[pname]
        if not mnames:
            mnames = prop["mnames"]

        exceptions = []

        for mname in mnames:
            package = None
            try:
                for package, val in self._get_prop_packages(pname, packages, mname):
                    _LOG.debug("'%s' is '%s' for package %d using mechanism '%s'%s",
                               pname, val, package, mname, self._pman.hostmsg)
                    pvinfo = self._construct_package_pvinfo(pname, package, mname, val)
                    yield pvinfo
                # Yielded a 'pvinfo' for every package.
                return
            except ErrorNotSupported as err:
                exceptions.append(err)
                # If something was yielded already, this is an error condition. Otherwise, try the
                # next mechanism.
                if package is not None:
                    name = self._props[pname]["name"]
                    raise Error(f"failed to get {name} using the '{mname}' mechanism:\n"
                                f"{err.indent(2)}\nSucceeded getting it for for some packages "
                                f"(e.g., package {package}), but not for all the requested "
                                f"packages") from err

        # None of the methods succeeded.
        if raise_not_supported:
            # The below will raise an exception and won't return.
            self._prop_not_supported_packages(pname, packages, mnames, "get", exceptions=exceptions)
        else:
            self._prop_not_supported_packages(pname, packages, mnames, "get")

        for package in packages:
            yield self._construct_package_pvinfo(pname, package, mnames[-1], None)

    def _get_prop_packages_mnames(self, pname, packages, mnames=None):
        """
        For every package in 'packages', yield '(package, val)' tuples, where 'val' is the 'pname'
        property value for package 'package'. Try mechanisms in 'mnames'.

        This method is similar to the API 'get_prop_packages()' method, but it does not validate
        input arguments.
        """

        for pvinfo in self._get_prop_pvinfo_packages(pname, packages, mnames):
            yield (pvinfo["package"], pvinfo["val"])

    def _get_package_prop_mnames(self, pname, package, mnames=None):
        """
        Read property 'pname' and return the value, try mechanisms in 'mnames'. This method is
        similar to the API method 'get_package_prop()', but it does not verify input arguments.
        """

        pvinfo = next(self._get_prop_pvinfo_packages(pname, (package,), mnames))
        return pvinfo["val"]

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

        packages = self._cpuinfo.normalize_packages(packages)
        if len(packages) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for package in packages:
                yield self._construct_package_pvinfo(pname, package, mnames[-1], None)
            return

        self._validate_prop_vs_scope(pname, "package")

        for package in packages:
            if self._props[pname]["sname"] == self._props[pname]["iosname"]:
                continue
            cpus = self._cpuinfo.package_to_cpus(package)
            self._validate_prop_vs_ioscope(pname, cpus, mnames=mnames, package=package)

        yield from self._get_prop_pvinfo_packages(pname, packages, mnames=mnames,
                                                  raise_not_supported=False)

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

        if val is None:
            name = Human.uncapitalize(prop["name"])
            raise Error(f"bad value 'None' for {name}")

        if not prop["writable"]:
            name = Human.uncapitalize(prop["name"])
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
                val = Human.parse_human(val, unit=prop["unit"], integer=is_integer, what=name)

        return val

    def _set_prop_cpus(self, pname, val, cpus, mname):
        """
        Set property 'pname' to value 'val' for CPUs in 'cpus'. Use mechanism 'mname'. This method
        should be implemented by the sub-class.
        """

        raise ErrorNotSupported("PropsClassBase.set_prop_cpus")

    def _set_prop_cpus_mnames(self, pname, val, cpus, mnames):
        """Implement 'set_prop_cpus()'."""

        if not mnames:
            mnames = self._props[pname]["mnames"]

        exceptions = []

        for mname in mnames:
            try:
                self._set_prop_cpus(pname, val, cpus, mname)
            except (ErrorNotSupported, ErrorTryAnotherMechanism) as err:
                exceptions.append(err)
                continue

            return mname

        self._prop_not_supported_cpus(pname, cpus, mnames, "set", exceptions=exceptions)

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
        if len(cpus) == 0:
            raise Error(f"BUG: no CPU numbers provided for setting {self._props[pname]['name']}"
                        f"{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_cpus_vs_scope(pname, cpus)

        return self._set_prop_cpus_mnames(pname, val, cpus, mnames)

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

    def _reduce_cpus_ioscope(self, cpus, iosname):
        """
        Reduce the list of CPUs in 'cpus' to only one CPU in the scope 'iosname'. The arguments are
        as follows.
          * cpus - list of integer CPU numbers to reduce.
          * iosname - I/O scope name to reduce the 'cpus' list to.

        Return the reduced list of CPU numbers.
        """

        if iosname == "CPU":
            return cpus

        handled = set()
        reduced = set()
        for cpu in cpus:
            if cpu in handled:
                continue

            siblings = self._cpuinfo.get_cpu_siblings(cpu, iosname)
            reduced.add(siblings[0])
            if len(siblings) > 1:
                handled.update(siblings[1:])

        result = []
        for cpu in cpus:
            if cpu in reduced:
                result.append(cpu)

        return result

    def _set_prop_dies(self, pname, val, dies, mname):
        """
        The default implementation of 'set_prop_dies()' using the per-CPU method. Subclasses may
        choose to override this default implementation.
        """

        cpus = []
        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                cpus += self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))

        cpus = self._reduce_cpus_ioscope(cpus, self._props[pname]["iosname"])
        return self._set_prop_cpus_mnames(pname, val, cpus, mnames=(mname,))

    def _set_prop_dies_mnames(self, pname, val, dies, mnames):
        """Implement 'set_prop_dies()'."""

        if not mnames:
            mnames = self._props[pname]["mnames"]

        exceptions = []

        for mname in mnames:
            try:
                self._set_prop_dies(pname, val, dies, mname)
            except (ErrorNotSupported, ErrorTryAnotherMechanism) as err:
                exceptions.append(err)
                continue

            return mname

        self._prop_not_supported_dies(pname, dies, mnames, "set", exceptions=exceptions)

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

        normalized_dies = {}
        for package in self._cpuinfo.normalize_packages(dies):
            normalized_dies[package] = []
            for die in self._cpuinfo.normalize_dies(dies[package], package=package):
                normalized_dies[package].append(die)

        # Make sure there are some die numbers.
        for package, pkg_dies in dies.copy().items():
            if len(pkg_dies) == 0:
                raise Error(f"BUG: no package {package} die numbers provided for setting "
                            f"{self._props[pname]['name']}{self._pman.hostmsg}")
        if len(dies) == 0:
            raise Error(f"BUG: no package and die numbers provided for setting "
                        f"{self._props[pname]['name']}{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "die")

        return self._set_prop_dies_mnames(pname, val, normalized_dies, mnames)

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

    def _set_prop_packages(self, pname, val, packages, mname):
        """
        The default implementation of 'set_prop_packages()' using the per-CPU method. Subclasses may
        choose to override this default implementation.
        """

        cpus = []
        for package in packages:
            cpus += self._cpuinfo.packages_to_cpus(packages=(package,))

        cpus = self._reduce_cpus_ioscope(cpus, self._props[pname]["iosname"])
        return self._set_prop_cpus_mnames(pname, val, cpus, mnames=(mname,))

    def _set_prop_packages_mnames(self, pname, val, packages, mnames):
        """Implement 'set_prop_packages()'."""

        if not mnames:
            mnames = self._props[pname]["mnames"]

        exceptions = []

        for mname in mnames:
            try:
                self._set_prop_packages(pname, val, packages, mname)
            except (ErrorNotSupported, ErrorTryAnotherMechanism) as err:
                exceptions.append(err)
                continue

            return mname

        self._prop_not_supported_packages(pname, packages, mnames, "set", exceptions=exceptions)

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

        normalized_packages = self._cpuinfo.normalize_packages(packages)
        if len(packages) == 0:
            raise Error(f"BUG: no package numbers provided for setting "
                        f"{self._props[pname]['name']}{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "package")

        return self._set_prop_packages_mnames(pname, val, normalized_packages, mnames)

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

        # Initialize the 'ioscope' to the same value as 'scope'. I/O scope may be different to the
        # scope for some MSR-based properties. Please, refer to 'MSR.py' for more information about
        # the difference between "scope" and "I/O scope".
        for prop in self._props.values():
            prop["iosname"] = prop["sname"]

        # Initialize the 'mechanisms' dictionary, which includes the mechanisms supported by the
        # subclass.
        seen = set()
        for prop in self._props.values():
            seen.update(prop["mnames"])

        self.mechanisms = {}
        for mname, minfo in MECHANISMS.items():
            if mname in seen:
                self.mechanisms[mname] = minfo

    def __init__(self, pman=None, cpuinfo=None, msr=None, sysfs_io=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target system..
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * sysfs_io - an '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                       files.
          * enable_cache - enable properties caching if 'True'.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._sysfs_io = sysfs_io

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_sysfs_io = sysfs_io is None

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

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
