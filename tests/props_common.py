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

from pepclibs.helperlibs.Exceptions import ErrorNotSupported

def is_prop_supported(pname, cpu0_pinfo):
    """
    Return 'True' or 'False' depending on if property 'pname' is supported on the system.

    The arguments are as follows.
      * pname - name of the property.
      * cpu0_pinfo - a properties dictionary.
    """

    return cpu0_pinfo[pname] is not None

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
        assert False, f"Unknown '{pname}' property datatype: {ptype}"

    assert ret, f"Property '{pname}' value '{val}' has the wrong datatype. Should be " \
                f"'{ptype}' but returns type '{type(val)}'"

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
