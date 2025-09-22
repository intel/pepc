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

"""Test public methods of Featured MSR modules."""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
import pytest
import common
import msr_common
from msr_common import get_params # pylint: disable=unused-import
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed

if typing.TYPE_CHECKING:
    from typing import Generator
    from pepclibs.msr import _FeaturedMSR
    from pepclibs.msr._FeaturedMSR import FeatureTypedDict, FeatureValueType
    from msr_common import FeaturedMSRTestParamsTypedDict

def _get_msr_feature_objs(params: FeaturedMSRTestParamsTypedDict) -> \
                                                    Generator[_FeaturedMSR.FeaturedMSR, None, None]:
    """
    Yield initialized FeaturedMSR sub-class objects for testing (e.g., 'PCStateConfigCtl').

    Args:
        params: The test parameters dictionary.

    Yields:
        Featured MSR objects initialized with different parameters for testing.
    """

    for fmsr_class in params["feature_classes"]:
        for enable_cache in (True, False):
            with CPUInfo.CPUInfo(pman=params["pman"]) as cpuinfo, \
                 MSR.MSR(cpuinfo, pman=params["pman"], enable_cache=enable_cache) as msr, \
                 fmsr_class(pman=params["pman"], cpuinfo=cpuinfo, msr=msr) as feature_msr:
                yield feature_msr

def _get_msr_feature_test_params(fmsr: _FeaturedMSR.FeaturedMSR,
                                 params: FeaturedMSRTestParamsTypedDict,
                                 include_ro: bool = True,
                                 include_rw: bool=True,
                                 supported_only: bool = True) -> \
                                            Generator[tuple[str, FeatureTypedDict], None, None]:
    """
    Yield tuples of feature name and feature information dictionary for testing featured MSR
    modules.

    Args:
        fmsr: The featured MSR module object that is being tested.
        params: The test parameters dictionary.
        include_ro: Include read-only features if True.
        include_rw: Include writable features if True.
        supported_only: Include unsupported features if True.

    Yields:
        Tuples containing the feature name and the feature information dictionary.
    """

    for name, finfo in fmsr.features.items():
        if finfo.get("writable"):
            if not include_rw:
                continue
        elif not include_ro:
            continue

        if not fmsr.is_feature_supported(name) and supported_only:
            continue

        # The 'pkg_cstate_limit' has a dependency to 'lock' feature. If 'lock' feature is
        # enabled, then 'pkg_cstate_limit' not included.
        if name == "pkg_cstate_limit":
            if fmsr.is_feature_supported("pkg_cstate_limit_lock") and \
               fmsr.is_cpu_feature_enabled("pkg_cstate_limit_lock", 0):
                continue

        if not msr_common.is_safe_to_set(name, params["hostname"]):
            continue

        yield name, finfo

def _get_bad_feature_names() -> Generator[str, None, None]:
    """
    Yield invalid feature names for testing purposes.
    """

    yield from ("C1_demotion", " c1_demotion", "c1_demotion ", "", "all", "0")

def _get_bad_feature_values(finfo: FeatureTypedDict) -> Generator[str | int, None, None]:
    """
    Yield invalid values for a feature based on its type information.

    Args:
        finfo: A feature information dictionary to yield invalid values for.

    Yields:
        Invalid values for the feature based on its type.
    """

    vals: set[str | int]

    ftype = finfo.get("type")
    if ftype == "bool":
        vals = {"0", "all", -1, ""}
    elif ftype in ("int", "float"):
        vals = {"True", True, -1, ""}
    else:
        raise AssertionError(f"Unknown feature type: {ftype}")

    # Ensure we don't return valid values.
    if "vals" in finfo:
        vals -= set(finfo["vals"].values())

    yield from vals

def _get_good_feature_values(finfo: FeatureTypedDict) -> Generator[bool | str, None, None]:
    """
    Yield valid values for a feature based on its type information.

    Args:
        finfo: A feature information dictionary to yield valid values for.

    Yields:
        Valid values for the feature based on its type.
    """

    ftype = finfo.get("type")
    if ftype == "bool":
        yield from (True, False, "enable", "disable")

def _check_feature_val_and_type(val: FeatureValueType, name: str, fmsr: _FeaturedMSR.FeaturedMSR):
    """
    Check feature value and its type.

    Args:
        val: The feature value to check.
        name: The name of the feature.
        fmsr: The featured MSR module object that is being tested.
    """

    finfo = fmsr.features[name]
    if "type" in finfo:
        if finfo["type"] == "int":
            assert isinstance(val, int)
        elif finfo["type"] == "float":
            assert isinstance(val, float)
        elif finfo["type"] == "bool":
            assert val in ("on", "off")
        elif finfo["type"] == "str":
            assert isinstance(val, str)
        else:
            raise AssertionError(f"Unknown '{name}' feature type: {type(val)}")

def test_msr_read_feature_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'read_feature()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        for name, _ in _get_msr_feature_test_params(msr, params):
            for cpu, val in msr.read_feature(name, cpus=params["testcpus"]):
                _check_feature_val_and_type(val, name, msr)
                assert cpu in params["testcpus"]

            allcpus = []
            for cpu, val in msr.read_feature(name):
                _check_feature_val_and_type(val, name, msr)
                allcpus.append(cpu)
            assert allcpus == params["cpus"]

def test_msr_read_feature_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'read_feature()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                for cpu, val in msr.read_feature(name, cpus=params["testcpus"]):
                    _check_feature_val_and_type(val, name, msr)
                    assert cpu in params["testcpus"]
            with pytest.raises(Error):
                for bad_cpu in msr_common.get_bad_cpu_nums(params):
                    for cpu, val in msr.read_feature(name, cpus=[bad_cpu]):
                        _check_feature_val_and_type(val, name, msr)
                        assert cpu in params["testcpus"]

def _is_verify_error_ok(params: FeaturedMSRTestParamsTypedDict, err: ErrorVerifyFailed) -> bool:
    """
    Determine whether an 'ErrorVerifyFailed' exception should be ignored.

    Some MSRs, such as the RAPL package power limit MSR, are known to not accept written values on
    certain platforms, resulting in verification failures that are not indicative of a real issue.

    Args:
        params: The test parameters dictionary.
        err: The 'ErrorVerifyFailed' exception object to check.

    Returns:
        True if the verification error should be ignored, False otherwise.
    """

    if common.is_emulated(params["pman"]):
        return False

    if not hasattr(err, "regname"):
        return False

    if err.regname == "MSR_PKG_POWER_LIMIT":
        # This MSR is known to not "accept" written values on some platforms.
        return True

    return False

def _flip_bits(val: int, bits: tuple[int, int]) -> int:
    """
    Flip the bits of an integer value within a specified bit range.

    Args:
        val: The integer value to flip bits of.
        bits: A tuple containing the bits range (MSB, LSB).

    Returns:
        The integer value with the specified bits flipped.
    """

    bits_cnt = (bits[0] - bits[1]) + 1
    max_val = (1 << bits_cnt) - 1
    return max_val ^ val

def test_msr_write_feature_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'write_feature()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        try:
            for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
                if "vals" in finfo:
                    for val in finfo["vals"]:
                        msr.write_feature(name, val, cpus=params["testcpus"])
                else:
                    val = msr.read_cpu_feature(name, params["testcpus"][0])
                    assert finfo["type"] == "int", \
                           f"Unexpected type for '{name}' feature: {finfo['type']}"
                    newval = _flip_bits(cast(int, val), finfo["bits"])
                    msr.write_feature(name, newval, cpus=params["testcpus"])
        except ErrorVerifyFailed as err:
            if not _is_verify_error_ok(params, err):
                raise

def test_msr_write_feature_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'write_feature()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        try:
            for name in _get_bad_feature_names():
                with pytest.raises(Error):
                    msr.write_feature(name, 0, cpus=params["testcpus"])

            for name, _ in _get_msr_feature_test_params(msr, params, include_rw=False):
                val = msr.read_cpu_feature(name, params["testcpus"][0])
                with pytest.raises(Error):
                    msr.write_feature(name, val, cpus=params["testcpus"])

            for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
                val = msr.read_cpu_feature(name, params["testcpus"][0])
                if "vals" in finfo:
                    for bad_val in _get_bad_feature_values(finfo):
                        with pytest.raises(Exception):
                            msr.write_feature(name, bad_val, cpus=params["testcpus"])
                else:
                    bad_bits = (finfo["bits"][0] + 1, finfo["bits"][1])
                    assert finfo["type"] == "int", \
                           f"Unexpected type for '{name}' feature: {finfo['type']}"
                    bad_val = _flip_bits(cast(int, val), bad_bits)
                    with pytest.raises(Error):
                        msr.write_feature(name, bad_val, cpus=params["testcpus"])
        except ErrorVerifyFailed as err:
            if not _is_verify_error_ok(params, err):
                raise

def test_msr_enable_feature_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'enable_feature()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        try:
            for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
                if finfo.get("type") != "bool":
                    continue

                for enable in _get_good_feature_values(finfo):
                    msr.enable_feature(name, enable, cpus=params["testcpus"])
                    msr.enable_feature(name, enable)
        except ErrorVerifyFailed as err:
            if not _is_verify_error_ok(params, err):
                raise

def test_msr_enable_feature_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'enable_feature()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        try:
            for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
                if finfo.get("type") != "bool":
                    finfo["type"] = "bool"
                    enable = next(_get_good_feature_values(finfo))
                    with pytest.raises(Error):
                        msr.enable_feature(name, enable, cpus=params["testcpus"])
                    with pytest.raises(Error):
                        msr.enable_feature(name, enable)

                for enable in _get_bad_feature_values(finfo):
                    with pytest.raises(Error):
                        msr.enable_feature(name, enable, cpus=params["testcpus"])
                    with pytest.raises(Error):
                        msr.enable_feature(name, enable)
        except ErrorVerifyFailed as err:
            if not _is_verify_error_ok(params, err):
                raise

def test_msr_is_feature_enabled_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'is_feature_enabled()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        try:
            for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
                if finfo.get("type") != "bool":
                    continue

                for enable in (True, False):
                    msr.enable_feature(name, enable, cpus=params["testcpus"])
                    for cpu, enabled in msr.is_feature_enabled(name, cpus=params["testcpus"]):
                        assert enable == enabled
                        assert cpu in params["testcpus"]

                    msr.enable_feature(name, enable)
                    allcpus = []
                    for cpu, enabled in msr.is_feature_enabled(name):
                        assert enable == enabled
                        allcpus.append(cpu)
                    assert allcpus == params["cpus"]
        except ErrorVerifyFailed as err:
            if not _is_verify_error_ok(params, err):
                raise

def test_msr_is_feature_enabled_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'is_feature_enabled()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
            if finfo.get("type") != "bool":
                with pytest.raises(Error):
                    for cpu, _ in msr.is_feature_enabled(name, cpus=params["testcpus"]):
                        assert cpu in params["testcpus"]
                with pytest.raises(Error):
                    for cpu, _ in msr.is_feature_enabled(name):
                        assert cpu in params["cpus"]

        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                for cpu, _ in msr.is_feature_enabled(name):
                    assert cpu in params["cpus"]

def test_msr_is_feature_supported_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'is_feature_supported()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        supported = []
        for name, _ in _get_msr_feature_test_params(msr, params):
            assert msr.is_feature_supported(name)
            supported.append(name)
        for name, _ in _get_msr_feature_test_params(msr, params, supported_only=False):
            if name in supported:
                continue
            assert not msr.is_feature_supported(name)

def test_msr_is_feature_supported_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'is_feature_supported()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                msr.is_feature_supported(name)

def test_msr_validate_feature_supported_good(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'validate_feature_supported()' method with valid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        supported = []
        for name, _ in _get_msr_feature_test_params(msr, params):
            msr.validate_feature_supported(name)
            supported.append(name)
        for name, _ in _get_msr_feature_test_params(msr, params, supported_only=False):
            if name in supported:
                continue
            with pytest.raises(Error):
                msr.validate_feature_supported(name)

def test_msr_validate_feature_supported_bad(params: FeaturedMSRTestParamsTypedDict):
    """
    Test 'validate_feature_supported()' method with invalid values.

    Args:
        params: The test parameters dictionary.
    """

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                msr.is_feature_supported(name)
