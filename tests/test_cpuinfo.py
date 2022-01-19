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

from common import fixture_proc, fixture_cpuinfo # pylint: disable=unused-import
from pepclibs import CPUInfo

def get_levels():
    """Yield 'CPUInfo.LEVEL' values as a lowercase strings."""

    for lvl in CPUInfo.LEVELS:
        yield lvl.lower()

def get_level_nums(lvl, cpuinfo, order=None, default=None):
    """
    Return numbers of level 'lvl', where the 'lvl' is one of the levels in CPUInfo.LEVELS (e.g.
    number of packages). The 'order' argument can be used to control the order of returned numbers.
    By default, the 'order' is the same as the level 'lvl'. The numbers are returned as a list of
    integers. If the 'lvl' does not have 'get' method, returns the 'default'.
    """

    if not isinstance(default, list):
        default = [default]
    nums=default

    if order is None:
        order = lvl

    # The 'cpu' level is special.
    order = order.replace("cpu", "CPU")

    get_method = getattr(cpuinfo, f"get_{lvl}s", None)
    if get_method:
        nums = get_method(order=order)

    return nums

def run_method(name, cpuinfo, args=None, kwargs=None, exp_res=None, ignore_res=False):
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

def test_get(cpuinfo):
    """
    Test following 'get' methods of the 'CPUInfo' class:
        * get_packages()
        * get_cpus()
        * get_offline_cpus()
        * get_cpu_siblings()
    """

    for lvl in get_levels():
        nums = get_level_nums(lvl, cpuinfo)
        assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"

        for order in get_levels():
            prev_nums = nums
            nums = get_level_nums(lvl, cpuinfo, order=order)
            assert nums, f"'get_{lvl}s()' is expected to return list of {lvl}s, got: '{nums}'"
            nums = sorted(nums)
            assert nums == prev_nums, f"'get_{lvl}s()' was expected to return '{prev_nums}', got " \
                                      f"'{nums}'"

    run_method("get_offline_cpus", cpuinfo, ignore_res=True)
    run_method("get_cpu_siblings", cpuinfo, args=0, ignore_res=True)

def test_get_count(cpuinfo):
    """
    Test following 'get_count' methods of the 'CPUInfo' class:
        * get_packages_count()
        * get_cpus_count()
        * get_offline_cpus_count()
    """

    for lvl in get_levels():
        nums = get_level_nums(lvl, cpuinfo)
        run_method(f"get_{lvl}s_count", cpuinfo, exp_res=len(nums))

    offline_cpus = cpuinfo.get_offline_cpus()
    run_method("get_offline_cpus_count", cpuinfo, exp_res=len(offline_cpus))

def test_convert(cpuinfo):
    """
    Test following conversion methods of the 'CPUInfo' class:
        * packages_to_cpus()
        * package_to_nodes()
        * package_to_cores()
        * cores_to_cpus()
    """

    for from_lvl in get_levels():
        nums = get_level_nums(from_lvl, cpuinfo, default=[0])

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

        for to_lvl in get_levels():
            nums = get_level_nums(to_lvl, cpuinfo, default=[0])

            # Test normalize method of single value.
            method_name = f"{from_lvl}_to_{to_lvl}s"
            for args in single_args:
                run_method(method_name, cpuinfo, args=args, ignore_res=True)

            # Test convert method for multiple values.
            method_name = f"{from_lvl}s_to_{to_lvl}s"
            run_method(method_name, cpuinfo, exp_res=nums)

            for args in multi_args:
                run_method(method_name, cpuinfo, args=args, ignore_res=True)

def test_normalize(cpuinfo):
    """
    Test following 'normalize' methods of the 'CPUInfo' class:
        * normalize_packages()
        * normalize_package()
        * normalize_cpus()
        * normalize_cpu()
    """

    for lvl in get_levels():
        nums = get_level_nums(lvl, cpuinfo)

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
            run_method(method_name, cpuinfo, args=args, exp_res=exp_res[0])

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
            run_method(method_name, cpuinfo, args=args, exp_res=exp_res)
