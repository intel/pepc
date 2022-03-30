#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Common mocked bits for the tests."""

import re
import random
from contextlib import contextmanager
from unittest.mock import patch, mock_open
from pathlib import Path
from pepclibs import CPUInfo, CStates
from pepclibs.helperlibs import LocalProcessManager, FSHelpers
from pepclibs.helperlibs.Exceptions import ErrorNotFound
from pepclibs.msr import MSR, PCStateConfigCtl, PlatformInfo, TurboRatioLimit, PMEnable

_TESTDATA = {
        ("cstates", "cstates_info.txt" ),
        ("cpufreq", "cpufreq_info.txt" ),
        ("lscpu", "lscpu_info.txt" ),
        ("lscpu_cpus", "lscpu_info_cpus.txt" ),
        ("intel_uncore_frequency", "intel_uncore_frequency.txt" ),
        ("intel_pstate", "intel_pstate.txt" ),
        ("aspm_policy", "aspm_policy.txt" ),
        ("cpu_online", "cpu_online.txt" ),
        ("dev_cpu", "dev_cpu.txt" ),
    }

# Max. 64-bit integer.
_MAX64 = (1 << 64) - 1

_ORIG_PROC = LocalProcessManager.LocalProcessManager()

def _get_mocked_data():
    """
    Get mocked data for testing purposes. The files with testdata can be opened only before mocking.
    Returns dictionary with following keys:
      * cstates - C-state info, similar to output of 'run_verify()' call from
                  'CStates.get_cstates_info()'.
      * files - dictionary of file paths relevant to testing.
      * lscpu - output of 'lscpu' command used for testing.
    """

    mock_data = {}
    basepath = Path(__file__).parents[1].resolve() # pylint: disable=no-member
    testdatapath = basepath / "tests" / "data_v1"

    for name, filename in _TESTDATA:
        with open(testdatapath / filename, "r") as fobj:
            mock_data[name] = fobj.readlines()

    return mock_data

def _get_mocked_files(names):
    """
    Get mocked files for testing purposes. Returns dictionary with file path as key and file content
    as value.
    """

    mock_data = {}
    for name in names:
        for line in _MOCKED_DATA[name]:
            split = line.split(":")
            mock_data[split[0]] = split[1].strip()

    return mock_data

_MOCKED_DATA = _get_mocked_data()
_MOCKED_FILES = _get_mocked_files(("cstates", "cpufreq", "intel_uncore_frequency", "intel_pstate",
                                   "aspm_policy", "cpu_online"))
_MOCKED_EXISTS_FILES = _MOCKED_FILES | _get_mocked_files(("dev_cpu", ))
_MOCKED_ASPM_POLICY_FILES = _get_mocked_files(("aspm_policy", ))

class MockedProc(LocalProcessManager.LocalProcessManager):
    """Mocked version of the 'LocalProcessManager' class."""

    def run_verify(self, command, **kwargs): # pylint: disable=arguments-differ
        """
        Mocked 'run_verify()' method. Inspect 'command' argument and return test data if command is
        relevant to the tests. Otherwise pass call to original method.
        """

        if re.match("find '.*' -type f -regextype posix-extended -regex", command):
            # Mock the call from CStates._get_cstates_info().
            cpus = []
            match = re.search(r"cpu\((\d.*)\)/cpuidle", command)
            if match:
                cpus = match.group(1).split("|")

            indexes = []
            match = re.search(r"cpuidle/state\((\d.*)\)/", command)
            if match:
                indexes = match.group(1).split("|")

            cstinfos = _MOCKED_DATA['cstates'].copy()
            for cstinfo in  _MOCKED_DATA['cstates']:
                cpu = re.findall(r"cpu(\d.*)/cpuidle", cstinfo)[0]
                if cpus and cpu not in cpus:
                    cstinfos.remove(cstinfo)
                    continue

                index = re.findall(r"cpuidle/state(\d.*)/", cstinfo)[0]
                if indexes and index not in indexes:
                    cstinfos.remove(cstinfo)

            fpaths = []
            self._cstvals = []
            keep_fnames = set(CStates.CST_SYSFS_FNAMES)

            for cstinfo in sorted(cstinfos):
                fpath, val = cstinfo.split(":")
                # Skip the unneeded files.
                if fpath.split("/")[-1] in keep_fnames:
                    fpaths.append(f"{fpath}\n")
                    self._cstvals.append(val)

            return (fpaths, "")

        if command.startswith("xargs -a "):
            return (self._cstvals, "")

        if command == "lscpu":
            # Mock the call from CPUInfo._get_cpu_info().
            return (_MOCKED_DATA['lscpu'], "")

        if command == "lscpu --physical --all -p=socket,node,core,cpu,online":
            # Mock the call from CPUInfo.CPUInfo._get_lscpu().
            return (_MOCKED_DATA['lscpu_cpus'], "")

        return _ORIG_PROC.run_verify(command, **kwargs)

    def _get_mock_fobj(self, path, mode):
        """Prepare new file object."""

        # Note: This implementation works only when single user access the file. I.e. when user A
        #       opens the file and write to it. User B opens the same file, but cannot see what user
        #       A wrote to it. Improve it by adding support for multiple users.

        if path in self._mock_fobj and self._mock_fobj[path].write.call_count:
            # Get last write value.
            read_data = self._mock_fobj[path].write.call_args.args[-1].strip()

            # The ASPM policy written to sysfs is expected to be in square brackets when it is read
            # again.
            if str(path) in _MOCKED_ASPM_POLICY_FILES:
                read_data = f"[{read_data}]"
        else:
            read_data = _MOCKED_FILES[str(path)]

        with patch("builtins.open", new_callable=mock_open, read_data=read_data):
            self._mock_fobj[path] = open(path, mode) # pylint: disable=consider-using-with
        return self._mock_fobj[path]

    def open(self, path, mode):
        """Mocked 'open()'."""

        if str(path).endswith("die_id"):
            # Pretend the "die_id" files do not exist, so that 'CPUInfo' will assume there is one
            # die per package.
            raise ErrorNotFound(f"'{path}' not found")

        if str(path) in _MOCKED_FILES:
            return self._get_mock_fobj(path, mode)

        return super().open(path, mode)

    def __init__(self):
        """Initialize mock class instance."""

        super().__init__()

        self._mock_fobj = {}
        self._cstvals = None

class MockedMSR(MSR.MSR):
    """Mock version of MSR class in pepclibs.msr.MSR module."""

    def read(self, regaddr, cpus="all"):
        """
        Mocked version of the 'MSR.read()' method. If MSR at 'regaddr' has not been written to yet,
        this method returns realistic data for MSRs in 'self._mocked_msr' dictionary, and random
        data for all other MSRs.
        """

        if regaddr in self._mocked_msr:
            read_data = int.to_bytes(self._mocked_msr[regaddr] & _MAX64,
                                     self.regbytes, byteorder="little")
        else:
            read_data = random.randbytes(8)

        with patch("builtins.open", new_callable=mock_open, read_data=read_data):
            yield from super().read(regaddr, cpus)

    def write(self, regaddr, regval, cpus="all"):
        """Mocked version of the 'MSR.write()' method."""

        self._mocked_msr[regaddr] = regval

    def __init__(self, pman=None, cpuinfo=None):
        """Initialize MSR object with test data."""

        super().__init__(pman=pman, cpuinfo=cpuinfo)

        self._mocked_msr = {}

        # Use realistice values for few MSRs.
        self._mocked_msr[PCStateConfigCtl.MSR_PKG_CST_CONFIG_CONTROL] = 0x14000402
        self._mocked_msr[PlatformInfo.MSR_PLATFORM_INFO] = 0x8008082ffb811800
        self._mocked_msr[TurboRatioLimit.MSR_TURBO_RATIO_LIMIT] = 0x1f1f212222232323
        self._mocked_msr[PMEnable.MSR_PM_ENABLE] = 1

def mock_exists(path: Path, pman=None): # pylint: disable=unused-argument
    """Mock version of 'exists' function in FSHelpers module."""

    return any(Path(m_path) for m_path in _MOCKED_EXISTS_FILES if str(path) in m_path)

def mock_isfile(path: Path, pman=None):
    """Mock version of 'isfile' function in FSHelpers module."""

    return mock_exists(path, pman)

def mock_lsdir(path: Path, must_exist: bool = True, pman=None):
    """Mock version of 'lsdir' function in FSHelpers module."""

    m_paths = [Path(m_path) for m_path in _MOCKED_FILES if str(path) in m_path]

    if not m_paths:
        yield from FSHelpers.lsdir(path, must_exist=must_exist, pman=pman)
    else:
        # Use test data to generate output similar to 'lsdir()'.
        entries = []
        for m_path in m_paths:
            einfo = {}
            m_path = m_path.relative_to(path)
            einfo["name"] = m_path.parts[0]
            einfo["ftype"] = "/" if len(m_path.parts) > 1 else ""

            if einfo not in entries:
                entries.append(einfo)

        for einfo in entries:
            yield (einfo["name"], path / einfo["name"], einfo["ftype"])

@contextmanager
def get_mocked_objects():
    """
    Helper function to mock 'lsdir()' function in 'FSHelpers' module, 'LocalProcessManager' and
    'MSR' classes. Returns objects as tuple.
    """

    with patch("pepclibs.helperlibs.FSHelpers.lsdir", new=mock_lsdir) as mock_FSHelpers_lsdir, \
         patch("pepclibs.helperlibs.FSHelpers.exists", new=mock_exists),  \
         patch("pepclibs.helperlibs.FSHelpers.isfile", new=mock_isfile), \
         patch("pepclibs.helperlibs.LocalProcessManager.LocalProcessManager",
               new=MockedProc) as mock_pman, \
         patch("pepclibs.msr.MSR.MSR", new=MockedMSR) as mock_msr:
        yield (mock_FSHelpers_lsdir, mock_pman, mock_msr)

def get_test_cpu_info():
    """
    Helper function to return information about the emulated CPU. Emulated methods are same as in
    'get_mocked_objects()'. Returns information as a dictionary.
    """

    with get_mocked_objects() as _, CPUInfo.CPUInfo() as cpuinfo, CStates.CStates() as csobj:
        result = {}
        result["cpus"] = cpuinfo.get_cpus()
        result["max_cpu"] = max(result["cpus"])
        result["cores"] = cpuinfo.package_to_cores(0)
        result["max_core"] = max(result["cores"])
        result["packages"] = cpuinfo.get_packages()
        result["max_package"] = max(result["packages"])
        result["cstates"] = []
        for _, cstinfo in csobj.get_cstates_info(cpus=[0]):
            for csname in cstinfo:
                result["cstates"].append(csname)

        return result
