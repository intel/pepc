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
Common functions for P-state and C-state property tests, used at both the class level
('PStates.Pstates', 'CStates.CStates') and for command-line options testing.
"""

# TODO: finish annotating.
from  __future__ import annotations # Remove when switching to Python 3.10+.

from pepclibs.helperlibs.Exceptions import ErrorNotSupported

def _verify_after_set_per_cpu(pobj, pname, val, cpus):
    """
    Helper for 'set_and_verify(). Verify that the value was set to 'val', use the per-CPU interface.
    """

    cpus_set = set(cpus)

    for pvinfo in pobj.get_prop_cpus(pname, cpus=cpus):
        if pvinfo["val"] != val:
            cpus = ", ".join([str(cpu) for cpu in cpus])
            assert False, f"Set property '{pname}' to value '{val}' for the following CPUs: " \
                          f"{cpus}.\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for CPU {pvinfo['cpu']}."

        cpus_set.remove(pvinfo["cpu"])

    assert not cpus_set, f"Set property '{pname}' to value '{val}' for the following CPUs: " \
                         f"{cpus}.\n" \
                         f"Read back property '{pname}', but did not get value for the " \
                         f"following CPUs: {cpus_set}"

def _verify_after_set_per_die(pobj, pname, val, dies):
    """
    Helper for 'set_and_verify(). Verify that the value was set to 'val', use the per-die interface.
    """

    dies_left = {}
    for pkg, dies_list in dies.items():
        dies_left[pkg] = set(dies_list)

    for pvinfo in pobj.get_prop_dies(pname, dies=dies):
        pkg = pvinfo["package"]
        die = pvinfo["die"]
        if pvinfo["val"] != val:
            assert False, f"Set property '{pname}' to value '{val}' for the following package " \
                          f"and dies: {dies}\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for die {die} and package {pkg}."

        dies_left[pkg].remove(die)
        if not dies_left[pkg]:
            del dies_left[pkg]

    assert not dies_left, f"Set property '{pname}' to value '{val}' for the following packages " \
                          f"and dies: {dies}.\n" \
                          f"Read back property '{pname}', but did not get value for the " \
                          f"following packages and dies: {dies_left}"

def _verify_after_set_per_package(pobj, pname, val, packages):
    """
    Helper for 'set_and_verify(). Verify that the value was set to 'val', use the per-package
    interface.
    """

    packages_set = set(packages)

    for pvinfo in pobj.get_prop_packages(pname, packages=packages):
        if pvinfo["val"] != val:
            packages = ", ".join([str(pkg) for pkg in packages])
            assert False, f"Set property '{pname}' to value '{val}' for the following packages: " \
                          f"{packages}'.\n" \
                          f"Read back property '{pname}', got a different value " \
                          f"'{pvinfo['val']}' for package {pvinfo['package']}."

        packages_set.remove(pvinfo["package"])

    assert not packages_set, f"Set property '{pname}' to value '{val}' for the following CPUs: " \
                             f"{packages}'.\n" \
                             f"Read back property '{pname}', but did not get value for the " \
                             f"following CPUs: {packages_set}"

def set_and_verify(params, props_vals, cpu):
    """
    Set property values, read them back and verify. The arguments are as follows.
      * params - the test parameters dictionary.
      * props_vals - an iterator of '(pname, value)' tuples, where 'pname' is the property to set
                     and verify, and 'value' is the value to set the property to.
      * cpu - CPU numbers to set the property for.
    """

    siblings = {}
    pobj = params["pobj"]
    cpuinfo = params["cpuinfo"]

    tline = cpuinfo.get_tline_by_cpu(cpu)
    packages = (tline["package"],)
    dies = {tline["package"]: (tline["die"],)}

    for pname, val in props_vals:
        sname = pobj.get_sname(pname)
        if sname is None:
            continue

        if sname not in siblings:
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, sname=sname)
        cpus = siblings[sname]

        if sname == "die":
            # Set the property on per-die basis.
            try:
                pobj.set_prop_dies(pname, val, dies, siblings[sname])
            except ErrorNotSupported:
                continue
        elif sname == "package":
            # Set the property on per-package basis.
            try:
                pobj.set_prop_packages(pname, val, packages, siblings[sname])
            except ErrorNotSupported:
                continue
        else:
            # Set the property on per-CPU basis.
            try:
                pobj.set_prop_cpus(pname, val, cpus)
            except ErrorNotSupported:
                continue

        _verify_after_set_per_cpu(pobj, pname, val, cpus)

        if pobj.props[pname]["sname"] in ("die", "package", "global"):
            _verify_after_set_per_die(pobj, pname, val, dies)

        if pobj.props[pname]["sname"] in ("package", "global"):
            _verify_after_set_per_package(pobj, pname, val, packages)

def get_max_cpu_freq(params, cpu, numeric=False):
    """
    Return the maximum CPU or uncore frequency the Linux frequency driver accepts. The arguments are
    as follows.
      * params - test parameters.
      * cpu - CPU number to return the frequency for.
      * numeric - if 'False', it is OK to return non-numeric values, such as "max" or "min".
    """

    pobj = params["pobj"]

    maxfreq = None
    turbo_status = pobj.get_cpu_prop("turbo", cpu)["val"]
    freqs = pobj.get_cpu_prop("frequencies", cpu)["val"]

    if turbo_status == "on":
        # On some platforms running 'acpi-cpufreq' driver, the 'max_freq_limit' contains a value
        # that cannot be used for setting the max. frequency. So check the available frequencies
        # and take the max. available in that case.
        max_limit = pobj.get_cpu_prop("max_freq_limit", cpu)["val"]

        if freqs and max_limit:
            if max_limit == freqs[-1]:
                if numeric:
                    maxfreq = max_limit
                else:
                    maxfreq = "max"
            else:
                maxfreq = freqs[-1]
    elif freqs:
        maxfreq = freqs[-1]

    if not maxfreq:
        if numeric:
            maxfreq = pobj.get_cpu_prop("base_freq", cpu)["val"]
        else:
            maxfreq = "hfm"
    return maxfreq

def _verify_value_type(pname, ptype, val):
    """Verify that value 'val' matches the expected type 'ptype' of property 'pname'."""

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

def verify_props_value_type(params, cpu):
    """
    Check that 'get_prop_cpus()' returns values of correct type for all supported properties. The
    arguments are as follows.
      * params - test parameters.
      * cpu - CPU number to verify the values for.
    """

    pobj = params["pobj"]

    for pname in pobj.props:
        pvinfo = pobj.get_cpu_prop(pname, cpu)
        if pvinfo["val"] is None:
            continue

        _verify_value_type(pname, pobj.props[pname]["type"], pvinfo["val"])

def verify_get_props_mechanisms(params, cpu):
    """
    Verify that the 'mname' arguments of 'get_prop_cpus()' works correctly. The arguments are as
    follows.
      * params - test parameters.
      * cpu - CPU number to verify mechanisms for.
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

def verify_set_props_mechanisms_bool(params, cpu):
    """
    Verify that the 'mname' arguments of 'set_prop_cpus()' works correctly for boolean properties.
    The arguments are as follows.
      * params - test parameters.
      * cpu - CPU number to verify mechanisms for.
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

        all_mnames = [(mname,) for mname in pinfo["mnames"]]
        all_mnames += [("msr", "sysfs"), ("sysfs", " msr")]
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
