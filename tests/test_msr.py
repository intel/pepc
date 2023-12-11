#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Unittests for the public methods of the 'MSR' module."""

import pytest
import msr_common
from msr_common import get_params # pylint: disable=unused-import
from pepclibs.msr.TurboRatioLimit import MSR_TURBO_RATIO_LIMIT
from pepclibs.msr.TurboRatioLimit1 import MSR_TURBO_RATIO_LIMIT1
from pepclibs.helperlibs.Exceptions import Error

def _get_msr_test_params(params, include_ro=True, include_rw=True):
    """
    Yields the dictionary with information that should be used for testing MSR module methods. The
    dictionary has following keys:
      * addr - the MSR register address.
      * bits - list of bit ranges in 'addr' to test. This is a list of tuples. If 'include_ro' is
               'False', then read-only MSR bit ranges are not included. If 'include_rw' is False,
               then readable and writable MSR bit ranges are not included.
      * sname - scope name (e.g. "package", "core").
    """

    for addr, features in params["msrs"].items():
        for finfo in features.values():
            if finfo.get("writable"):
                if not include_rw:
                    continue
            elif not include_ro:
                continue

            if not finfo["bits"]:
                continue

            yield {"addr": addr, "bits": finfo["bits"], "sname": finfo["sname"]}

def _bits_to_mask(bits):
    """
    Convert list of tuples to bit mask. You can refer to '_get_msr_test_params()' for the details on
    the list of tuples.
    """

    mask = 0
    bits_cnt = (bits[0] - bits[1]) + 1
    max_val = (1 << bits_cnt) - 1
    mask |= max_val << bits[1]
    return mask

def _get_good_msr_cpu_nums(params):
    """Yield good CPU numbers."""

    allcpus = params["cpus"]
    medidx = int(len(allcpus) / 2)
    for cpu in (allcpus[0], allcpus[medidx], allcpus[-1]):
        yield cpu

def _test_msr_read_good(params):
    """Test 'read()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu, _ in msr.read(tp["addr"], cpus=params["testcpus"], sname=tp["sname"]):
                assert cpu in params["testcpus"]

            read_cpus = []
            for cpu, _ in msr.read(tp["addr"], sname=tp["sname"]):
                read_cpus.append(cpu)
            assert read_cpus == params["cpus"]

def _test_msr_read_bad(params):
    """Test 'read()' method for bad option values."""

    for msr in msr_common.get_msr_objs(params):
        tp = next(_get_msr_test_params(params))
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                for cpu, _ in msr.read(tp["addr"], cpus=[bad_cpu], sname=tp["sname"]):
                    assert cpu == bad_cpu

def test_msr_read(params):
    """Test the 'read()' method of the 'MSR' class."""

    _test_msr_read_good(params)
    _test_msr_read_bad(params)

def _test_msr_write_good(params):
    """Test 'write()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            val = msr.read_cpu(tp["addr"], params["testcpus"][0], sname=tp["sname"])
            mask = _bits_to_mask(tp["bits"])
            newval = mask ^ val
            msr.write(tp["addr"], newval, cpus=params["testcpus"], sname=tp["sname"])

            for cpu, val in msr.read(tp["addr"], cpus=params["testcpus"], sname=tp["sname"]):
                assert cpu in params["testcpus"]
                assert val == newval

            msr.write(tp["addr"], val, sname=tp["sname"])
            for cpu, newval in msr.read(tp["addr"], sname=tp["sname"]):
                assert cpu in params["cpus"]
                assert val == newval

def _test_msr_write_bad(params):
    """Test 'write()' method for bad option values."""

    tp = next(_get_msr_test_params(params))

    for msr in msr_common.get_msr_objs(params):
        val = msr.read_cpu(tp["addr"], params["testcpus"][0], sname=tp["sname"])
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.write(tp["addr"], val, cpus=[bad_cpu], sname=tp["sname"])

    # Following test will expect failure when writing to readonly MSR. On emulated host, such writes
    # don't fail.
    if params["hostname"] == "emulation":
        return

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_rw=False):
            # Writes to Turbo MSRs pass, skip them.
            if tp["addr"] in (MSR_TURBO_RATIO_LIMIT, MSR_TURBO_RATIO_LIMIT1):
                continue

            val = msr.read_cpu(tp["addr"], params["testcpus"][0], sname=tp["sname"])
            mask = _bits_to_mask(tp["bits"])
            with pytest.raises(Error):
                msr.write(tp["addr"], mask ^ val, cpus=params["testcpus"], sname=tp["sname"])

def test_msr_write(params):
    """Test the 'write()' method of the 'MSR' class."""

    _test_msr_write_good(params)
    _test_msr_write_bad(params)

def _test_msr_read_cpu_good(params):
    """Test the 'read_cpu()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu in _get_good_msr_cpu_nums(params):
                msr.read_cpu(tp["addr"], cpu=cpu, sname=tp["sname"])

def _test_msr_read_cpu_bad(params):
    """Test the 'read_cpu()' method for bad option values."""

    tp = next(_get_msr_test_params(params))
    for msr in msr_common.get_msr_objs(params):
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.read_cpu(tp["addr"], cpu=bad_cpu, sname=tp["sname"])

def test_msr_read_cpu(params):
    """Test the 'read_cpu()' method."""

    _test_msr_read_cpu_good(params)
    _test_msr_read_cpu_bad(params)

def _test_msr_write_cpu_good(params):
    """Test the 'write_cpu()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])
            for cpu in _get_good_msr_cpu_nums(params):
                val = msr.read_cpu(tp["addr"], cpu, sname=tp["sname"])
                newval = mask ^ val
                msr.write_cpu(tp["addr"], newval, cpu, sname=tp["sname"])
                assert newval == msr.read_cpu(tp["addr"], cpu, sname=tp["sname"])

def _test_msr_write_cpu_bad(params):
    """Test the 'write_cpu()' method for bad option values."""

    tp = next(_get_msr_test_params(params))

    for msr in msr_common.get_msr_objs(params):
        val = msr.read_cpu(tp["addr"], params["testcpus"][0], sname=tp["sname"])
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.write_cpu(tp["addr"], val, bad_cpu, sname=tp["sname"])

def test_msr_write_cpu(params):
    """Test the 'write_cpu()' method."""

    _test_msr_write_cpu_good(params)
    _test_msr_write_cpu_bad(params)

def _test_msr_read_bits_good(params):
    """Test 'read_bits()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], cpus=params["testcpus"],
                                        sname=tp["sname"]):
                assert cpu in params["testcpus"]

        for tp in _get_msr_test_params(params, include_ro=False):
            read_cpus = []
            for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], sname=tp["sname"]):
                read_cpus.append(cpu)
            assert read_cpus == params["cpus"]

            # No need to test 'read_bits()' with default 'cpus' argument multiple times.
            break

def _test_msr_read_bits_bad(params):
    """Test 'read_bits()' method for bad option values."""

    tp = next(_get_msr_test_params(params))
    cpu = params["testcpus"][0]

    for msr in msr_common.get_msr_objs(params):
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], cpus=[bad_cpu],
                                            sname=tp["sname"]):
                    assert cpu == bad_cpu

        bad_bits = (msr.regbits + 1, 0)
        with pytest.raises(Error):
            for cpu1, _ in msr.read_bits(tp["addr"], bad_bits, cpus=[cpu], sname=tp["sname"]):
                assert cpu == cpu1

def test_msr_read_bits(params):
    """Test the 'read_bits()' method."""

    _test_msr_read_bits_good(params)
    _test_msr_read_bits_bad(params)

def _test_msr_write_bits_good(params):
    """Test the 'write_bits()' method with good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])

            for cpu, val in msr.read(tp["addr"], cpus=params["testcpus"], sname=tp["sname"]):
                newval = msr.get_bits(val ^ mask, tp["bits"])
                msr.write_bits(tp["addr"], tp["bits"], newval, cpus=[cpu], sname=tp["sname"])

                for _, bval in msr.read_bits(tp["addr"], tp["bits"], cpus=[cpu], sname=tp["sname"]):
                    assert newval == bval

            val = msr.read_cpu(tp["addr"], params["testcpus"][0], sname=tp["sname"])
            newval = msr.get_bits(val ^ mask, tp["bits"])
            msr.write_bits(tp["addr"], tp["bits"], newval, sname=tp["sname"])
            for _, val in msr.read_bits(tp["addr"], tp["bits"], sname=tp["sname"]):
                assert val == newval

def _test_msr_write_bits_bad(params):
    """Test the 'write_bits()' method with bad option values."""

    tp = next(_get_msr_test_params(params))
    cpu = params["testcpus"][0]

    for msr in msr_common.get_msr_objs(params):
        val = msr.read(tp["addr"], cpus=cpu, sname=tp["sname"])

        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.write_bits(tp["addr"], tp["bits"], val, cpus=[bad_cpu], sname=tp["sname"])

        bits_cnt = (tp["bits"][0] - tp["bits"][1]) + 1
        bad_val = 1 << bits_cnt
        with pytest.raises(Error):
            msr.write_bits(tp["addr"], tp["bits"], bad_val, cpus=[cpu], sname=tp["sname"])

        bad_bits = (msr.regbits + 1, 0)
        with pytest.raises(Error):
            msr.write_bits(tp["addr"], bad_bits, val, cpus=[cpu], sname=tp["sname"])

        # Repeating this negative test for every CPU is an overkill.
        break

def test_msr_write_bits(params):
    """Test the 'write_bits()' method."""

    _test_msr_write_bits_good(params)
    _test_msr_write_bits_bad(params)

def _test_msr_read_cpu_bits_good(params):
    """Test 'read_cpu_bits()' method for good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu in _get_good_msr_cpu_nums(params):
                msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, sname=tp["sname"])

def _test_msr_read_cpu_bits_bad(params):
    """Test 'read_cpu_bits()' method for bad option values."""

    tp = next(_get_msr_test_params(params))
    cpu = params["testcpus"][0]

    for msr in msr_common.get_msr_objs(params):
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.read_cpu_bits(tp["addr"], tp["bits"], bad_cpu, sname=tp["sname"])

        bad_bits = (msr.regbits + 1, 0)
        with pytest.raises(Error):
            msr.read_cpu_bits(tp["addr"], bad_bits, cpu, sname=tp["sname"])

        # Repeating this negative test for every CPU is an overkill.
        break

def test_msr_read_cpu_bits(params):
    """Test the 'read_cpu_bits()' method."""

    _test_msr_read_cpu_bits_good(params)
    _test_msr_read_cpu_bits_bad(params)

def _test_msr_write_cpu_bits_good(params):
    """Test the 'write_cpu_bits()' method with good option values."""

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])
            for cpu in _get_good_msr_cpu_nums(params):
                val = msr.read_cpu(tp["addr"], cpu, sname=tp["sname"])
                newval = msr.get_bits(val ^ mask, tp["bits"])
                msr.write_cpu_bits(tp["addr"], tp["bits"], newval, cpu, sname=tp["sname"])

                val = msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, sname=tp["sname"])
                assert val == newval

def _test_msr_write_cpu_bits_bad(params):
    """Test the 'write_cpu_bits()' method with bad option values."""

    tp = next(_get_msr_test_params(params))
    cpu = params["testcpus"][0]

    for msr in msr_common.get_msr_objs(params):
        val = msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, sname=tp["sname"])
        for bad_cpu in msr_common.get_bad_cpu_nums(params):
            with pytest.raises(Error):
                msr.write_cpu_bits(tp["addr"], tp["bits"], val, bad_cpu, sname=tp["sname"])

        bits_cnt = (tp["bits"][0] - tp["bits"][1]) + 1
        bad_val = 1 << bits_cnt
        with pytest.raises(Error):
            msr.write_cpu_bits(tp["addr"], tp["bits"], bad_val, cpu, sname=tp["sname"])

        bad_bits = (msr.regbits + 1, 0)
        with pytest.raises(Error):
            msr.write_cpu_bits(tp["addr"], bad_bits, val, cpu, sname=tp["sname"])

        # Repeating this negative test for every CPU is an overkill.
        break

def test_msr_write_cpu_bits(params):
    """Test the 'write_cpu_bits()' method."""

    _test_msr_write_cpu_bits_good(params)
    _test_msr_write_cpu_bits_bad(params)
