# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Tests for the 'PythonPrjInstaller' module.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import stat
import subprocess
from pathlib import Path

import pytest

from tests import _Common

from pepctools import PythonPrjInstaller, InstallPepc

if typing.TYPE_CHECKING:
    from typing import Final, Generator
    from tests._Common import CommonTestParamsTypedDict

    class _TestParamsTypedDict(CommonTestParamsTypedDict, total=False):
        """
        The test parameters dictionary for 'PythonPrjInstaller' tests.

        Attributes:
            installer: A 'PythonPrjInstaller' instance with pepc installed.
            tpmi_debugfs: Path to the TPMI debugfs dump on the target host.
        """

        installer: PythonPrjInstaller.PythonPrjInstaller
        tpmi_debugfs: Path

# Path to the TPMI debugfs dump used for data-file verification tests.
_TPMI_DEBUGFS_DUMP: Final[Path] = _Common.get_test_data_base() / "test_tpmi_nohost" / "debugfs-dump"

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str, username: str) -> Generator[_TestParamsTypedDict, None, None]:
    """
    Install pepc on the target host and yield test parameters.

    Args:
        hostspec: The host specification/name to create a process manager for.
        username: The username to use when connecting to a remote host.

    Yields:
        A dictionary with test parameters including the installer and TPMI test data path.
    """

    with _Common.get_pman(hostspec, username=username) as pman:
        install_path = pman.mkdtemp(prefix="pepc-venv-")
        tpmi_base: Path | None = None
        try:
            inst = PythonPrjInstaller.PythonPrjInstaller("pepc", str(_Common.get_prj_src_path()),
                                                          pman=pman, install_path=install_path,
                                                          logging=True)
            inst.install(exclude=InstallPepc.PEPC_COPY_EXCLUDE)
            inst.create_rc_file()

            if pman.is_remote:
                # Copy the TPMI test data to the remote host for use in tests.
                tpmi_base = pman.mkdtemp(prefix="pepc-tpmi-test-")
                tpmi_debugfs = tpmi_base / "debugfs-dump"
                pman.rsync(str(_TPMI_DEBUGFS_DUMP) + "/", tpmi_debugfs,
                           remotesrc=False, remotedst=True)
            else:
                tpmi_debugfs = _TPMI_DEBUGFS_DUMP

            params: _TestParamsTypedDict = {**_Common.build_params(pman),  # type: ignore[misc]
                                            "installer": inst,
                                            "tpmi_debugfs": tpmi_debugfs}
            yield params
        finally:
            pman.rmtree(install_path)
            if tpmi_base is not None:
                pman.rmtree(tpmi_base)

def test_install_layout(params: _TestParamsTypedDict):
    """
    Verify that 'install()' creates the expected virtual environment layout.

    Args:
        params: A dictionary with test parameters.
    """

    pman = params["pman"]
    installer = params["installer"]

    pepc_bin = installer.install_path / "bin" / "pepc"
    assert pman.is_file(pepc_bin), f"Expected 'pepc' binary at '{pepc_bin}'"

    rcfile = installer.rcfile_path
    assert pman.is_file(rcfile), f"Expected RC file at '{rcfile}'"

def test_install_runs(params: _TestParamsTypedDict):
    """
    Verify the installed 'pepc' binary executes and reports its version.

    Args:
        params: A dictionary with test parameters.
    """

    pman = params["pman"]
    pepc_bin = params["installer"].install_path / "bin" / "pepc"
    pman.run_verify(f"'{pepc_bin}' --version")

def test_standalone_created(params: _TestParamsTypedDict, tmp_path: Path):
    """
    Verify that 'create_standalone()' produces an executable file.

    Args:
        params: A dictionary with test parameters.
        tmp_path: The pytest temporary directory for the standalone output file.
    """

    if params["pman"].is_remote:
        pytest.skip("Standalone creation is not supported for remote hosts")

    output_path = tmp_path / "pepc-standalone"
    params["installer"].create_standalone("pepc", output_path)

    assert output_path.is_file(), f"Expected standalone executable at '{output_path}'"
    assert output_path.stat().st_mode & stat.S_IXUSR, \
           f"Standalone executable is not executable: '{output_path}'"

def test_standalone_runs(params: _TestParamsTypedDict, tmp_path: Path):
    """
    Verify the standalone 'pepc' executable runs and reports its version.

    Args:
        params: A dictionary with test parameters.
        tmp_path: The pytest temporary directory for the standalone output file.
    """

    if params["pman"].is_remote:
        pytest.skip("Standalone creation is not supported for remote hosts")

    output_path = tmp_path / "pepc-standalone"
    params["installer"].create_standalone("pepc", output_path)

    result = subprocess.run([str(output_path), "--version"], capture_output=True, check=False)
    assert result.returncode == 0, \
           f"Standalone 'pepc --version' failed with exit code {result.returncode}:\n" \
           f"{result.stderr.decode()}"

def test_install_data_files(params: _TestParamsTypedDict):
    """
    Verify the installed 'pepc' can access its data files (e.g., TPMI spec files).

    Run 'pepc tpmi ls' against a local debugfs dump. If the TPMI spec files are missing from the
    installation, the command will fail to decode any features.

    Args:
        params: A dictionary with test parameters.
    """

    pman = params["pman"]
    pepc_bin = params["installer"].install_path / "bin" / "pepc"
    tpmi_debugfs = params["tpmi_debugfs"]
    pman.run_verify(f"'{pepc_bin}' tpmi ls --base '{tpmi_debugfs}'")

def test_standalone_data_files(params: _TestParamsTypedDict, tmp_path: Path):
    """
    Verify the standalone 'pepc' zipapp bundles its data files (e.g., TPMI spec files).

    Run 'pepc tpmi ls' against a local debugfs dump using the standalone executable. If the TPMI
    spec files are not bundled in the zip archive, the command will fail to decode any features.

    Args:
        params: A dictionary with test parameters.
        tmp_path: The pytest temporary directory for the standalone output file.
    """

    if params["pman"].is_remote:
        pytest.skip("Standalone creation is not supported for remote hosts")

    output_path = tmp_path / "pepc-standalone"
    params["installer"].create_standalone("pepc", output_path)

    result = subprocess.run([str(output_path), "tpmi", "ls", "--base", str(_TPMI_DEBUGFS_DUMP)],
                            capture_output=True, check=False)
    assert result.returncode == 0, \
           f"Standalone 'pepc tpmi ls' failed with exit code {result.returncode}:\n" \
           f"{result.stderr.decode()}"
