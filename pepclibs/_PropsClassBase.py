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
Provide the base class for implementing property classes, such as 'PStates' and 'CStates'.

Terminology:
 * Sub-property: A property that is related to a main property and only exists or is meaningful when
                 the main property is supported by the platform. Sub-properties must be read-only.

Naming conventions:
 * props: A dictionary describing the properties. For example, see 'PROPS' in 'PStates' and
         'CStates'.
 * pvinfo: The property value dictionary returned by 'get_prop_cpus()' and 'get_cpu_prop()'. It has
           the 'PVInfoTypedDict' type.
 * pname: The name of a property.
 * sname: The functional scope name of the property, indicating whether the property is per-CPU,
          per-core, per-package, etc. Scope names correspond to those in 'CPUInfo.LEVELS': CPU,
          core, package, etc.
 * iosname: The I/O scope name of the property. Typically the same as 'sname', but may differ in
            for some MSR-backed properties. More information:
            https://github.com/intel/pepc/blob/main/docs/misc-msr-scope.md
 * core siblings: All CPUs sharing the same core. For example, "CPU6 core siblings" are all CPUs
                  sharing the same core as CPU 6.
 * module siblings: All CPUs sharing the same module.
 * die siblings: All CPUs sharing the same die.
 * package siblings: All CPUs sharing the same package.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
from typing import Any, TypedDict, Literal, get_args, Generator
from pepclibs.CPUInfo import CPUInfo
from pepclibs.helperlibs import Logging, Trivial, Human, ClassHelpers, LocalProcessManager
from pepclibs.msr import MSR
from pepclibs import _SysfsIO
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class MechanismsTypedDict(TypedDict):
    """
    Type for the mechanism description dictionary.

    Attributes:
        short: A short name or identifier for the mechanism.
        long: A more descriptive name for the mechanism (but still a one-liner).
        writable: Whether the mechanism property is writable.
    """

    short: str
    long: str
    writable: bool

ScopeNameType = Literal["CPU", "core", "package", "die", "global"]
MechanismNameType = Literal["sysfs", "cdev", "msr", "cppc", "doc"]

# A handy alias for a collection of mechanism names
MechanismNamesType = list[MechanismNameType] | tuple[MechanismNameType, ...]

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

PropertyTypeType = Literal["int", "float", "bool", "str"]

class PropertyTypedDict(TypedDict, total=False):
    """
    Type for the property description dictionary.

    Attributes:
        name: The name of the property.
        unit: The unit of the property value (e.g., "Hz", "W").
        type: The type of the property value (e.g., "int", "float", "bool").
        sname: The scope name of the property (e.g., "CPU", "core", "package").
        iosname: The I/O scope name of the property.
        mnames: A tuple of mechanism names supported by the property.
        writable: Whether the property is writable.
        special_vals: A set of special values for the property.
        subprops: A tuple of sub-properties related to this property.
    """

    name: str
    unit: str
    type: PropertyTypeType
    sname: ScopeNameType
    iosname: ScopeNameType
    mnames: tuple[MechanismNameType, ...]
    writable: bool
    special_vals: set[str]
    subprops: tuple[str, ...]

class IntPropertyTypedDict(TypedDict, total=False):
    """
    Type for the internal property description dictionary. It is similar to 'PropertyTypedDict', but
    some attributes may not be initialized, and there are some additional internal attributes.
    """

    name: str
    unit: str
    type: PropertyTypeType
    sname: ScopeNameType | None
    iosname: ScopeNameType | None
    mnames: tuple[MechanismNameType, ...]
    writable: bool
    special_vals: set[str]
    subprops: tuple[str, ...]

PropertyValueType = int | float | bool | str | None

class PVInfoTypedDict(TypedDict, total=False):
    """
    Type for the property value dictionary (pvinfo).

    Attributes:
        cpu: The CPU number.
        die: The die number.
        package: The package number.
        pname: The name of the property.
        val: The value of the property.
        mname: The name of the mechanism used to retrieve the property.
    """

    cpu: int
    die: int
    package: int
    pname: str
    val: PropertyValueType
    mname: MechanismNameType

# A type for CPU, package, die, etc numbers.
NumsType = list[int] | tuple[int, ...]
# A type for CPU, package, die, etc numbers plus the "all" literal to specify all CPUs, packages,
# dies, etc.
NumsOrAllType = list[int] | tuple[int, ...] | Literal["all"]

class ErrorUsePerCPU(Error):
    """
    Raise when a per-die or per-package property "get" method cannot provide a reliable result due
    to sibling CPUs having different property values.

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
    Base class for implementing property classes, such as 'CStates' or 'PStates'.

    Provide a unified interface for getting and setting properties at various levels of CPU
    topology: per-CPU, per-core, per-module, per-die, and per-package. Handle property validation,
    mechanism selection, and error reporting.

    Public Methods Overview:

    Per-CPU Methods:
        - get_prop_cpus(): Yield property values for multiple CPUs.
        - get_cpu_prop(): Return property value for a single CPU.
        - set_prop_cpus(): Set property value for multiple CPUs.
        - set_cpu_prop(): Set property value for a single CPU.
        - prop_is_supported_cpu(): Check if a property is supported for a single CPU.

    Per-die Methods:
        - get_prop_dies(): Yield property values for multiple dies.
        - get_die_prop(): Return property value for a single die.
        - set_prop_dies(): Set property value for multiple dies.
        - set_die_prop(): Set property value for a single die.
        - prop_is_supported_die(): Check if a property is supported for a single die.

    Per-package Methods:
        - get_prop_packages(): Yield property values for multiple packages.
        - get_package_prop(): Return property value for a single package.
        - set_prop_packages(): Set property value for multiple packages.
        - set_package_prop(): Set property value for a single package.
        - prop_is_supported_package(): Check if a property is supported for a single package.

    Miscellaneous Methods:
        - get_sname(): Return the scope name for a property.
        - get_mechanism_descr(): Return a description string for a mechanism.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()'). If not provided, one is
                     created.
            msr: The MSR access object ('MSR.MSR()'). If not provided, one is created.
            sysfs_io: The sysfs access object ('_SysfsIO.SysfsIO()'). If not provided, one is
                      created.
            enable_cache: Enable property caching if True, do not use caching if False.
        """

        self._msr = msr
        self._sysfs_io = sysfs_io

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_sysfs_io = sysfs_io is None

        # The write-through per-CPU properties cache. The properties that are backed by MSR/EPP/EPB
        # are not cached, because they implement their own caching.
        self._enable_cache = enable_cache

        # The properties dictionary, has to be initialized by the sub-class.
        self.props: dict[str, PropertyTypedDict]
        # Internal version of 'self.props'. Contains some data which we don't want to expose to the
        # user. Has to be initialized by the sub-class.
        self._props: dict[str, IntPropertyTypedDict]

        # Dictionary describing all supported mechanisms. Same as 'MECHANISMS', but includes only
        # the mechanisms that at least one property supports. Has to be initialized by the
        # sub-class.
        self.mechanisms: dict[MechanismNameType, MechanismsTypedDict]

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        if cpuinfo:
            self._cpuinfo = cpuinfo
        else:
            self._cpuinfo = CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def get_mechanism_descr(self, mname: MechanismNameType) -> str:
        """
        Return a 1-line description string for the specified mechanism name.

        Args:
            mname: Name of the mechanism to describe.

        Returns:
            A string containing a 1-line description of the mechanism.
        """

        if mname not in self.mechanisms:
            mnames = ", ".join(self.mechanisms)
            raise ErrorNotSupported(f"Unsupported mechanism '{mname}', supported mechanisms are: "
                                    f"{mnames}.", mname=mname)

        try:
            return self.mechanisms[mname]["long"]
        except KeyError:
            raise Error(f"BUG: missing mechanism description for '{mname}'") from None

    def _validate_mname(self,
                        mname: MechanismNameType,
                        pname: str | None = None,
                        allow_readonly: bool = True):
        """
        Validate that the specified mechanism name is supported and meets the required access model.

        Args:
            mname: Name of the mechanism to validate.
            pname: Optional property name; if provided, ensure 'mname' is supported by this
                   property.
            allow_readonly: If True, allow both read-only and read-write mechanisms access models,
                            otherwise, allow only read-write read-write access model.

        Raises:
            ErrorNotSupported: If the mechanism is not supported for the property or overall.
        """

        all_mnames: dict[MechanismNameType, MechanismsTypedDict] | tuple[MechanismNameType, ...]
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
            raise ErrorNotSupported(f"Unsupported mechanism '{mname}', supported mechanisms are: "
                                    f"{mnames}.", mname=mname)

        if not allow_readonly and not self.mechanisms[mname]["writable"]:
            if pname:
                name = Human.uncapitalize(self._props[pname]["name"])
                raise Error(f"Can't use read-only mechanism '{mname}' for modifying {name}\n")
            raise Error(f"Can't use read-only mechanism '{mname}'")

    def _normalize_mnames(self,
                          mnames: MechanismNamesType | None,
                          pname: str | None = None,
                          allow_readonly: bool = True) -> list[MechanismNameType]:
        """
        Validate and deduplicate a list of mechanism names.

        If 'mnames' is None, normalize mechanisms of property 'pname' if provided, otherwise return
        all available mechanisms.

        Args:
            mnames: Mechanism names to validate and normalize, or None to use defaults.
            pname: Optional property name to retrieve mechanism names from if 'mnames' is None.
            allow_readonly: Whether to allow read-only mechanisms during validation.

        Returns:
            List of validated and deduplicated mechanism names.
        """

        if mnames is None:
            if pname:
                return list(self._props[pname]["mnames"])
            return list(self.mechanisms)

        for mname in mnames:
            self._validate_mname(mname, pname=pname, allow_readonly=allow_readonly)

        return Trivial.list_dedup(mnames)

    def _set_sname(self, pname: str):
        """
        Assign a scope name to the specified property if not already set.

        Some properties have platform-dependent scope names. Assign the appropriate scope name for
        the given property name based on the platform. If the scope name is already set, return
        immediately.

        Expected to be overridden by the sub-class.

        Args:
            pname: Name of the property to assign a scope name to.
        """

        if self._props[pname]["sname"]:
            return

        raise NotImplementedError("PropsClassBase._set_sname")

    def get_sname(self, pname: str) -> ScopeNameType | None:
        """
        Return the scope name for the given property name.

        If the property is not supported, return None, but this is not guaranteed. In some cases,
        a valid scope name may be returned even if the property is unsupported on the current
        platform. Therefore, the caller should check if the property is supported before or after
        calling this method.

        Args:
            pname: Name of the property.

        Returns:
            The scope name for the property, or None if unavailable.
        """

        try:
            if not self._props[pname]["sname"]:
                try:
                    self._set_sname(pname)
                except ErrorNotSupported:
                    return None

            return self._props[pname]["sname"]
        except KeyError as err:
            raise Error(f"Property '{pname}' does not exist") from err

    def _normalize_bool_type_value(self, pname: str, val: bool | str) -> bool:
        """
        Normalize and validate a boolean-type property value.

        Convert the input value for a boolean property to its canonical boolean form. Accept boolean
        values, as well as string representations: "on", "enable" (True), and "off", "disable"
        (False).

        Args:
            pname: Property name.
            val: Value to normalize.

        Returns:
            Normalized boolean value.
        """

        if val is True or val is False:
            return val

        val = val.lower()
        if val in ("on", "enable"):
            return True

        if val in ("off", "disable"):
            return False

        name = Human.uncapitalize(self._props[pname]["name"])
        raise Error(f"Bad value '{val}' for {name}, use one of: True, False, on, off, enable, "
                    f"disable")

    def _validate_pname(self, pname: str):
        """
        Validate that the provided property name exists in the known properties.

        Args:
            pname: Property name to validate.

        Raise:
            Error: If the property name is not recognized.
        """

        if pname not in self._props:
            pnames_str = ", ".join(set(self._props))
            raise Error(f"Unknown property name '{pname}', known properties are: {pnames_str}")

    def _validate_cpus_vs_scope(self, pname: str, cpus: NumsType):
        """
        Validate that the provided list of CPUs matches the scope of the specified property.

        Args:
            pname: Name of the property whose scope is being validated.
            cpus: CPU numbers to validate.

        Ensure that the CPUs provided align with the property's scope (e.g., global, package, core,
        die). E.g., if the scope is 'global', all CPUs must be included. For other scopes, verify
        that the CPUs form complete groups according to the scope.
        """

        sname = self._props[pname]["sname"]

        if sname not in get_args(ScopeNameType):
            raise Error(f"BUG: Unknown scope name '{sname}'")

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

    def _validate_prop_vs_scope(self, pname: str, sname: ScopeNameType):
        """
        Validate that the property 'pname' can be accessed at the specified scope 'sname'.

        Args:
            pname: Name of the property to validate.
            sname: Scope name to validate against.
        """

        if sname == "die":
            ok_scopes = set(("die", "package", "global"))
        elif sname == "package":
            ok_scopes = set(("package", "global"))
        else:
            raise Error(f"BUG: Support for scope {sname} is not implemented")

        prop = self._props[pname]

        if prop["sname"] not in ok_scopes:
            name = Human.uncapitalize(prop["name"])
            snames = ", ".join(ok_scopes)
            raise Error(f"Cannot access {name} on per-{sname} basis, because it has "
                        f"{prop['sname']} scope{self._pman.hostmsg}.\nPer-{sname} access is only "
                        f"allowed for properties with the following scopes: {snames}")

    def _validate_prop_vs_ioscope(self,
                                  pname: str,
                                  cpus: NumsType,
                                  mnames: MechanismNamesType | None = None,
                                  package: int | None = None,
                                  die: int | None = None):
        """
        Validate that a property has the same value across specified CPUs, considering differences
        between property functional scope and I/O scope.

        The intention is to check properties where the functional scope differs from the I/O scope
        and detects inconsistencies that may arise when a property is expected to be uniform within
        a scope, but it is not, due to I/O scope.

        For example, a property with package scope may be backed by an MSR with core I/O scope,
        potentially leading to conflicting values across cores within the same package.

        Args:
            pname: Name of the property to validate.
            cpus: CPU numbers to check.
            mnames: Mechanism names to use for property retrieval.
            package: Package number to validate for.
            die: Die number to validate for.

        Raises:
            ErrorUsePerCPU: If the property value differs across CPUs within the same scope.
        """

        prev_cpu: int | None = None
        disagreed_pvinfos: tuple[PVInfoTypedDict, PVInfoTypedDict] | None = None
        pvinfos: dict[int, PVInfoTypedDict] = {}

        for pvinfo in self._get_prop_pvinfo_cpus(pname, cpus, mnames=mnames,
                                                 raise_not_supported=False):
            cpu = pvinfo["cpu"]
            pvinfos[cpu] = pvinfo

            if prev_cpu is None:
                prev_cpu = cpu
                continue

            if pvinfo["val"] != pvinfos[prev_cpu]["val"]:
                disagreed_pvinfos = (pvinfos[prev_cpu], pvinfo)
                break

        if disagreed_pvinfos is None:
            return

        if die is not None:
            op_sname = "die"
            for_what = f" for package {package}, die {die}"
        elif package is not None:
            op_sname = "package"
            for_what = f" for package {package}"
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
    def _construct_cpu_pvinfo(pname: str,
                              cpu: int,
                              mname: MechanismNameType,
                              val: PropertyValueType) -> PVInfoTypedDict:
        """
        Construct and return a property value dictionary.

        If the value is a boolean, convert it to "on" or "off" string.

        Args:
            pname: Name of the property.
            cpu: CPU number.
            mname: Name of the mechanism.
            val: Property value.

        Returns:
            The constructed property value dictionary.
        """

        if isinstance(val, bool):
            val = "on" if val is True else "off"

        return {"cpu": cpu, "pname": pname, "val": val, "mname": mname}

    @staticmethod
    def _construct_die_pvinfo(pname: str,
                              package: int,
                              die: int,
                              mname: MechanismNameType,
                              val: PropertyValueType) -> PVInfoTypedDict:
        """
        Construct and return a property value dictionary for a die.

        Convert boolean values to "on"/"off" strings.

        Args:
            pname: Property name.
            package: Package number.
            die: Die number.
            mname: Module name.
            val: Property value.

        Returns:
            The constructed property value dictionary.
        """

        if isinstance(val, bool):
            val = "on" if val is True else "off"

        return {"package": package, "die" : die, "pname": pname, "val": val, "mname": mname}

    @staticmethod
    def _construct_package_pvinfo(pname: str,
                                  package: int,
                                  mname: MechanismNameType,
                                  val: PropertyValueType) -> PVInfoTypedDict:
        """
        Construct and return a property value dictionary for a package.

        Convert boolean values to "on"/"off" strings.

        Args:
            pname: Property name.
            package: Package number.
            mname: Module name.
            val: Property value.

        Returns:
            The constructed property value dictionary.
        """

        if isinstance(val, bool):
            val = "on" if val is True else "off"

        return {"package": package, "pname": pname, "val": val, "mname": mname}

    def _get_msr(self) -> MSR.MSR:
        """Return an instance of 'MSR.MSR'."""

        if not self._msr:
            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_sysfs_io(self) -> _SysfsIO.SysfsIO:
        """Return an instance of '_SysfsIO.SysfsIO'."""

        if not self._sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(self._pman, enable_cache=self._enable_cache)

        return self._sysfs_io

    def _do_prop_not_supported(self,
                               pname: str,
                               nums_str: str,
                               mnames: MechanismNamesType,
                               action: str,
                               exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            nums_str: String describing the target CPU, packages, etc.
            mnames: The attempted mechanism names.
            action: The action: "get" or "set".
            exceptions: List of exception objects encountered during the operation.

        Raises:
            ErrorNotSupported: The unsupported property exception with details (if 'exceptions' is
                               not None).
        """

        if len(mnames) > 2:
            mnames_quoted = [f"'{mname}'" for mname in mnames]
            mnames_str = f"using {', '.join(mnames_quoted[:-1])} and {mnames_quoted[-1]} methods"
        elif len(mnames) == 2:
            mnames_str = f"using '{mnames[0]}' and '{mnames[1]}' methods"
        else:
            mnames_str = f"using the '{mnames[0]}' method"

        if exceptions:
            emsgs = Trivial.list_dedup([str(err) for err in exceptions])
            errmsgs = "\n" + "\n".join([Error(errmsg).indent(2) for errmsg in emsgs])
        else:
            errmsgs = ""

        what = Human.uncapitalize(self._props[pname]["name"])
        msg = f"Cannot {action} {what} {mnames_str} for {nums_str}{errmsgs}"
        if exceptions:
            raise ErrorNotSupported(msg)
        _LOG.debug(msg)

    def _prop_not_supported_cpus(self,
                                 pname: str,
                                 cpus: NumsType,
                                 mnames: MechanismNamesType,
                                 action: str,
                                 exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            cpus: CPU numbers.
            mnames: Attempted mechanism names.
            action: The action: "get" or "set".
            exceptions: List of exception objects encountered during the operation.

        Raises:
            ErrorNotSupported: The unsupported property exception with details (if 'exceptions' is
                               not None).
        """

        if len(cpus) > 1:
            cpus_str = f"the following CPUs: {Trivial.rangify(cpus)}"
        else:
            cpus_str = f"CPU {cpus[0]}"

        self._do_prop_not_supported(pname, cpus_str, mnames, action, exceptions=exceptions)

    def _prop_not_supported_dies(self,
                                 pname: str,
                                 dies: dict[int, NumsType],
                                 mnames: MechanismNamesType,
                                 action: str,
                                 exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            dies: Mapping of package numbers to die numbers (one package -> many dies).
            mnames: Attempted mechanism names.
            action: The action: "get" or "set".
            exceptions: List of exception objects encountered during the operation.

        Raises:
            ErrorNotSupported: The unsupported property exception with details (if 'exceptions' is
                               not None).
        """

        dies_str = self._cpuinfo.dies_to_str(dies)
        self._do_prop_not_supported(pname, dies_str, mnames, action, exceptions=exceptions)

    def _prop_not_supported_packages(self,
                                     pname: str,
                                     packages: NumsType,
                                     mnames: MechanismNamesType,
                                     action: str,
                                     exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            packages: Package numbers.
            mnames: Attempted mechanism names.
            action: The action: "get" or "set".
            exceptions: List of exception objects encountered during the operation.

        Raises:
            ErrorNotSupported: The unsupported property exception with details (if 'exceptions' is
                               not None).
        """

        if len(packages) > 1:
            packages_str = f"the following packages: {Trivial.rangify(packages)}"
        else:
            packages_str = f"CPU {packages[0]}"

        self._do_prop_not_supported(pname, packages_str, mnames, action, exceptions=exceptions)

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: NumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield property values for the specified CPUs using the specified mechanism.

        Has to be implemented by the sub-class.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve the property for.
            mname: Name of the mechanism to use.

        Yields:
            (cpu, value) tuples for each CPU in 'cpus'. Yield (cpu, None) if the property is not
            supported for a CPU.
        """

        raise NotImplementedError("PropsClassBase._get_cpu_prop")

    def _get_prop_pvinfo_cpus(self,
                              pname: str,
                              cpus: NumsType,
                              mnames: MechanismNamesType | None = None,
                              raise_not_supported: bool = True) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Retrieve and yield property value dictionaries ('pvinfo') for the specified CPUs using the
        specified mechanisms.

        If a mechanism fails for some CPUs after succeeding for others, raise an error. If all
        mechanisms fail, either raise an exception or yield 'pvinfo' with value 'None' for each CPU,
        depending on 'raise_not_supported'.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve the property for.
            mnames: Mechanism names to use. Use the default mechanisms if not specified.
            raise_not_supported: Whether to raise an exception if the property is not supported.

        Yields:
            Dictionary containing property value dictionary ('pvinfo') for each CPU.

        Raises:
            ErrorNotSupported: If none of the CPUs an mechanisms support the property and
                               'raise_not_supported' is True.
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
                    raise Error(f"Failed to get {name} using the '{mname}' mechanism:\n"
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

    def _get_prop_cpus_mnames(self,
                              pname: str,
                              cpus: NumsType,
                              mnames: MechanismNamesType | None = None) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """
        Yield (cpu, value) tuples for the specified property and CPUs, using provided mechanisms.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to process.
            mnames: Mechanisms to use for retrieving the property value.

        Yields:
            Tuple of (cpu, value) for each CPU in 'cpus'. If the property is not supported for a CPU,
            yield (cpu, None).

        Raises:
            ErrorNotSupported: If none of the CPUs and mechanisms support the property.
        """

        for pvinfo in self._get_prop_pvinfo_cpus(pname, cpus, mnames):
            yield (pvinfo["cpu"], pvinfo["val"])

    def _get_cpu_prop_mnames(self,
                             pname: str,
                             cpu: int,
                             mnames: MechanismNamesType | None = None) -> PropertyValueType:
        """
        Retrieve the value of a CPU property using specified mechanisms.

        Unlike 'get_cpu_prop()', this method does not validate input arguments.

        Args:
            pname: Name of the property to retrieve.
            cpu: CPU number for which to retrieve the property.
            mnames: Mechanism names to try for retrieving the property.

        Returns:
            The value of the requested property for the specified CPU.

        Raises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        pvinfo = next(self._get_prop_pvinfo_cpus(pname, (cpu,), mnames))
        return pvinfo["val"]

    def get_prop_cpus(self,
                      pname: str,
                      cpus: NumsOrAllType = "all",
                      mnames: MechanismNamesType | None = None) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Read property 'pname' for CPUs in 'cpus', and for every CPU yield the property value
        dictionary.

        Args:
            pname: Name of the property to read and yield the values for. The property will be read
                   for every CPU in 'cpus'.
            cpus: Collection of integer CPU numbers. Special value 'all' means "all CPUs".
            mnames: Mechanisms to use for getting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Yields:
            PVInfoTypedDict: A property value dictionary for every CPU in 'cpus'.

        Raises:
            ErrorNotSupported: If none of the CPUs and mechanisms support the property.

        Notes:
            If a property is not supported, the 'val' and 'mname' keys will contain 'None'. Except
            if none of the mechanisms supported the property, in which case 'ErrorNotSupported' is
            raised.

            Properties of "bool" type use the following values:
               * "on" if the feature is enabled.
               * "off" if the feature is disabled.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        cpuz = self._cpuinfo.normalize_cpus(cpus)
        if len(cpuz) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for cpu in cpuz:
                yield self._construct_cpu_pvinfo(pname, cpu, mnames[-1], None)
            return

        yield from self._get_prop_pvinfo_cpus(pname, cpuz, mnames=mnames, raise_not_supported=False)

    def get_cpu_prop(self,
                     pname: str,
                     cpu: int,
                     mnames: MechanismNamesType | None = None) -> PVInfoTypedDict:
        """
        Retrieve the value of a property for a CPU.

        Args:
            pname: Name of the property to retrieve.
            cpu: CPU number to retrieve the property for.
            mnames: Mechanism names to use.

        Returns:
            PVInfoTypedDict: Dictionary containing the property value for the specified CPU.

        Raises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        for pvinfo in self.get_prop_cpus(pname, cpus=(cpu,), mnames=mnames):
            return pvinfo

        raise Error(f"BUG: failed to get property '{pname}' for CPU {cpu}")

    def prop_is_supported_cpu(self, pname: str, cpu: int) -> bool:
        """
        Check if a property is supported by a CPU.

        Args:
            pname: Name of the property to check.
            cpu: CPU number to check for.

        Returns:
            True if the property is supported by the specified CPU, False otherwise.
        """

        return self.get_cpu_prop(pname, cpu)["val"] is not None

    def _get_prop_dies(self,
                       pname: str,
                       dies: dict[int, NumsType],
                       mname: MechanismNameType) -> Generator[tuple[int, int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield property values for the specified dies using the specified mechanism.

        If the property is not supported for a die, yield None for 'value'. Raise
        'ErrorNotSupported' if the property is not supported for any die in 'dies'.

        Args:
            pname: Name of the property to retrieve.
            dies: Mapping of package numbers to die numbers (one package -> many dies).
            mname: Mechanism name to use.

        Yields:
            Tuples of (package, die, value), where 'value' is the property value or None.

        Raises:
            ErrorNotSupported: If none of the dies support the property.
        """

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                val = self._get_cpu_prop_mnames(pname, cpus[0], mnames=(mname,))
                yield package, die, val

    def _get_prop_pvinfo_dies(self,
                              pname: str,
                              dies: dict[int, NumsType],
                              mnames: MechanismNamesType | None = None,
                              raise_not_supported: bool = True) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Retrieve and yield property value dictionaries for the specified dies using the specified
        mechanisms.

        If a mechanism fails for some dies but succeeds for others, raise an error. If all
        mechanisms fail, either raise an exception or yield 'pvinfo' with value 'None', depending on
        'raise_not_supported'.

        Args:
            pname: Name of the property to retrieve.
            dies: Mapping of package numbers to die numbers (one package -> many dies).
            mnames: Mechanisms to use for retrieving the property. If None, use default mechanisms.
            raise_not_supported: Whether to raise an exception if the property is not supported.

        Yields:
            Dictionary containing property value information for each die.

        Raises:
            ErrorNotSupported: If none of the dies and mechanisms support the property and
                               'raise_not_supported' is True.
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
                    raise Error(f"Failed to get {name} using the '{mname}' mechanism:\n"
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

    def _get_prop_dies_mnames(self,
                              pname: str,
                              dies: dict[int, NumsType],
                              mnames: MechanismNamesType | None = None) -> \
                                          Generator[tuple[int, int, PropertyValueType], None, None]:
        """
        Retrieve and yield property values for the specified dies using the specified mechanisms.

        Args:
            pname: Name of the property to retrieve.
            dies: Mapping of package numbers to die numbers (one package -> many dies).
            mnames: Mechanisms to use for retrieving the property. If None, use default mechanisms.

        Yields:
            Tuples of (package, die, value) for each die.

        Raises:
            ErrorNotSupported: If none of the dies and mechanisms support the property and
                               'raise_not_supported' is True.
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

        raise NotImplementedError("PropsClassBase.set_prop_cpus")

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
