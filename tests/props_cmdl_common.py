#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Common functions for the C-state, P-state and uncore command-line option tets."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
from pepclibs.helperlibs import Trivial, TestRunner
from pepctool import _Pepc

if typing.TYPE_CHECKING:
    from typing import Generator, Mapping
    from pepclibs import CPUInfo, CStates, PStates, Uncore
    from common import CommonTestParamsTypedDict
    from pepclibs.CPUInfoTypes import ScopeNameType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.helperlibs.Exceptions import ExceptionType

    _PropsClassType = CStates.CStates | PStates.PStates | Uncore.Uncore

    class PropsCmdlTestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary with keys used by the common part of the command-line
        property tests.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            pobj: A property object.
            cpus: List of CPU numbers available on the test platform.
            cores: A dictionary mapping package numbers to lists of core numbers in the package.
            modules: A dictionary mapping package numbers to lists of module numbers in the package.
            dies: A dictionary mapping package numbers to lists of die numbers in the package.
            packages: List of package numbers available on the test platform.
        """

        cpuinfo: CPUInfo.CPUInfo
        pobj: _PropsClassType
        cpus: list[int]
        cores: dict[int, list[int]]
        modules: dict[int, list[int]]
        dies: dict[int, list[int]]
        packages: list[int]

def extend_params(params: CommonTestParamsTypedDict,
                  pobj: _PropsClassType,
                  cpuinfo: CPUInfo.CPUInfo) -> PropsCmdlTestParamsTypedDict:
    """
    Extend the common test parameters dictionary with additional keys required for running
    properties tests.

    Args:
        params: The common test parameters dictionary.
        pobj: A property object for the host under test.
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

def run_pepc(arguments: str,
             pman: ProcessManagerType,
             exp_exc: ExceptionType | None = None,
             ignore: Mapping[ExceptionType, str] | None = None):
    """
    Execute the 'pepc' command and validate its outcome.

    Args:
        arguments: The command-line arguments to execute the 'pepc' command with, e.g.,
                   'pstate info --cpus 0-43'.
        pman: The process manager object that specifies the host to run the command on.
        exp_exc: The expected exception. If set, the test fails if the command does not raise the
                 expected exception. By default, any exception is considered a failure.
        ignore: A dictionary mapping error types to command argument strings. Can be used for
                ignoring certain exceptions.

    Raises:
        AssertionError: If the command execution does not match the expected outcome.
    """

    TestRunner.run_tool(_Pepc, _Pepc.TOOLNAME, arguments, pman=pman, exp_exc=exp_exc,
                        ignore=cast(dict[type[Exception], str], ignore))

def get_mechanism_opts(params: PropsCmdlTestParamsTypedDict,
                       allow_readonly: bool = True) -> Generator[str, None, None]:
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

def get_good_optarget_opts(params: PropsCmdlTestParamsTypedDict,
                           sname: ScopeNameType = "package") -> Generator[str, None, None]:
    """
    Yield valid command-line options for specifying the operation target options, such as '--cpus',
    '--packages', etc.

    Args:
        params: The test parameters dictionary.
        sname: Scope name indicating the topology level for which to generate options.

    Yields:
        Valid operation target command-line options for the specified scope.
    """

    def _get_package_opts(params, pkg):
        """
        Yield operation target command-line options for the package scope.

        Args:
            params: The test parameters dictionary.
            pkg: The package number for which to generate options.

        Yields:
            str: Package scope command-line option string for the specified package.
        """

        pkg = params["packages"][0]
        opts = [f"--packages {pkg}",
                f"--packages {pkg}-{params['packages'][-1]}"]

        yield from opts

    def _get_die_opts(params: PropsCmdlTestParamsTypedDict, pkg: int) -> Generator[str, None, None]:
        """
        Yield operation target command-line options for the die scope.

        Args:
            params: The test parameters dictionary.
            pkg: The package number for which to generate die options.

        Yields:
            str: Command-line option string for the specified die within the package.
        """

        first_die = params["dies"][pkg][0]
        last_die = params["dies"][pkg][-1]

        yield from [f"--packages {pkg} --dies {first_die}", f"--package {pkg} --dies all"]

        if first_die != last_die:
            yield f"--packages {pkg} --dies {last_die}"

    def _get_module_opts(params: PropsCmdlTestParamsTypedDict,
                         pkg: int) -> Generator[str, None, None]:
        """
        Yield operation target command-line options for the module scope.

        Args:
            params: The test parameters dictionary.
            pkg: The package number for which to generate module options.

        Yields:
            str: Command-line option string for the specified module within the package.
        """

        first_module = params["modules"][pkg][0]
        last_module = params["modules"][pkg][-1]

        yield from [f"--package {pkg} --modules {first_module}", f"--package {pkg} --modules all"]

        if first_module != last_module:
            yield f"--package {pkg} --modules {last_module}"
        else:
            return

        if len(params["modules"][pkg]) > 1:
            pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][1:])
            yield f"--packages {pkg} --modules {pkg_modules_range_part}"
            pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][:-1])
            yield f"--packages {pkg} --modules {pkg_modules_range_part}"

            if len(params["packages"]) > 1:
                pkgs_range_part = Trivial.rangify(params["packages"][1:])
                yield f"--packages {pkgs_range_part} --modules {first_module}"
                pkg_modules_range_part = Trivial.rangify(params["modules"][pkg][1:])
                yield f"--packages {pkgs_range_part} --modules {pkg_modules_range_part}"

    if sname == "global":
        opts = ["",
                "--packages all --dies all --modules all --cores all",
                f"--cpus  0-{params['cpus'][-1]}"]
        yield from opts
        return

    if sname == "package":
        yield from _get_package_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            yield from _get_package_opts(params, params["packages"][-1])
        return

    if sname == "die":
        yield from _get_die_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            yield from _get_die_opts(params, params["packages"][-1])
        return

    if sname == "module":
        yield from _get_module_opts(params, params["packages"][0])
        if len(params["packages"]) > 1:
            yield from _get_module_opts(params, params["packages"][-1])
        return

    assert sname == "CPU", f"BUG: Bad scope name {sname}"

    yield from ["--core-siblings 0", "--module-siblings 0"]

    cpus_per_pkg = len(params["cpus"]) // len(params["packages"])
    cores_per_pkg = len(params["cores"][0])
    modules_per_pkg = len(params["modules"][0])

    cpus_per_core = cpus_per_pkg // cores_per_pkg
    if cpus_per_core > 1:
        siblings = ",".join([str(i) for i in range(0, cpus_per_core + 1)])
        yield f"--core-siblings {siblings}"
        siblings = ",".join([str(i) for i in range(1, cpus_per_core)])
        yield f"--core-siblings {siblings}"

    cpus_per_module = cpus_per_pkg // modules_per_pkg
    if cpus_per_module > 1:
        siblings = ",".join([str(i) for i in range(0, cpus_per_module + 1)])
        yield f"--module-siblings {siblings}"
        siblings = ",".join([str(i) for i in range(1, cpus_per_module)])
        yield f"--module-siblings {siblings}"

def get_bad_optarget_opts(params: PropsCmdlTestParamsTypedDict) -> Generator[str, None, None]:
    """
    Yield invalid command-line options for specifying the operation target options.

    Args:
        params: The test parameters dictionary.

    Yields:
        Valid operation target command-line options.
    """

    yield from [f"--cpus {params['cpus'][-1] + 1}",
                f"--packages 0 --cores {params['cores'][0][-1] + 1}",
                f"--packages {params['packages'][-1] + 1}"]

    # The '--cores' option must be used together with '--packages', except on single-package or
    # single-socket systems.
    if len(params["packages"]) > 1:
        pkg0_core_ranges = Trivial.rangify(params["cores"][0])
        yield f"--cores {pkg0_core_ranges}"
