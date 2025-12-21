#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Test the public methods of the 'TPMI.py' module."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import shutil
from pathlib import Path

import pytest
from tests import common
from pepclibs import CPUInfo, TPMI
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, cast, Final
    from tests.common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary.

        Attributes:
            cpuinfo: A 'CPUInfo.CPUInfo' object.
            tpmi: A 'TPMI.TPMI' object.
        """

        cpuinfo: CPUInfo.CPUInfo
        tpmi: TPMI.TPMI

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Yield a dictionary containing parameters required for the tests.

    Args:
        hostspec: The host specification/name to create a process manager for. If the hostspec
                  starts with "emulation:", it indicates an emulated environment.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters.
    """

    with common.get_pman(hostspec, username=username) as pman, \
         CPUInfo.CPUInfo(pman=pman) as cpuinfo:
        params = common.build_params(pman)

        if typing.TYPE_CHECKING:
            params = cast(_TestParamsTypedDict, params)

        params["cpuinfo"] = cpuinfo
        try:
            params["tpmi"] = TPMI.TPMI(cpuinfo.info, pman=pman)
        except ErrorNotSupported:
            pytest.skip(f"TPMI is not supported by {hostspec}.")

        yield params

def test_get_unknown_features(params: _TestParamsTypedDict):
    """
    Test the 'get_unknown_features()' method.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    fids = tpmi.get_unknown_features()

    assert isinstance(fids, list)
    assert all(isinstance(fid, int) for fid in fids)

def test_get_known_features(params: _TestParamsTypedDict):
    """
    Test the 'get_known_features()' method.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    unknown_fids = set(tpmi.get_unknown_features())

    sdicts = tpmi.get_known_features()
    assert isinstance(sdicts, list)

    for sdict in sdicts:
        assert isinstance(sdict, dict)

        assert "name" in sdict
        assert isinstance(sdict["name"], str)

        assert "desc" in sdict
        assert isinstance(sdict["desc"], str)

        assert "feature_id" in sdict
        assert isinstance(sdict["feature_id"], int)

        assert "path" in sdict
        assert isinstance(sdict["path"], Path)

        # Make sure that known features are not reported as unknown.
        assert sdict["feature_id"] not in unknown_fids

def test_get_fdict(params: _TestParamsTypedDict):
    """
    Test the 'get_fdict()' method.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    for sdict in sdicts:
        fname = sdict["name"]

        fdict = tpmi.get_fdict(fname)
        assert isinstance(fdict, dict)

        for regname, regdict in fdict.items():
            assert isinstance(regname, str)
            assert isinstance(regdict, dict)

            assert "offset" in regdict
            assert isinstance(regdict["offset"], int)

            assert "width" in regdict
            assert isinstance(regdict["width"], int)

            assert "readonly" in regdict
            assert isinstance(regdict["readonly"], bool)

            assert "fields" in regdict
            assert isinstance(regdict["fields"], dict)

            for fname, finfo in regdict["fields"].items():
                assert isinstance(fname, str)
                assert isinstance(finfo, dict)

                assert "desc" in finfo
                assert isinstance(finfo["desc"], str)

                assert "readonly" in finfo
                assert isinstance(finfo["readonly"], bool)

                assert "bitshift" in finfo
                assert isinstance(finfo["bitshift"], int)

                assert "bitmask" in finfo
                assert isinstance(finfo["bitmask"], int)

                assert "bits" in finfo
                assert isinstance(finfo["bits"], tuple)
                assert len(finfo["bits"]) == 2
                assert all(isinstance(bit, int) for bit in finfo["bits"])
                # Ensure bits order: highbit >= lowbit
                highbit, lowbit = finfo["bits"]
                assert highbit >= lowbit

def test_iter_feature(params: _TestParamsTypedDict):
    """
    Test the 'iter_feature()' method.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    sdicts = tpmi.get_known_features()

    packages: list[int] = []
    # TPMI devices are per-package.
    addrs: dict[int, list[str]] = {}
    # Instances are per-address.
    instances: dict[str, list[int]] = {}

    valid_packages = set(params["cpuinfo"].get_packages())

    for sdict in sdicts:
        fname = sdict["name"]
        for package, addr, instance in tpmi.iter_feature(fname):
            assert isinstance(addr, str)
            assert isinstance(package, int)
            assert isinstance(instance, int)

            assert package in valid_packages

            packages.append(package)
            addrs.setdefault(package, []).append(addr)
            instances.setdefault(addr, []).append(instance)

        assert len(packages) > 0
        for package in packages:
            assert len(addrs[package]) > 0
            for addr in addrs[package]:
                assert len(instances[addr]) > 0

        # Verify that limiting the parameters works.
        packages_set = set([packages[0], packages[-1]])
        addrs_set: dict[int, set] = {}
        instances_set: dict[str, set] = {}

        for package in packages_set:
            addrs_set[package] = set([addrs[package][0], addrs[package][-1]])
            for addr in addrs_set[package]:
                assert addr in instances
                instances_set[addr] = set([instances[addr][0], instances[addr][-1]])

        for package, addr, instance in tpmi.iter_feature(fname, packages=packages_set):
            assert package in packages_set

        for package in packages_set:
            for pkg, addr, instance in tpmi.iter_feature(fname, packages=[package],
                                                         addrs=addrs_set[package]):

                assert pkg == package
                assert addr in addrs_set[pkg]

        for package, addr, instance in tpmi.iter_feature(fname, addrs=addrs_set[package],
                                                         instances=instances_set[addr]):
            assert package in packages_set
            assert addr in addrs_set[package]
            assert instance in instances_set[addr]

def test_read_register(params: _TestParamsTypedDict):
    """
    Test the 'read_register()' and 'get_bitfield()' methods.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    sdicts = tpmi.get_known_features()

    for sdict in sdicts:
        fname = sdict["name"]
        fdict = tpmi.get_fdict(fname)
        for _, addr, instance in tpmi.iter_feature(fname):
            for regname in fdict:
                regval = tpmi.read_register(fname, addr, instance, regname)
                assert isinstance(regval, int)

                for bfname in fdict[regname]["fields"]:
                    bfval = tpmi.read_register(fname, addr, instance, regname, bfname=bfname)
                    assert isinstance(bfval, int)

                    # Validate 'get_bitfield()' method as well.
                    assert tpmi.get_bitfield(regval, fname, regname, bfname) == bfval

def test_write_register(params: _TestParamsTypedDict):
    """
    Test the 'write_register()' method.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    fname = "ufs"
    regname = "UFS_ADV_CONTROL_2"
    bfname = "UTILIZATION_THRESHOLD"

    fdict = tpmi.get_fdict(fname)
    bits = fdict[regname]["fields"][bfname]["bits"]

    for _, addr, instance in tpmi.iter_feature(fname):
        bfval = tpmi.read_register(fname, addr, instance, regname, bfname=bfname)

        new_bfval = (bfval - 1) % (1 << (bits[0] - bits[1] + 1))

        tpmi.write_register(new_bfval, fname, addr, instance, regname, bfname=bfname)

        resulting_bfval = tpmi.read_register(fname, addr, instance, regname, bfname=bfname)
        assert resulting_bfval == new_bfval

        tpmi.write_register(bfval, fname, addr, instance, regname, bfname=bfname)

        resulting_bfval = tpmi.read_register(fname, addr, instance, regname, bfname=bfname)
        assert resulting_bfval == bfval

def test_specdirs(params: _TestParamsTypedDict):
    """
    Test the 'specdirs' argument of the 'TPMI.TPMI' class constructor.

    Args:
        params: A dictionary with test parameters.
    """

    pman = params["pman"]
    cpuinfo = params["cpuinfo"]

    # Attempt to create a TPMI object with a non-existent specdir.
    with pytest.raises(Error):
        TPMI.TPMI(cpuinfo.info, pman=pman, specdirs=[Path("/non/existent/dir")])

    # Create a TPMI object with valid specdirs.
    tpmi = TPMI.TPMI(cpuinfo.info, pman=pman, specdirs=params["tpmi"].specdirs)
    tpmi.close()

    # Create a TPMI object with a mix of valid and non-existent specdirs.
    specdirs = [Path("/non/existent/dir"), *params["tpmi"].specdirs]
    tpmi = TPMI.TPMI(cpuinfo.info, pman=pman, specdirs=specdirs)
    tpmi.close()

_TMP_UFS_SPEC_FILE_CONTENTS: Final[str] = r"""# Modified version of the UFS spec file for testing.
name: "ufs"
desc: >-
    Processor uncore (fabric) monitoring and control
feature_id: 0x2

registers:
    UFS_SOMETHING:
        offset: 16
        width: 64
        fields:
            SOME_FIELD:
                bits: "7:1"
                readonly: true
                desc: >-
                    Some stuff.
"""

def _prepare_specdir(params: _TestParamsTypedDict, tmp_path: Path) -> Path:
    """
    Prepare a temporary spec files directory with a modified "ufs" spec file.

    Find the "ufs" spec file in one of the provided specdirs, copy the specdir to a temporary
    location, modify the "ufs" spec file in the temporary location, and return the path to the
    temporary specdir path.

    Args:
        params: A dictionary with test parameters.
        tmp_path: A temporary directory path for testing (provided by the pytest framework).

    Returns:
        The path to the temporary specdir.
    """

    fname = "ufs"

    pman = params["pman"]
    cpuinfo = params["cpuinfo"]
    specdirs = params["tpmi"].specdirs

    ufs_specpath = Path()

    for specdir in specdirs:
        try:
            with TPMI.TPMI(cpuinfo.info, pman=pman, specdirs=[specdir]) as tpmi:
                for _, addr, instance in tpmi.iter_feature("ufs"):
                    tpmi.read_register("ufs", addr, instance, "UFS_HEADER",
                                       bfname="INTERFACE_VERSION")
                    # The UFS feature is supported, so the spec file exists in this specdir.
                    break
                ufs_specpath = tpmi.get_sdict(fname)["path"]
                break
        except Error:
            continue
    else:
        raise Error("Cannot find the 'ufs' feature in any of the provided specdirs")

    tmpspecdir = tmp_path / "specdir"

    tmpspecdir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(specdir / "index.yml", tmpspecdir / "index.yml")

    tmp_ufs_specpath = tmpspecdir / ufs_specpath.parent.name / ufs_specpath.name
    tmp_ufs_specpath.parent.mkdir(parents=True, exist_ok=False)

    with open(tmp_ufs_specpath, "w+", encoding="utf-8") as fobj:
        fobj.write(_TMP_UFS_SPEC_FILE_CONTENTS)

    return tmpspecdir

def test_spec_file_override(params: _TestParamsTypedDict, tmp_path: Path):
    """
    Test that it is possible to override spec files by providing a custom specdir.

    Args:
        params: A dictionary with test parameters.
        tmp_path: A temporary directory path for testing (provided by the pytest framework).

    Notes:
        Test strategy:
          * Create a temporary copy of a specdir.
          * Modify one of the spec files.
          * Create a TPMI object with the modified specdir having precedence.
          * Verify that the modified spec is used.
    """

    tmpspecdir = _prepare_specdir(params, tmp_path)

    pman = params["pman"]
    cpuinfo = params["cpuinfo"]

    specdirs = [tmpspecdir, *params["tpmi"].specdirs]

    with TPMI.TPMI(cpuinfo.info, pman=pman, specdirs=specdirs) as tpmi:
        # Verify that original spec file is overridden.
        for _, addr, instance in tpmi.iter_feature("ufs"):
            tpmi.read_register("ufs", addr, instance, "UFS_SOMETHING", bfname="SOME_FIELD")
            with pytest.raises(Error):
                tpmi.read_register("ufs", addr, instance, "UFS_HEADER", bfname="INTERFACE_VERSION")
            break

        # Verify that other spec files are still usable.
        for _, addr, instance in tpmi.iter_feature("rapl"):
            tpmi.read_register("rapl", addr, instance, "SOCKET_RAPL_DOMAIN_HEADER")
