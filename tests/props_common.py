#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Common functions for the property class tests (e.g., 'CStates', 'PStates')."""

from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

def is_prop_supported(pname, cpu0_pinfo):
    """
    Return 'True' or 'False' depending on if property 'pname' is supported on the system.

    The arguments are as follows.
      * pname - name of the property.
      * cpu0_pinfo - a properties dictionary.
    """

    return cpu0_pinfo[pname] is not None

def get_good_cpunum_opts(params, sname="package"):
    """
    Return a list of good options that specify CPU numbers (--cpus, --packages, etc).
    """

    if sname == "global":
        opts = ["",
                "--cpus all",
                "--packages all",
                f"--cpus  0-{params['cpus'][-1]}"]
        return opts

    pkg0_core_ranges = Human.rangify(params['cores'][0])
    opts = ["",
            "--packages 0 --cpus all",
            f"--cpus 0-{params['cpus'][-1]}",
            "--packages 0 --cores all",
            f"--packages 0 --cores {pkg0_core_ranges}",
            "--packages all",
            f"--packages 0-{params['packages'][-1]}"]

    if len(params["packages"]) == 1:
        opts.append(f"--cores {pkg0_core_ranges}")

    return opts

def get_bad_cpunum_opts(params):
    """
    Return a dictionary of good and bad options that specify CPU numbers (--cpus, --packages, etc).
    """

    opts = [f"--cpus {params['cpus'][-1] + 1}",
            f"--packages 0 --cores {params['cores'][0][-1] + 1}",
            f"--packages {params['packages'][-1] + 1}"]

    # Option '--cores' must be used with '--packages', except for 1-package systems, or single
    # socket system.
    if len(params["packages"]) > 1:
        pkg0_core_ranges = Human.rangify(params['cores'][0])
        opts += [f"--cores {pkg0_core_ranges}"]

    return opts

def get_mechanism_opts(params, allow_readonly=True):
    """Return a list of various variants of the '--mecahnism' option."""

    opts = []
    mnames = params["pobj"].mechanisms
    if not allow_readonly:
        mnames = [mname for mname, minfo in mnames.items() if minfo["writable"]]

    for mname in mnames:
        opts.append(f"--mechanism {mname}")

    opts += ["--mechanism msr,sysfs",
             "--mechanism sysfs,msr"]
    return opts

def set_and_verify(params, props_vals, cpu):
    """
    Set property values, read them back and verify. The arguments are as follows.
      * params - the test parameters dictionary.
      * props_val - an iterator of '(pname, value)' tuples, where 'pname' is the property to set and
                    verify, and 'value' is the value to set the property to.
      * cpu - CPU numbers to set the property for.
    """

    siblings = {}
    pobj = params["pobj"]
    cpuinfo = params["cpuinfo"]

    for pname, val in props_vals:
        sname = pobj.get_sname(pname)
        if sname is None:
            continue

        if sname not in siblings:
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, level=sname)
        cpus = siblings[sname]

        try:
            pobj.set_prop(pname, val, cpus)
        except ErrorNotSupported:
            continue

        for pvinfo in pobj.get_prop(pname, cpus):
            if pvinfo["val"] != val:
                cpus = ", ".join(cpus)
                assert False, f"Set property '{pname}' to value '{val} for CPU the following " \
                              f"CPUs: {cpus}'.\n" \
                              f"Read back property '{pname}', got a different value " \
                              f"'{pvinfo['val']}' for CPU {pvinfo['cpu']}."

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
    elif ptype == "bool":
        ret = val in ("on", "off")
    elif ptype == "dict[str,str]":
        ret = isinstance(val, dict) and all(isinstance(key, str) and isinstance(val, str) \
                                              for key, val in val.items())
    else:
        assert False, f"Unknown '{pname}' property datatype: {ptype}."

    assert ret, f"Property '{pname}' value '{val}' has the wrong datatype. Should be " \
                f"'{ptype}' but returns type '{type(val)}'."

def verify_props_value_type(params, cpu):
    """
    Check that 'get_prop()' returns values of correct type for all supported properties.
    """

    pobj = params["pobj"]

    for pname in pobj.props:
        pvinfo = pobj.get_cpu_prop(pname, cpu)
        if pvinfo["val"] is None:
            continue

        _verify_value_type(pname, pobj.props[pname]["type"], pvinfo["val"])

def verify_get_props_mechanisms(params, cpu):
    """Verify that the 'mname' arguments of 'get_prop()' works correctly."""

    pobj = params["pobj"]

    for pname, pinfo in pobj.props.items():
        # Test all mechanisms one by one.
        for mname in pinfo["mnames"]:
            try:
                pvinfo = pobj.get_cpu_prop(pname, cpu, mnames=(mname,))
            except ErrorNotSupported:
                pass

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
    """Verify that the 'mname' arguments of 'set_prop()' works correctly for boolean properties."""

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
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, level=sname)
        cpus = siblings[sname]

        all_mnames = [(mname,) for mname in pinfo["mnames"]]
        all_mnames += [("msr","sysfs"), ("sysfs" ," msr")]
        for mnames in all_mnames:
            try:
                mname = pobj.set_prop(pname, val, cpus, mnames=mnames)
            except ErrorNotSupported:
                continue

            assert mname in mnames, f"Set property '{pname}' to value '{val}' on CPU {cpu} " \
                                    f"using mechanisms '{','.join(mnames)}', but 'set_prop()' " \
                                    f"return machanism name '{mname}'."

            pvinfo1 = pobj.get_cpu_prop(pname, cpu)
            assert pvinfo1["val"] == val, f"Set property '{pname}' to value '{val}' on " \
                                          f"CPU {cpu}, but read back value '{pvinfo1['val']}'."

            pobj.set_prop(pname, pvinfo["val"], cpus, mnames=mnames)
