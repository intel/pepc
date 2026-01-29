#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""Test the public methods of the 'CPUInfo' module."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import random
import pytest
from tests import common
from pepclibs import CPUInfo, CPUOnline
from pepclibs.helperlibs import Trivial

if typing.TYPE_CHECKING:
    from typing import Generator, cast, TypedDict
    from tests.common import CommonTestParamsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

    class _ExpectedTopology(TypedDict, total=False):
        """
        Typed dictionary for expected CPU topology structure used in tests.

        Attributes:
            cpus: List of CPU numbers.
            cores: Dictionary mapping package numbers to core numbers.
            modules: List of module numbers.
            dies: Dictionary mapping package numbers to compute die numbers.
            packages: List of package numbers.
        """

        cpus: AbsNumsType
        cores: RelNumsType
        modules: AbsNumsType
        dies: RelNumsType
        packages: AbsNumsType

# A unique object used in '_run_method()' for ignoring a method's return value by default.
_IGNORE = object()

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman:
        params = common.build_params(pman)
        yield params

def _get_scope_nums(sname: ScopeNameType,
                    cpuinfo: CPUInfo.CPUInfo,
                    order: ScopeNameType | None = None) -> AbsNumsType | RelNumsType:
    """
    Execute the 'get_<sname>s()' (e.g., 'get_cores()') method and return the result.

    Args:
        sname: Name of the CPU scope (e.g., "package", "core", "die") to run the method for.
        cpuinfo: The 'CPUInfo' object under test.
        order: The order to pass down to the 'get_<sname>s()' method. The 'sname' value is used
               as the order by default.

    Returns:
        List of CPU/core/etc (<sname>) numbers as returned by the corresponding 'get_<sname>s()'
        method.
    """

    if order is None:
        order = sname

    get_method = getattr(cpuinfo, f"get_{sname}s".lower(), None)

    assert get_method, f"BUG: 'get_{sname}s()' does not exist"

    result = get_method(order=order)

    return result

def _get_snames_and_nums(cpuinfo: CPUInfo.CPUInfo) -> \
                            Generator[tuple[ScopeNameType, AbsNumsType | RelNumsType], None, None]:
    """
    Yield tuples of scope names and the result of '_get_scope_nums()' for each scope name.

    Args:
        cpuinfo: The 'CPUInfo' object under test.

    Yields:
        A tuple containing the scope name and the result of '_get_scope_nums()' for that scope name.
    """

    for sname in CPUInfo.SCOPE_NAMES:
        yield (sname, _get_scope_nums(sname, cpuinfo))

def _get_expected_topology(full_tlines: list[dict[ScopeNameType, int ]],
                           offlined_cpus: set[int]) -> _ExpectedTopology:
    """
    Create and return expected topology after offlining certain CPUs.

    Args:
        full_tlines: The full topology lines before offlining any CPUs.
        offlined_cpus: CPU numbers that have been offlined.

    Returns:
        The expected CPU topology after offlining the specified CPUs.
    """

    exp_topo: _ExpectedTopology = {}

    offlined_set = set(offlined_cpus)

    cpus: list[int] = []
    cores: dict[int, list[int]] = {}
    modules: list[int] = []
    dies: dict[int, list[int]] = {}
    packages: list[int] = []

    for tline in full_tlines:
        if tline["CPU"] in offlined_set:
            continue

        die = tline["die"]
        pkg = tline["package"]

        packages.append(pkg)

        cpu = tline["CPU"]
        cpus.append(cpu)
        cores.setdefault(pkg, []).append(tline["core"])
        modules.append(tline["module"])
        dies.setdefault(pkg, []).append(die)

    cpus = Trivial.list_dedup(cpus)
    for pkg in cores:
        cores[pkg] = Trivial.list_dedup(cores[pkg])
    modules = Trivial.list_dedup(modules)
    for pkg in dies:
        dies[pkg] = Trivial.list_dedup(dies[pkg])
    packages = Trivial.list_dedup(packages)

    exp_topo["cpus"] = cpus
    exp_topo["cores"] = cores
    exp_topo["modules"] = modules
    exp_topo["dies"] = dies
    exp_topo["packages"] = packages

    return exp_topo

def _validate_topo(cpuinfo: CPUInfo.CPUInfo, exp_topo: _ExpectedTopology):
    """
    Validate that the topology returned by the 'cpuinfo' object matches the expected topology.

    Args:
        cpuinfo: The 'CPUInfo' object under test.
        exp_topo: The expected CPU topology.
    """

    cpus = cpuinfo.get_cpus()
    assert sorted(cpus) == sorted(exp_topo["cpus"]), \
           f"get_cpus() returned {cpus}, expected {exp_topo['cpus']}"

    cores = cpuinfo.get_cores()
    for pkg in exp_topo["cores"]:
        assert sorted(cores[pkg]) == sorted(exp_topo["cores"][pkg]), \
               f"get_cores() returned {cores[pkg]} for package {pkg}, expected " \
               f"{exp_topo['cores'][pkg]}"

    modules = cpuinfo.get_modules()
    assert sorted(modules) == sorted(exp_topo["modules"]), \
           f"get_modules() returned {modules}, expected {exp_topo['modules']}"

    dies = cpuinfo.get_dies()
    for pkg in exp_topo["dies"]:
        assert sorted(dies[pkg]) == sorted(exp_topo["dies"][pkg]), \
               f"get_dies() returned {dies[pkg]} for package {pkg}, " \
               f"expected {exp_topo['dies'][pkg]}"

def _get_cpuinfos(params: CommonTestParamsTypedDict) -> Generator[CPUInfo.CPUInfo, None, None]:
    """
    Yield 'CPUInfo' objects for testing based on the host type.

    This generator yields CPUInfo objects with different CPU online/offline patterns:
        1. All CPUs online (initial state)
        2. Odd-numbered CPUs offline
        3. Even-numbered CPUs offline (excluding CPU 0)

    Args:
        params: Dictionary containing test parameters.

    Yields:
        'CPUInfo' objects configured according to the host type for use in tests.
    """

    pman = params["pman"]

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        full_tlines = list(cpuinfo.get_topology())

        # Ensure that all CPUs are online.
        with CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
            cpuonline.online()

    full_exp_topo = _get_expected_topology(full_tlines, set())

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:
        # Pattern 0: All CPUs online
        yield cpuinfo
        _validate_topo(cpuinfo, full_exp_topo)

        # Pattern 1: Take odd-numbered CPUs offline.
        all_cpus = cpuinfo.get_cpus()
        odd_cpus = [cpu for cpu in all_cpus if cpu % 2 == 1]

        if odd_cpus:
            cpuonline.offline(cpus=odd_cpus)
            yield cpuinfo
            _validate_topo(cpuinfo, _get_expected_topology(full_tlines, set(odd_cpus)))

            cpuonline.online(cpus=odd_cpus)
            _validate_topo(cpuinfo, full_exp_topo)

        # Pattern 2: Take even-numbered CPUs offline, excluding CPU 0, which can't be offlined.
        even_cpus = [cpu for cpu in all_cpus if cpu % 2 == 0 and cpu != 0]
        if even_cpus:
            cpuonline.offline(cpus=even_cpus)
            yield cpuinfo
            _validate_topo(cpuinfo, _get_expected_topology(full_tlines, set(even_cpus)))

            cpuonline.online(cpus=even_cpus)
            _validate_topo(cpuinfo, full_exp_topo)

def _run_method(name: str,
                cpuinfo: CPUInfo.CPUInfo,
                args: list | tuple | None = None,
                kwargs: dict | None = None,
                exp_res: object = _IGNORE,
                exp_exc: type[BaseException] | None = None):
    """
    Execute a specified method of the 'CPUInfo' object with provided arguments and validate its
    result or exception.

    Args:
        name: Name of the method to invoke on the cpuinfo object.
        cpuinfo: The 'CPUInfo' object whose method will be called.
        args: List of positional arguments to pass to the method. Defaults to an empty list.
        kwargs: Dictionary of keyword arguments to pass to the method. Defaults to an empty
                dictionary.
        exp_res: Expected result from the method call. If not provided, the result is not checked.
        exp_exc: Expected exception type. If provided, assert that the method raises this exception.
                 Use '_IGNORE' to ignore exceptions.

    Returns:
        The result of the method call if successful, or None if the method does not exist or if an
        expected exception was raised.
    """

    # The 'exp_res' and 'exp_exc' arguments are mutually exclusive.
    assert exp_res is _IGNORE or exp_exc in (None, _IGNORE)

    if args is None:
        args = []

    if kwargs is None:
        kwargs = {}

    method = getattr(cpuinfo, name, None)
    if not method:
        return None

    try:
        res = method(*args, **kwargs)
    except Exception as err: # pylint: disable=broad-except
        if exp_exc is _IGNORE:
            return None

        if exp_exc is None:
            assert False, f"Method '{name}()' raised the following exception:\n\t" \
                          f"type: {type(err)}\n\tmessage: {err}"

        if isinstance(err, exp_exc):
            return None

        assert False, f"Method '{name}()' raised the following exception:\n\t" \
                      f"type: {type(err)}\n\tmessage: {err}\n" \
                      f"But it was expected to raise the following exception type: {type(exp_exc)}"

    if exp_res is not _IGNORE:
        assert res == exp_res, f"Method '{name}()' returned:\n\t{res}\n" \
                               f"But it was expected to return:\n\t'{exp_res}'"

    return res

def _test_get_good(cpuinfo: CPUInfo.CPUInfo):
    """
    Test the 'get_<sname>s()' methods of the 'cpuinfo' object.

    This function iterates through all scope names and their corresponding numbers, verifying that:
        - The 'get_{sname}s()' methods return non-empty lists of the expected items.
        - The returned lists are consistent and sorted, regardless of the 'order' parameter.
        - The 'get_offline_cpus()' method can be called without error.

    Args:
        cpuinfo: The 'CPUInfo' object to test.
    """

    for sname, ref_nums in _get_snames_and_nums(cpuinfo):
        assert ref_nums, \
               f"'get_{sname}s()' is expected to return list of {sname}s, got: '{ref_nums}'"

        for order in CPUInfo.SCOPE_NAMES:
            nums = _get_scope_nums(sname, cpuinfo, order=order)
            if sname in ("die", "core"):
                # For dies and cores, the numbers are relative to the package numbers.
                if typing.TYPE_CHECKING:
                    ref_nums_dict = cast(RelNumsType, ref_nums)
                    nums_dict = cast(RelNumsType, nums)
                else:
                    ref_nums_dict = ref_nums
                    nums_dict = nums

                sorted_ref_nums = {pkg: sorted(pkg_nums) for pkg, pkg_nums in ref_nums_dict.items()}
                sorted_nums = {pkg: sorted(pkg_nums) for pkg, pkg_nums in nums_dict.items()}

                assert sorted_nums == sorted_ref_nums, \
                       f"'get_{sname}s()' was expected to return '{ref_nums}', got '{nums}'"
            else:
                assert sorted(nums) == sorted(ref_nums), \
                       f"'get_{sname}s()' was expected to return '{ref_nums}', got '{nums}'"

    _run_method("get_offline_cpus", cpuinfo)

def test_cpuinfo_get(params: CommonTestParamsTypedDict):
    """
    Test the 'get_<sname>s()' methods of the 'CPUInfo' object.

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_get_good(cpuinfo)

def test_cpuinfo_get_count(params: CommonTestParamsTypedDict):
    """
    Test the count retrieval methods for various CPU topology levels.

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        for sname, nums in _get_snames_and_nums(cpuinfo):
            if sname in ("core", "die"):
                if typing.TYPE_CHECKING:
                    nums_dict = cast(RelNumsType, nums)
                else:
                    nums_dict = nums
                count = sum(len(pkg_nums) for pkg_nums in nums_dict.values())
            else:
                count = len(nums)
            _run_method(f"get_{sname}s_count", cpuinfo, exp_res=count)

        offline_cpus = cpuinfo.get_offline_cpus()
        _run_method("get_offline_cpus_count", cpuinfo, exp_res=len(offline_cpus))

def _test_convert_good(cpuinfo: CPUInfo.CPUInfo):
    """
    Test the conversion methods of the 'CPUInfo' class.

    Args:
        cpuinfo: An instance of the 'CPUInfo' class to test conversion methods on.
    """

    # There are two types of conversion methods for translating between different scopes defined in
    # 'CPUInfo.SCOPE_NAMES':
    #   1. Methods that convert a single value to another scope, e.g., 'package_to_cpus()'.
    #   2. Methods that convert multiple values to another scope, e.g., 'packages_to_cpus()'.
    #
    # Single-value conversion methods accept a single integer, while multi-value conversion methods
    # also accept lists.
    for from_sname, from_nums in _get_snames_and_nums(cpuinfo):
        if from_sname in ("die", "core"):
            if typing.TYPE_CHECKING:
                from_nums_dict = cast(RelNumsType, from_nums)
            else:
                from_nums_dict = from_nums
            pkg_num = next(iter(from_nums_dict))
            from_nums_list = from_nums_dict[pkg_num]
        else:
            if typing.TYPE_CHECKING:
                from_nums_list = cast(AbsNumsType, from_nums)
            else:
                from_nums_list = from_nums

        single_args = [from_nums_list[0], from_nums_list[-1]]
        multi_args = [{from_nums_list[0], }, [from_nums_list[-1]]]
        if len(from_nums_list) > 1:
            multi_args.append((from_nums_list[-1], from_nums_list[0]))

        for to_sname, to_nums in _get_snames_and_nums(cpuinfo):
            # Test conversion method for a single value.
            method_name = f"{from_sname}_to_{to_sname}s"
            for arg in single_args:
                _run_method(method_name, cpuinfo, args=(arg,))

            # Test convert method for multiple values.
            method_name = f"{from_sname}s_to_{to_sname}s"
            _run_method(method_name, cpuinfo, exp_res=to_nums)

            for args in multi_args:
                _run_method(method_name, cpuinfo, args=(args,))

def test_cpuinfo_convert(params: CommonTestParamsTypedDict):
    """
    Tests various conversion methods of the 'CPUInfo' class, for example:
        - packages_to_cpus()
        - package_to_cpus()
        - package_to_cores()
        - dies_to_cpus()
        - cores_to_cpus()

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_convert_good(cpuinfo)

def _test_normalize_good(cpuinfo: CPUInfo.CPUInfo):
    """
    Test the 'normalize' methods of the 'CPUInfo' class with valid input values.

    Args:
        cpuinfo: An instance of the 'CPUInfo' class to be tested.
    """

    # There are two types of normalize methods:
    #   1. Methods for a single value (e.g., normalize_package()), which accept a single integer
    #      as input and return an integer.
    #   2. Methods for multiple values (e.g., normalize_packages()), which accept a list or a
    #      dictionary and return a list of integers.
    multiple: list[tuple[AbsNumsType | RelNumsType, AbsNumsType | RelNumsType]]
    for sname, nums in _get_snames_and_nums(cpuinfo):
        if sname in ("die", "core"):
            if typing.TYPE_CHECKING:
                nums_dict = cast(RelNumsType, nums)
            else:
                nums_dict = nums
            pkg_num = next(iter(nums_dict))
            nums_list = nums_dict[pkg_num]
            multiple = [({pkg_num: [nums_list[0]]}, {pkg_num: [nums_list[0]]}),
                        ({pkg_num: (nums_list[0],)}, {pkg_num: [nums_list[0]]})]
            if len(nums_list) > 1:
                # Test with a list and tuple with multiple integers.
                multiple += [({pkg_num: [nums_list[-1],  nums_list[0]]},
                              {pkg_num: [nums_list[-1],  nums_list[0]]}),
                             ({pkg_num: (nums_list[-1],  nums_list[0])},
                              {pkg_num: [nums_list[-1],  nums_list[0]]})]
        else:
            if typing.TYPE_CHECKING:
                nums_list = cast(AbsNumsType, nums)
            else:
                nums_list = nums
            multiple = [([nums_list[0]], [nums_list[0]]),
                        ((nums_list[0], ), [nums_list[0]])]
            if len(nums_list) > 1:
                # Test with a list and tuple with multiple integers.
                multiple += [([nums_list[-1], nums_list[0]], [nums_list[-1],  nums_list[0]]),
                             ((nums_list[-1], nums_list[0]), [nums_list[-1],  nums_list[0]])]

            single = [nums_list[0], nums_list[-1]]

            method_name  = f"normalize_{sname}"
            for arg in single:
                _run_method(method_name, cpuinfo, args=(arg,), exp_res=arg)

        method_name  = f"normalize_{sname}s"
        for args, exp_res in multiple:
            _run_method(method_name, cpuinfo, args=(args,), exp_res=exp_res)

def test_cpuinfo_normalize(params: CommonTestParamsTypedDict):
    """
    Test normalization methods of the 'CPUInfo' class, for example:
        - normalize_packages()
        - normalize_package()
        - normalize_cpus()
        - normalize_cpu()

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_normalize_good(cpuinfo)

def _is_globally_numbered(sname: ScopeNameType) -> bool:
    """
    Determine if a given CPU scope name is globally numbered.

    Args:
        sname: The scope name to check (e.g., "package", "die", "core", etc.).

    Returns:
        True if the scope is globally numbered, False if it is per-package numbered.
    """

    if sname not in ("die", "core"):
        return True
    return False

def _test_div_create_exp_res(sname: ScopeNameType,
                             nums: AbsNumsType,
                             cpus: AbsNumsType) -> tuple[AbsNumsType | RelNumsType, AbsNumsType]:
    """
    Create and return expected results for CPU division method tests.

    Methods like 'cpus_div_packages()' return a tuple, while methods like 'cpus_div_cores()' and
    'cpus_div_dies()' return a dictionary. Create the expected results based on scope name.

    Args:
        sname: The name of the CPU subdivision scope (e.g., "package", "core", "die").
        nums: CPU/core/etc numbers expected to be present in first element of the tuple returned by
              the division method.
        cpus: The expected second element of the tuple returned by the division method.

    Returns:
        The result of the division method.
    """

    if _is_globally_numbered(sname):
        return (nums, cpus)

    if nums:
        return ({0: nums}, cpus)

    return ({}, cpus)

def _test_cpuinfo_div(cpuinfo):
    """
    Test the division methods of the 'cpuinfo' object for various CPU topology levels.

    Args:
        cpuinfo: An instance of the 'CPUInfo' class to be tested.
    """

    for sname, nums in _get_snames_and_nums(cpuinfo):
        method_name  = f"cpus_div_{sname}s"
        if not getattr(cpuinfo, method_name, None):
            continue

        if sname in ("die", "core"):
            if typing.TYPE_CHECKING:
                nums_dict = cast(RelNumsType, nums)
            else:
                nums_dict = nums
            pkg_num = next(iter(nums_dict))
            nums_list = nums_dict[pkg_num]
        else:
            if typing.TYPE_CHECKING:
                nums_list = cast(AbsNumsType, nums)
            else:
                nums_list = nums

        # Note: In the comments below we'll assume that 'sname' is 'package', for simplicity.
        # However, it may be anything else, like 'core'.

        # Resolving an empty CPUs list.
        exp_res = _test_div_create_exp_res(sname, [], [])
        _run_method(method_name, cpuinfo, args=([],), exp_res=exp_res)

        if _is_globally_numbered(sname):
            # Resolving all CPUs in all packages.
            allcpus = cpuinfo.get_cpus()
        else:
            # In case of a non-globally numbered level, we'll operate only with package 0 numbers.
            allcpus = cpuinfo.package_to_cpus(0)
        exp_res = _test_div_create_exp_res(sname, nums_list, [])
        _run_method(method_name, cpuinfo, args=(allcpus,), exp_res=exp_res)

        # Get the list of CPUs in the first scope element.
        num0_cpus = _run_method(f"{sname}_to_cpus", cpuinfo, args=(nums_list[0],))
        if num0_cpus is None or len(num0_cpus) < 2:
            # The rest of the test-cases require the '<sname>_to_cpus()' method and more than one
            # CPU per scope element.
            continue

        # Resolving all CPUs except for the very first one.
        rnums, rcpus = _run_method(method_name, cpuinfo, args=(allcpus[1:],))
        assert len(rnums) == len(nums_list) - 1 and len(rcpus) > 0, \
               f"Bad result from '{method_name}({allcpus[1:]})':\n\t({rnums}, {rcpus})\n"

        # Resolving a single CPU - the first and the last.
        exp_res = _test_div_create_exp_res(sname, [], allcpus[0:1])
        _run_method(method_name, cpuinfo, args=(allcpus[0:1],), exp_res=exp_res)
        exp_res = _test_div_create_exp_res(sname, [], allcpus[-1:])
        _run_method(method_name, cpuinfo, args=(allcpus[-1:],), exp_res=exp_res)

        if len(nums_list) < 2:
            # The rest of the test-cases require more than one package.
            continue

        # Resolving all CPUs in the first package.
        exp_res = _test_div_create_exp_res(sname, nums_list[0:1], [])
        _run_method(method_name, cpuinfo, args=(num0_cpus,), exp_res=exp_res)

        # Same, but without the first CPU in the first package.
        exp_res = _test_div_create_exp_res(sname, [], num0_cpus[1:])
        _run_method(method_name, cpuinfo, args=(num0_cpus[1:],), exp_res=exp_res)

        # Resolving first package CPUs but for the second package.
        args = (num0_cpus,)
        kwargs = {"packages" : [nums_list[1]]}
        exp_res = _test_div_create_exp_res(sname, [], num0_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

        exp_cpus = []
        for cpu in allcpus:
            if cpu not in num0_cpus:
                exp_cpus.append(cpu)

        # Resolving all CPUs but only for the first package.
        args = (allcpus,)
        kwargs = {"packages" : [nums_list[0]]}
        exp_res = _test_div_create_exp_res(sname, nums_list[0:1], exp_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

def test_cpuinfo_div(params: CommonTestParamsTypedDict):
    """
    Test the division methods, for example:
        - 'cpus_div_packages()'
        - 'cpus_div_dies()'
        - 'cpus_div_cores()'

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_cpuinfo_div(cpuinfo)

def test_core_siblings(params: CommonTestParamsTypedDict):
    """
    Test the 'select_core_siblings()' method.

    Args:
        params: The test parameters.
    """

    for cpuinfo in _get_cpuinfos(params):
        topology = cpuinfo.get_topology(order="core")

        # We get the CPU siblings count for the first core in the topology list. Depending on how
        # many CPUs the core has determines the index we use for testing.
        index = 0
        for tline in topology[1:]:
            if tline["package"] != topology[0]["package"] or tline["core"] != topology[0]["core"]:
                break
            index += 1

        # 'l1' - input list, random 50% of the online CPUs. There can be duplicates.
        l1 = random.choices(cpuinfo.get_cpus(), k=int(cpuinfo.get_cpus_count() / 2))
        # 'l2' - output list, returned by 'select_core_siblings()' with 'l1' as input.
        l2 = cpuinfo.select_core_siblings(l1, [index])

        # Here we test that the 'l2' is a subset of the 'l1' and in the same order. But first we
        # must dedup 'l1', because 'select_core_siblings()' does not return duplicates. Secondly we
        # remove values from 'l1' that are not in 'l2'.
        l1 = list(dict.fromkeys(l1))
        l1 = [x for x in l1 if x in l2]
        assert l1 == l2, "List returned by 'select_core_siblings()' is not a subset of input " \
                         "list and in the same order"

        # Here we verify that the index of the returned CPUs is 'index'.
        l2_set = set(l2)
        core = pkg = None
        i = -1
        for tline in topology:
            cpu = tline["CPU"]
            if tline["core"] != core or tline["package"] != pkg:
                core = tline["core"]
                pkg = tline["package"]
                i = 0
            else:
                i += 1

            if cpu in l2_set:
                assert index == i, f"CPU {cpu} is not sibling index {index}, in core {core} "\
                                   f"package {pkg}"

def test_delayed_init(params: CommonTestParamsTypedDict):
    """
    In some scenarios certain pieces of 'CPUInfo' should not be initialized for optimization
    purposes. This test ensures that delayed initialization works correctly.

    Args:
        params: The test parameters.
    """

    # pylint: disable=protected-access

    for cpuinfo in _get_cpuinfos(params):
        # A newly created 'CPUInfo' object should not have any topology initialized.
        assert "CPU" not in cpuinfo._initialized_snames, "'CPU' scope should not be initialized"
        assert "die" not in cpuinfo._initialized_snames, "'die' scope should not be initialized"
        assert not cpuinfo._topology, "Topology should not be initialized"

        # The 'get_cpus()' does not initialize topology either.
        cpuinfo.get_cpus()
        assert "CPU" not in cpuinfo._initialized_snames, "'CPU' scope should not be initialized"
        assert "die" not in cpuinfo._initialized_snames, "'die' scope should not be initialized"
        assert not cpuinfo._topology, "Topology should not be initialized"

        # But it initializes the '_cpus' member.
        assert cpuinfo._cpus, "'_cpus' member should be initialized"

        # The 'get_cores()' initializes 'CPU', 'core', and 'package' scopes.
        cpuinfo.get_cores()
        assert "CPU" in cpuinfo._initialized_snames, "'CPU' scope should be initialized"
        assert "core" in cpuinfo._initialized_snames, "'core' scope should be initialized"
        assert "package" in cpuinfo._initialized_snames, "'package' scope should be initialized"
        assert cpuinfo._topology, "Topology should be initialized"

        # But 'module' and 'die' scopes remain uninitialized.
        assert "module" not in cpuinfo._initialized_snames, \
               "'module' scope should not be initialized"
        assert "die" not in cpuinfo._initialized_snames, "'die' scope should not be initialized"

        # The 'get_modules()' initializes the 'module' scope.
        cpuinfo.get_modules()
        assert "module" in cpuinfo._initialized_snames, "'module' scope should be initialized"
        assert "die" not in cpuinfo._initialized_snames, "'die' scope should not be initialized"

        # Finally, the 'get_dies()' initializes the 'die' scope.
        cpuinfo.get_dies()
        assert "die" in cpuinfo._initialized_snames, "'die' scope should be initialized"
