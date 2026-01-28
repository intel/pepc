#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test public methods of the 'MSR' module."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pytest
from tests import common, msr_common
from tests.msr_common import get_params # pylint: disable=unused-import

from pepclibs.msr.TurboRatioLimit import MSR_TURBO_RATIO_LIMIT
from pepclibs.msr.TurboRatioLimit1 import MSR_TURBO_RATIO_LIMIT1
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import TypedDict, Generator
    from pepclibs.CPUInfoTypes import ScopeNameType
    from tests.msr_common import FeaturedMSRTestParamsTypedDict

    class _MSRTestParamsTypedDict(TypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            addr: MSR register address.
            bits: Bit range in the register to test (MSB, LSB).
            sname: Scope name (e.g., "package", "core").
        """

        addr: int
        bits: tuple[int, int]
        sname: ScopeNameType

def _get_msr_test_params(params: FeaturedMSRTestParamsTypedDict,
                         include_ro: bool = True,
                         include_rw: bool = True) -> Generator[_MSRTestParamsTypedDict, None, None]:
    """
    Yield MSR module test parameters.

    Args:
        params: The common test parameters dictionary.
        include_ro: If True, include read-only MSR bit ranges.
        include_rw: If True, include readable and writable MSR bit ranges.

    Yields:
        A dictionary with MSR test parameters.
    """

    for addr, features in params["finfo"].items():
        for finfo in features.values():
            if finfo.get("writable"):
                if not include_rw:
                    continue
            elif not include_ro:
                continue

            if not common.is_emulated(params["pman"]) and include_rw:
                continue

            if not finfo["bits"]:
                continue

            yield {"addr": addr, "bits": finfo["bits"], "sname": finfo["sname"]}

def _bits_to_mask(bits: tuple[int, int]) -> int:
    """
    Generate a bitmask for a given bit range.

    Args:
        bits: The bit range (MSB, LSB) to create the bitmask for.

    Returns:
        The bitmask for the specified bit range.
    """

    mask = 0
    bits_cnt = (bits[0] - bits[1]) + 1
    max_val = (1 << bits_cnt) - 1
    mask |= max_val << bits[1]
    return mask

def test_msr_read_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu, _ in msr.read(tp["addr"], cpus=params["testcpus"], iosname=tp["sname"]):
                assert cpu in params["testcpus"]

            read_cpus = []
            for cpu, _ in msr.read(tp["addr"], iosname=tp["sname"]):
                read_cpus.append(cpu)
            assert read_cpus == params["cpus"]

def test_msr_read_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            for bad_cpus in msr_common.get_bad_cpus_nums(params):
                with pytest.raises(Error):
                    for _ in msr.read(tp["addr"], cpus=bad_cpus, iosname=tp["sname"]):
                        pass
        break

def test_msr_write_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            val = msr.read_cpu(tp["addr"], params["testcpus"][0], iosname=tp["sname"])
            mask = _bits_to_mask(tp["bits"])
            newval = mask ^ val
            msr.write(tp["addr"], newval, cpus=params["testcpus"], iosname=tp["sname"])

            for cpu, val in msr.read(tp["addr"], cpus=params["testcpus"], iosname=tp["sname"]):
                assert cpu in params["testcpus"]
                assert val == newval

            msr.write(tp["addr"], val, iosname=tp["sname"])
            for cpu, newval in msr.read(tp["addr"], iosname=tp["sname"]):
                assert cpu in params["cpus"]
                assert val == newval

def test_msr_write_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            val = msr.read_cpu(tp["addr"], params["testcpus"][0], iosname=tp["sname"])
            for bad_cpus in msr_common.get_bad_cpus_nums(params):
                with pytest.raises(Error):
                    msr.write(tp["addr"], val, cpus=bad_cpus, iosname=tp["sname"])
        break

    # Following test will expect failure when writing to readonly MSR. On emulated host, such writes
    # don't fail.
    if common.is_emulated(params["pman"]):
        return

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_rw=False):
            # Writes to Turbo MSRs go through, even thought they are really R/O, skip them.
            if tp["addr"] in (MSR_TURBO_RATIO_LIMIT, MSR_TURBO_RATIO_LIMIT1):
                continue

            val = msr.read_cpu(tp["addr"], params["testcpus"][0], iosname=tp["sname"])
            mask = _bits_to_mask(tp["bits"])
            with pytest.raises(Error):
                msr.write(tp["addr"], mask ^ val, cpus=params["testcpus"], iosname=tp["sname"])

def test_msr_read_cpu_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_cpu()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu in params["testcpus"]:
                msr.read_cpu(tp["addr"], cpu=cpu, iosname=tp["sname"])

def test_msr_read_cpu_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_cpu()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    msr.read_cpu(tp["addr"], cpu=bad_cpu, iosname=tp["sname"])
        break

def test_msr_write_cpu_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_cpu()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])
            for cpu in params["testcpus"]:
                val = msr.read_cpu(tp["addr"], cpu, iosname=tp["sname"])
                newval = mask ^ val
                msr.write_cpu(tp["addr"], newval, cpu, iosname=tp["sname"])
                assert newval == msr.read_cpu(tp["addr"], cpu, iosname=tp["sname"])

def test_msr_write_cpu_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_cpu()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            val = msr.read_cpu(tp["addr"], params["testcpus"][0], iosname=tp["sname"])
            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    msr.write_cpu(tp["addr"], val, bad_cpu, iosname=tp["sname"])
        break

def test_msr_read_bits_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_bits()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], cpus=params["testcpus"],
                                        iosname=tp["sname"]):
                assert cpu in params["testcpus"]

        for tp in _get_msr_test_params(params, include_ro=False):
            read_cpus = []
            for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], iosname=tp["sname"]):
                read_cpus.append(cpu)
            assert read_cpus == params["cpus"]

            # No need to test 'read_bits()' with default 'cpus' argument multiple times.
            break

def test_msr_read_bits_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_bits()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    cpu = params["testcpus"][0]

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    for cpu, _ in msr.read_bits(tp["addr"], tp["bits"], cpus=[bad_cpu],
                                                iosname=tp["sname"]):
                        assert cpu == bad_cpu

            bad_bits = (msr.regbits + 1, 0)
            with pytest.raises(Error):
                for cpu1, _ in msr.read_bits(tp["addr"], bad_bits, cpus=[cpu], iosname=tp["sname"]):
                    assert cpu == cpu1
        break

def test_msr_write_bits_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_bits()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])

            for cpu, val in msr.read(tp["addr"], cpus=params["testcpus"], iosname=tp["sname"]):
                newval = msr.get_bits(val ^ mask, tp["bits"])
                msr.write_bits(tp["addr"], tp["bits"], newval, cpus=[cpu], iosname=tp["sname"])

                for _, bval in msr.read_bits(tp["addr"], tp["bits"], cpus=[cpu],
                                             iosname=tp["sname"]):
                    assert newval == bval

            val = msr.read_cpu(tp["addr"], params["testcpus"][0], iosname=tp["sname"])
            newval = msr.get_bits(val ^ mask, tp["bits"])
            msr.write_bits(tp["addr"], tp["bits"], newval, iosname=tp["sname"])
            for _, val in msr.read_bits(tp["addr"], tp["bits"], iosname=tp["sname"]):
                assert val == newval

def test_msr_write_bits_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_bits()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    cpu = params["testcpus"][0]

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            for cpu, val in msr.read(tp["addr"], cpus=[cpu], iosname=tp["sname"]):
                break
            else:
                continue

            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    msr.write_bits(tp["addr"], tp["bits"], val, cpus=[bad_cpu], iosname=tp["sname"])

            bits_cnt = (tp["bits"][0] - tp["bits"][1]) + 1
            bad_val = 1 << bits_cnt
            with pytest.raises(Error):
                msr.write_bits(tp["addr"], tp["bits"], bad_val, cpus=[cpu], iosname=tp["sname"])

            bad_bits = (msr.regbits + 1, 0)
            with pytest.raises(Error):
                msr.write_bits(tp["addr"], bad_bits, val, cpus=[cpu], iosname=tp["sname"])

            # Repeating this negative test for every CPU is an overkill.
            break
        break

def test_msr_read_cpu_bits_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_cpu_bits()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params):
            for cpu in params["testcpus"]:
                msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, iosname=tp["sname"])

def test_msr_read_cpu_bits_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'read_cpu_bits()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    cpu = params["testcpus"][0]

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    msr.read_cpu_bits(tp["addr"], tp["bits"], bad_cpu, iosname=tp["sname"])

            bad_bits = (msr.regbits + 1, 0)
            with pytest.raises(Error):
                msr.read_cpu_bits(tp["addr"], bad_bits, cpu, iosname=tp["sname"])

            # Repeating this negative test for every CPU is an overkill.
            break
        break

def test_msr_write_cpu_bits_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_cpu_bits()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in msr_common.get_msr_objs(params):
        for tp in _get_msr_test_params(params, include_ro=False):
            mask = _bits_to_mask(tp["bits"])
            for cpu in params["testcpus"]:
                val = msr.read_cpu(tp["addr"], cpu, iosname=tp["sname"])
                newval = msr.get_bits(val ^ mask, tp["bits"])
                msr.write_cpu_bits(tp["addr"], tp["bits"], newval, cpu, iosname=tp["sname"])

                val = msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, iosname=tp["sname"])
                assert val == newval

def test_msr_write_cpu_bits_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test the 'write_cpu_bits()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    cpu = params["testcpus"][0]

    for tp in _get_msr_test_params(params):
        for msr in msr_common.get_msr_objs(params):
            val = msr.read_cpu_bits(tp["addr"], tp["bits"], cpu, iosname=tp["sname"])
            for bad_cpu in msr_common.get_bad_cpu_nums(params):
                with pytest.raises(Error):
                    msr.write_cpu_bits(tp["addr"], tp["bits"], val, bad_cpu, iosname=tp["sname"])

            bits_cnt = (tp["bits"][0] - tp["bits"][1]) + 1
            bad_val = 1 << bits_cnt
            with pytest.raises(Error):
                msr.write_cpu_bits(tp["addr"], tp["bits"], bad_val, cpu, iosname=tp["sname"])

            bad_bits = (msr.regbits + 1, 0)
            with pytest.raises(Error):
                msr.write_cpu_bits(tp["addr"], bad_bits, val, cpu, iosname=tp["sname"])

            # Repeating this negative test for every CPU is an overkill.
            break
        break
