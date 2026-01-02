# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide API for printing properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import sys
import typing
from typing import Literal, get_args, cast
from pepctools import _PepcCommon
from pepctools._OpTarget import ErrorNoCPUTarget
from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, ClassHelpers, Human, YAML, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs._PropsClassBase import ErrorUsePerCPU, ErrorTryAnotherMechanism

PrintFormatType = Literal["human", "yaml"]

if typing.TYPE_CHECKING:
    from typing import TypedDict, Iterable, Sequence, IO, Iterator, Union, Generator
    from pepctools import _OpTarget
    from pepclibs import CStates, PStates, Uncore, PMQoS
    from pepclibs.CPUIdle import ReqCStateInfoTypedDict, ReqCStateInfoValuesType
    from pepclibs.CPUIdle import ReqCStateInfoKeysType
    from pepclibs.PropsTypes import PropertyTypedDict, PropertyValueType, PVInfoTypedDict
    from pepclibs.PropsTypes import MechanismNameType, PropsClassType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

    _AggrPropertyValueTypeNonTuple = Union[int, float, bool, str, None]
    _AggrPropertyValueTypeTuple = Union[tuple[str, ...], tuple[int, ...]]
    # Should be same as PropertyValueType, but include only hashable.
    _AggrPropertyValueType = Union[_AggrPropertyValueTypeNonTuple, _AggrPropertyValueTypeTuple]

    class _AggrSubPinfoTypdDict(TypedDict, total=False):
        """
        Type for the aggregate properties sub-dictionary for human-readable output.

        Attributes:
            sname: Scope name used for reading the property (e.g., "CPU", "die", "package").
            vals: A dictionary mapping property values to lists of CPUs, dies, or package numbers
                  that have this value.
        """

        sname: ScopeNameType
        vals: dict[_AggrPropertyValueType, AbsNumsType | RelNumsType]

    # The aggregate properties dictionary for human-readable output.
    _AggrPinfoType = dict[MechanismNameType, dict[str, _AggrSubPinfoTypdDict]]

    class _YAMLAggrPinfoValueTypedDict(TypedDict, total=False):
        """
        Type for property value in the aggregate properties sub-dictionary.

        Attributes:
            value: The value of the property.
            CPU: CPUs for which the property value applies.
            die: Dies for which the property value applies.
            package: Packages for which the property value applies.
        """

        value: _AggrPropertyValueType
        CPU: str
        die: dict[int, str]
        package: str

    class _YAMLAggrSubPinfoTypedDict(TypedDict, total=False):
        """
        Type for the aggregate properties sub-dictionary for YAML output. Describes a single
        property and its value on one or multiple CPUs, dies, or packages.

        Attributes:
            mechanism: Name of the mechanism used for reading the property.
            unit: The unit of the property value (e.g., "Hz", "W").
            values: A list of dictionaries mapping property values to their corresponding CPU, die,
                    or package.
        """

        mechanism: MechanismNameType
        unit: str
        values: list[_YAMLAggrPinfoValueTypedDict]

    # Type for the aggregate properties dictionary for YAML output.
    _YAMLAggrPinfoType = dict[str, _YAMLAggrSubPinfoTypedDict]

    # Type for the requestable C-state aggregate properties dictionary for human output.
    _RCAggrPinfoType = dict[str, dict[ReqCStateInfoKeysType,
                                      dict[ReqCStateInfoValuesType, list[int]]]]

    # Type for a requestable C-state property for YAML output.
    _YAMLRCAggrPinfoPropertyTypedDict = dict[Union[ReqCStateInfoKeysType, Literal["CPU"]],
                                             Union[ReqCStateInfoValuesType, str]]

    class _YAMLRCAggrSubPinfoTypedDict(TypedDict, total=False):
        """
        Type for the requestable C-state aggregate properties sub-dictionary for YAML output.

        Attributes:
            mechanism: Name of the mechanism used for reading the property.
            values: A list of dictionaries mapping, each dictionary contains a property value and
                    its CPU numbers (as a rangified string).
        """

        mechanism: MechanismNameType
        properties: list[_YAMLRCAggrPinfoPropertyTypedDict]

    # Type for the requestable C-state aggregate properties dictionary for YAML output.
    _YAMLRCAggrPinfoType = dict[str, _YAMLRCAggrSubPinfoTypedDict]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class _PropsPrinter(ClassHelpers.SimpleCloseContext):
    """
    Provide API for printing properties.
    """

    def __init__(self,
                 pobj: PropsClassType,
                 cpuinfo: CPUInfo.CPUInfo,
                 fobj: IO[str] | None = None,
                 fmt: PrintFormatType = "human"):
        """
        Initialize the class instance.

        Args:
            pobj: The properties object to print the properties for (e.g., 'PStates', 'CStates').
            cpuinfo: The 'CPUInfo' object initialized for the same host as 'pobj'.
            fobj: File object to print output to. Defaults to standard output.
            fmt: Output format. Supported values are 'human' (human-readable) and 'yaml' (YAML
                 format).
        """

        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._fobj = fobj
        self._fmt = fmt

        names = get_args(PrintFormatType)
        if self._fmt not in names:
            formats = ", ".join(names)
            raise Error(f"Unsupported format '{self._fmt}', supported formats are: {formats}")

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, unref_attrs=("_fobj", "_cpuinfo", "_pobj"))

    def _print(self, msg: str):
        """
        Print a message to the designated output.

        Args:
            msg: The message to print.
        """

        if self._fobj:
            self._fobj.write(msg)
        else:
            _LOG.info(msg)

    def _fmt_cpus(self, cpus: AbsNumsType) -> str:
        """
        Format CPU numbers into a human-readable string.

        Args:
            cpus: The CPU numbers to format.

        Returns:
            A string summarizing the CPUs numbers.
        """

        cpus_range = Trivial.rangify(cpus)
        if len(cpus) == 1:
            return f"CPU {cpus_range}"

        allcpus = self._cpuinfo.get_cpus()
        if set(cpus) == set(allcpus):
            return "all CPUs"

        msg = f"CPUs {cpus_range}"
        pkgs, rem_cpus = self._cpuinfo.cpus_div_packages(cpus)
        if pkgs and not rem_cpus:
            # CPUs in 'cpus' are actually the packages in 'pkgs'.
            pkgs_range = Trivial.rangify(pkgs)
            if len(pkgs) == 1:
                msg += f" (package {pkgs_range})"
            else:
                msg += f" (packages {pkgs_range})"

        if self._cpuinfo.info["hybrid"]:
            hybrid_info = self._cpuinfo.get_hybrid_cpus()
            if len(hybrid_info) > 1:
                for htype, hcpus in hybrid_info.items():
                    if set(cpus) == set(hcpus):
                        hname = CPUInfo.HYBRID_TYPE_INFO[htype]["name"]
                        if len(cpus) == 1:
                            msg += f" ({hname})"
                        else:
                            msg += f" ({hname}s)"
                        break
        return msg

    def _fmt_packages(self, packages: AbsNumsType) -> str:
        """
        Format package numbers into a human-readable string.

        Args:
            packages: The package numbers to format.

        Returns:
            A string summarizing the package numbers.
        """

        allpkgs = self._cpuinfo.get_packages()
        if set(packages) == set(allpkgs):
            if len(allpkgs) == 1:
                return "all CPUs"
            return "all packages"

        pkgs_range = Trivial.rangify(packages)
        if len(packages) == 1:
            return f"package {pkgs_range}"
        return f"packages {pkgs_range}"

    def _fmt_dies(self, pkgs_dies: RelNumsType) -> str:
        """
        Format die numbers into a human-readable string.

        Args:
            pkgs_dies: The die numbers to format.

        Returns:
            A string summarizing the die numbers.

        Notes:
            Die numbers are relative to package numbers, so 'pkgs_dies' is a dictionary where keys
            are package numbers and values are lists of die numbers within the package.
        """

        # Special case: provide a simpler and easier to read message when dealing with all
        # dies in all packages.
        all_dies_all_packages = True
        for pkg, dies in pkgs_dies.items():
            if len(dies) != self._cpuinfo.get_package_dies_count(package=pkg):
                all_dies_all_packages = False

        packages_count = self._cpuinfo.get_packages_count()
        if all_dies_all_packages and len(pkgs_dies) == packages_count:
            if packages_count == 1:
                return "all CPUs"
            return "all dies in all packages"

        # Format the detailed string. Examples:
        #   - all dies of package 0, dies 1,2 of package 1.
        #   - die 1 of package 0, dies 0-3 of package 1.
        result = []
        for pkg, dies in pkgs_dies.items():
            if len(dies) == self._cpuinfo.get_package_dies_count(package=pkg):
                dies_str = "all dies"
            else:
                dies_str = Trivial.rangify(dies)
                if len(dies) == 1:
                    plural = ""
                else:
                    plural = "s"
                dies_str = f"die{plural} {dies_str}"

            result.append(f"{dies_str} in package {pkg}")

        return ", ".join(result)

    def _fmt_nums(self, sname: str, nums: AbsNumsType | RelNumsType) -> str:
        """
        Format and return a human-readable string describing CPU, die, or package numbers.

        Args:
            sname: Scope name, expected to be "CPU", "package", or "die".
            nums: The CPU, die, or package numbers to format.

        Returns:
            Human-readable string summarizing the CPU, die, or package numbers.
        """

        if sname == "CPU":
            return self._fmt_cpus(nums) # type: ignore[arg-type]
        if sname == "package":
            return self._fmt_packages(nums) # type: ignore[arg-type]
        if sname == "die":
            # Use package formatting if there is only one die per package.
            if self._cpuinfo.get_package_dies_count(package=0) == 1:
                return self._fmt_packages(nums) # type: ignore[arg-type]
            return self._fmt_dies(nums) # type: ignore[arg-type]

        raise Error(f"BUG: Unexpected scope name {sname} for message formatting")

    def _format_value_human(self, _, prop: PropertyTypedDict, val: _AggrPropertyValueType) -> str:
        """
        Format a property value into a human-readable string based on its type and metadata.

        Args:
            _ : Unused parameter.
            prop: The property description dictionary containing metadata about the property (e.g.,
                  name, type, unit).
            val: The value of the property to format.

        Returns:
            Human-readable representation of the value.
        """

        def _detect_progression(vals: list[int], min_len: int) -> int | None:
            """
            Determine if a list of numbers forms an arithmetic progression.

            Args:
                vals: List of numeric values to check.
                min_len: Minimum length of the list to consider it for progression detection.

            Returns:
                The common difference if the list is an arithmetic progression, or None otherwise.
            """

            if len(vals) < min_len:
                return None

            step = vals[1] - vals[0]
            for idx, val in enumerate(vals[:-1]):
                if vals[idx + 1] - val != step:
                    return None

            return step

        def _format_unit(val: int, prop: PropertyTypedDict) -> str:
            """
            Format a numeric value with its unit, applying SI prefixes when appropriate.

            Args:
                val: Numeric value to format.
                prop: The property description dictionary for the property whose value is being
                      formatted.


            Returns:
                Formatted string representing the value with its unit.
            """

            unit = prop.get("unit")

            if unit:
                if unit == "%" or (unit == "s" and val > 100):
                    # Avoid kiloseconds and the like.
                    if prop["type"] == "int":
                        return f"{int(val)}{unit}"
                    return f"{val:.2f}{unit}"
                return Human.num2si(val, unit=unit, decp=2)
            return str(val)

        if prop["type"] in ("str", "bool"):
            return str(val)

        if prop["type"] in ("int", "float"):
            return _format_unit(val, prop) # type: ignore[arg-type]

        result = ""

        if prop["type"] == "list[str]":
            result = ", ".join(cast(list[str], val))
        elif prop["type"] == "list[int]":
            if typing.TYPE_CHECKING:
                cval = cast(list[int], val)
            else:
                cval = val
            step = _detect_progression(cval, 4)
            has_tar = False

            if len(cval) == 1:
                result = _format_unit(cval[0], prop)
            elif not step and len(cval) > 1:
                # The frequency numbers are expected to be sorted in the ascending order. The last
                # frequency number is often the Turbo Activation Ration (TAR) - a value just
                # slightly higher than the base frequency to activate turbo. Detect this situation
                # and use concise notation for it too.
                step = _detect_progression(cval[:-1], 3)
                if not step:
                    result = ", ".join([_format_unit(v, prop) for v in cval])
                else:
                    has_tar = True

            if step:
                # This is an arithmetic progression, use concise notation.
                first = _format_unit(cval[0], prop)
                if has_tar:
                    last = _format_unit(cval[-2], prop)
                    tar = _format_unit(cval[-1], prop)
                else:
                    last = _format_unit(cval[-1], prop)
                    tar = None

                step_str = _format_unit(step, prop)
                result = f"{first} - {last} with step {step_str}"
                if has_tar:
                    result += f", {tar}"
        else:
            raise Error(f"BUG: Property {prop['name']} as unsupported type '{prop['type']}")

        return result

    def _print_prop_human(self,
                          pname: str,
                          prop: PropertyTypedDict,
                          sname: ScopeNameType,
                          val: _AggrPropertyValueType,
                          nums: AbsNumsType | RelNumsType,
                          action: str | None = None,
                          prefix: str | None = None):
        """
        Format and print a message about a property in the human-readable format.

        Args:
            pname: Name of the property to print.
            prop: The property information dictionary.
            sname: Scope name used for reading the property (e.g., "die", "package", "CPU").
            val: Value of the property for the specified CPUs/dies/packages.
            nums: The CPU, package, or die numbers where the property value applies.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>".
            prefix: An optional string to prepend to the message.

        Notes:
            - Omit CPU/die/package numbers in case of a global property.
            - If the property value is None, indicate it is not supported.
            - For non-numeric types, quote the value when printing with a suffix.
        """

        if prop["sname"] == "global":
            sfx = ""
        else:
            nums_str = self._fmt_nums(sname, nums)
            sfx = f" for {nums_str}"

        msg = f"{prop['name']}: "

        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        else:
            val = self._format_value_human(pname, prop, val)
            if val == "" and (prop["type"].startswith("list")):
                return

            if sfx and prop["type"] not in ("int", "float"):
                val = f"'{val}'"

        if action is not None:
            msg += f"{action} "

        msg += f"{val}{sfx}"
        self._print(msg)

    def _do_print_aggr_pinfo_human(self,
                                   apinfo: dict[str, _AggrSubPinfoTypdDict],
                                   action: str | None = None,
                                   prefix: str | None = None) -> int:
        """
        Print a property sub-dictionary of the aggregated property dictionary in a human-readable
        format.

        Args:
            apinfo: A sub-dictionary of the aggregate properties dictionary to print.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>".
            prefix: An optional string to prepend to the message.

        Returns:
            The number of property entries printed.
        """

        props = self._pobj.props

        printed = 0
        for pname, pinfo in apinfo.items():
            for val, nums, in pinfo["vals"].items():
                self._print_prop_human(pname, props[pname], pinfo["sname"], val, nums,
                                       action=action, prefix=prefix)
                printed += 1

        return printed

    def _print_aggr_pinfo_human(self,
                                aggr_pinfo: _AggrPinfoType,
                                group: bool = False,
                                action: str | None = None) -> int:
        """
        Print an aggregate property dictionary in a human-readable format.

        Args:
            aggr_pinfo: The aggregate properties dictionary to print.
            group: If True, properties are grouped and printed by their mechanism name. If False,
                   properties are printed without grouping.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>".

        Returns:
            The total number of properties printed.
        """

        if group:
            prefix = " - "
        else:
            prefix = None

        printed = 0
        for mname, pinfo in aggr_pinfo.items():
            if group:
                self._print(f"Source: {self._pobj.get_mechanism_descr(mname)}")
            printed += self._do_print_aggr_pinfo_human(pinfo, action=action, prefix=prefix)

        return printed

    def _yaml_dump(self, yaml_pinfo: dict):
        """
        Dump an aggregate properties dictionary in YAML format to a file object or
        stdout.

        Args:
            yaml_pinfo: The aggregate properties dictionary to dump.
        """

        fobj = self._fobj
        if not fobj:
            fobj = sys.stdout

        YAML.dump(yaml_pinfo, fobj)

    def _print_aggr_pinfo_yaml(self, aggr_pinfo: _AggrPinfoType) -> int:
        """
        Print aggregate properties dictionary in YAML format.

        Args:
            aggr_pinfo: The aggregate properties dictionary.

        Returns:
            The number of printed properties.
        """

        yaml_pinfo: _YAMLAggrPinfoType = {}

        for mname, ainfo in aggr_pinfo.items():
            for pname, pinfo in ainfo.items():
                # Only a sub-set of scope names is used.
                sname = pinfo["sname"]

                for val, nums in pinfo["vals"].items():
                    if val is None:
                        val = "not supported"

                    if pname not in yaml_pinfo:
                        yaml_pinfo[pname] = {}

                    yaml_pinfo[pname]["mechanism"] = mname

                    prop = self._pobj.props[pname]
                    unit = prop.get("unit")
                    if unit:
                        yaml_pinfo[pname]["unit"] = unit

                    if "values" not in yaml_pinfo[pname]:
                        yaml_pinfo[pname]["values"] = []

                    if sname != "die":
                        ragified_str = Trivial.rangify(cast(list[int], nums))
                        sname_wa = cast(Literal["CPU"], sname)
                        yaml_pinfo[pname]["values"].append({"value": val, sname_wa: ragified_str})
                    else:
                        rangified_dict: dict[int, str] = {}
                        nums_dict = cast(dict[int, list[int]], nums)
                        for pkg, dies in nums_dict.items():
                            rangified_dict[pkg] = Trivial.rangify(dies)
                        yaml_pinfo[pname]["values"].append({"value": val, sname: rangified_dict})

        self._yaml_dump(yaml_pinfo)
        return len(yaml_pinfo)

    @staticmethod
    def _get_pvinfo_num(pvinfo: PVInfoTypedDict) -> tuple[ScopeNameType, int | tuple[int, int]]:
        """
        Extract and return a tuple containing the scope name and the CPU/die/package number from
        the property value information dictionary.

        Args:
            pvinfo: The property value information dictionary.

        Returns:
            A tuple of scope name and the CPU/die/package number.
        """

        if "cpu" in pvinfo:
            return "CPU", pvinfo["cpu"]
        if "die" in pvinfo:
            return "die", (pvinfo["package"], pvinfo["die"])
        if "package" in pvinfo:
            return "package", pvinfo["package"]

        raise Error("BUG: Bad property value dictionary, no 'cpu', 'die', or 'package' key found\n"
                    "The dictionary: {pvinfo}")

    def _get_prop_sname(self,
                        pname: str,
                        optar: _OpTarget.OpTarget,
                        mnames: Sequence[MechanismNameType],
                        override_sname: ScopeNameType | None = None) -> \
                                                        Generator[PVInfoTypedDict, None, None]:
        """
        Yield property value dictionaries for a property, accounting for its scope.

        Args:
            pname: Name of the property to retrieve.
            optar: Operation target object specifying CPUs, packages, etc.
            mnames: Mechanism names to use for retrieving the property.
            override_sname: Optional scope name to use instead of the property's default scope.

        Yields:
            Property value info dictionaries ('PVInfoTypedDict') for the specified property.

        Raises:
            ErrorNoCPUTarget: If no valid CPUs/dies/packages can be determined for the operation.
        """

        try:
            sname, nums = _PepcCommon.get_sname_and_nums(self._pobj, pname, optar,
                                                         override_sname=override_sname)
        except ErrorNoCPUTarget as err:
            name = self._pobj.props[pname]["name"]
            raise ErrorNoCPUTarget(f"Impossible to get {name}:\n{err.indent(2)}") from err

        if sname == "die":
            if typing.TYPE_CHECKING:
                nums = cast(RelNumsType, nums)
            yield from self._pobj.get_prop_dies(pname, nums, mnames=mnames)
        else:
            if typing.TYPE_CHECKING:
                nums = cast(AbsNumsType, nums)
            if sname == "CPU":
                yield from self._pobj.get_prop_cpus(pname, nums, mnames=mnames)
            else:
                yield from self._pobj.get_prop_packages(pname, nums, mnames=mnames)

    def _build_aggr_pinfo_pname(self,
                                pname: str,
                                optar: _OpTarget.OpTarget,
                                mnames: Sequence[MechanismNameType],
                                skip_unsupp_props: bool,
                                override_sname: ScopeNameType | None = None) -> _AggrPinfoType:
        """
        Build and return an aggregate properties dictionary for human-readable output for a single
        property.

        Args:
            pname: Name of the property to aggregate.
            optar: Operation target specifying the hardware scope.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence.
            skip_unsupp_props: Whether to skip unsupported properties.
            override_sname: Override the default scope name for the property.

        Raises:
            ErrorUsePerCPU: If the property value is inconsistent across package or die siblings,
                            indicating that per-CPU access should be used instead.
            ErrorTryAnotherMechanism: If the property is not supported by the requested mechanism,
                                      and another mechanism should be used instead.
        Returns:
            The aggregate properties dictionary for the property.
        """

        prop = self._pobj.props[pname]
        apinfo: _AggrPinfoType = {}

        for pvinfo in self._get_prop_sname(pname, optar, mnames, override_sname=override_sname):
            sname, num = self._get_pvinfo_num(pvinfo)
            val = pvinfo["val"]
            mname = pvinfo["mname"]

            if skip_unsupp_props and val is None:
                continue

            # Dictionary keys must be of an immutable type, turn lists into tuples.
            val_key: _AggrPropertyValueType
            if prop["type"].startswith("list[") and val is not None:
                if typing.TYPE_CHECKING:
                    val = cast(Union[list[str], list[int]], val)
                    val_key = cast(_AggrPropertyValueTypeTuple, tuple(val))
                else:
                    val_key = tuple(val)
            else:
                if typing.TYPE_CHECKING:
                    val_key = cast(_AggrPropertyValueTypeNonTuple, val)
                else:
                    val_key = val

            num_tuple: tuple[int, int]
            num_int: int

            if sname == "die":
                num_tuple = cast(tuple[int, int], num)
                package, die = num_tuple
            else:
                package, die = -1, -1
                num_int = cast(int, num)

            if mname not in apinfo:
                apinfo[mname] = {}
            if pname not in apinfo[mname]:
                apinfo[mname][pname] = {"sname": sname, "vals": {}}

            pinfo = apinfo[mname][pname]

            if val_key not in pinfo["vals"]:
                if sname == "die":
                    pinfo["vals"][val_key] = {package: [die]}
                else:
                    pinfo["vals"][val_key] = [num_int]
            else:
                if sname == "die":
                    dies = cast(dict[int, list[int]], pinfo["vals"][val_key])
                    if package not in dies:
                        dies[package] = []
                    dies[package].append(die)
                else:
                    nums = cast(list[int], pinfo["vals"][val_key])
                    nums.append(num_int)

            if sname != pinfo["sname"]:
                raise Error(f"BUG: Varying scope name for property '{pname}': was "
                            f"'{pinfo['sname']}', now '{sname}'")

        return apinfo

    def _build_aggr_pinfo(self,
                          pnames: Iterable[str],
                          optar: _OpTarget.OpTarget,
                          mnames: Sequence[MechanismNameType],
                          skip_ro_props: bool,
                          skip_unsupp_props: bool,
                          skip_unsupp_mechanisms: bool) -> _AggrPinfoType:
        """
        Build and return an aggregate properties infomation dictionary for human-readable output for
        the specified property names.

        Constructs a nested dictionary that maps mechanism names to property names, and then to a
        dictionary mapping property values to the CPUs, dies, or packages that have those values. In
        other words, if the multiple CPUs, dies, or packages share the same property value,
        they will be grouped together under that value.

        The format of the returned aggregate properties dictionary is as follows:
            {
                mechanism_name: {
                    property_name: {
                        "sname": scope_name,
                        "vals": {
                            value1: [list of CPUs/packages] or {package: [dies]},
                            value2: ...,
                            ...
                        }
                    },
                    ...
                },
                ...
            }

        - If the scope name ("sname") is "CPU" or "package", property values are mapped to lists of
          CPU or package numbers.
        - If the scope name is "die", property values are mapped to dictionaries where keys are
          package numbers and values are lists of die numbers within each package.

        Args:
            pnames: Names of the properties to aggregate.
            optar: Operation target specifying the hardware scope.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence.
            skip_ro_props: Whether to skip read-only properties.
            skip_unsupp_props: Whether to skip unsupported properties.
            skip_unsupp_mechanisms: If True, skip the properties that cannot be retrieved using
                                    the mechanisms in 'mnames', but can be retrieved using other
                                    mechanisms. Otherwise, raise an exception.

        Returns:
            The aggregate properties dictionary structured as described above.
        """

        aggr_pinfo: _AggrPinfoType = {}
        _LOG.debug("Build aggregate properties information dictionary for: %s",
                   ", ".join(pnames))

        for pname in pnames:
            prop = self._pobj.props[pname]
            if skip_ro_props and not prop["writable"]:
                continue

            try:
                apinfo = self._build_aggr_pinfo_pname(pname, optar, mnames, skip_unsupp_props)
            except ErrorTryAnotherMechanism as err:
                _LOG.debug(err)
                if skip_unsupp_mechanisms:
                    continue
                raise
            except ErrorUsePerCPU as err:
                # Inconsistent property value across package or die siblings. Use per-CPU access.
                _LOG.warning(err)
                apinfo = self._build_aggr_pinfo_pname(pname, optar, mnames, skip_unsupp_props,
                                                      override_sname="CPU")

            # Merge 'apinfo' to 'aggr_pinfo'.
            for mname, info in apinfo.items():
                if mname not in aggr_pinfo:
                    aggr_pinfo[mname] = {}
                aggr_pinfo[mname].update(info)

        return aggr_pinfo

    def _normalize_pnames(self,
                          pnames: Iterable[str] | Literal["all"],
                          skip_ro_props: bool = False) -> Iterable[str]:
        """
        Validate and normalize a list of property names.

        Args:
            pnames: Property names to validate and normalize, or the string "all" to include all
                    properties.
            skip_ro_props: If True, excludes read-only properties from the returned list.

        Returns:
            An iterable of validated and normalized property names.
        """

        if pnames == "all":
            pnames = list(self._pobj.props)
        else:
            for pname in pnames:
                if pname not in self._pobj.props:
                    raise Error(f"Unknown property name '{pname}'")

        if not skip_ro_props:
            return pnames

        return [pname for pname in pnames if self._pobj.props[pname]["writable"]]

    def print_props(self,
                    pnames: Iterable[str] | Literal["all"],
                    optar: _OpTarget.OpTarget,
                    mnames: Sequence[MechanismNameType] = (),
                    skip_ro_props: bool = False,
                    skip_unsupp_props: bool = False,
                    skip_unsupp_mechanisms: bool = False,
                    group: bool = False,
                    action: str | None = None) -> int:
        """
        Read and print properties for specified CPUs, cores, modules, etc.

        Args:
            pnames: Property names to read and print. Read all properties if set to "all".
            optar: An '_OpTarget.OpTarget()' object representing the CPUs, cores, modules, etc., for
                   which to print the properties.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.
            skip_ro_props: If True, skip read-only properties. If False, include read-only
                           properties in the output.
            skip_unsupp_props: If True, skip unsupported properties. If False, print "not supported"
                              for unsupported properties.
            skip_unsupp_mechanisms: If True, skip the properties that cannot be retrieved using
                                    the mechanisms in 'mnames', but can be retrieved using other
                                    mechanisms. Otherwise, raise an exception.
            group: If True, properties are grouped and printed by their mechanism name. If False,
                   properties are printed without grouping.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>". Not applicable for YAML output.

        Returns:
            The number of printed properties.
        """

        pnames = self._normalize_pnames(pnames, skip_ro_props=skip_ro_props)

        aggr_pinfo = self._build_aggr_pinfo(pnames, optar, mnames, skip_ro_props, skip_unsupp_props,
                                            skip_unsupp_mechanisms)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group, action=action)
        return self._print_aggr_pinfo_yaml(aggr_pinfo)

class PStatesPrinter(_PropsPrinter):
    """Provide API for printing P-states information."""

    def __init__(self,
                 pobj: PStates.PStates,
                 cpuinfo: CPUInfo.CPUInfo,
                 fobj: IO[str] | None = None,
                 fmt: PrintFormatType = "human"):
        """Refer to '_PropsPrinter.__init__()'."""

        super().__init__(pobj, cpuinfo, fobj=fobj, fmt=fmt)

        self._pobj: PStates.PStates

class UncorePrinter(_PropsPrinter):
    """Provide API for printing uncore information."""

    def __init__(self,
                 pobj: Uncore.Uncore,
                 cpuinfo: CPUInfo.CPUInfo,
                 fobj: IO[str] | None = None,
                 fmt: PrintFormatType = "human"):
        """Refer to '_PropsPrinter.__init__()'."""

        super().__init__(pobj, cpuinfo, fobj=fobj, fmt=fmt)

        self._pobj: Uncore.Uncore

class PMQoSPrinter(_PropsPrinter):
    """Provide API for printing PM QoS information."""

    def __init__(self,
                 pobj: PMQoS.PMQoS,
                 cpuinfo: CPUInfo.CPUInfo,
                 fobj: IO[str] | None = None,
                 fmt: PrintFormatType = "human"):
        """Refer to '_PropsPrinter.__init__()'."""

        super().__init__(pobj, cpuinfo, fobj=fobj, fmt=fmt)

        self._pobj: PMQoS.PMQoS

    def _format_value_human(self,
                            pname: str,
                            prop: PropertyTypedDict,
                            val: _AggrPropertyValueType) -> str:
        """
        Format a property value into a human-readable string based on its type and metadata.

        Args:
            pname: Name of the property to format the value for.
            prop: The property description dictionary containing metadata about the property (e.g.,
                  name, type, unit).
            val: The value of the property to format.

        Returns:
            Human-readable representation of the value.
        """

        if pname == "latency_limit" and val == 0:
            # Per-CPU latency limit 0 means "no latency".
            return "0 (no limit)"
        if pname == "global_latency_limit" and val == 0:
            # The global latency limit 0 means "cannot tolerate any latency".
            return "0 (absolute minimum)"

        return super()._format_value_human(pname, prop, val)

class CStatesPrinter(_PropsPrinter):
    """Provide API for printing C-states information."""

    def __init__(self,
                 pobj: CStates.CStates,
                 cpuinfo: CPUInfo.CPUInfo,
                 fobj: IO[str] | None = None,
                 fmt: PrintFormatType = "human"):
        """Refer to '_PropsPrinter.__init__()'."""

        super().__init__(pobj, cpuinfo, fobj=fobj, fmt=fmt)

        self._pobj: CStates.CStates

    def _adjust_aggr_pinfo_pcs_limit(self,
                                     aggr_pinfo: _AggrPinfoType,
                                     cpus: AbsNumsType,
                                     mnames: Sequence[MechanismNameType] = ()) -> _AggrPinfoType:
        """
        Adjust the 'pkg_cstate_limit' property in the aggregate properties information dictionary by
        removing it for locked CPUs. This is necessary when user requested to exclude R/O
        properties, and the 'pkg_cstate_limit' property is effectively read-only when it is locked.

        In practice, it is locked either for all CPUs or none. But this method is designed to handle
        the general case where some CPUs may be locked and others may not.

        Args:
            aggr_pinfo: Dictionary containing aggregate properties information for CPUs, including
                        'pkg_cstate_limit'.
            cpus: CPU numbers for which to adjust the 'pkg_cstate_limit' property.
            mnames: Mechanism names to use for reading properties.  Use all available mechanisms in
                    case of an empty sequence (default).

        Returns:
            The updated 'aggr_pinfo' dictionary with locked CPUs removed from the 'pkg_cstate_limit'
            property, or with the property removed entirely if all CPUs are locked.
        """

        for pinfo in aggr_pinfo.values():
            pcsl_info = pinfo.get("pkg_cstate_limit")
            if not pcsl_info:
                continue

            if set(pcsl_info) == {None}:
                # The 'pkg_cstate_limit' property is not supported, nothing to do.
                continue

            locked_cpus = set()
            for pvinfo in self._pobj.get_prop_cpus("pkg_cstate_limit_lock", cpus=cpus,
                                                   mnames=mnames):
                cpu = pvinfo["cpu"]
                if pvinfo["val"] == "on":
                    locked_cpus.add(cpu)

            if not locked_cpus:
                # There are no locked CPUs, nothing to do.
                continue

            if len(locked_cpus) == len(cpus):
                # All CPUs are locked, "pkg_cstate_limit" is considered read-only, and is removed.
                del pinfo["pkg_cstate_limit"]
                continue

            new_pcsl_info: _AggrSubPinfoTypdDict = {"sname": pcsl_info["sname"], "vals": {}}
            for val, _cpus in pcsl_info["vals"].items():
                new_cpus = []
                for cpu in _cpus:
                    if cpu not in locked_cpus:
                        new_cpus.append(cpu)
                if new_cpus:
                    new_pcsl_info["vals"][val] = new_cpus

            pinfo["pkg_cstate_limit"] = new_pcsl_info

        return aggr_pinfo

    def print_props(self,
                    pnames: Iterable[str] | Literal["all"],
                    optar: _OpTarget.OpTarget,
                    mnames: Sequence[MechanismNameType] = (),
                    skip_ro_props: bool = False,
                    skip_unsupp_props: bool = False,
                    skip_unsupp_mechanisms: bool = False,
                    group: bool = False,
                    action: str | None = None) -> int:
        """
        Read and print properties for specified CPUs, cores, modules, etc.

        Args:
            pnames: Property names to read and print. Read all properties if set to "all".
            optar: An '_OpTarget.OpTarget()' object representing the CPUs, cores, modules, etc., for
                   which to print the properties.
            mnames: Mechanism names to use for property retrieval. Use all available mechanisms in
                    case of an empty sequence (default).
            skip_ro_props: If True, skip read-only properties. If False, include read-only
                           properties in the output.
            skip_unsupp_props: If True, skip unsupported properties. If False, print "not supported"
                              for unsupported properties.
            skip_unsupp_mechanisms: If True, skip the properties that cannot be retrieved using
                                    the mechanisms in 'mnames', but can be retrieved using other
                                    mechanisms. Otherwise, raise an exception.
            group: If True, properties are grouped and printed by their mechanism name. If False,
                   properties are printed without grouping.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>". Not applicable for YAML output.

        Returns:
            The number of printed properties.
        """

        pnames = self._normalize_pnames(pnames, skip_ro_props=skip_ro_props)
        aggr_pinfo = self._build_aggr_pinfo(pnames, optar, mnames, skip_ro_props, skip_unsupp_props,
                                            skip_unsupp_mechanisms)

        if skip_ro_props and "pkg_cstate_limit" in pnames:
            # Special case: the package C-state limit option is read-write in general, but if it is
            # locked, it is effectively read-only. Since 'skip_ro_props' is 'True', we need to
            # adjust 'aggr_pinfo'.
            aggr_pinfo = self._adjust_aggr_pinfo_pcs_limit(aggr_pinfo, optar.get_cpus(), mnames)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group, action=action)

        return self._print_aggr_pinfo_yaml(aggr_pinfo)

    def _print_val_msg(self,
                       val: ReqCStateInfoValuesType,
                       name: str | None = None,
                       cpus: AbsNumsType | None = None,
                       prefix: str | None = None,
                       suffix: str | None = None,
                       action: str | None = None):
        """
        Format and print a message describing a value of a requestable C-state property.

        Args:
            val: The value to print. If None, "not supported" will be displayed.
            name: Property name. If None, no name will be included in the message.
            cpus: CPU numbers that have this value. If None, no CPU information will be included.
            prefix: An optional string to prepend to the message.
            suffix: An optional string to append to the message.
            action: An "action" word to include into the messages (nothing by default). For example,
                    if 'action' is "set to", the messages will be like "property <pname> set to
                    <value>". Not applicable for YAML output.
        """

        if cpus is None:
            sfx = ""
        else:
            cpus_str = self._fmt_cpus(cpus)
            sfx = f" for {cpus_str}"

        if suffix is not None:
            sfx = sfx + suffix

        if name is not None:
            pfx = f"{name}: "
        else:
            pfx = ""

        if action:
            pfx += f"{action} "

        msg = pfx
        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        elif cpus is not None:
            val = f"'{val}'"

        msg += f"{val}{sfx}"
        self._print(msg)

    def _print_aggr_rcsinfo_human(self,
                                  aggr_rcsinfo: _RCAggrPinfoType,
                                  group: bool = False,
                                  action: str | None = None) -> int:
        """
        Print a requestable C-states aggregate dictionary in a human-readable format.

        Args:
            aggr_rcsinfo: The requestable C-states aggregate dictionary to print.
            group: If True, properties are grouped and printed by their mechanism name. If False,
                   properties are printed without grouping.
            action: An "action" word to include into the messages (nothing by default). For example,
                    if 'action' is "set to", the messages will be like "property <pname> set to
                    <value>". Not applicable for YAML output.

        Returns:
            The number of C-states printed.
        """

        if not aggr_rcsinfo:
            self._print("This system does not support C-states")
            return 1

        if not group:
            prefix = None
            sub_prefix = " - "
        else:
            prefix = " - "
            sub_prefix = "    - "
            self._print(f"Source: {self._pobj.get_mechanism_descr('sysfs')}")

        printed = 0
        for csname, csinfo in aggr_rcsinfo.items():
            if "disable" not in csinfo:
                # Do not print the C-state if it's enabled/disabled status is unknown.
                continue

            printed += 1
            for val, cpus in csinfo["disable"].items():
                val = "off" if val else "on"
                self._print_val_msg(val, name=csname, cpus=cpus, action=action, prefix=prefix)

            for key, kinfo in csinfo.items():
                if key == "latency":
                    name = "expected latency"
                    suffix = " us"
                elif key == "residency":
                    name = "target residency"
                    suffix = " us"
                elif key == "desc":
                    name = "description"
                    suffix = None
                else:
                    continue

                for val, cpus in kinfo.items():
                    self._print_val_msg(val, name=name, prefix=sub_prefix, suffix=suffix)

        return printed

    def _print_aggr_rcsinfo_yaml(self, aggr_rcsinfo: _RCAggrPinfoType) -> int:
        """
        Print the requestable C-states aggregate dictionary in YAML format.

        Args:
            aggr_rcsinfo: The requestable C-states aggregate dictionary to print.

        Returns:
            The number of C-state entries processed and printed.
        """

        yaml_rcsinfo: _YAMLRCAggrPinfoType = {}

        for csname, csinfo in aggr_rcsinfo.items():
            for key, kinfo in csinfo.items():
                for val, cpus in kinfo.items():
                    if csname not in yaml_rcsinfo:
                        yaml_rcsinfo[csname] = {"mechanism": "sysfs", "properties": []}

                    properties = yaml_rcsinfo[csname]["properties"]
                    properties.append({key: val, "CPU": Trivial.rangify(cpus)})

        self._yaml_dump({"cstates": yaml_rcsinfo})
        return len(yaml_rcsinfo)

    def _build_aggr_rcsinfo(self,
                            csinfo_iter: Iterator[tuple[int, dict[str, ReqCStateInfoTypedDict]]],
                            keys: set[ReqCStateInfoKeysType]) -> _RCAggrPinfoType:
        """
        Build and return requestable C-states aggregate dictionary for human-readable output.

        Args:
            csinfo_iter: Iterator yielding (cpu, csinfo) tuples, where 'cpu' is a CPU number and
                         'csinfo' is a dictionary with C-state information for that CPU.
            keys: Set of C-state property names to include in the aggregate dictionary, such as
                  "disable", "latency", or "residency".

        Returns:
            The aggregate C-states information dictionary for requestable C-states output.
        """

        aggr_rcsinfo: _RCAggrPinfoType = {}

        # C-states info 'csinfo' has the following format:
        #
        # {"POLL": {"disable": True, "latency": 0, "residency": 0, ...},
        #  "C1E": {"disable": False, "latency": 2, "residency": 1, ...},
        #  ...}
        for cpu, csinfo in csinfo_iter:
            for csname, values in csinfo.items():
                if csname not in aggr_rcsinfo:
                    aggr_rcsinfo[csname] = {}

                for key, val in values.items():
                    if key not in keys or val is None:
                        continue

                    if typing.TYPE_CHECKING:
                        val = cast(ReqCStateInfoValuesType, val)
                        key = cast(ReqCStateInfoKeysType, key)

                    if key not in aggr_rcsinfo[csname]:
                        aggr_rcsinfo[csname][key] = {val: [cpu]}
                    elif val not in aggr_rcsinfo[csname][key]:
                        aggr_rcsinfo[csname][key][val] = [cpu]
                    else:
                        aggr_rcsinfo[csname][key][val].append(cpu)

        return aggr_rcsinfo

    def print_cstates(self,
                      csnames: Iterable[str] | Literal["all"] = "all",
                      cpus: AbsNumsType | Literal["all"] = "all",
                      mnames: Sequence[MechanismNameType] = (),
                      skip_ro_props: bool = False,
                      group: bool = False,
                      action: str | None = None) -> int:
        """
        Print information about requestable C-states for specified CPUs.

        Args:
            csnames: Names of C-states to include in the output. Use "all" to include all C-states.
            cpus: CPU numbers to include in the output. Use "all" to include all CPUs.
            mnames: Mechanisms to use for property retrieval. The mechanisms will be tried in the
                    order specified in 'mnames'. By default, all mechanisms supported by the 'pname'
                    property will be tried.
            skip_ro_props: If True, print only modifiable properties and skip read-only information.
            group: If True, properties are grouped and printed by their mechanism name. If False,
                   properties are printed without grouping.
            action: An "action" word to include into the messages (nothing by default). For
                    example, if 'action' is "set to", the messages will be like
                    "property <pname> set to <value>". Not applicable for YAML output.

        Returns:
            The number of requestable C-states printed.
        """

        if not mnames:
            mnames = ["sysfs"]

        if "sysfs" not in mnames:
            if csnames == "all":
                return 0
            raise ErrorTryAnotherMechanism("The 'sysfs' mechanism is required for printing "
                                           "C-states information")

        keys: set[ReqCStateInfoKeysType]

        if skip_ro_props:
            keys = {"disable"}
        else:
            keys = {"disable", "latency", "residency", "desc"}

        csinfo_iter = self._pobj.get_cstates_info(csnames=csnames, cpus=cpus)

        try:
            aggr_rcsinfo = self._build_aggr_rcsinfo(csinfo_iter, keys)
        except ErrorNotSupported as err:
            _LOG.warning(err)
            _LOG.info("C-states are not supported")
            return 0

        if self._fmt == "human":
            return self._print_aggr_rcsinfo_human(aggr_rcsinfo, group=group, action=action)

        return self._print_aggr_rcsinfo_yaml(aggr_rcsinfo)
