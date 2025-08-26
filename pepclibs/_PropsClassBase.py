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
    - Sub-property: A property that is related to a main property and only exists or is meaningful
      when he main property is supported by the platform. Sub-properties must be read-only.

Naming conventions:
    - props: A dictionary describing the properties. For example, see 'PROPS' in 'PStates' and
             'CStates'.
    - pvinfo: The property value dictionary returned by 'get_prop_cpus()' and 'get_cpu_prop()'. It
              has the 'PVInfoTypedDict' type.
    - pname: The name of a property.
    - sname: The functional scope name of the property, indicating whether the property is per-CPU,
             per-core, per-package, etc.
    - iosname: The I/O scope name of the property. Typically the same as 'sname', but may may be
               different to the functional scope in case of some MSR-backed properties. More
               information: https://github.com/intel/pepc/blob/main/docs/misc-msr-scope.md
    - core siblings: All CPUs sharing the same core. For example, "CPU6 core siblings" are all CPUs
                     sharing the same core as CPU 6.
    - module siblings: All CPUs sharing the same module.
    - die siblings: All CPUs sharing the same die.
    - package siblings: All CPUs sharing the same package.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
import typing
from typing import Any, Sequence, Literal, Generator, cast, get_args

from pepclibs.helperlibs import Logging, Trivial, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

from pepclibs._PropsClassBaseTypes import PropertyTypedDict, ScopeNameType, PropertyValueType

if typing.TYPE_CHECKING:
    from pepclibs.msr import MSR
    from pepclibs import _SysfsIO
    from pepclibs.CPUInfo import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._PropsClassBaseTypes import MechanismTypedDict, MechanismNameType
    from pepclibs._PropsClassBaseTypes import PVInfoTypedDict, AbsNumsType, RelNumsType

class _PropertyTypedDict(PropertyTypedDict):
    """
    Represents the internal property description dictionary used for property metadata.

    This class extends 'PropertyTypedDict' and is intended for internal use to describe properties
    with additional metadata, such as the I/O scope name.

    Attributes:
        iosname: The name of the I/O scope associated with the property, or None if not applicable.
                 Type for the internal property description dictionary.
    """

    iosname: ScopeNameType | None

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

MECHANISMS: dict[MechanismNameType, MechanismTypedDict] = {
    "sysfs" : {
        "short": "sysfs",
        "long":  "Linux sysfs file-system",
        "writable": True,
    },
    "tpmi" : {
        "short": "tpmi",
        "long":  "Topology Aware Register and PM Capsule Interface (TPMI)",
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
    Raise when a per-die or per-package property "get" method cannot provide a reliable result due
    to sibling CPUs having different property values.

    Use the per-CPU 'get_prop_cpus()' method instead. This situation can occur when a property's
    scope differs from its I/O scope, resulting in inconsistent values among sibling CPUs.
    """

class ErrorTryAnotherMechanism(ErrorNotSupported):
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
            enable_cache: Enable property caching if True.
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
        self._props: dict[str, _PropertyTypedDict]

        # Dictionary describing all supported mechanisms. Same as 'MECHANISMS', but includes only
        # the mechanisms that at least one property supports. Has to be initialized by the
        # sub-class.
        self.mechanisms: dict[MechanismNameType, MechanismTypedDict]

        if pman:
            self._pman = pman
        else:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.helperlibs import LocalProcessManager

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
            ErrorTryAnotherMechanism: If the mechanism is not supported for the property, but
                                      alternative mechanisms are available.
        """

        all_mnames: dict[MechanismNameType, MechanismTypedDict] | tuple[MechanismNameType, ...]
        if pname:
            all_mnames = self._props[pname]["mnames"]
        else:
            all_mnames = self.mechanisms

        if mname not in all_mnames:
            mnames = ", ".join(all_mnames)
            if pname:
                name = self._props[pname]["name"]
                raise ErrorTryAnotherMechanism(f"{name} is not available via the '{mname}' "
                                               f"mechanism{self._pman.hostmsg}.\n"
                                               f"Use one the following mechanism(s) instead: "
                                               f"{mnames}.", mname=mname)
            raise ErrorNotSupported(f"Unsupported mechanism '{mname}', supported mechanisms are: "
                                    f"{mnames}.", mname=mname)

        if not allow_readonly and not self.mechanisms[mname]["writable"]:
            if pname:
                name = Human.uncapitalize(self._props[pname]["name"])
                raise Error(f"Can't use read-only mechanism '{mname}' for modifying {name}\n")
            raise Error(f"Can't use read-only mechanism '{mname}'")

    def _normalize_mnames(self,
                          mnames: Sequence[MechanismNameType],
                          pname: str | None = None,
                          allow_readonly: bool = True) -> list[MechanismNameType]:
        """
        Validate and deduplicate a list of mechanism names.

        If 'mnames' is an empty sequence, return mechanisms of property 'pname' if provided,
        otherwise return all available mechanisms.

        Args:
            mnames: Mechanism names to validate and normalize.
            pname: Optional property name to retrieve mechanism names from if 'mnames' is None.
            allow_readonly: Whether to allow read-only mechanisms during validation.

        Returns:
            List of validated and deduplicated mechanism names.
        """

        if not mnames:
            if pname:
                return list(self._props[pname]["mnames"])
            return list(self.mechanisms)

        supported_mnames: list[MechanismNameType] = []
        errors: list[ErrorNotSupported] = []

        for mname in mnames:
            try:
                self._validate_mname(mname, pname=pname, allow_readonly=allow_readonly)
            except ErrorNotSupported as err:
                errors.append(err)
            else:
                supported_mnames.append(mname)

        if not supported_mnames:
            raise errors[0]

        return Trivial.list_dedup(supported_mnames)

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

    def _validate_cpus_vs_scope(self, pname: str, cpus: AbsNumsType):
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
            name = self._props[pname]["name"]
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
                # pylint: disable-next=import-outside-toplevel
                import textwrap

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

        name = self._props[pname]["name"]
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
                                  cpus: AbsNumsType,
                                  mnames: Sequence[MechanismNameType] = (),
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
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).
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

        raise ErrorUsePerCPU(f"Cannot determine {name} {for_what}{self._pman.hostmsg}:\n"
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
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_sysfs_io(self) -> _SysfsIO.SysfsIO:
        """Return an instance of '_SysfsIO.SysfsIO'."""

        if not self._sysfs_io:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _SysfsIO

            self._sysfs_io = _SysfsIO.SysfsIO(self._pman, enable_cache=self._enable_cache)

        return self._sysfs_io

    def _do_prop_not_supported(self,
                               pname: str,
                               nums_str: str,
                               mnames: Sequence[MechanismNameType],
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
                                 cpus: AbsNumsType,
                                 mnames: Sequence[MechanismNameType],
                                 action: str,
                                 exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            cpus: CPU numbers.
            mnames: The attempted mechanism names.
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
                                 dies: RelNumsType,
                                 mnames: Sequence[MechanismNameType],
                                 action: str,
                                 exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mnames: The attempted mechanism names.
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
                                     packages: AbsNumsType,
                                     mnames: Sequence[MechanismNameType],
                                     action: str,
                                     exceptions: list[Any] | None = None):
        """
        Handle an unsupported property access by raising an error or logging a debug message.

        Args:
            pname: Property name.
            packages: Package numbers.
            mnames: The attempted mechanism names.
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
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield property values for the specified CPUs using the specified mechanism.

        If the property is not supported for a CPU, yield (cpu, None). If the property is not
        supported for the specified CPUs and mechanism, raise 'ErrorNotSupported'.

        Has to be implemented by the sub-class.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve the property for.
            mname: Name of the mechanism to use.

        Yields:
            (cpu, value) tuples for each CPU in 'cpus'. Yield (cpu, None) if the property is not
            supported for a CPU.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified CPUs and
                               mechanism.
        """

        raise NotImplementedError("PropsClassBase._get_cpu_prop")

    def _get_prop_pvinfo_cpus(self,
                              pname: str,
                              cpus: AbsNumsType,
                              mnames: Sequence[MechanismNameType] = (),
                              raise_not_supported: bool = True) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Retrieve and yield property value dictionaries for the specified CPUs using the specified
        mechanisms.

        If the property is not supported for a CPU, yield a dictionary with 'None' value. If the
        property is not supported for the specified CPUs and mechanisms, raise 'ErrorNotSupported'
        or yield a property value dictionary with 'None' values, depending on the
        'raise_not_supported' argument.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve the property for.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).
            raise_not_supported: Whether to raise an exception if the property is not supported.

        Yields:
            PVInfoTypedDict: A property value dictionary for each CPU in 'cpus'.

        Raises:
            ErrorNotSupported: If none of the CPUs and mechanisms support the property and
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
                              cpus: AbsNumsType,
                              mnames: Sequence[MechanismNameType] = ()) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """
        Yield (cpu, value) tuples for the specified property and CPUs, using specified mechanisms.

        If the property is not supported for a CPU, yield (cpu, None). If the property is not
        supported for the specified CPUs and mechanisms, raise 'ErrorNotSupported'.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve the property for.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Yields:
            Tuple of (cpu, value) for each CPU in 'cpus'. If the property is not supported for a
            CPU, yield (cpu, None).

        Raises:
            ErrorNotSupported: If none of the CPUs and mechanisms support the property.
        """

        for pvinfo in self._get_prop_pvinfo_cpus(pname, cpus, mnames):
            yield (pvinfo["cpu"], pvinfo["val"])

    def _get_cpu_prop_mnames(self,
                             pname: str,
                             cpu: int,
                             mnames: Sequence[MechanismNameType] = ()) -> PropertyValueType:
        """
        Retrieve the value of a CPU property using specified mechanisms.

        Args:
            pname: Name of the property to retrieve.
            cpu: CPU number for which to retrieve the property.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            The value of the requested property for the specified CPU.

        Raises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        pvinfo = next(self._get_prop_pvinfo_cpus(pname, (cpu,), mnames))
        return pvinfo["val"]

    def get_prop_cpus(self,
                      pname: str,
                      cpus: AbsNumsType | Literal["all"] = "all",
                      mnames: Sequence[MechanismNameType] = ()) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Read property 'pname' for CPUs in 'cpus', and for every CPU yield the property value
        dictionary.

        If the property is not supported for a CPU, yield a dictionary with 'None' value. If the
        property is not supported for the specified CPUs and mechanisms, raise an
        'ErrorNotSupported'.

        Args:
            pname: Name of the property to read and yield the values for. The property will be read
                   for every CPU in 'cpus'.
            cpus: Collection of integer CPU numbers. Special value 'all' means "all CPUs".
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Yields:
            PVInfoTypedDict: A property value dictionary for every CPU in 'cpus'.

        Raises:
            ErrorNotSupported: If none of the CPUs and mechanisms support the property.

        Notes:
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
                     mnames: Sequence[MechanismNameType] = ()) -> PVInfoTypedDict:
        """
        Retrieve the value of a property for a CPU.

        Args:
            pname: Name of the property to retrieve.
            cpu: CPU number to retrieve the property for.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

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
                       dies: RelNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int, PropertyValueType],
                                                              None, None]:
        """
        Retrieve and yield property values for the specified dies using the specified mechanism.

        If the property is not supported for a die, yield None the value. Raise 'ErrorNotSupported'
        if the property is not supported for any die in 'dies'.

        Args:
            pname: Name of the property to retrieve.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mname: Mechanism name to use.

        Yields:
            Tuples of (package, die, value), where 'value' is the property value or None.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified dies and
                               mechanism.
        """

        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                val = self._get_cpu_prop_mnames(pname, cpus[0], mnames=(mname,))
                yield package, die, val

    def _get_prop_pvinfo_dies(self,
                              pname: str,
                              dies: RelNumsType,
                              mnames: Sequence[MechanismNameType] = (),
                              raise_not_supported: bool = True) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Retrieve and yield property value dictionaries for the specified dies using the specified
        mechanisms.

        If a property is not supported for a die, yield a dictionary with 'None' value. If the
        property is not supported for the specified dies and mechanisms, raise 'ErrorNotSupported'
        or yield a property value dictionary with 'None' values, depending on the
        'raise_not_supported' argument.

        Args:
            pname: Name of the property to retrieve.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).
            raise_not_supported: Whether to raise an exception if the property is not supported.

        Yields:
            PVInfoTypedDict: A property value dictionary for each die in 'dies'.

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
                              dies: RelNumsType,
                              mnames: Sequence[MechanismNameType] = ()) -> \
                                          Generator[tuple[int, int, PropertyValueType], None, None]:
        """
        Retrieve and yield property values for the specified dies using the specified mechanisms.

        If the property is not supported for a die, yield None the value. Raise 'ErrorNotSupported'
        if the property is not supported for any die in 'dies' and any mechanism.

        Args:
            pname: Name of the property to retrieve.
            dies: Dictionary mapping package numbers to collections of die numbers.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Yields:
            Tuples of (package, die, value) for each die.

        Raises:
            ErrorNotSupported: If none of the dies and mechanisms support the property.
        """

        for pvinfo in self._get_prop_pvinfo_dies(pname, dies, mnames):
            yield (pvinfo["package"], pvinfo["die"], pvinfo["val"])

    def _get_die_prop_mnames(self,
                             pname: str,
                             package: int,
                             die: int,
                             mnames: Sequence[MechanismNameType] = ()) -> PropertyValueType:
        """
        Retrieve the value of a property for a specific die using specified mechanisms.

        Args:
            pname: Name of the property to retrieve.
            package: Package number.
            die: Die number within the package.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            The value of the requested property for the specified die.

        Rises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        pvinfo = next(self._get_prop_pvinfo_dies(pname, {package: [die]}, mnames))
        return pvinfo["val"]

    def get_prop_dies(self,
                      pname: str,
                      dies: RelNumsType | Literal["all"] = "all",
                      mnames: Sequence[MechanismNameType] = ()) -> Generator[PVInfoTypedDict,
                                                                             None, None]:
        """
        Read property 'pname' for dies in 'dies', and for every die yield the property value
        dictionary.

        If the property is not supported for a die, yield a dictionary with 'None' value. If the
        property is not supported for the specified dies and mechanisms, raise an
        'ErrorNotSupported'.

        Args:
            pname: Name of the property to read and yield the values for. The property will be read
                   for every die in 'dies'.
            dies: Dictionary mapping package numbers to collections of die numbers, or 'all' for all
                  dies in all packages.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Yields:
            PVInfoTypedDict: A property value dictionary for every die in 'dies'.

        Raises:
            ErrorNotSupported: If none of the dies and mechanisms support the property.

        Notes:
            Properties of "bool" type use the following values:
               - "on" if the feature is enabled.
               - "off" if the feature is disabled.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        diez = self._cpuinfo.normalize_dies(dies)

        # Get rid of empty die lists.
        for package, pkg_dies in diez.copy().items():
            if len(pkg_dies) == 0:
                del diez[package]

        if len(diez) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for package, pkg_dies in diez.items():
                for die in pkg_dies:
                    yield self._construct_die_pvinfo(pname, package, die, mnames[-1], None)
            return

        self._validate_prop_vs_scope(pname, "die")

        for package, pkg_dies in diez.items():
            for die in pkg_dies:
                if self._props[pname]["sname"] == self._props[pname]["iosname"]:
                    continue
                cpus = self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))
                self._validate_prop_vs_ioscope(pname, cpus, mnames=mnames, package=package, die=die)

        yield from self._get_prop_pvinfo_dies(pname, diez, mnames=mnames,
                                              raise_not_supported=False)

    def get_die_prop(self,
                     pname: str,
                     die: int,
                     package: int,
                     mnames: Sequence[MechanismNameType] = ()) -> PVInfoTypedDict:
        """
        Retrieve a single property value for a specific die and package. Similar to
        'get_prop_dies()', but operates on a single die and property.

        Args:
            pname: Name of the property to retrieve.
            die: Die number.
            package: Package number containing the die.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            The property value dictionary for the specified die and property.

        Raises:
            ErrorNotSupported: If the property is not supported by any mechanism.
        """

        dies: RelNumsType = {package: (die,)}
        for pvinfo in self.get_prop_dies(pname, dies=dies, mnames=mnames):
            return pvinfo

        raise Error(f"BUG: failed to get property '{pname}' for package {package}, die {die}")

    def prop_is_supported_die(self, pname: str, die: int, package: int) -> bool:
        """
        Check if a property is supported by a specific die on a given package.

        Args:
            pname: Name of the property to check.
            die: Die number to check the property for.
            package: Package number containing the die.

        Returns:
            True if the property is supported by the specified die and package, False otherwise.
        """

        return self.get_die_prop(pname, die, package)["val"] is not None

    def _get_prop_packages(self,
                           pname: str,
                           packages: AbsNumsType,
                           mname: MechanismNameType) -> Generator[tuple[int, PropertyValueType],
                                                                  None, None]:
        """
        Retrieve and yield property values for the specified packages using the specified mechanism.

        If the property is not supported for a package, yield None as the value. Raise
        'ErrorNotSupported' if the property is not supported for any package.

        Args:
            pname: Name of the property to retrieve.
            packages: Package numbers.
            mname: Mechanism name to use for property retrieval.

        Yields:
            Tuple of (package, value), where value is the property value or None.

        Raises:
            ErrorNotSupported: If the property is not supported for any package.
        """

        for package in packages:
            cpus = self._cpuinfo.package_to_cpus(package)
            val = self._get_cpu_prop_mnames(pname, cpus[0], mnames=(mname,))
            yield package, val

    def _get_prop_pvinfo_packages(self,
                                  pname: str,
                                  packages: AbsNumsType,
                                  mnames: Sequence[MechanismNameType] = (),
                                  raise_not_supported: bool = True) -> Generator[PVInfoTypedDict,
                                                                                 None, None]:
        """
        Retrieve and yield property value dictionaries for the specified packages using the
        specified mechanisms.

        If a property is not supported for a package, yield a dictionary with 'None' value. If the
        property is not supported for the specified packages and mechanisms, raise
        'ErrorNotSupported' or yield a property value dictionary with 'None' values, depending on
        the 'raise_not_supported' argument.

        Args:
            pname: Name of the property to retrieve.
            packages: Package numbers to retrieve the property for.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).
            raise_not_supported: Whether to raise an exception if the property is not supported.

        Yields:
            PVInfoTypedDict: Property value dictionary for each package in 'packages'.

        Raises:
            ErrorNotSupported: If none of the packages and mechanisms support the property and
                               'raise_not_supported' is True.
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
                    raise Error(f"Failed to get {name} using the '{mname}' mechanism:\n"
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

    def _get_prop_packages_mnames(self,
                                  pname: str,
                                  packages: AbsNumsType,
                                  mnames: Sequence[MechanismNameType] = ()) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """
        Yield (package, value) tuples for the specified property and packages, using specified
        mechanisms.

        If the property is not supported for a package, yield (package, None). If the property is
        not supported for the specified packages and mechanisms, raise 'ErrorNotSupported'.

        Args:
            pname: Name of the property to retrieve.
            packages: package numbers to retrieve the property for.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Yields:
            Tuple of (package, value) for each package in 'packages'. If the property is not
            supported for a package, yield (package, None).

        Raises:
            ErrorNotSupported: If none of the packages and mechanisms support the property.
        """

        for pvinfo in self._get_prop_pvinfo_packages(pname, packages, mnames):
            yield (pvinfo["package"], pvinfo["val"])

    def _get_package_prop_mnames(self,
                                 pname: str,
                                 package: int,
                                 mnames: Sequence[MechanismNameType] = ()) -> PropertyValueType:
        """
        Retrieve the value of a property for a specific package using specified mechanisms.

        Args:
            pname: Name of the property to retrieve.
            package: Package number.
            package: Die number within the package.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            The value of the requested property for the specified package.

        Rises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        pvinfo = next(self._get_prop_pvinfo_packages(pname, (package,), mnames))
        return pvinfo["val"]

    def get_prop_packages(self,
                          pname: str,
                          packages: AbsNumsType | Literal["all"] = "all",
                          mnames: Sequence[MechanismNameType] = ()) -> Generator[PVInfoTypedDict,
                                                                                 None, None]:
        """
        Read property 'pname' for packages in 'packages', and for every package yield the property
        value dictionary.

        If the property is not supported for a package, yield a dictionary with 'None' value. If the
        property is not supported for the specified packages and mechanisms, raise an
        'ErrorNotSupported'.

        Args:
            pname: Name of the property to read and yield the values for. The property will be read
                   for every package in 'packages'.
            packages: Collection of integer package numbers. Special value 'all' means "all
                      packages".
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Yields:
            PVInfoTypedDict: A property value dictionary for every package in 'packages'.

        Raises:
            ErrorNotSupported: If none of the packages and mechanisms support the property.

        Notes:
            Properties of "bool" type use the following values:
               * "on" if the feature is enabled.
               * "off" if the feature is disabled.
        """

        self._validate_pname(pname)
        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=True)

        normalizes_packages = self._cpuinfo.normalize_packages(packages)
        if len(normalizes_packages) == 0:
            return

        try:
            self._set_sname(pname)
        except ErrorNotSupported:
            for package in normalizes_packages:
                yield self._construct_package_pvinfo(pname, package, mnames[-1], None)
            return

        self._validate_prop_vs_scope(pname, "package")

        for package in normalizes_packages:
            if self._props[pname]["sname"] == self._props[pname]["iosname"]:
                continue
            cpus = self._cpuinfo.package_to_cpus(package)
            self._validate_prop_vs_ioscope(pname, cpus, mnames=mnames, package=package)

        yield from self._get_prop_pvinfo_packages(pname, normalizes_packages, mnames=mnames,
                                                  raise_not_supported=False)

    def get_package_prop(self,
                         pname: str,
                         package: int,
                         mnames: Sequence[MechanismNameType] = ()) -> PVInfoTypedDict:
        """
        Retrieve the value of a property for a package.

        Args:
            pname: Name of the property to retrieve.
            package: Package number to retrieve the property for.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            PVInfoTypedDict: Dictionary containing the property value for the specified package.

        Raises:
            ErrorNotSupported: If none of the mechanisms support the property.
        """

        for pvinfo in self.get_prop_packages(pname, packages=(package,), mnames=mnames):
            return pvinfo

        raise Error(f"BUG: failed to get property '{pname}' for package {package}")

    def prop_is_supported_package(self, pname: str, package: int) -> bool:
        """
        Check if a property is supported by a specific package on a given package.

        Args:
            pname: Name of the property to check.
            package: Package number to check the property for.
            package: Package number containing the package.

        Returns:
            True if the property is supported by the specified package and package, False otherwise.
        """

        return self.get_package_prop(pname, package)["val"] is not None

    def _normalize_bool_type_value(self, pname: str, val: PropertyValueType) -> bool:
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

        if not isinstance(val, str):
            name = Human.uncapitalize(self._props[pname]["name"])
            raise Error(f"Bad value '{val}' for {name}, use one of: True, False, on, off, enable, "
                        f"disable")

        val = val.lower()
        if val in ("on", "enable"):
            return True

        if val in ("off", "disable"):
            return False

        name = Human.uncapitalize(self._props[pname]["name"])
        raise Error(f"Bad value '{val}' for {name}, use one of: True, False, on, off, enable, "
                    f"disable")

    def _normalize_inprop(self, pname: str, val: PropertyValueType) -> PropertyValueType:
        """
        Normalize and validate an input property value.

        Args:
            pname: Property name to normalize.
            val: Input value to normalize.

        Returns:
            Normalized property value.
        """

        self._validate_pname(pname)

        prop = self._props[pname]

        if not prop["writable"]:
            raise Error(f"{prop['name']} is read-only and can not be modified{self._pman.hostmsg}")

        if val is None:
            name = Human.uncapitalize(prop["name"])
            raise Error(f"Bad value 'None' for {name}")

        if prop.get("type") == "bool":
            val = self._normalize_bool_type_value(pname, val)

        if isinstance(val, (list, dict)):
            # At this point properties of this type are all read-only.
            raise Error(f"Bad type {type(val)} for {prop['name']}: expected a single value")

        if "unit" not in prop:
            return val

        if Trivial.is_num(val):
            if prop["type"] == "int":
                val = Trivial.str_to_int(cast(str, val))
            else:
                val = Trivial.str_to_float(cast(str, val))
        elif "special_vals" not in prop or val not in prop["special_vals"]:
            # This property has a unit, and the value is not a number, nor it is one of the
            # special values. Presumably this is a value with a unit, such as "100MHz" or
            # something like that.
            is_integer = prop["type"] == "int"
            name = Human.uncapitalize(prop["name"])
            val = Human.parse_human(val, unit=prop["unit"], integer=is_integer, what=name)

        return val

    def _set_prop_cpus(self,
                       pname: str,
                       val: PropertyValueType,
                       cpus: AbsNumsType,
                       mname: MechanismNameType):
        """
        Set a property to a specified value for specified CPUs using a specified mechanism.

        Has to be implemented by the sub-class.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            cpus: CPU numbers to set the property for.
            mname: Name of the mechanism to use for setting the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified CPUs and
                               mechanism.
            ErrorTryAnotherMechanism: If the property is not supported for the specified CPUs by the
                                      specified mechanism, but may be supported by another
                                      mechanism.
        """

        raise NotImplementedError("PropsClassBase.set_prop_cpus")

    def _set_prop_cpus_mnames(self,
                              pname: str,
                              val: PropertyValueType,
                              cpus: AbsNumsType,
                              mnames: Sequence[MechanismNameType] = ()) -> MechanismNameType:
        """
        Set a property for specified CPUs using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            cpus: CPU numbers to set the property for.
            mnames: Mechanism names to use for setting the property. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified CPUs and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified CPUs by the
                                      specified mechanisms, but may be supported by other
                                      mechanisms.
        """

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
        raise Error("BUG: Reached code that should be unreachable")

    def set_prop_cpus(self,
                      pname: str,
                      val: PropertyValueType,
                      cpus: AbsNumsType,
                      mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for specified CPUs using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            cpus: CPU numbers to set the property for.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified CPUs and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified CPUs by the
                                      specified mechanisms, but may be supported by other
                                      mechanisms.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)

        cpus = self._cpuinfo.normalize_cpus(cpus)
        if len(cpus) == 0:
            raise Error(f"BUG: No CPU numbers provided for setting {self._props[pname]['name']}"
                        f"{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_cpus_vs_scope(pname, cpus)

        return self._set_prop_cpus_mnames(pname, val, cpus, mnames)

    def set_cpu_prop(self,
                     pname: str,
                     val: PropertyValueType,
                     cpu: int,
                     mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for a specified CPU using the specified mechanisms.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            cpu: CPU number to set the property for.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported the CPU and mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for CPU by the specified
                                      mechanisms, but may be supported by other mechanisms.
        """

        return self.set_prop_cpus(pname, val, (cpu,), mnames=mnames)

    def _reduce_cpus_ioscope(self, cpus: list[int], iosname: ScopeNameType) -> list[int]:
        """
        Reduce a list of CPUs to a single representative CPU per I/O scope.

        Args:
            cpus: List of CPU numbers to reduce.
            iosname: I/O scope name to group CPUs by.

        Returns:
            List of reduced CPU numbers, containing one CPU per I/O scope group.
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

    def _set_prop_dies(self,
                       pname: str,
                       val: PropertyValueType,
                       dies: RelNumsType,
                       mname: MechanismNameType):
        """
        Set a property to a specified value for specified dies using a specified mechanism.

        Has to be implemented by the sub-class.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            die: Die numbers to set the property for.
            mname: Name of the mechanism to use for setting the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified dies and
                               mechanism.
            ErrorTryAnotherMechanism: If the property is not supported for the specified dies by the
                                      specified mechanism, but may be supported by other mechanisms.
        """

        cpus = []
        for package, pkg_dies in dies.items():
            for die in pkg_dies:
                cpus += self._cpuinfo.dies_to_cpus(dies=(die,), packages=(package,))

        iosname = self._props[pname]["iosname"]
        if iosname is None:
            raise Error(f"BUG: I/O scope was not set for property '{pname}'")

        cpus = self._reduce_cpus_ioscope(cpus, iosname)
        self._set_prop_cpus_mnames(pname, val, cpus, mnames=(mname,))

    def _set_prop_dies_mnames(self,
                              pname: str,
                              val: PropertyValueType,
                              dies: RelNumsType,
                              mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for specified CPUs using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            cpus: CPU numbers to set the property for.
            mnames: Mechanism names to use for setting the property. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified CPUs and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified CPUs by the
                                      specified mechanisms, but may be supported by other
                                      mechanisms.
        """

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
        raise Error("BUG: Reached code that should be unreachable")

    def set_prop_dies(self,
                      pname: str,
                      val: PropertyValueType,
                      dies: RelNumsType,
                      mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for specified dies using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            dies: Die numbers to set the property for.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified dies and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified dies by the
                                      specified mechanisms, but may be supported by other
                                      mechanisms.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)

        normalized_dies: dict[int, list[int]] = {}
        for package in self._cpuinfo.normalize_packages(list(dies)):
            normalized_dies[package] = []
            for die in self._cpuinfo.normalize_package_dies(dies[package], package=package):
                normalized_dies[package].append(die)

        # Make sure there are some die numbers.
        for package, pkg_dies in dies.items():
            if len(pkg_dies) == 0:
                raise Error(f"BUG: No package {package} die numbers provided for setting "
                            f"{self._props[pname]['name']}{self._pman.hostmsg}")
        if len(dies) == 0:
            raise Error(f"BUG: No package and die numbers provided for setting "
                        f"{self._props[pname]['name']}{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "die")

        return self._set_prop_dies_mnames(pname, val, normalized_dies, mnames)

    def set_die_prop(self,
                     pname: str,
                     val: PropertyValueType,
                     die: int,
                     package: int,
                     mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for a specified die using the specified mechanisms.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            die: Die number to set the property for.
            package: Package number containing the die.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported the die and mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for die by the specified
                                      mechanisms, but may be supported by other mechanisms.
        """

        dies: dict[int, tuple[int, ...]] = {package: (die,)}
        return self.set_prop_dies(pname, val, dies, mnames=mnames)

    def _set_prop_packages(self,
                           pname: str,
                           val: PropertyValueType,
                           packages: AbsNumsType,
                           mname: MechanismNameType):
        """
        Set a property to a specified value for a specified package using a specified mechanism.

        Has to be implemented by the sub-class.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            package: Package numbers to set the property for.
            mname: Name of the mechanism to use for setting the property.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified packages and
                               mechanism.
            ErrorTryAnotherMechanism: If the property is not supported for the specified packages by
                                      the specified mechanism, but may be supported by other
                                      mechanisms.
        """

        cpus = []
        for package in packages:
            cpus += self._cpuinfo.packages_to_cpus(packages=(package,))

        iosname = self._props[pname]["iosname"]
        if iosname is None:
            raise Error(f"BUG: I/O scope was not set for property '{pname}'")

        cpus = self._reduce_cpus_ioscope(cpus, iosname)
        return self._set_prop_cpus_mnames(pname, val, cpus, mnames=(mname,))

    def _set_prop_packages_mnames(self,
                                  pname: str,
                                  val: PropertyValueType,
                                  packages: AbsNumsType,
                                  mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for specified packages using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            packages: package numbers to set the property for.
            mnames: Mechanism names to use for setting the property. Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified packages and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified packages by
                                      the specified mechanisms, but may be supported by other
                                      mechanisms.
        """

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
        raise Error("BUG: Reached code that should be unreachable")

    def set_prop_packages(self,
                          pname: str,
                          val: PropertyValueType,
                          packages: AbsNumsType,
                          mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for specified packages using specified mechanisms.

        For boolean properties, use True/"on"/"enable" to enable and False/"off"/"disable" to
        disable.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            packages: Package numbers to set the property for.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported for the specified packages and
                               mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for the specified packages by
                                      the specified mechanisms, but may be supported by other
                                      mechanisms.
        """

        mnames = self._normalize_mnames(mnames, pname=pname, allow_readonly=False)
        val = self._normalize_inprop(pname, val)

        normalized_packages = self._cpuinfo.normalize_packages(packages)
        if len(packages) == 0:
            raise Error(f"BUG: No package numbers provided for setting "
                        f"{self._props[pname]['name']}{self._pman.hostmsg}")

        self._set_sname(pname)
        self._validate_prop_vs_scope(pname, "package")

        return self._set_prop_packages_mnames(pname, val, normalized_packages, mnames)

    def set_package_prop(self,
                         pname: str,
                         val: PropertyValueType,
                         package: int,
                         mnames: Sequence[MechanismNameType] = ()) -> str:
        """
        Set a property for a specified package using the specified mechanisms.

        Args:
            pname: Name of the property to set.
            val: Value to set the property to.
            package: Package number to set the property for.
            mnames: Mechanisms to use for setting the property. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.

        Returns:
            Name of the mechanism used to set the property.

        Raises:
            ErrorNotSupported: If the property is not supported the package and mechanisms.
            ErrorTryAnotherMechanism: If the property is not supported for package by the specified
                                      mechanisms, but may be supported by other mechanisms.
        """

        return self.set_prop_packages(pname, val, (package,), mnames=mnames)

    def _init_props_dict(self, props: dict[str, PropertyTypedDict]):
        """Initialize the 'props' and 'mechanisms' dictionaries."""

        self._props = copy.deepcopy(cast(dict[str, _PropertyTypedDict], props))
        self.props = props

        # Initialize the 'ioscope' to the same value as 'scope'. I/O scope may be different to the
        # scope for some MSR-based properties. Please, refer to 'MSR.py' for more information about
        # the difference between "scope" and "I/O scope".
        for prop in self._props.values():
            prop["iosname"] = prop["sname"]

        # Initialize the 'mechanisms' dictionary, which includes the mechanisms supported by the
        # subclass.
        seen: set[MechanismNameType] = set()
        for prop in self._props.values():
            seen.update(prop["mnames"])

        self.mechanisms = {}
        for mname, minfo in MECHANISMS.items():
            if mname in seen:
                self.mechanisms[mname] = minfo
