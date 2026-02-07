# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Common functions for pepc command-line tools.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo, CPUModels
from pepclibs.helperlibs import Logging, Systemctl, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
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

def override_cpu_model(cpuinfo: CPUInfo.CPUInfo, user_vfm: str):
    """
    Override the CPU model in the provided 'CPUInfo' object.

    Args:
        cpuinfo: The 'CPUInfo' object to modify CPU model in.
        user_vfm: The user-provided CPU model specification. It can be either and integer VFM code
                  or a string in the format '[<Vendor>]:<Family>:<Model>'.

    Raises:
        ErrorBadFormat: If the provided 'user_vfm' string is not in the correct format or contains
                        invalid values.
        ErrorNotSupported: If the specified CPU vendor is not supported.
    """

    mdict = CPUModels.parse_user_vfm(user_vfm)

    proc_cpuinfo = cpuinfo.get_proc_cpuinfo()
    proc_cpuinfo["vendor_name"] = mdict["vendor_name"]
    proc_cpuinfo["vendor"] = mdict["vendor"]
    proc_cpuinfo["family"] = mdict["family"]
    proc_cpuinfo["model"] = mdict["model"]
    proc_cpuinfo["vfm"] = CPUModels.make_vfm(mdict["vendor"], mdict["family"],
                                                     mdict["model"])
    cpuinfo.cpudescr += f" (overridden with {user_vfm})"

    _LOG.notice("Overriding CPU model with '%s', resulting VFM is '%s:%s:%s",
                user_vfm, mdict["vendor_name"], mdict["family"], mdict["model"])

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
        optar: Operation target object containing information about the target CPUs, dies, packages
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

    if sname == "global":
        return "global", optar.get_cpus()

    if sname == "package":
        try:
            return "package", optar.get_packages()
        except ErrorNoTarget:
            sname = "CPU"

    if sname == "die":
        try:
            return "die", optar.get_all_dies()
        except ErrorNoTarget:
            sname = "CPU"

    return "CPU", optar.get_cpus()
