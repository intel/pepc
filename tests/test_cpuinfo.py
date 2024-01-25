#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Tests for the public methods of the 'CPUInfo' module."""

import random
import pytest
import common
from pepclibs import CPUModels, CPUInfo, CPUOnline
from pepclibs.helperlibs.Exceptions import Error

# A unique object used in '_run_method()' for ignoring method's return value by default.
_IGNORE = object()

@pytest.fixture(name="params", scope="module")
def get_params(hostspec):
    """Yield a dictionary with information we need for testing."""

    emul_modules = ["CPUInfo"]

    with common.get_pman(hostspec, modules=emul_modules) as pman:
        params = common.build_params(pman)
        yield params

def _get_levels():
    """Yield 'CPUInfo.LEVEL' values as a lowercase strings."""

    for lvl in CPUInfo.LEVELS:
        yield lvl.lower()

def _get_level_nums(lvl, cpuinfo, order=None):
    """
    Run the 'get_<lvl>(order=<order>)' method of 'cpuinfo' and return the result (e.g., runs
    'get_packages()' if 'lvl' is "packages").
      * cpuinfo - the 'CPUInfo' object.
      * order - value for the 'order' keyword argument of the executed "get" method. Set to 'lvl' by
                default.

    Notice! If 'lvl' is a non-globally numbered level ("core" or "die"), this method returns level
    numbers for the first package.
    """

    if order is None:
        order = lvl

    # The 'cpu' level is special.
    order = order.replace("cpu", "CPU")

    get_method = getattr(cpuinfo, f"get_{lvl}s", None)

    assert get_method, f"BUG: 'get_{lvl}s()' does not exist"

    if lvl == "die":
        # TODO: cover I/O dies too.
        return get_method(order=order, io_dies=False)
    return get_method(order=order)

def _get_levels_and_nums(cpuinfo):
    """
    This is a combination of '_get_levels()' and '_get_level_nums()'. For every level name which has
    the corresponding 'get_<lvl>()' method, yield a tuple of lower-cased level name and the
    'get_<lvl>()' result.
    """

    for lvl in CPUInfo.LEVELS:
        lvl = lvl.lower()
        if not getattr(cpuinfo, f"get_{lvl}s", None):
            continue

        yield (lvl, _get_level_nums(lvl, cpuinfo))

def _get_bad_orders():
    """Yield bad 'order' argument values."""

    for order in "CPUS", "CORE", "nodes", "pkg":
        yield order

def _get_emulated_cpuinfos(pman):
    """Yield the 'CPUInfo' objects with emulated testdata."""

    # Offline CPUs with following patterns.
    # 1. All CPUs online.
    # 2. Odd CPUs offline.
    # 3. All but first CPU offline.
    with CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         CPUOnline.CPUOnline(pman=pman, cpuinfo=cpuinfo) as cpuonline:

        # By default all CPUs are online on emulated data.
        yield cpuinfo

        for pattern in (lambda x: not(x % 2), lambda x: x == 0):
            cpus = [cpu for cpu in cpuinfo.get_cpus() if not pattern(cpu)]

            cpuonline.offline(cpus=cpus)
            yield cpuinfo
            cpuonline.online(cpus=cpus)

        if cpuinfo.info["model"] == CPUModels.MODELS["ICELAKE_X"]["model"]:
            # Yield CPUInfo object with unknown CPU model number.
            cpuinfo.info["model"] = 255
            yield cpuinfo

def _get_cpuinfos(params):
    """
    Yield the 'CPUInfo' objects to test with. If 'pman' object is for emulated host, then attributes
    of the 'CPUInfo' object is modified with different permutations that we want to test with. If
    the 'pman' object is for real host, yield single 'CPUInfo' object.
    """

    pman = params["pman"]
    if common.is_emulated(pman):
        yield from _get_emulated_cpuinfos(pman)
    else:
        with CPUInfo.CPUInfo(pman=pman) as cpuinfo:
            yield cpuinfo

def _run_method(name, cpuinfo, args=None, kwargs=None, exp_res=_IGNORE, exp_exc=None):
    """
    Run the 'name' method of the 'cpuinfo' object. The arguments are as follows.
      * name - the name of the method.
      * cpuinfo - the 'CPUInfo' object.
      * args - the ordered arguments to pass down to the method.
      * kwargs - keyword arguments to pass down to the method.
      * exp_res - the expected result (not checked by default).
      * exp_exc - the expected exception type. By default, any exception is considered to be a
                  failure. Use '_IGNORE' to ignore exceptions.

    The 'name' method is called and tested only if it exists in 'cpuinfo'. Returns the result of the
    'name' method and 'None' if it does not exist.
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
            assert False, f"method '{name}()' raised the following exception:\n\t" \
                          f"type: {type(err)}\n\tmessage: {err}"

        if isinstance(err, exp_exc):
            return None

        assert False, f"method '{name}()' raised the following exception:\n\t" \
                      f"type: {type(err)}\n\tmessage: {err}\n" \
                      f"but it was expected to raise the following exception type: {type(exp_exc)}"

    if exp_res is not _IGNORE:
        assert res == exp_res, f"method '{name}()' returned:\n\t{res}\n" \
                               f"But it was expected to return:\n\t'{exp_res}'"

    return res

def _test_get_good(cpuinfo):
    """Test 'get' methods for bad option values."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"
        ref_nums = sorted(nums)

        for order in _get_levels():
            nums = _get_level_nums(lvl, cpuinfo, order=order)
            assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"
            nums = sorted(nums)
            assert nums == ref_nums, f"'get_{lvl}s()' was expected to return '{ref_nums}', " \
                                     f"got '{nums}'"

    _run_method("get_offline_cpus", cpuinfo)

def _test_get_bad(cpuinfo):
    """Test 'get' methods with bad 'order' values and expect methods to fail."""

    for lvl in _get_levels():
        if not getattr(cpuinfo, f"get_{lvl}s", None):
            continue

        for order in _get_bad_orders():
            with pytest.raises(Error):
                _get_level_nums(lvl, cpuinfo, order=order)

def test_cpuinfo_get(params):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages()'
      * 'get_cpus()'
      * 'get_offline_cpus()'
      * 'get_cpu_siblings()'
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_get_good(cpuinfo)
        _test_get_bad(cpuinfo)

def test_cpuinfo_get_count(params):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages_count()'
      * 'get_cpus_count()'
      * 'get_offline_cpus_count()'
    """

    for cpuinfo in _get_cpuinfos(params):
        for lvl, nums in _get_levels_and_nums(cpuinfo):
            kwargs = {}
            if lvl == "die":
                # TODO: cover I/O dies too.
                kwargs = {"io_dies" : False}
            _run_method(f"get_{lvl}s_count", cpuinfo, kwargs=kwargs, exp_res=len(nums))

        offline_cpus = cpuinfo.get_offline_cpus()
        _run_method("get_offline_cpus_count", cpuinfo, exp_res=len(offline_cpus))

def _test_convert_good(cpuinfo):
    """Test public convert methods of the 'CPUInfo' class with good option values."""

    for from_lvl, from_nums in _get_levels_and_nums(cpuinfo):
        # We have two types of conversion methods to convert values between different "levels"
        # defined in 'CPUInfo.LEVELS'. We have methods for converting single value to other level,
        # e.g. 'package_to_cpus()'. And we have methods for converting multiple values to other
        # level, e.g. 'packages_to_cpus()'.
        # Methods to convert single value accept single integer in different forms, and methods
        # converting multiple values accept also integers in lists.

        single_args = [from_nums[0], from_nums[-1]]
        multi_args = [{from_nums[0], }, [from_nums[-1]]]
        if len(from_nums) > 1:
            multi_args.append((from_nums[-1], from_nums[0]))

        for to_lvl, to_nums in _get_levels_and_nums(cpuinfo):
            # Test normalize method of single value.
            method_name = f"{from_lvl}_to_{to_lvl}s"
            for args in single_args:
                _run_method(method_name, cpuinfo, args=(args,))

            # Test convert method for multiple values.
            method_name = f"{from_lvl}s_to_{to_lvl}s"
            _run_method(method_name, cpuinfo, exp_res=to_nums)

            for args in multi_args:
                _run_method(method_name, cpuinfo, args=(args,))

def _test_convert_bad(cpuinfo):
    """Same as '_test_convert_good()', but use bad option values."""

    for from_lvl, from_nums in _get_levels_and_nums(cpuinfo):
        bad_num = from_nums[-1] + 1

        for to_lvl in _get_levels():
            method_name = f"{from_lvl}_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (bad_num, f"{bad_num}", f"{from_nums[0]}, ", (bad_num,))

                for args in bad_args:
                    _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    _run_method(method_name, cpuinfo, args=(args,), kwargs=kwargs, exp_exc=Error)

            method_name = f"{from_lvl}s_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (-1, bad_num, (-1, bad_num), "-1", (bad_num,))

                for args in bad_args:
                    _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    _run_method(method_name, cpuinfo, args=(args,), kwargs=kwargs, exp_exc=Error)

def test_cpuinfo_convert(params):
    """
    Test the following 'CPUInfo' class methods:
      * 'packages_to_cpus()'
      * 'package_to_cpus()'
      * 'package_to_nodes()'
      * 'package_to_dies()'
      * 'package_to_cores()'
      * 'dies_to_cpus()'
      * 'cores_to_cpus()'
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_convert_good(cpuinfo)
        _test_convert_bad(cpuinfo)

def _test_normalize_good(cpuinfo):
    """Test public 'normalize' methods of the 'CPUInfo' class with good option values."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        # We have two types of normalize methods, normalize methods for single value
        # (e.g. normalize_package()), and multiple values (e.g. normalize_packages()). Methods for
        # single value, accept single integer as input value, and the return value
        # is an integer. Normalize methods for multiple values, accept single and multiple integers
        # in different forms, and return integers as a list.
        #
        # Build a list of tuples with input and expected output value pairs.
        testcase = [nums[0], nums[-1]]

        method_name  = f"normalize_{lvl}"
        for args in testcase:
            _run_method(method_name, cpuinfo, args=(args,), exp_res=args)

        # Test with a list and tuple with a single integer.
        testcase = [([nums[0]], [nums[0]]),
                    ((nums[0], ), [nums[0]])]
        if len(nums) > 1:
            # Test with a list and tuple with multiple integers.
            testcase += [([nums[-1], nums[0]], [nums[-1],  nums[0]]),
                         ((nums[-1], nums[0]), [nums[-1],  nums[0]])]

        method_name  = f"normalize_{lvl}s"
        for args, exp_res in testcase:
            _run_method(method_name, cpuinfo, args=(args,), exp_res=exp_res)

def _test_normalize_bad(cpuinfo):
    """Same as '_test_normalize_good()', but use bad option values."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        bad_num = nums[-1] + 1
        bad_args = (-1, "-1", f"{nums[0]},", bad_num)

        method_name  = f"normalize_{lvl}"
        for args in bad_args:
            _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

        bad_args = ([[nums[0], bad_num]])

        method_name  = f"normalize_{lvl}s"
        for args in bad_args:
            _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

def test_cpuinfo_normalize(params):
    """
    Test the following 'CPUInfo' class methods:
      * 'normalize_packages()'
      * 'normalize_package()'
      * 'normalize_cpus()'
      * 'normalize_cpu()'
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_normalize_good(cpuinfo)
        _test_normalize_bad(cpuinfo)

def _is_globally_numbered(lvl):
    """
    There are 2 types of 'CPUInfo' levels: globally numbered and non-globally (per-package)
    numbered. This helper returns 'True' if 'lvl' is globally-numbered, and 'False' otherwise.
    """

    if lvl.lower() in {"package", "node", "cpu"}:
        return True
    return False

def _test_div_create_exp_res(lvl, nums, cpus):
    """
    This is a helper for 'test_div()' and it exists because of inconsistency between some "div"
    method of "CPUInfo".
       * 'cpus_div_packages()' returns a tuple with first element being a list of integers. For
          example: ([0,1], []).
       * 'cpus_div_cores()' and 'cpu_div_dies()' return a tuple with first element being a
          dictionary of lists. For example ({0: [0[], 1: [0])}, []).

    The difference is that 'cpus_div_cores()' and 'cpus_div_dies()' return the dictionary n the
    {package: [list of cores or dies]} format. , while 'cpus_div_packages()' returns the list of
    package numbers. And the reason for this is that core and die numbers are relative to the
    package.

    For globally-numbered levels, such as "package", this function does nothing and just returns the
    ('nums', 'cpus') tuple.
    """

    if _is_globally_numbered(lvl):
        return (nums, cpus)

    if nums:
        return ({0:nums}, cpus)
    return ({}, cpus)

def _test_cpuinfo_div(cpuinfo):
    """Implements the 'test_cpuinfo_div()'."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        method_name  = f"cpus_div_{lvl}s"
        if not getattr(cpuinfo, method_name, None):
            continue

        # Note! In the comments below we'll assume that 'lvl' is packages, for simplicity. However,
        # it may be anything else, like 'cores'.

        # Resolving an empty CPUs list.
        exp_res = _test_div_create_exp_res(lvl, [], [])
        _run_method(method_name, cpuinfo, args=([],), exp_res=exp_res)

        if _is_globally_numbered(lvl):
            # Resolving all CPUs in all packages.
            allcpus = cpuinfo.get_cpus()
        else:
            # In case of a non-globally numbered level, we'll operate only with package 0 numbers.
            allcpus = cpuinfo.package_to_cpus(0)
        exp_res = _test_div_create_exp_res(lvl, nums, [])
        _run_method(method_name, cpuinfo, args=(allcpus,), exp_res=exp_res)

        # Get the list of CPUs in the first package.
        num0_cpus = _run_method(f"{lvl}_to_cpus", cpuinfo, args=(nums[0],))
        if num0_cpus is None or len(num0_cpus) < 2:
            # The rest of the test-cases require the '<lvl>_to_cpus()' method and more than one CPU
            # per package.
            continue

        # Resolving all CPUs except for the very first one.
        rnums, rcpus = _run_method(method_name, cpuinfo, args=(allcpus[1:],))
        assert len(rnums) == len(nums) - 1 and len(rcpus) > 0, \
               f"bad result from '{method_name}({allcpus[1:]})':\n\t(rnums, rcpus)\n"

        # Resolving a single CPU - the first and the last.
        exp_res = _test_div_create_exp_res(lvl, [], allcpus[0:1])
        _run_method(method_name, cpuinfo, args=(allcpus[0:1],), exp_res=exp_res)
        exp_res = _test_div_create_exp_res(lvl, [], allcpus[-1:])
        _run_method(method_name, cpuinfo, args=(allcpus[-1:],), exp_res=exp_res)

        if len(nums) < 2:
            # The rest of the test-cases require more than one package.
            continue

        # Resolving all CPUs in the first package.
        exp_res = _test_div_create_exp_res(lvl, nums[0:1], [])
        _run_method(method_name, cpuinfo, args=(num0_cpus,), exp_res=exp_res)

        # Same, but without the first CPU in the first package.
        exp_res = _test_div_create_exp_res(lvl, [], num0_cpus[1:])
        _run_method(method_name, cpuinfo, args=(num0_cpus[1:],), exp_res=exp_res)

        # Resolving first package CPUs but for the second package.
        args = (num0_cpus,)
        kwargs = {"packages" : [nums[1]]}
        exp_res = _test_div_create_exp_res(lvl, [], num0_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

        exp_cpus = []
        for cpu in allcpus:
            if cpu not in num0_cpus:
                exp_cpus.append(cpu)

        # Resolving all CPUs but for only for the first package.
        args = (allcpus,)
        kwargs = {"packages" : [nums[0]]}
        exp_res = _test_div_create_exp_res(lvl, nums[0:1], exp_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

def test_cpuinfo_div(params):
    """
    Test the following 'CPUInfo' class methods:
      * 'cpus_div_packages()'
      * 'cpus_div_dies()'
      * 'cpus_div_cores()'
    """

    for cpuinfo in _get_cpuinfos(params):
        _test_cpuinfo_div(cpuinfo)

def test_core_siblings(params):
    """Test 'select_core_siblings()'."""

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
        assert l1 == l2, "list retured by 'select_core_siblings()' is not a subset of input " \
                         "list and in the same order"

        # Here we verify that the index of the returned CPUs is 'index'.
        l2 = set(l2)
        core = pkg = i = None
        for tline in topology:
            cpu = tline["CPU"]
            if tline["core"] != core or tline["package"] != pkg:
                core = tline["core"]
                pkg = tline["package"]
                i = 0
            else:
                i += 1

            if cpu in l2:
                assert index == i, f"CPU {cpu} is not sibling index {index}, in core {core} "\
                                   f"package {pkg}"
