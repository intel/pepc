# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains common bits and pieces shared between different modules in this package. Not
supposed to be imported directly by users.
"""

from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import Error

def validate_prop_scope(prop, cpus, cpuinfo, hostmsg):
    """
    Make sure that CPUs in 'cpus' match the scope of a property described by 'prop'. For example, if
    the property has "package" scope, 'cpus' should include all CPUs in one or more packages.
    """

    scope = prop["scope"]

    if scope not in {"global", "package", "die", "core", "CPU"}:
        raise Error(f"BUG: unsupported scope \"{scope}\"")

    if scope == "CPU":
        return

    if scope == "global":
        all_cpus = set(cpuinfo.get_cpus())

        if all_cpus.issubset(cpus):
            return

        name = Human.untitle(prop["name"])
        missing_cpus = all_cpus - set(cpus)
        raise Error(f"{name} has {scope} scope, so the list of CPUs must include all CPUs.\n"
                    f"However, the following CPUs are missing from the list: {missing_cpus}")

    _, rem_cpus = getattr(cpuinfo, f"cpus_div_{scope}s")(cpus)
    if not rem_cpus:
        return

    mapping = ""
    for pkg in cpuinfo.get_packages():
        pkg_cpus = cpuinfo.package_to_cpus(pkg)
        pkg_cpus_str = Human.rangify(pkg_cpus)
        mapping += f"\n  * package {pkg}: CPUs: {pkg_cpus_str}"

        if scope in {"core", "die"}:
            # Build the cores or dies to packages map, in order to make the error message more
            # helpful. We use "core" in variable names, but in case of the "die" scope, they
            # actually mean "die".

            pkg_cores = getattr(cpuinfo, f"package_to_{scope}s")(pkg)
            pkg_cores_str = Human.rangify(pkg_cores)
            mapping += f"\n               {scope}s: {pkg_cores_str}"

            # Build the cores to CPUs mapping string.
            clist = []
            for core in pkg_cores:
                if scope == "core":
                    cpus = cpuinfo.cores_to_cpus(cores=(core,), packages=(pkg,))
                else:
                    cpus = cpuinfo.dies_to_cpus(dies=(core,), packages=(pkg,))
                cpus_str = Human.rangify(cpus)
                clist.append(f"{core}:{cpus_str}")

            # The core/die->CPU mapping may be very long, wrap it to 100 symbols.
            import textwrap # pylint: disable=import-outside-toplevel

            prefix = f"               {scope}s to CPUs: "
            indent = " " * len(prefix)
            clist_wrapped = textwrap.wrap(", ".join(clist), width=100,
                                          initial_indent=prefix, subsequent_indent=indent)
            clist_str = "\n".join(clist_wrapped)

            mapping += f"\n{clist_str}"

    name = Human.untitle(prop["name"])
    rem_cpus_str = Human.rangify(rem_cpus)

    if scope == "core":
        mapping_name = "relation between CPUs, cores, and packages"
    elif scope == "die":
        mapping_name = "relation between CPUs, dies, and packages"
    else:
        mapping_name = "relation between CPUs and packages"

    errmsg = f"{name} has {scope} scope, so the list of CPUs must include all CPUs " \
             f"in one or multiple {scope}s.\n" \
             f"However, the following CPUs do not comprise full {scope}(s): {rem_cpus_str}\n" \
             f"Here is the {mapping_name}{hostmsg}:{mapping}"

    raise Error(errmsg)
