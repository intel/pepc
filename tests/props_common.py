#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""
Common functions for class-level P-state and C-state property tests ('PStates.Pstates',
'CStates.CStates').
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, cast, Iterable
    from common import CommonTestParamsTypedDict
    from pepclibs.CPUInfoTypes import ScopeNameType, AbsNumsType, RelNumsType
    from pepclibs.PropsTypes import PropertyTypeType, PropertyValueType, MechanismNameType
    from pepclibs import CPUInfo, PStates, CStates

    _PropsClassType = PStates.PStates | CStates.CStates

    class PropsTestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            pobj: A 'PStates.PStates' or 'CStates.CStates' object.
        """

        cpuinfo: CPUInfo.CPUInfo
        pobj: _PropsClassType

def get_enable_cache_param() -> Generator[bool, None, None]:
    """
    Yield boolean values to toggle the 'enable_cache' parameter for the 'PStates' or 'CStates'
    modules.

    Yields:
        bool: The next value for the 'enable_cache' parameter (True or False).
    """

    yield True
    yield False

def extend_params(params: CommonTestParamsTypedDict,
                  pobj: _PropsClassType,
                  cpuinfo: CPUInfo.CPUInfo) -> PropsTestParamsTypedDict:
    """
    Extend the common test parameters dictionary with additional keys required for running
    properties tests.

    Args:
        params: The common test parameters dictionary.
        pobj: The 'PStates.Pstates' object for the host under test.
        cpuinfo: The 'CPUInfo.CPUInfo' object for the host under test.

    Yields:
        A dictionary with test parameters.
    """

    if typing.TYPE_CHECKING:
        params = cast(PropsTestParamsTypedDict, params)

    params["cpuinfo"] = cpuinfo
    params["pobj"] = pobj

    return params

def _verify_after_set_per_cpu(pobj: _PropsClassType,
                              pname: str,
                              val: PropertyValueType,
                              cpus: AbsNumsType):
    """
    Verify that a property value was correctly set for specified CPUs.

    Args:
        pobj: The property object.
        pname: Name of the property to verify.
        val: Expected value of the property.
        cpus: List of CPU numbers to verify.
    """

    cpus_set = set(cpus)
    orig_val = val

    for pvinfo in pobj.get_prop_cpus(pname, cpus=cpus):
        val = orig_val

        if val in ("min", "max") and "freq" in pname:
            if "uncore" in pname:
                limit_pname = f"{val}_uncore_freq_limit"
            else:
                limit_pname = f"{val}_freq_limit"
            val = pobj.get_cpu_prop(limit_pname, pvinfo["cpu"])["val"]

        if pvinfo["val"] != val:
            cpus_str = ", ".join([str(cpu) for cpu in cpus])
            assert False, f"Set property '{pname}' to value '{val}' for the following CPUs: " \
                          f"{cpus_str}.\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for CPU {pvinfo['cpu']}."

        cpus_set.remove(pvinfo["cpu"])

    if not cpus_set:
        return

    cpus_str = ", ".join([str(cpu) for cpu in cpus])
    assert False, f"Set property '{pname}' to value '{val}' for the following CPUs: " \
                  f"{cpus_str}.\n" \
                  f"Read back property '{pname}', but did not get value for the " \
                  f"following CPUs: {cpus_set}"

def _verify_after_set_per_die(pobj: _PropsClassType,
                              cpuinfo: CPUInfo.CPUInfo,
                              pname: str,
                              val: PropertyValueType,
                              dies: RelNumsType):
    """
    Verify that a property value was correctly set for specified dies.

    Args:
        pobj: The property object.
        cpuinfo: A 'CPUInfo.CPUInfo' object.
        pname: Name of the property to verify.
        val: Expected value of the property.
        dies: Die numbers to verify for.
    """

    dies_left: dict[int, set[int]] = {}
    for pkg, dies_list in dies.items():
        dies_left[pkg] = set(dies_list)
    orig_val = val

    for pvinfo in pobj.get_prop_dies(pname, dies=dies):
        val = orig_val

        if val in ("min", "max") and "freq" in pname:
            if "uncore" in pname:
                limit_pname = f"{val}_uncore_freq_limit"
            else:
                limit_pname = f"{val}_freq_limit"
            val = pobj.get_die_prop(limit_pname, pvinfo["package"], pvinfo["die"])["val"]

        pkg = pvinfo["package"]
        die = pvinfo["die"]
        if pvinfo["val"] != val:
            dies_str = cpuinfo.dies_to_str(dies)
            assert False, f"Set property '{pname}' to value '{val}' for the following package " \
                          f"and dies: {dies_str}\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for die {die} and package {pkg}."

        dies_left[pkg].remove(die)
        if not dies_left[pkg]:
            del dies_left[pkg]

    if not dies_left:
        return

    dies_str = cpuinfo.dies_to_str(dies)
    dies_left_str = cpuinfo.dies_to_str({pkg: list(pkgdies) for pkg, pkgdies in dies_left.items()})
    assert False, f"Set property '{pname}' to value '{val}' for the following packages " \
                  f"and dies: {dies_str}.\n" \
                  f"Read back property '{pname}', but did not get value for the " \
                  f"following packages and dies: {dies_left_str}"

def _verify_after_set_per_package(pobj: _PropsClassType,
                                  pname: str,
                                  val: PropertyValueType,
                                  packages: AbsNumsType):
    """
    Verify that a property value was correctly set for specified packages.

    Args:
        pobj: The property object.
        pname: Name of the property to verify.
        val: Expected value of the property.
        packages: List of package numbers to verify.
    """

    packages_set = set(packages)

    for pvinfo in pobj.get_prop_packages(pname, packages=packages):
        if pvinfo["val"] != val:
            packages_str = ", ".join([str(pkg) for pkg in packages])
            assert False, f"Set property '{pname}' to value '{val}' for the following packages: " \
                          f"{packages_str}.\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for package {pvinfo['package']}."

        packages_set.remove(pvinfo["package"])

    if not packages_set:
        return

    packages_str = ", ".join([str(pkg) for pkg in packages])
    packages_set_str = ", ".join([str(pkg) for pkg in packages_set])
    assert False, f"Set property '{pname}' to value '{val}' for the following " \
                  f"packages: {packages_str}.\n" \
                  f"Read back property '{pname}', but did not get value for the " \
                  f"following packages: {packages_set_str}"

def set_and_verify(params: PropsTestParamsTypedDict,
                   props_vals: Iterable[tuple[str, PropertyValueType]],
                   cpu: int):
    """
    Set property values for a CPU, verify them by reading back, and check consistency across
    different scopes (CPU, die, package).

    Args:
        params: The test parameters dictionary.
        props_vals: Iterable of (property name, value) tuples to set and verify.
        cpu: CPU number to set properties for.
    """

    pobj = params["pobj"]
    cpuinfo = params["cpuinfo"]

    tline = cpuinfo.get_tline_by_cpu(cpu)
    dies = {tline["package"]: (tline["die"],)}
    packages = (tline["package"],)
    core_cpus = cpuinfo.cores_to_cpus(cores=(tline["core"],), packages=(tline["package"],))

    for pname, val in props_vals:
        sname = pobj.get_sname(pname)
        if sname is None:
            continue

        if sname == "CPU":
            try:
                pobj.set_prop_cpus(pname, val, (cpu,))
            except ErrorNotSupported:
                continue
        elif sname == "core":
            try:
                pobj.set_prop_cpus(pname, val, core_cpus)
            except ErrorNotSupported:
                continue
        elif sname == "die":
            try:
                pobj.set_prop_dies(pname, val, dies)
            except ErrorNotSupported:
                continue
        elif sname == "package":
            try:
                pobj.set_prop_packages(pname, val, packages)
            except ErrorNotSupported:
                continue
        elif sname == "global":
            try:
                pobj.set_prop_packages(pname, val, cpuinfo.get_packages())
            except ErrorNotSupported:
                continue
        else:
            assert False, f"Unknown scope name '{sname}'."

        _verify_after_set_per_cpu(pobj, pname, val, (cpu,))

        if pobj.props[pname]["sname"] in {"core", "die", "package", "global"}:
            _verify_after_set_per_cpu(pobj, pname, val, core_cpus)

        if pobj.props[pname]["sname"] in {"die", "package", "global"}:
            _verify_after_set_per_die(pobj, cpuinfo, pname, val, dies)

        if pobj.props[pname]["sname"] in ("package", "global"):
            _verify_after_set_per_package(pobj, pname, val, packages)

def _verify_value_type(pname: str, ptype: PropertyTypeType, val: PropertyValueType):
    """
    Verify that a property value matches the expected type.

    Args:
        pname: Name of the property being checked.
        ptype: Expected type of the property as a string.
        val: Value to verify against the expected type.
    """

    if ptype == "int":
        ret = isinstance(val, int)
    elif ptype == "str":
        ret = isinstance(val, str)
    elif ptype == "float":
        ret = isinstance(val, float)
    elif ptype == "list[str]":
        ret = isinstance(val, list) and all(isinstance(item, str) for item in val)
    elif ptype == "list[int]":
        ret = isinstance(val, list) and all(isinstance(item, int) for item in val)
    elif ptype == "bool":
        ret = val in ("on", "off")
    elif ptype == "dict[str,str]":
        ret = isinstance(val, dict) and \
              all(isinstance(key, str) and isinstance(val, str) for key, val in val.items())
    else:
        assert False, f"Unknown '{pname}' property datatype: {ptype}."

    assert ret, f"Property '{pname}' value '{val}' has the wrong datatype. Should be " \
                f"'{ptype}' but returns type '{type(val)}'."

def verify_get_all_props(params: PropsTestParamsTypedDict, cpu: int):
    """
    Verify 'get_cpu_prop()' works for all available properties.

    Check all mechanisms, verify the type of the returned property value.

    Args:
        params: The test parameters dictionary.
        cpu: CPU number to verify.
    """

    pobj = params["pobj"]

    for pname, pinfo in pobj.props.items():
        # Test all mechanisms one by one.
        for mname in pinfo["mnames"]:
            try:
                pvinfo = pobj.get_cpu_prop(pname, cpu, mnames=(mname,))
            except ErrorNotSupported:
                pass
            else:
                assert pvinfo["mname"] == mname, \
                       f"Bad mechanism name returned by" \
                       f"'get_cpu_props(\"{pname}\", {cpu}, mnames=(\"{mname}\",))'.\n" \
                       f"Expected '{mname}', got '{pvinfo['mname']}'."

        pvinfo = pobj.get_cpu_prop(pname, cpu)
        if pvinfo["val"] is not None:
            _verify_value_type(pname, pobj.props[pname]["type"], pvinfo["val"])

        # Test all mechanisms in reverse order.
        reverse_mnames = list(pinfo["mnames"])
        reverse_mnames.reverse()
        pvinfo = pobj.get_cpu_prop(pname, cpu, mnames=reverse_mnames)
        assert pvinfo["mname"] in reverse_mnames, \
               f"Bad mechanism name returned by" \
               f"'get_cpu_props(\"{pname}\", {cpu}, mnames=(\"{reverse_mnames}\",))'.\n" \
               f"Expected one of '{reverse_mnames}', got '{pvinfo['mname']}'."

        # Read using the claimed mechanisms and compare.
        mnames = (pvinfo["mname"],)
        pvinfo1 = pobj.get_cpu_prop(pname, cpu, mnames=mnames)
        assert pvinfo1["mname"] == pvinfo["mname"], \
               f"Bad mechanism name returned by" \
               f"'get_cpu_props(\"{pname}\", {cpu}, mnames=(\"{mnames}\",))'\n" \
               f"Expected '{pvinfo['mname']}', got '{pvinfo1['mname']}'."

def verify_set_bool_props(params: PropsTestParamsTypedDict, cpu: int):
    """
    Verify that 'set_prop_cpus()' works correctly for all available boolean properties with
    different mechanisms.

    Args:
        params: The test parameters dictionary.
        cpu: CPU number to verify.
    """

    siblings = {}
    cpuinfo = params["cpuinfo"]
    pobj = params["pobj"]

    for pname, pinfo in pobj.props.items():
        if not pinfo["writable"]:
            continue
        if not pinfo["type"] == "bool":
            continue

        try:
            pvinfo = pobj.get_cpu_prop(pname, cpu)
        except ErrorNotSupported:
            continue

        if pvinfo["val"] == "on":
            val = "off"
        elif pvinfo["val"] == "off":
            val = "on"
        else:
            continue

        sname = pobj.get_sname(pname)
        if sname is None:
            continue

        if sname not in siblings:
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, sname=sname)
        cpus = siblings[sname]

        all_mnames: list[tuple[MechanismNameType, ...]] = [(mname,) for mname in pinfo["mnames"]]
        if len(pinfo["mnames"]) > 1:
            all_mnames += [(pinfo["mnames"][0], pinfo["mnames"][-1]),
                           (pinfo["mnames"][-1], pinfo["mnames"][0])]
        for mnames in all_mnames:
            try:
                mname = pobj.set_prop_cpus(pname, val, cpus, mnames=mnames)
            except ErrorNotSupported:
                continue

            assert mname in mnames, f"Set property '{pname}' to value '{val}' on CPU {cpu} " \
                                    f"using mechanisms '{','.join(mnames)}', but " \
                                    f"'set_prop_cpus()' return machanism name '{mname}'."

            pvinfo1 = pobj.get_cpu_prop(pname, cpu)
            assert pvinfo1["val"] == val, f"Set property '{pname}' to value '{val}' on " \
                                          f"CPU {cpu}, but read back value '{pvinfo1['val']}'."

            pobj.set_prop_cpus(pname, pvinfo["val"], cpus, mnames=mnames)
