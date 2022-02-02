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
        if not getattr(cpuinfo, f"get_{lvl}s", None):
            continue

        yield (lvl.lower(), _get_level_nums(lvl, cpuinfo))


def _get_bad_orders():
    """Yield bad 'order' argument values."""

    for order in "CPUS", "CORE", "nodes", "pkg":
        yield order

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

    res = None
    method = getattr(cpuinfo, name, None)
    if method:
        try:
            res = method(*args, **kwargs)
            if exp_res is not _IGNORE:
                assert res == exp_res, f"method '{name}()' returned:\n\t{res}\n" \
                                       f"But it was expected to return:\n\t'{exp_res}'"
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
                          f"but it was expected to raise the following exception type: " \
                          f"{type(exp_exc)}"

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

def test_get(cpuinfo):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages()'
      * 'get_cpus()'
      * 'get_offline_cpus()'
      * 'get_cpu_siblings()'
    """

    _test_get_good(cpuinfo)
    _test_get_bad(cpuinfo)

def test_get_count(cpuinfo):
    """
    Test the following 'CPUInfo' class methods:
      * 'get_packages_count()'
      * 'get_cpus_count()'
      * 'get_offline_cpus_count()'
    """

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        _run_method(f"get_{lvl}s_count", cpuinfo, exp_res=len(nums))

    offline_cpus = cpuinfo.get_offline_cpus()
    _run_method("get_offline_cpus_count", cpuinfo, exp_res=len(offline_cpus))

def _test_convert_get_nums(cpuinfo, lvl):
    """
    This is a helper function for '_test_convert_good()' and '_test_convert_bad()' which returns
    level 'lvl' numbers.

    Levels like "package" have global numbering, and this method just returns the result of
    'get_packages()' in this case.

    Some levels like "die" have per-package numbering, in which case this method returns all die
    numbers in the first package.

    Returns 'None' level numbers could not be found out, because there are no 'CPUInfo' methods for
    getting them.
    """

    nums = None
    if getattr(cpuinfo, f"get_{lvl}s", None):
        nums = _get_level_nums(lvl, cpuinfo)
    else:
        # Some levels do not have 'get_<lvl>()' method (e.g., "core"). In this case, we have to
        # fall back for getting level numbers for the first package.
        method_name = f"package_to_{lvl}s"
        if getattr(cpuinfo, method_name, None):
            allpkgs = cpuinfo.get_packages()
            nums = _run_method(method_name, cpuinfo, args=(allpkgs[0],))

    return nums

def _test_convert_good(cpuinfo):
    """Test public convert methods of the 'CPUInfo' class with good option values."""

    for from_lvl in _get_levels():
        from_nums = _test_convert_get_nums(cpuinfo, from_lvl)
        if from_nums is None:
            continue

        # We have two types of conversion methods to convert values between different "levels"
        # defined in 'CPUInfo.LEVELS'. We have methods for converting single value to other level,
        # e.g. 'package_to_cpus()'. And we have methods for converting multiple values to other
        # level, e.g. 'packages_to_cpus()'.
        # Methods to convert single value accept single integer in different forms, and methods
        # converting multiple values accept also ingeters in lists.


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
    """Same as '_test_converrt_good()', but use bad option values."""

    for from_lvl in _get_levels():
        from_nums = _test_convert_get_nums(cpuinfo, from_lvl)
        if from_nums is None:
            continue

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

def test_convert(cpuinfo):
    """
    Test the following 'CPUInfo' class methods:
      * 'packages_to_cpus()'
      * 'package_to_nodes()'
      * 'package_to_cores()'
      * 'cores_to_cpus()'
    """

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

def test_normalize(cpuinfo):
    """
    Test the following 'CPUInfo' class methods:
      * 'normalize_packages()'
      * 'normalize_package()'
      * 'normalize_cpus()'
      * 'normalize_cpu()'
    """

    _test_normalize_good(cpuinfo)
    _test_normalize_bad(cpuinfo)

def test_div(cpuinfo):
    """
    Test the following 'CPUInfo' class methods:
      * 'cpus_div_packages()'
    """

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        method_name  = f"cpus_div_{lvl}s"
        if not getattr(cpuinfo, method_name, None):
            continue

        # Note! In the comments below we'll assume that 'lvl' is packages, for simplicity. However,
        # it may be anythine else, like 'cores'.

        # Resolving an empty CPUs list.
        exp_res = ([], [])
        _run_method(method_name, cpuinfo, args=([],), exp_res=exp_res)

        # Resolving all CPUs in all packages.
        allcpus = cpuinfo.get_cpus()
        exp_res = (nums, [])
        _run_method(method_name, cpuinfo, args=(allcpus,), exp_res=exp_res)

        # And do the same, but with string inputs.
        allcpus_str = Human.rangify(allcpus)
        _run_method(method_name, cpuinfo, args=(allcpus_str,), exp_res=exp_res)
        allcpus_str = ",".join(str(cpu) for cpu in allcpus)
        _run_method(method_name, cpuinfo, args=(allcpus_str,), exp_res=exp_res)

        if len(allcpus) < 2:
            # The rest of the test-cases require more than one CPU per package.
            continue

        # Resolving all CPUs except for the very first one.
        rnums, rcpus = _run_method(method_name, cpuinfo, args=(allcpus[1:],))
        assert len(rnums) == len(nums) - 1 and len(rcpus) > 0, \
               f"bad result from '{method_name}({allcpus[1:]})':\n\t(rnums, rcpus)\n"

        # Resolving a single CPU - the first and the last.
        exp_res = ([], allcpus[0:1])
        _run_method(method_name, cpuinfo, args=(allcpus[0:1],), exp_res=exp_res)
        exp_res = ([], allcpus[-1:])
        _run_method(method_name, cpuinfo, args=(allcpus[-1:],), exp_res=exp_res)

        if len(nums) < 2:
            # The rest of the test-cases requre more than one package.
            continue

        # Get the list of CPUs in the first package.
        num0_cpus = _run_method(f"{lvl}_to_cpus", cpuinfo, args=(nums[0],))
        if num0_cpus is None:
            # The '<lvl>_to_cpus()' method does not exist.
            continue

        # Resolving all CPUs in the first package.
        exp_res = (nums[0:1], [])
        _run_method(method_name, cpuinfo, args=(num0_cpus,), exp_res=exp_res)

        # Same, but without the first CPU in the first package.
        exp_res = ([], num0_cpus[1:])
        _run_method(method_name, cpuinfo, args=(num0_cpus[1:],), exp_res=exp_res)

        # Resolving first package CPUs but for the second package.
        args = (num0_cpus,)
        kwargs = {"packages" : nums[1]}
        exp_res = ([], num0_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)

        # Get the list of CPUs in the second package.
        num1_cpus = _run_method(f"{lvl}_to_cpus", cpuinfo, args=(nums[1],))

        # Resolving all CPUs but for only for the first package.
        args = (allcpus,)
        kwargs = {"packages" : nums[0]}
        exp_res = (nums[0:1], num1_cpus)
        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, exp_res=exp_res)
