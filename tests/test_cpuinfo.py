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

def _run_method(name, cpuinfo, args=None, kwargs=None, exp_res=_IGNORE):
    """
    Run the 'name' method of the 'cpuinfo' object. The arguments are as follows.
      * name - the name of the method.
      * cpuinfo - the 'CPUInfo' object.
      * args - the ordered arguments to pass down to the method.
      * kwargs - keyword arguments to pass down to the method.
      * exp_res - the expected result (not checked by default).

    The 'name' method is called and tested only if it exists in 'cpuinfo'. Returns the result of the
    'name' method and 'None' if it does not exist.
    """

    if args is None:
        args = []

    if not isinstance(args, list):
        args = [args]

    if kwargs is None:
        kwargs = {}

    res = None
    method = getattr(cpuinfo, name, None)
    if method:
        res = method(*args, **kwargs)
        if exp_res is not _IGNORE:
            assert res == exp_res, f"'{name}()' is expected to return '{exp_res}', got '{res}'"

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
    _run_method("get_cpu_siblings", cpuinfo, args=0)

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
    with pytest.raises(Error):
        _run_method("get_cpu_siblings", cpuinfo, args=bad_cpu)

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

def _test_convert_good(cpuinfo):
    """Test public convert methods of the 'CPUInfo' class with good option values."""

    for from_lvl, nums in _get_levels_and_nums(cpuinfo):
        # We have two types of conversion methods to convert values between different "levels"
        # defined in 'CPUInfo.LEVELS'. We have methods for converting single value to other level,
        # e.g. 'package_to_cpus()'. And we have methods for converting multiple values to other
        # level, e.g. 'packages_to_cpus()'.
        # Methods to convert single value accept single integer in different forms, and methods
        # converting multiple values accept also ingeters in lists.
        single_args = []
        for idx in 0, -1:
            single_args += [nums[idx], f"{nums[idx]}", f" {nums[idx]} ", [nums[idx]]]

        multi_args = []
        for idx in 0, -1:
            multi_args += [f"{nums[idx]},", [nums[idx]]]

            if len(nums) > 1:
                multi_args += [(nums[-1], nums[0]),
                               f"{nums[0]}, {nums[-1]}",
                               f"{nums[0]}, {nums[-1]},",
                               f" {nums[0]}, {nums[-1]} ",]

        for to_lvl, nums in _get_levels_and_nums(cpuinfo):
            # Test normalize method of single value.
            method_name = f"{from_lvl}_to_{to_lvl}s"
            for args in single_args:
                _run_method(method_name, cpuinfo, args=args)

            # Test convert method for multiple values.
            method_name = f"{from_lvl}s_to_{to_lvl}s"
            _run_method(method_name, cpuinfo, exp_res=nums)

            for args in multi_args:
                _run_method(method_name, cpuinfo, args=args)

def _test_convert_bad(cpuinfo):
    """Same as '_test_converrt_good()', but use bad option values."""

    for from_lvl, from_nums in _get_levels_and_nums(cpuinfo):
        bad_num = from_nums[-1] + 1

        for to_lvl in _get_levels():
            method_name = f"{from_lvl}_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (bad_num, f"{bad_num}", f"{from_nums[0]}, ", (bad_num,))

                for args in bad_args:
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs)

            method_name = f"{from_lvl}s_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (-1, bad_num, (-1, bad_num), "-1", (bad_num,))

                for args in bad_args:
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs)

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
            _run_method(method_name, cpuinfo, args=args, exp_res=exp_res[0])

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
            _run_method(method_name, cpuinfo, args=args, exp_res=exp_res)

def _test_normalize_bad(cpuinfo):
    """Same as '_test_normalize_good()', but use bad option values."""

    for lvl, nums in _get_levels_and_nums(cpuinfo):
        bad_num = nums[-1] + 1

        method_name  = f"normalize_{lvl}"
        if getattr(cpuinfo, method_name, None):
            bad_args = (-1, "-1", f"{nums[0]},", bad_num, [bad_num])

            for args in bad_args:
                with pytest.raises(Error):
                    _run_method(method_name, cpuinfo, args=args)

        method_name  = f"normalize_{lvl}s"
        if getattr(cpuinfo, method_name, None):
            bad_args = (f"{nums[0]}, {nums[-1]}, ",
                        f", {nums[0]}, {nums[-1]}, ",
                        f" {nums[0]}-{nums[-1]}, ",
                        f" {nums[0]}, {nums[-1]}, ,",
                        [[nums[0], bad_num]])

            for args in bad_args:
                with pytest.raises(Error):
                    _run_method(method_name, cpuinfo, args=args)

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
