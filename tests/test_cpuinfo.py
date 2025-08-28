#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Test the public methods of the 'CPUInfo' module."""

from __future__ import annotations # Remove when switching to Python 3.10+.

from typing import Generator, cast
import random
import pytest
import common
from common import CommonTestParamsTypedDict
from pepclibs import CPUModels, CPUInfo, CPUOnline
from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType
from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# A unique object used in '_run_method()' for ignoring method's return value by default.
_IGNORE = object()

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required 'CPUInfo' tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec) as pman:
        params = common.build_params(pman)
        yield params

def _get_scope_nums(sname: ScopeNameType,
                    cpuinfo: CPUInfo.CPUInfo,
                    order: ScopeNameType | None = None) -> AbsNumsType | RelNumsType:
    """
    Execute the 'get_<sname>s()' (e.g., 'get_cores()') method of the given return the result.

    Args:
        sname: Name of the Cscope (e.g., "package", "core", "die") to run the method for.
        cpuinfo: The 'CPUInfo' object under test.
        order: The order to pass down to the 'get_<sname>s()' method. Use the 'sname' value is used
               as the order by default.

    Returns:
        List of CPU/code/etc (<sname>) numbers as returned by the corresponding 'get_<sname>s()'
        method.
    """

    if order is None:
        order = sname

    get_method = getattr(cpuinfo, f"get_{sname}s".lower(), None)

    assert get_method, f"BUG: 'get_{sname}s()' does not exist"

    if sname == "die":
        result = get_method(order=order, io_dies=False)
    else:
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

def _get_emulated_cpuinfos(pman: ProcessManagerType) -> Generator[CPUInfo.CPUInfo, None, None]:
    """
    Yield CPUInfo objects with various emulated CPU online/offline patterns for testing.

    This generator simulates different CPU online/offline scenarios using emulated test data:
        1. All CPUs online.
        2. Odd-numbered CPUs offline.
        3. All CPUs except the first one offline.
        4. (If applicable) CPUInfo object with an unknown CPU Vendor/Family/Model (VFM).

    Args:
        pman: Process manager instance used to control and query CPU state.

    Yields:
        CPUInfo objects reflecting the current emulated CPU online/offline state.
    """

    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:

        # In the emulated environment, all CPUs are initially online by default.
        yield cpuinfo

        for pattern in (lambda x: not(x % 2), lambda x: x == 0):
            cpus = [cpu for cpu in cpuinfo.get_cpus() if not pattern(cpu)]

            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)

        if cpuinfo.info["vfm"] == CPUModels.MODELS["ICELAKE_X"]["vfm"]:
            cpuinfo.info["vfm"] = 255
            yield cpuinfo

def _get_cpuinfos(params: CommonTestParamsTypedDict) -> Generator[CPUInfo.CPUInfo, None, None]:
    """
    Yield 'CPUInfo' objects for testing based on the host type.

    Args:
        params: Dictionary containing test parameters.

    Yields:
        'CPUInfo' objects configured according to the host type for use in tests.
    """

    pman = params["pman"]
    if common.is_emulated(pman):
        yield from _get_emulated_cpuinfos(pman)
    else:
        with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
            yield cpuinfo

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

    This function iterates through all scope name and their corresponding numbers, verifying that:
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
                ref_nums_dict = cast(RelNumsType, ref_nums)
                nums_dict = cast(RelNumsType, nums)

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
            kwargs = {}
            if sname == "die":
                # TODO: cover I/O dies too.
                kwargs = {"io_dies" : False}
            if sname in ("core", "die"):
                nums_dict = cast(RelNumsType, nums)
                count = sum(len(pkg_nums) for pkg_nums in nums_dict.values())
            else:
                count = len(nums)
            _run_method(f"get_{sname}s_count", cpuinfo, kwargs=kwargs, exp_res=count)

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
            from_nums_dict = cast(RelNumsType, from_nums)
            pkg_num = next(iter(from_nums_dict))
            from_nums_list = from_nums_dict[pkg_num]
        else:
            from_nums_list = cast(AbsNumsType, from_nums)

        single_args = [from_nums_list[0], from_nums_list[-1]]
        multi_args = [{from_nums_list[0], }, [from_nums_list[-1]]]
        if len(from_nums_list) > 1:
            multi_args.append((from_nums_list[-1], from_nums_list[0]))

        for to_sname, to_nums in _get_snames_and_nums(cpuinfo):
            # Test normalize method of single value.
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
    #   2. Methods for multiple values (e.g., normalize_packages()), which accept a list of a
    #      dictionary and return a list of integers.
    multiple: list[tuple[AbsNumsType | RelNumsType, AbsNumsType | RelNumsType]]
    for sname, nums in _get_snames_and_nums(cpuinfo):
        if sname in ("die", "core"):
            nums_dict = cast(RelNumsType, nums)
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
            nums_list = cast(AbsNumsType, nums)
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
            nums_dict = cast(RelNumsType, nums)
            pkg_num = next(iter(nums_dict))
            nums_list = nums_dict[pkg_num]
        else:
            nums_list = cast(AbsNumsType, nums)

        # Note! In the comments below we'll assume that 'sname' is packages, for simplicity.
        # However, it may be anything else, like 'cores'.

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

        # Get the list of CPUs in the first package.
        num0_cpus = _run_method(f"{sname}_to_cpus", cpuinfo, args=(nums_list[0],))
        if num0_cpus is None or len(num0_cpus) < 2:
            # The rest of the test-cases require the '<sname>_to_cpus()' method and more than one
            # CPU per package.
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

        # Resolving all CPUs but for only for the first package.
        args = (allcpus,)
        kwargs = {"packages" : [nums_list[0]]}
        exp_res = _test_div_create_exp_res(sname, nums_list[0:1], exp_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

def test_cpuinfo_div(params: CommonTestParamsTypedDict):
    """
    Test the division method, for example:
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
        # many CPUs the core has, will determine the index we use for testing.
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
