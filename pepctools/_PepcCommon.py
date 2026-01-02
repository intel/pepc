# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Common functions for pepc command-line tools.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo, CPUModels
from pepclibs.helperlibs import Logging, Systemctl, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported, ErrorBadFormat
from pepctools._OpTarget import ErrorNoTarget

if typing.TYPE_CHECKING:
    from typing import cast, Union, Iterable
    from pepctools import _OpTarget
    from pepclibs.PropsTypes import PropertyTypedDict, PropsClassType, MechanismNameType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def check_tuned_presence(pman: ProcessManagerType):
    """
    Check if the 'tuned' service is active and warn if it may override pepc changes.

    Args:
        pman: Process manager object for the target host.
    """

    try:
        with Systemctl.Systemctl(pman=pman) as systemctl:
            if systemctl.is_active("tuned"):
                _LOG.warning("The 'tuned' service is active%s! It may override the changes made by "
                             "'pepc'\nConsider having 'tuned' disabled while experimenting with "
                             "power management settings.", pman.hostmsg)
    except ErrorNotFound:
        pass
    except Error as err:
        _LOG.warning("Failed to check for 'tuned' presence:\n%s", err.indent(2))

def override_cpu_model(cpuinfo: CPUInfo.CPUInfo, vfmarg: str):
    """
    Override the CPU model in the provided 'CPUInfo' object.

    Args:
        cpuinfo: The 'CPUInfo' object to modify CPU model in.
        vfmarg: The CPU '[<Vendor>]:[<Family>]:<Model>' string to parse and override the the
                'cpuinfo' object with. The <Model> part can be a decimal or hexadecimal number.

    Raises:
        ErrorBadFormat: If the provided 'vfmarg' string is not in the correct format or contains
                        invalid values.
        ErrorNotSupported: If the specified CPU vendor is not supported.
    """

    split = vfmarg.split(":")
    if len(split) > 3:
        raise ErrorBadFormat(f"Bad CPU model '{vfmarg}': should be in the form of "
                             f"'[<Vendor>]:[<Family>]:<Model>'.")

    if len(split) == 3:
        vendor = split[0]
        family_str = split[1]
        model_str = split[2]
    elif len(split) == 2:
        vendor = cpuinfo.info["vendor"]
        family_str = split[0]
        model_str = split[1]
    else:
        vendor = cpuinfo.info["vendor"]
        family_str = str(cpuinfo.info["family"])
        model_str = split[0]

    if vendor not in CPUModels.X86_CPU_VENDORS:
        raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor}', supported vendors are: "
                                f"{', '.join(CPUModels.X86_CPU_VENDORS)}")
    if not Trivial.is_int(family_str):
        raise ErrorBadFormat(f"Bad CPU family '{family_str}': Should be an integer")
    if not Trivial.is_int(model_str):
        raise ErrorBadFormat(f"Bad CPU model '{model_str}': Should be an integer")

    family = Trivial.str_to_int(family_str, what="CPU family")
    if family < 0 or family > 255:
        raise ErrorBadFormat(f"Bad CPU family '{family_str}': Should be in the range of 0-255")
    model = Trivial.str_to_int(model_str, what="CPU model")
    if model < 0 or model > 4095:
        raise ErrorBadFormat(f"Bad CPU model '{model_str}': Should be in the range of 0-4095")

    cpuinfo.info["vendor"] = vendor
    cpuinfo.info["family"] = family
    cpuinfo.info["model"] = model
    cpuinfo.info["vfm"] = CPUModels.make_vfm(vendor, family, model)

    cpuinfo.cpudescr += f", overridden with {vfmarg}"

    _LOG.notice("Overriding CPU model with '%s', resulting VFM is '%s:%s:%s",
                vfmarg, vendor, family, model)

def expand_subprops(pnames: Iterable[str], props: dict[str, PropertyTypedDict]) -> list[str]:
    """
    Expand a list of property names to include their sub-properties.

    Args:
        pnames: A collection of property names to expand.
        props: The properties dictionary (e.g., 'CStates.PROPS').

    Returns:
        A list of property names including the original names and their sub-properties.
    """

    expanded: list[str] = []

    for pname in pnames:
        expanded.append(pname)

        prop = props.get(pname)
        if prop and "subprops" in prop:
            spnames = prop["subprops"]
            expanded.extend(spnames)

    return expanded

def parse_mechanisms(mechanisms: str, pobj: PropsClassType) -> list[MechanismNameType]:
    """
    Parse and validate comma-separated mechanism names.

    Args:
        mechanisms: Comma-separated string of mechanism names.
        pobj: The properties object (e.g., 'PStates', 'CStates') containing valid mechanisms.

    Returns:
        List of validated mechanism names.

    Raises:
        ErrorNotSupported: If any mechanism name is not supported by 'pobj'.
    """

    mnames = Trivial.split_csv_line(mechanisms, dedup=True)
    for mname in mnames:
        if mname not in pobj.mechanisms:
            mnames_str = ", ".join(pobj.mechanisms)
            raise ErrorNotSupported(f"Mechanism '{mname}' is not supported. The supported "
                                    f"mechanisms are: {mnames_str}")
    if typing.TYPE_CHECKING:
        return cast(list[MechanismNameType], mnames)
    return mnames

def get_sname_and_nums(pobj: PropsClassType,
                       pname: str,
                       optar: _OpTarget.OpTarget,
                       override_sname: ScopeNameType | None = None) -> \
                                        tuple[ScopeNameType, Union[AbsNumsType, RelNumsType]]:
    """
    Determine the scope and target CPU, die, or package number for a property operation.

    Args:
        pobj: The properties object (e.g., 'PStates', 'CStates').
        pname: Name of the property to query.
        optar: Operation target object containgin information about the target CPUs, dies, packages
               for an ongoing operation on property 'pname'.
        override_sname: Optional scope name to use instead of the property's default scope.

    Returns:
        A tuple of (scope_name, target_numbers) where scope_name is "CPU", "die", or "package",
        and target_numbers are the CPU/die/package numbers to operate on.
    """

    if override_sname is None:
        try:
            sname = pobj.get_sname(pname)
        except ErrorNotSupported:
            sname = "CPU"
    else:
        sname = override_sname

    if sname == "package":
        try:
            return "package", optar.get_packages()
        except ErrorNoTarget:
            sname = "CPU"

    if sname == "die":
        try:
            return "die", optar.get_dies()
        except ErrorNoTarget:
            sname = "CPU"

    return "CPU", optar.get_cpus()
