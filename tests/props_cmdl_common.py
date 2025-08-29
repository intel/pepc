#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Common functions for the P-state and C-state command-line options testing."""

# TODO: finish annotating.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import Generator, cast
from pepclibs.helperlibs import Trivial

if typing.TYPE_CHECKING:
    from pepclibs import CPUInfo, PStates
    from common import CommonTestParamsTypedDict

    class PropsCmdlTestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary with keys used by the common part of the command-line
        property tests.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            pobj: A 'PStates.PStates' object.
            cpus: List of CPU numbers available on the test platform.
            cores: A dictionary mapping package numbers to lists of core numbers in the package.
            modules: A dictionary mapping package numbers to lists of module numbers in the package.
            dies: A dictionary mapping package numbers to lists of die numbers in the package.
            packages: List of package numbers available on the test platform.
        """

        cpuinfo: CPUInfo.CPUInfo
        pobj: PStates.PStates
        cpus: list[int]
        cores: dict[int, list[int]]
        modules: dict[int, list[int]]
        dies: dict[int, list[int]]
        packages: list[int]

def extend_params(params: CommonTestParamsTypedDict,
                  pobj: PStates.PStates,
                  cpuinfo: CPUInfo.CPUInfo) -> PropsCmdlTestParamsTypedDict:
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
        params = cast(PropsCmdlTestParamsTypedDict, params)

    params["cpuinfo"] = cpuinfo
    params["pobj"] = pobj

    params["cpus"] = cpuinfo.get_cpus()
    params["packages"] = cpuinfo.get_packages()

    params["cores"] = {}
    params["modules"] = {}
    params["dies"] = {}

    for pkg in params["packages"]:
        params["cores"][pkg] = cpuinfo.get_package_cores(package=pkg)
        params["modules"][pkg] = cpuinfo.package_to_modules(package=pkg)
        params["dies"][pkg] = cpuinfo.get_package_dies(package=pkg, io_dies=False)

    return params

def get_mechanism_opts(params: PropsCmdlTestParamsTypedDict, allow_readonly: bool = True) -> Generator[str, None, None]:
    """
    Generate the '--mechanism <mechanism name>' command-line options for testing.

    Args:
        params: The test parameters dictionary.
        allow_readonly: Whether to include read-only mechanisms.

    Yields:
        str: Command-line option string for each mechanism.
    """

    for mname, minfo in params["pobj"].mechanisms.items():
        if not allow_readonly and not minfo["writable"]:
            continue
        yield f"--mechanism {mname}"

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
                f"--modules {pkg_modules_range}",
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
                "--dies all --modules all --cores all --cpus all",
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
