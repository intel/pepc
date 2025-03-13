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

from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

def is_prop_supported(pname, cpu0_pinfo):
    """
    Return 'True' or 'False' depending on if property 'pname' is supported on the system.

    The arguments are as follows.
      * pname - name of the property.
      * cpu0_pinfo - a properties dictionary.
    """

    return cpu0_pinfo[pname] is not None

def get_good_cpu_opts(params, sname="package"):
    """
    Return a list of good options that specify CPU numbers ('--cpus', '--packages', etc). The
    arguments are as follows.
      * params - test parameters.
      * sname - scope name to get CPU numbers for.
    """

    def _get_package_opts(params, pkg):
        """Return package scope options for package 'pkg'."""

        pkg = params["packages"][0]
        pkg_cores_range = Trivial.rangify(params["cores"][pkg])
        pkg_modules_range = Trivial.rangify(params["modules"][pkg])
        pkg_dies_range = Trivial.rangify(params["dies"][pkg])
        opts = [f"--packages {pkg} --cpus all",
                f"--packages {pkg} --modules all",
                f"--modules {pkg_modules_range}",
                f"--packages {pkg} --dies all",
                f"--packages {pkg} --cores all",
                f"--packages {pkg} --cores {pkg_cores_range}",
                f"--packages {pkg} --dies {pkg_dies_range}",
                f"--packages {pkg}-{params['packages'][-1]}"]
        return opts

    def _get_die_opts(params, pkg):
        """Return die scope options for package 'pkg'."""

        first_die = params["dies"][pkg][0]
        last_die = params["dies"][pkg][-1]

        opts = [f"--package {pkg} --dies {first_die}", f"--package {pkg} --dies all"]

        if first_die != last_die:
            opts.append(f"--package {pkg} --dies {last_die}")
        else:
            return opts

        if len(params["dies"][pkg]) > 1:
            pkg_dies_range_partial = Trivial.rangify(params["dies"][pkg][1:])
            opts.append(f"--packages {pkg} --dies {pkg_dies_range_partial}")
            pkg_dies_range_partial = Trivial.rangify(params["dies"][pkg][:-1])
            opts.append(f"--packages {pkg} --dies {pkg_dies_range_partial}")

        return opts

    def _get_module_opts(params, pkg):
        """Return module scope options for package 'pkg'."""

        first_module = params["modules"][pkg][0]
        last_module = params["modules"][pkg][-1]

        opts = [f"--package {pkg} --modules {first_module}", f"--package {pkg} --modules all"]

        if first_module != last_module:
            opts.append(f"--package {pkg} --modules {last_module}")
        else:
            return opts

        if len(params["modules"][pkg]) > 1:
            pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][1:])
            opts.append(f"--packages {pkg} --modules {pkg_modules_range_part}")
            pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][:-1])
            opts.append(f"--packages {pkg} --modules {pkg_modules_range_part}")

            if len(params["packages"]) > 1:
                pkgs_range_part = Trivial.rangify(params["packages"][1:])
                opts.append(f"--packages {pkgs_range_part} --modules {first_module}")
                pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][1:])
                opts.append(f"--packages {pkgs_range_part} --modules {pkg_modules_range_part}")

        return opts

    if sname == "global":
        opts = ["",
                "--cpus all",
                "--cores all",
                "--modules all",
                "--dies all",
                "--cores all --cpus all",
                "--modules all --cores all",
                "--dies all --modules all",
                "--dies all --cores all",
                "--dies all --modules all --cores all --cpus all",
                "--packages all",
                "--packages all --cpus all",
                "--packages all --cores all",
                "--packages all --modules all",
                "--packages all --dies all",
                "--packages all --dies all --cores all",
                f"--cpus  0-{params['cpus'][-1]}"]
        return opts

    if sname == "package":
        opts = _get_package_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            opts += _get_package_opts(params, params["packages"][-1])
        return opts

    if sname == "die":
        opts = _get_die_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            opts += _get_die_opts(params, params["packages"][-1])
        return opts

    if sname == "module":
        opts = _get_module_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            opts += _get_module_opts(params, params["packages"][-1])
        return opts

    if sname == "CPU":
        opts = ["--core-siblings 0", "--module-siblings 0"]

        cpus_per_pkg = len(params["cpus"]) // len(params["packages"])
        cores_per_pkg = len(params["cores"][0])
        modules_per_pkg = len(params["modules"][0])

        cpus_per_core = cpus_per_pkg // cores_per_pkg
        if cpus_per_core > 1:
            siblings = ",".join([str(i) for i in range(0, cpus_per_core + 1)])
            opts.append(f"--core-siblings {siblings}")
            siblings = ",".join([str(i) for i in range(1, cpus_per_core)])
            opts.append(f"--core-siblings {siblings}")

        cpus_per_module = cpus_per_pkg // modules_per_pkg
        if cpus_per_module > 1:
            siblings = ",".join([str(i) for i in range(0, cpus_per_module + 1)])
            opts.append(f"--module-siblings {siblings}")
            siblings = ",".join([str(i) for i in range(1, cpus_per_module)])
            opts.append(f"--module-siblings {siblings}")

        return opts

    assert False, f"BUG: bad scope name {sname}"

def get_bad_cpu_opts(params):
    """
    Return bad target CPU specification options. The arguments are as follows.
      * params - test parameters.
    """

    opts = [f"--cpus {params['cpus'][-1] + 1}",
            f"--packages 0 --cores {params['cores'][0][-1] + 1}",
            f"--packages {params['packages'][-1] + 1}"]

    # Option '--cores' must be used with '--packages', except for 1-package systems, or single
    # socket system.
    if len(params["packages"]) > 1:
        pkg0_core_ranges = Trivial.rangify(params["cores"][0])
        opts += [f"--cores {pkg0_core_ranges}"]

    return opts

def get_mechanism_opts(params, allow_readonly=True):
    """
    Return a list of various variants of the '--mechanism' option.
    The arguments are as follows.
      * params - test parameters.
      * allow_readonly - 'True' if including read-only mechanisms is OK.
    """

    opts = []
    mnames = params["pobj"].mechanisms
    if not allow_readonly:
        mnames = [mname for mname, minfo in mnames.items() if minfo["writable"]]

    for mname in mnames:
        opts.append(f"--mechanism {mname}")

    opts += ["--mechanism msr,sysfs", "--mechanism sysfs,msr"]
    return opts

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
                          f"following prackages and dies: {dies_left}"

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

    levels = cpuinfo.get_cpu_levels(cpu)
    packages = (levels["package"],)
    dies = {levels["package"]: (levels["die"],)}

    for pname, val in props_vals:
        sname = pobj.get_sname(pname)
        if sname is None:
            continue

        if sname not in siblings:
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, level=sname)
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
            siblings[sname] = cpuinfo.get_cpu_siblings(cpu, level=sname)
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
