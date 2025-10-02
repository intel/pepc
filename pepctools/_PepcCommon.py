# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Misc. helpers shared between various 'pepc' commands.
"""

# TODO: finish adding type hints to this module.
from  __future__ import annotations # Remove when switching to Python 3.10+.

from pepclibs import CPUInfo, CPUModels
from pepclibs.helperlibs import Logging, Systemctl, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported, ErrorBadFormat
from pepctools._OpTarget import ErrorNoTarget, ErrorNoCPUTarget

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def check_tuned_presence(pman):
    """
    Check if the 'tuned' service is active, and if it is, print a warning message. The arguments are
    as follows.
      * pman - the process manager object that defines the target system..
    """

    try:
        with Systemctl.Systemctl(pman=pman) as systemctl:
            if systemctl.is_active("tuned"):
                _LOG.warning("the 'tuned' service is active%s! It may override the changes made by "
                             "'pepc'\nConsider having 'tuned' disabled while experimenting with "
                             "power management settings.", pman.hostmsg)
    except ErrorNotFound:
        pass
    except Error as err:
        _LOG.warning("failed to check for 'tuned' presence:\n%s", err.indent(2))

def parse_cpus_string(cpus_str):
    """
    Parse string of comma-separated numbers and number ranges, and return them as a list of
    integers. The arguments are as follows.
      * cpus_str - a string of comma-separated CPU numbers or number ranges to parse.
    """

    if cpus_str == "all":
        return cpus_str
    return Trivial.parse_int_list(cpus_str, dedup=True, what="CPU numbers")

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

def expand_subprops(pnames, props):
    """
    Expand list of property names 'pnames' with sub-property names. The arguments are as follows.
      * pnames - a collection of property names to expand.
      * props - the properties dictionary (e.g., 'CStates.PROPS').

    Receive a list of property names in 'pnames', and if any property in 'pnames' has a
    sub-property, insert the sub-property names into 'pnames' right after the main property name.
    Well, the sub-property names are inserted to a copy of 'pnames', and the resulting copy is
    returned.
    """

    expanded = []

    for pname in pnames:
        expanded.append(pname)

        spnames = []
        prop = props.get(pname)
        if prop:
            spnames = prop.get("subprops", [])

        for spname in spnames:
            expanded.append(spname)

    return expanded

def parse_mechanisms(mechanisms, pobj):
    """
    Parse and validate a string of comma-separated mechanism names for a properties object 'pobj'.
    Return the resulting mechanism names list. The arguments are as follows.
      * mechanisms - list of mechanism names to parse.
      * pobj - a "properties" object ('PStates', 'CStates', etc) to parse the mechanisms for.
    """

    mnames = Trivial.split_csv_line(mechanisms, dedup=True)
    for mname in mnames:
        if mname not in pobj.mechanisms:
            mnames = ", ".join(pobj.mechanisms)
            raise ErrorNotSupported(f"mechanism '{mname}' is not supported. The supported "
                                    f"mechanisms are: {mnames}")
    return mnames

def _get_sname_and_nums(pobj, pname, optar, override_sname=None):
    """
    Find out whether property 'pname' should be accessed on the per-CPU, per-die, or per-package
    manner. Return the corresponding scope name and CPU, die, or package numbers.
    """

    if override_sname is None:
        sname = pobj.get_sname(pname)
        if sname is None:
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

def get_prop_sname(pobj, pname, optar, mnames, override_sname=None):
    """
    Yield property value dictionaries ('pvinfo', refer to '_PropsClassBase.get_prop_cpu()')
    for property 'pname' taking into account its scope. The arguments are as follows.
      * pobj - a property object, such as 'PStates' or 'CStates'.
      * pname - name of the property to get values for.
      * optar - an '_OpTarget.OpTarget()' object specifying the CPUs, packages, etc to get property
                value dictionaries for.
      * mnames - list of mechanisms to use for getting the property (see
                 '_PropsClassBase.MECHANISMS').
      * override_sname - use this scope name for the 'pname' property, instead of using its real
                         scope name.
    """

    try:
        sname, nums = _get_sname_and_nums(pobj, pname, optar, override_sname=override_sname)
    except ErrorNoCPUTarget as err:
        name = pobj.props[pname]["name"]
        raise ErrorNoCPUTarget(f"impossible to get {name}:\n{err.indent(2)}") from err

    if sname == "CPU":
        yield from pobj.get_prop_cpus(pname, nums, mnames=mnames)
    elif sname == "die":
        yield from pobj.get_prop_dies(pname, nums, mnames=mnames)
    else:
        yield from pobj.get_prop_packages(pname, nums, mnames=mnames)

def set_prop_sname(pobj, pname, optar, val, mnames):
    """
    Set property 'pname' to value 'val'. The arguments are as follows.
      * pobj - a property object, such as 'PStates' or 'CStates'.
      * pname - name of the property to set.
      * optar - an '_OpTarget.OpTarget()' object specifying the CPUs, packages, etc to set property
                value dictionaries for.
      * val - the value to set the property to.
      * mnames - list of mechanisms to use for getting the property (see
                 '_PropsClassBase.MECHANISMS').
    """

    try:
        sname, nums = _get_sname_and_nums(pobj, pname, optar)
    except ErrorNoCPUTarget as err:
        name = pobj.props[pname]["name"]
        raise ErrorNoCPUTarget(f"impossible to set {name}:\n{err.indent(2)}") from err

    if sname == "CPU":
        return pobj.set_prop_cpus(pname, val, nums, mnames=mnames)

    if sname == "die":
        return pobj.set_prop_dies(pname, val, nums, mnames=mnames)

    return pobj.set_prop_packages(pname, val, nums, mnames=mnames)
