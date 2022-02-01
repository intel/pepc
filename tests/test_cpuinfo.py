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

def _get_levels():
    """Yield 'CPUInfo.LEVEL' values as a lowercase strings."""

    for lvl in CPUInfo.LEVELS:
        yield lvl.lower()

def _get_level_nums(lvl, cpuinfo, order=None, default=None):
    """
    Return numbers of level 'lvl', where the 'lvl' is one of the levels in CPUInfo.LEVELS (e.g.
    number of packages). The 'order' argument can be used to control the order of returned numbers.
    By default, the 'order' is the same as the level 'lvl'. The numbers are returned as a list of
    integers. If the 'lvl' does not have 'get' method, returns the 'default'.
    """

    if not isinstance(default, list):
        default = [default]
    nums = default

    if order is None:
        order = lvl

    # The 'cpu' level is special.
    order = order.replace("cpu", "CPU")

    get_method = getattr(cpuinfo, f"get_{lvl}s", None)
    if get_method:
        nums = get_method(order=order)

    return nums

def _get_bad_orders():
    """Yield bad 'order' argument values."""

    for order in "CPUS", "CORE", "nodes", "pkg":
        yield order

def _run_method(name, cpuinfo, args=None, kwargs=None, exp_res=None, ignore_res=False):
    """
    Run the '<name>()' method of the 'CPUInfo' class. The arguments are as follows:
      * name - The name of the method.
      * cpuinfo - The 'CPUInfo' object.
      * args - The ordered arguments to pass down to the method.
      * kwargs - Keyword arguments to pass down to the method.
      * exp_res - The expected result.
      * ignore_res - If 'True', the method result is not compared against 'exp_res'.
    The method is called and tested only if it exists in the 'CPUInfo' object.
    """

    if args is None:
        args = []

    if not isinstance(args, list):
        args = [args]

    if kwargs is None:
        kwargs = {}

    method = getattr(cpuinfo, name, None)
    if method:
        res = method(*args, **kwargs)
        if ignore_res:
            return

        assert res == exp_res, f"'{name}()' is expected to return '{exp_res}', got '{res}'"

def _test_get_good(cpuinfo):
    """Test 'get' methods for bad option values."""

    for lvl in _get_levels():
        nums = _get_level_nums(lvl, cpuinfo)
        assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"
        ref_nums = sorted(nums)

        for order in _get_levels():
            nums = _get_level_nums(lvl, cpuinfo, order=order)
            assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"
            nums = sorted(nums)
            assert nums == ref_nums, f"'get_{lvl}s()' was expected to return '{ref_nums}', " \
                                     f"got '{nums}'"

    _run_method("get_offline_cpus", cpuinfo, ignore_res=True)
    _run_method("get_cpu_siblings", cpuinfo, args=0, ignore_res=True)

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
        _run_method("get_cpu_siblings", cpuinfo, args=bad_cpu, ignore_res=True)

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

    for lvl in _get_levels():
        nums = _get_level_nums(lvl, cpuinfo)
        _run_method(f"get_{lvl}s_count", cpuinfo, exp_res=len(nums))

    offline_cpus = cpuinfo.get_offline_cpus()
    _run_method("get_offline_cpus_count", cpuinfo, exp_res=len(offline_cpus))

def _test_convert_good(cpuinfo):
    """Test public convert methods of the 'CPUInfo' class with good option values."""

    for from_lvl in _get_levels():
        nums = _get_level_nums(from_lvl, cpuinfo, default=[0])

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

        for to_lvl in _get_levels():
            nums = _get_level_nums(to_lvl, cpuinfo, default=[0])

            # Test normalize method of single value.
            method_name = f"{from_lvl}_to_{to_lvl}s"
            for args in single_args:
                _run_method(method_name, cpuinfo, args=args, ignore_res=True)

            # Test convert method for multiple values.
            method_name = f"{from_lvl}s_to_{to_lvl}s"
            _run_method(method_name, cpuinfo, exp_res=nums)

            for args in multi_args:
                _run_method(method_name, cpuinfo, args=args, ignore_res=True)

def _test_convert_bad(cpuinfo):
    """Same as '_test_converrt_good()', but use bad option values."""

    for from_lvl in _get_levels():
        from_nums = _get_level_nums(from_lvl, cpuinfo, default="NA")
        if "NA" in from_nums:
            continue

        bad_num = from_nums[-1] + 1

        for to_lvl in _get_levels():
            method_name = f"{from_lvl}_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (bad_num, f"{bad_num}", f"{from_nums[0]}, ", (bad_num,))

                for args in bad_args:
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, ignore_res=True)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, ignore_res=True)

            method_name = f"{from_lvl}s_to_{to_lvl}s"

            if getattr(cpuinfo, method_name, None):
                bad_args = (-1, bad_num, (-1, bad_num), "-1", (bad_num,))

                for args in bad_args:
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, ignore_res=True)

                args = from_nums[0]
                for order in _get_bad_orders():
                    kwargs = {"order": order}
                    with pytest.raises(Error):
                        _run_method(method_name, cpuinfo, args=args, kwargs=kwargs, ignore_res=True)

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

    for lvl in _get_levels():
        nums = _get_level_nums(lvl, cpuinfo)

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

    for lvl in _get_levels():
        nums = _get_level_nums(lvl, cpuinfo, default="NA")
        if "NA" in nums:
            continue

        bad_num = nums[-1] + 1

        method_name  = f"normalize_{lvl}"
        if getattr(cpuinfo, method_name, None):
            bad_args = (-1, "-1", f"{nums[0]},", bad_num, [bad_num])

            for args in bad_args:
                with pytest.raises(Error):
                    _run_method(method_name, cpuinfo, args=args, ignore_res=True)

        method_name  = f"normalize_{lvl}s"
        if getattr(cpuinfo, method_name, None):
            bad_args = (f"{nums[0]}, {nums[-1]}, ",
                        f", {nums[0]}, {nums[-1]}, ",
                        f" {nums[0]}-{nums[-1]}, ",
                        f" {nums[0]}, {nums[-1]}, ,",
                        [[nums[0], bad_num]])

            for args in bad_args:
                with pytest.raises(Error):
                    _run_method(method_name, cpuinfo, args=args, ignore_res=True)

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
