#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Unittests for the public methods of the MSR Feature modules."""

import pytest
import msr_common
from msr_common import get_params # pylint: disable=unused-import
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.helperlibs.Exceptions import Error

def _get_msr_feature_objs(params):
    """
    Yield the MSR Feature objects, e.g. 'PCStateConfigCtl', initialized with different parameters
    that we want to run tests with.
    """

    for msr_feature_class in params["feature_classes"]:
        for enable_cache in (True, False):
            with CPUInfo.CPUInfo(pman=params["pman"]) as cpuinfo, \
                 MSR.MSR(pman=params["pman"], cpuinfo=cpuinfo, enable_cache=enable_cache) as msr, \
                 msr_feature_class(pman=params["pman"], cpuinfo=cpuinfo, msr=msr) as feature_msr:
                yield feature_msr

def _get_msr_feature_test_params(msr, params, include_ro=True, include_rw=True,
                                 supported_only=True):
    """
    Yields tuple of feature name and feature info dictionary that should be used for testing MSR
    Feature module methods. Arguments are:
      * msr - The MSR feature module object.
      * params - The 'params' dictionary from 'params' fixture.
      * include_ro - If 'False', then read-only features are not include.
      * include_rw - If 'False', then writable features are not included.
      * supported_only - if 'False', then also unsupported features are included.
    """

    for name, finfo in msr.features.items():
        if finfo.get("writable"):
            if not include_rw:
                continue
        elif not include_ro:
            continue

        if not msr.is_feature_supported(name) and supported_only:
            continue

        # The 'pkg_cstate_limit' has a dependency to 'locked' feature. If 'locked' feature is
        # enabled, then 'pkg_cstate_limit' not included.
        if name == "pkg_cstate_limit" and \
            (msr.is_feature_supported("locked") and msr.is_cpu_feature_enabled("locked", 0)):
            continue

        if not msr_common.is_safe_to_set(name, params["hostname"]):
            continue

        yield name, finfo

def _flip_bits(val, bits):
    """Flip bits of the value 'val', value range is in tuple 'bits' as maximum and minimum."""

    bits_cnt = (bits[0] - bits[1]) + 1
    max_val = (1 << bits_cnt) - 1
    return max_val ^ val

def _get_bad_feature_names():
    """Yield bad MSR feature names."""

    for name in ("C1_demotion", " c1_demotion", "c1_demotion ", "", 0, None):
        yield name

def _get_bad_feature_values(finfo):
    """Yield bad feature values for feature described with info 'finfo'."""

    ftype = finfo.get("type")
    if ftype == "bool":
        vals = {"0", None, -1, ""}
    elif ftype in ("int", "float"):
        vals = {"True", True, None, ""}
    elif ftype == "dict":
        vals = {"str", 1}

    # Ensure we don't return valid values.
    if "vals" in finfo:
        vals -= set(finfo["vals"].values())

    for val in vals:
        yield val

def _get_good_feature_values(finfo):
    """Yield good feature values for feature described with info 'finfo'."""

    ftype = finfo.get("type")
    if ftype == "bool":
        for val in (True, False, "enable", "disable"):
            yield val

def _check_feature_val(val, name, msr):
    """Check feature value 'val' against feature 'name' attributes."""

    finfo = msr.features[name]
    if "type" in finfo:
        if finfo["type"] == "int":
            assert isinstance(val, int)
        elif finfo["type"] == "float":
            assert isinstance(val, float)
        elif finfo["type"] == "bool":
            assert val in ("on", "off")
        elif finfo["type"] == "dict":
            assert isinstance(val, dict)
            if name == "pkg_cstate_limit":
                assert isinstance(val["pkg_cstate_limit"], str)
                assert isinstance(val["pkg_cstate_limits"], list)
                assert isinstance(val["pkg_cstate_limit_aliases"], dict)
        else:
            assert False, f"Unknown '{name}' feature type: {type(val)}"

def _test_msr_read_feature_good(params):
    """Test 'read_feature()' method for good option values."""

    for msr in _get_msr_feature_objs(params):
        for name, _ in _get_msr_feature_test_params(msr, params):
            for cpu, val in msr.read_feature(name, cpus=params["testcpus"]):
                _check_feature_val(val, name, msr)
                assert cpu in params["testcpus"]

            allcpus = []
            for cpu, val in msr.read_feature(name):
                _check_feature_val(val, name, msr)
                allcpus.append(cpu)
            assert allcpus == params["cpus"]

def _test_msr_read_feature_bad(params):
    """Test 'read_feature()' method for bad option values."""

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                for cpu, val in msr.read_feature(name, cpus=params["testcpus"]):
                    _check_feature_val(val, name, msr)
                    assert cpu in params["testcpus"]
            with pytest.raises(Error):
                for bad_cpu in msr_common.get_bad_cpu_nums(params):
                    for cpu, val in msr.read_feature(name, cpus=bad_cpu):
                        _check_feature_val(val, name, msr)
                        assert cpu in params["testcpus"]

def test_msr_read_feature(params):
    """Test 'read_feature()' method."""

    _test_msr_read_feature_good(params)
    _test_msr_read_feature_bad(params)

def _test_msr_write_feature_good(params):
    """Test 'write_feature()' method for good option values."""

    for msr in _get_msr_feature_objs(params):
        for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
            if "vals" in finfo:
                for val in finfo["vals"]:
                    msr.write_feature(name, val, cpus=params["testcpus"])
            else:
                val = msr.read_cpu_feature(name, params["testcpus"][0])
                newval = _flip_bits(val, finfo["bits"])
                msr.write_feature(name, newval, cpus=params["testcpus"])

def _test_msr_write_feature_bad(params):
    """Test 'write_feature()' method for bad option values."""

    for msr in _get_msr_feature_objs(params):
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
                bad_val = _flip_bits(val, bad_bits)
                with pytest.raises(Error):
                    msr.write_feature(name, bad_val, cpus=params["testcpus"])

def test_msr_write_feature(params):
    """Test 'write_feature()' method."""

    _test_msr_write_feature_good(params)
    _test_msr_write_feature_bad(params)

def _test_msr_enable_feature_good(params):
    """Test 'enable_feature()' method for good option values."""

    for msr in _get_msr_feature_objs(params):
        for name, finfo in _get_msr_feature_test_params(msr, params, include_ro=False):
            if finfo.get("type") != "bool":
                continue

            for enable in _get_good_feature_values(finfo):
                msr.enable_feature(name, enable, cpus=params["testcpus"])
                msr.enable_feature(name, enable)

def _test_msr_enable_feature_bad(params):
    """Test 'enable_feature()' method for bad option values."""

    for msr in _get_msr_feature_objs(params):
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

def test_msr_enable_feature(params):
    """Test 'enable_feature()' method."""

    _test_msr_enable_feature_good(params)
    _test_msr_enable_feature_bad(params)

def _test_msr_is_feature_enabled_good(params):
    """Test 'is_feature_enabled()' method for good option values."""

    for msr in _get_msr_feature_objs(params):
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

def _test_msr_is_feature_enabled_bad(params):
    """Test 'is_feature_enabled()' method for bad option values."""

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

def test_msr_is_feature_enabled(params):
    """Test 'is_feature_enabled()' method."""

    _test_msr_is_feature_enabled_good(params)
    _test_msr_is_feature_enabled_bad(params)

def _test_msr_is_feature_supported_good(params):
    """Test 'is_feature_supported()' method for good option values."""

    for msr in _get_msr_feature_objs(params):
        supported = []
        for name, _ in _get_msr_feature_test_params(msr, params):
            assert msr.is_feature_supported(name)
            supported.append(name)
        for name, _ in _get_msr_feature_test_params(msr, params, supported_only=False):
            if name in supported:
                continue
            assert not msr.is_feature_supported(name)

def _test_msr_is_feature_supported_bad(params):
    """Test 'is_feature_supported()' method for bad option values."""

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                msr.is_feature_supported(name)

def test_msr_is_feature_supported(params):
    """Test 'is_feature_supported()' method."""

    _test_msr_is_feature_supported_good(params)
    _test_msr_is_feature_supported_bad(params)

def _test_msr_validate_feature_supported_good(params):
    """Test 'validate_feature_supported()' method for good option values."""

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

def _test_msr_validate_feature_supported_bad(params):
    """Test 'validate_feature_supported()' method for bad option values."""

    for msr in _get_msr_feature_objs(params):
        for name in _get_bad_feature_names():
            with pytest.raises(Error):
                msr.is_feature_supported(name)

def test_msr_validate_feature_supported(params):
    """Test 'validate_feature_supported()' method."""

    _test_msr_validate_feature_supported_good(params)
    _test_msr_validate_feature_supported_bad(params)
