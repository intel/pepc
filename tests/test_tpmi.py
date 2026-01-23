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
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied

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
            params["tpmi"] = cpuinfo.get_tpmi()
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
    assert isinstance(sdicts, dict)

    for sdict in sdicts.values():
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

    for fname in sdicts:
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

            for bfname, finfo in regdict["fields"].items():
                assert isinstance(bfname, str)
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

    valid_packages = set(params["cpuinfo"].get_packages())

    for fname in sdicts:
        packages: list[int] = []
        # TPMI devices are per-package.
        addrs: dict[int, list[str]] = {}
        # Instances are per-address.
        instances: dict[str, list[int]] = {}
        # Clusters are per-instance.
        clusters: dict[int, list[int]] = {}

        for package, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
            assert isinstance(addr, str)
            assert isinstance(package, int)
            assert isinstance(instance, int)
            assert isinstance(cluster, int)

            assert package in valid_packages

            packages.append(package)
            addrs.setdefault(package, []).append(addr)
            instances.setdefault(addr, []).append(instance)
            clusters.setdefault(instance, []).append(cluster)

        assert len(packages) > 0
        for package in packages:
            assert len(addrs[package]) > 0
            for addr in addrs[package]:
                assert len(instances[addr]) > 0

        # Verify that limiting the parameters works.
        packages_set = set([packages[0], packages[-1]])
        addrs_set: dict[int, set] = {}
        instances_set: dict[str, set] = {}
        clusters_set: dict[int, set] = {}

        for package in packages_set:
            addrs_set[package] = set([addrs[package][0], addrs[package][-1]])
            for addr in addrs_set[package]:
                assert addr in instances
                instances_set[addr] = set([instances[addr][0], instances[addr][-1]])

                for instance in instances_set[addr]:
                    assert instance in clusters
                    clusters_set[instance] = set([clusters[instance][0],
                                                 clusters[instance][-1]])

        for package, addr, instance in tpmi.iter_feature(fname, packages=packages_set):
            assert package in packages_set

        for package in packages_set:
            for pkg, addr, instance in tpmi.iter_feature(fname, packages=[package],
                                                         addrs=addrs_set[package]):

                assert pkg == package
                assert addr in addrs_set[pkg]

        for package in packages_set:
            for address in addrs_set[package]:
                iterator = tpmi.iter_feature_cluster(fname, addrs=(address,),
                                                     instances=instances_set[address])
                for pkg, addr, instance, cluster in iterator:
                    assert pkg in packages_set
                    assert addr in addrs_set[package]
                    assert instance in instances_set[address]
                    assert cluster in clusters_set[instance]

        for package in packages_set:
            for address in addrs_set[package]:
                for instance in instances_set[address]:
                    iterator = tpmi.iter_feature_cluster(fname, addrs=(address,),
                                                         instances=(instance,),
                                                         clusters=clusters_set[instance])
                    for pkg, addr, instance, cluster in iterator:
                        assert pkg in packages_set
                        assert addr in addrs_set[package]
                        assert instance in instances_set[address]
                        assert cluster in clusters_set[instance]

def test_read_register(params: _TestParamsTypedDict):
    """
    Test the 'read_register()' and 'get_bitfield()' methods.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    sdicts = tpmi.get_known_features()

    for fname in sdicts:
        fdict = tpmi.get_fdict(fname)
        for _, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
            for regname in fdict:
                if cluster != 0 and regname in TPMI.UFS_HEADER_REGNAMES:
                    continue
                regval = tpmi.read_register_cluster(fname, addr, instance, cluster, regname)
                assert isinstance(regval, int)

                for bfname in fdict[regname]["fields"]:
                    bfval = tpmi.read_register_cluster(fname, addr, instance, cluster, regname,
                                                       bfname=bfname)
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

    for _, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
        bfval = tpmi.read_register_cluster(fname, addr, instance, cluster, regname, bfname=bfname)

        new_bfval = (bfval - 1) % (1 << (bits[0] - bits[1] + 1))

        tpmi.write_register_cluster(new_bfval, fname, addr, instance, cluster, regname,
                                    bfname=bfname)
        resulting_bfval = tpmi.read_register_cluster(fname, addr, instance, cluster, regname,
                                                     bfname=bfname)
        assert resulting_bfval == new_bfval

        tpmi.write_register_cluster(bfval, fname, addr, instance, cluster, regname,
                                    bfname=bfname)
        resulting_bfval = tpmi.read_register_cluster(fname, addr, instance, cluster, regname,
                                                     bfname=bfname)
        assert resulting_bfval == bfval

def test_specdirs(params: _TestParamsTypedDict):
    """
    Test the 'specdirs' argument of the 'TPMI.TPMI' class constructor.

    Args:
        params: A dictionary with test parameters.
    """

    pman = params["pman"]
    cpuinfo = params["cpuinfo"]

    vfm = cpuinfo.proc_cpuinfo["vfm"]

    # Attempt to create a TPMI object with a non-existent specdir.
    with pytest.raises(Error):
        TPMI.TPMI(vfm, pman=pman, specdirs=[Path("/non/existent/dir")])

    # Create a TPMI object with valid specdirs.
    tpmi = TPMI.TPMI(vfm, pman=pman, specdirs=params["tpmi"].sdds)
    tpmi.close()

    # Create a TPMI object with a mix of valid and non-existent specdirs.
    specdirs = [Path("/non/existent/dir"), *params["tpmi"].sdds]
    tpmi = TPMI.TPMI(vfm, pman=pman, specdirs=specdirs)
    tpmi.close()

_TMP_UFS_SPEC_FILE_CONTENTS: Final[str] = r"""# Modified version of the UFS spec file for testing.
name: "ufs"
desc: >-
    Processor uncore (fabric) monitoring and control
feature_id: 0x2

registers:
    UFS_HEADER:
        offset: 0
        width: 64
        fields:
            INTERFACE_VERSION:
                bits: "7:0"
                readonly: true
                desc: >-
                    Version number for this interface
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
    sdds = params["tpmi"].sdds

    vfm = cpuinfo.proc_cpuinfo["vfm"]
    ufs_specpath = Path()

    for specdir in sdds:
        try:
            with TPMI.TPMI(vfm, pman=pman, specdirs=[specdir]) as tpmi:
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

    sdds = [tmpspecdir, *params["tpmi"].sdds]
    vfm = cpuinfo.proc_cpuinfo["vfm"]

    with TPMI.TPMI(vfm, pman=pman, specdirs=sdds) as tpmi:
        # Verify that original spec file is overridden.
        for _, addr, instance in tpmi.iter_feature("ufs"):
            tpmi.read_register("ufs", addr, instance, "UFS_SOMETHING", bfname="SOME_FIELD")
            with pytest.raises(Error):
                tpmi.read_register("ufs", addr, instance, "UFS_HEADER", bfname="FLAGS")
            break

        # Verify that other spec files are still usable.
        for _, addr, instance in tpmi.iter_feature("rapl"):
            tpmi.read_register("rapl", addr, instance, "SOCKET_RAPL_DOMAIN_HEADER")

def test_invalid_feature_name(params: _TestParamsTypedDict):
    """
    Test that invalid feature names raise appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    # Test with non-existent feature name.
    with pytest.raises(Error):
        tpmi.get_fdict("non_existent_feature")

    with pytest.raises(Error):
        tpmi.get_sdict("non_existent_feature")

    with pytest.raises(Error):
        for _ in tpmi.iter_feature("non_existent_feature"):
            pass

def test_invalid_register_name(params: _TestParamsTypedDict):
    """
    Test that invalid register names raise appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    fname = next(iter(sdicts))

    for _, addr, instance in tpmi.iter_feature(fname):
        # Test with non-existent register name.
        with pytest.raises(Error):
            tpmi.read_register(fname, addr, instance, "NON_EXISTENT_REGISTER")

        with pytest.raises(Error):
            tpmi.write_register(0, fname, addr, instance, "NON_EXISTENT_REGISTER")

        break

def test_invalid_bitfield_name(params: _TestParamsTypedDict):
    """
    Test that invalid bitfield names raise appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    fname = next(iter(sdicts))
    fdict = tpmi.get_fdict(fname)
    regname = next(iter(fdict))

    for _, addr, instance in tpmi.iter_feature(fname):
        # Test with non-existent bitfield name.
        with pytest.raises(Error):
            tpmi.read_register(fname, addr, instance, regname, bfname="NON_EXISTENT_BITFIELD")

        with pytest.raises(Error):
            tpmi.write_register(0, fname, addr, instance, regname, bfname="NON_EXISTENT_BITFIELD")

        # Test get_bitfield with invalid bitfield name.
        regval = tpmi.read_register(fname, addr, instance, regname)
        with pytest.raises(Error):
            tpmi.get_bitfield(regval, fname, regname, "NON_EXISTENT_BITFIELD")
        break

def test_invalid_address(params: _TestParamsTypedDict):
    """
    Test that invalid PCI addresses raise appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    fname = next(iter(sdicts))
    fdict = tpmi.get_fdict(fname)
    regname = next(iter(fdict))

    # Test with non-existent address.
    with pytest.raises(Error):
        tpmi.read_register(fname, "ffff:ff:ff.f", 0, regname)

    with pytest.raises(Error):
        tpmi.write_register(0, fname, "ffff:ff:ff.f", 0, regname)

def test_invalid_instance(params: _TestParamsTypedDict):
    """
    Test that invalid instance numbers raise appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    fname = next(iter(sdicts))
    fdict = tpmi.get_fdict(fname)
    regname = next(iter(fdict))

    for _, addr, _ in tpmi.iter_feature(fname):
        # Test with very large instance number (unlikely to exist).
        with pytest.raises(Error):
            tpmi.read_register(fname, addr, 9999, regname)

        with pytest.raises(Error):
            tpmi.write_register(0, fname, addr, 9999, regname)
        break

def test_invalid_cluster(params: _TestParamsTypedDict):
    """
    Test that invalid cluster numbers raise appropriate errors for non-UFS features.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    # Find a non-UFS feature.
    non_ufs_features = [fname for fname in sdicts if fname != "ufs"]

    if not non_ufs_features:
        pytest.skip("No non-UFS features available")

    fname = non_ufs_features[0]
    fdict = tpmi.get_fdict(fname)
    regname = next(iter(fdict))

    for _, addr, instance in tpmi.iter_feature(fname):
        # Non-UFS features should not support cluster != 0.
        with pytest.raises(Error):
            tpmi.read_register_cluster(fname, addr, instance, 1, regname)

        with pytest.raises(Error):
            tpmi.write_register_cluster(0, fname, addr, instance, 1, regname)
        break

def test_readonly_register_write(params: _TestParamsTypedDict):
    """
    Test that attempting to write to read-only registers raises appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    # Find a read-only register.
    for fname in sdicts:
        fdict = tpmi.get_fdict(fname)
        for regname, regdict in fdict.items():
            if regdict["readonly"]:
                for _, addr, instance in tpmi.iter_feature(fname):
                    # Attempting to write to a read-only register should fail.
                    with pytest.raises(ErrorPermissionDenied):
                        tpmi.write_register(0, fname, addr, instance, regname)
                    return
                break

    pytest.skip("No read-only registers found")

def test_readonly_bitfield_write(params: _TestParamsTypedDict):
    """
    Test that attempting to write to read-only bitfields raises appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]
    sdicts = tpmi.get_known_features()

    if not sdicts:
        pytest.skip("No known features available")

    # Find a read-only bitfield.
    for fname in sdicts:
        fdict = tpmi.get_fdict(fname)
        for regname, regdict in fdict.items():
            for bfname, bfdict in regdict["fields"].items():
                if bfdict["readonly"]:
                    for _, addr, instance in tpmi.iter_feature(fname):
                        # Attempting to write to a read-only bitfield should fail.
                        with pytest.raises(Error):
                            tpmi.write_register(0, fname, addr, instance, regname, bfname=bfname)
                        return
                    break
            break

    pytest.skip("No read-only bitfields found")

def test_bitfield_value_out_of_range(params: _TestParamsTypedDict):
    """
    Test that writing out-of-range values to bitfields raises appropriate errors.

    Args:
        params: A dictionary with test parameters.
    """

    tpmi = params["tpmi"]

    fname = "ufs"
    regname = "UFS_ADV_CONTROL_2"
    bfname = "UTILIZATION_THRESHOLD"

    try:
        fdict = tpmi.get_fdict(fname)
    except Error:
        pytest.skip("UFS feature not available")

    bits = fdict[regname]["fields"][bfname]["bits"]
    max_value = (1 << (bits[0] - bits[1] + 1)) - 1

    for _, addr, instance, cluster in tpmi.iter_feature_cluster(fname):
        # Test with value exceeding bitfield capacity.
        with pytest.raises(Error):
            tpmi.write_register_cluster(max_value + 1, fname, addr, instance, cluster, regname,
                                        bfname=bfname)

        # Test with negative value.
        with pytest.raises(Error):
            tpmi.write_register_cluster(-1, fname, addr, instance, cluster, regname, bfname=bfname)
        break
