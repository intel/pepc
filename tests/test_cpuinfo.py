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

import pytest
from common import fixture_proc, fixture_cpuinfo # pylint: disable=unused-import
from pepclibs import CPUInfo
from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import Error

# A unique object used in '_run_method()' for ignoring method's return value by default.
_IGNORE = object()

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

def _get_cpuinfos_cpus_offlined(cpuinfo, pattern):
    """Yield the 'CPUInfo' object with different patterns of offlined CPUs."""

    online_cpus = set()
    offline_cpus = set()

    for cpu in cpuinfo.get_cpus():
        if pattern(cpu):
            online_cpus.add(cpu)
        else:
            offline_cpus.add(cpu)

    cpuinfo.mark_cpus_online(online_cpus)
    cpuinfo.mark_cpus_offline(offline_cpus)

    return cpuinfo

def _get_emulated_cpuinfos(proc):
    """
    Yield the 'CPUInfo' objects with emulated testdata. The testdata is modified with different
    permutations that we want to test with.
    """

    # Offline CPUs with following patterns.
    # 1. All CPUs online.
    # 2. Odd CPUs offline.
    # 3. All but first CPU offline.
    for pattern in (lambda x: True, lambda x: not(x % 2), lambda x: x == 0):
        with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
            yield _get_cpuinfos_cpus_offlined(cpuinfo, pattern)

def _get_cpuinfos(proc):
    """
    Yield the 'CPUInfo' objects to test with. If 'proc' object is for emulated host, then attributes
    of the 'CPUInfo' object is modified with different permutations that we want to test with. If
    the 'proc' object is for real host, yield single 'CPUInfo' object.
    """

    if "emulated" in proc.hostname:
        yield from _get_emulated_cpuinfos(proc)
    else:
        with CPUInfo.CPUInfo(proc=proc) as cpuinfo:
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
    _run_method("get_cpu_siblings", cpuinfo, args=(0,))

def _test_get_bad(cpuinfo):
    """Test 'get' methods with bad 'order' values and expect methods to fail."""

    for lvl in _get_levels():
        if not getattr(cpuinfo, f"get_{lvl}s", None):
            continue

        for order in _get_bad_orders():
            with pytest.raises(Error):
                _get_level_nums(lvl, cpuinfo, order=order)

    cpus = _get_level_nums("cpu", cpuinfo)
    bad_cpu = cpus[-1] + 1
    _run_method("get_cpu_siblings", cpuinfo, args=(bad_cpu,), exp_exc=Error)

def test_cpuinfo_get(proc):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages()'
      * 'get_cpus()'
      * 'get_offline_cpus()'
      * 'get_cpu_siblings()'
    """

    for cpuinfo in _get_cpuinfos(proc):
        _test_get_good(cpuinfo)
        _test_get_bad(cpuinfo)

def test_cpuinfo_get_count(proc):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages_count()'
      * 'get_cpus_count()'
      * 'get_offline_cpus_count()'
    """

    for cpuinfo in _get_cpuinfos(proc):
        for lvl, nums in _get_levels_and_nums(cpuinfo):
            _run_method(f"get_{lvl}s_count", cpuinfo, exp_res=len(nums))

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
        single_args = []
        for idx in 0, -1:
            num = from_nums[idx]
            single_args += [num, f"{num}", f" {num} "]

        multi_args = []
        for idx in 0, -1:
            num = from_nums[idx]
            multi_args += [f"{num},", [num]]

            if len(from_nums) > 1:
                multi_args += [(from_nums[-1], from_nums[0]),
                               f"{from_nums[0]}, {from_nums[-1]}",
                               f"{from_nums[0]}, {from_nums[-1]},",
                               f" {from_nums[0]}, {from_nums[-1]} ",]

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

def test_cpuinfo_convert(proc):
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

    for cpuinfo in _get_cpuinfos(proc):
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
        testcase = []
        for idx in 0, -1:
            testcase += [(nums[idx], [nums[idx]]),
                         ((nums[idx]), [nums[idx]]),
                         (f"{nums[idx]}", [nums[idx]]),
                         (f" {nums[idx]} ", [nums[idx]])]

        method_name  = f"normalize_{lvl}"
        for args, exp_res in testcase:
            _run_method(method_name, cpuinfo, args=(args,), exp_res=exp_res[0])

        # The methods for normalizing multiple values accept input as single integers, and multiple
        # integers in different forms. Add more input and expected values to test normalize methods
        # for multiple values.
        for idx in 0, -1:
            testcase += [(f"{nums[idx]},", [nums[idx]])]

        if len(nums) > 1:
            testcase += [((nums[-1], nums[0]), [nums[-1], nums[0]]),
                         (f"{nums[0]}, {nums[-1]}", [nums[0], nums[-1]]),
                         (f"{nums[0]}, {nums[-1]},", [nums[0], nums[-1]]),
                         (f" {nums[0]}, {nums[-1]} ", [nums[0], nums[-1]])]

        method_name  = f"normalize_{lvl}s"
        for args, exp_res in testcase:
            _run_method(method_name, cpuinfo, args=(args,), exp_res=exp_res)

def _test_normalize_bad(cpuinfo):
    """Same as '_test_normalize_good()', but use bad option values."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        bad_num = nums[-1] + 1

        method_name  = f"normalize_{lvl}"
        if getattr(cpuinfo, method_name, None):
            bad_args = (-1, "-1", f"{nums[0]},", bad_num, [bad_num])

            for args in bad_args:
                _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

        method_name  = f"normalize_{lvl}s"
        if getattr(cpuinfo, method_name, None):
            bad_args = (f"{nums[0]}, {nums[-1]}, ",
                        f", {nums[0]}, {nums[-1]}, ",
                        f" {nums[0]}-{nums[-1]}, ",
                        f" {nums[0]}, {nums[-1]}, ,",
                        [[nums[0], bad_num]])

            for args in bad_args:
                _run_method(method_name, cpuinfo, args=(args,), exp_exc=Error)

def test_cpuinfo_normalize(proc):
    """
    Test the following 'CPUInfo' class methods:
      * 'normalize_packages()'
      * 'normalize_package()'
      * 'normalize_cpus()'
      * 'normalize_cpu()'
    """

    for cpuinfo in _get_cpuinfos(proc):
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
       * 'cpus_div_cores()' returns a tuple with first element being a list of tuples of 2 integers.
          For example ([(0,0), (1,0)], []).

    The difference is that 'cpus_div_cores()' returns the list of (core, package) pairs, while
    'cpus_div_packages()' returns the list of package numbers. And the reason for this is that core
    numbers are not global.

    For globally-numbered levels, such as "package", this function does nothing and just returns the
    ('nums', 'cpus') tuple.

    For non-globally numbered levels this function  the list of core numbers in 'nums' into '(core,
    package)' pairs. It uses the fact that '_get_level_nums()' returns only package 0 numbers.
    """

    if _is_globally_numbered(lvl):
        return (nums, cpus)

    return ([(num, 0) for num in nums], cpus)

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

        # And do the same, but with string inputs.
        allcpus_str = Human.rangify(allcpus)
        _run_method(method_name, cpuinfo, args=(allcpus_str,), exp_res=exp_res)
        allcpus_str = ",".join(str(cpu) for cpu in allcpus)
        _run_method(method_name, cpuinfo, args=(allcpus_str,), exp_res=exp_res)

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
        kwargs = {"packages" : nums[1]}
        exp_res = _test_div_create_exp_res(lvl, [], num0_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

        exp_cpus = []
        for cpu in allcpus:
            if cpu not in num0_cpus:
                exp_cpus.append(cpu)

        # Resolving all CPUs but for only for the first package.
        args = (allcpus,)
        kwargs = {"packages" : nums[0]}
        exp_res = _test_div_create_exp_res(lvl, nums[0:1], exp_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

def test_cpuinfo_div(proc):
    """
    Test the following 'CPUInfo' class methods:
      * 'cpus_div_packages()'
      * 'cpus_div_dies()'
      * 'cpus_div_cores()'
    """

    for cpuinfo in _get_cpuinfos(proc):
        _test_cpuinfo_div(cpuinfo)
