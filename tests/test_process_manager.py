# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Tests for the 'ProcessManager', 'LocalProcessManager', and 'SSHProcessManager' modules.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import stat
from pathlib import Path
import typing
from typing import Generator, cast
import pytest
import common
from pepclibs.helperlibs import Trivial, LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error, ErrorExists, ErrorNotFound
if typing.TYPE_CHECKING:
    from common import CommonTestParamsTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

@pytest.fixture(name="params", scope="module")
def get_params(hostspec: str) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    Establish a connection to the host described by 'hostspec' and build a dictionary of parameters
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.

    Yields:
        A dictionary containing testing parameters.
    """

    with common.get_pman(hostspec) as pman:
        params = common.build_params(pman)
        yield params

def test_get_envar(params: CommonTestParamsTypedDict):
    """Test the 'get_envar()' method."""

    pman = params["pman"]

    # Let's assume the 'SHELL' environment variable is set.
    shell = pman.get_envar("SHELL")
    assert shell is not None
    assert isinstance(shell, str)

def test_which(params: CommonTestParamsTypedDict):
    """Test the 'which()' method."""

    pman = params["pman"]

    path = pman.which("sh")
    assert path is not None
    assert pman.is_exe(path)

    # Test the 'must_find' argument.
    with pytest.raises(ErrorNotFound):
        pman.which("_bogus_777", must_find=True)

    assert pman.which("_bogus_777", must_find=False) is None

def test_get_python_path(params: CommonTestParamsTypedDict):
    """Test the 'get_python_path()', 'is_exe()' and 'exists()' methods."""

    pman = params["pman"]
    python_path = pman.get_python_path()

    assert pman.exists(python_path)
    assert pman.is_exe(python_path)

def test_time_time(params: CommonTestParamsTypedDict):
    """Test the 'time_time()' method."""

    pman = params["pman"]
    time = pman.time_time()

    assert isinstance(time, float)
    assert time > 0

_HELLO_WORLD_START = """-c 'import sys
print("1: hello")
print("2: world")
print("1: hello-x", file=sys.stderr)
print("2: world-x", file=sys.stderr)"""

_HELLO_WORLD_CMD = _HELLO_WORLD_START + "'"
_HELLO_WORLD_CMD_EXIT_7 = _HELLO_WORLD_START + "\nraise SystemExit(7)'"

def test_run_verify_join_capture_output(params: CommonTestParamsTypedDict):
    """Test the 'join' and 'capture_output' arguments of the 'run_verify()' method."""

    pman = params["pman"]
    python_path = pman.get_python_path()
    cmd = f"{python_path} {_HELLO_WORLD_CMD}"

    stdout, stderr = pman.run_verify(cmd, join=True, capture_output=True)
    assert stdout == "1: hello\n2: world\n"
    assert stderr == "1: hello-x\n2: world-x\n"

    stdout, stderr = pman.run_verify(cmd, join=False, capture_output=True)
    assert stdout == ["1: hello\n", "2: world\n"]
    assert stderr == ["1: hello-x\n", "2: world-x\n"]

    stdout, stderr = pman.run_verify(cmd, join=True, capture_output=False)
    assert stdout == ""
    assert stderr == ""

    stdout, stderr = pman.run_verify(cmd, join=False, capture_output=False)
    assert stdout == []
    assert stderr == []

    stdout, stderr = pman.run_verify(cmd, join=False, capture_output=True, mix_output=True)
    assert sorted(stdout) == ["1: hello\n", "1: hello-x\n", "2: world\n", "2: world-x\n"]
    assert stderr == []

def test_run_verify_output_fobjs(params: CommonTestParamsTypedDict, tmp_path: Path):
    """Test the 'output_fobjs' argument of the 'run_verify()' method."""

    pman = params["pman"]
    python_path = pman.get_python_path()
    cmd = f"{python_path} {_HELLO_WORLD_CMD}"

    stdout_path = tmp_path / "stdout.txt"
    stderr_path = tmp_path / "stderr.txt"
    with open(stdout_path, "w+", encoding="utf-8") as stdout_fobj, \
         open(stderr_path, "w+", encoding="utf-8") as stderr_fobj:
        stdout, stderr = pman.run_verify(cmd, join=True, mix_output=False,
                                         output_fobjs=(stdout_fobj, stderr_fobj))
        assert stdout == "1: hello\n2: world\n"
        assert stderr == "1: hello-x\n2: world-x\n"

        stdout_fobj.seek(0)
        stdout = stdout_fobj.read()
        stderr_fobj.seek(0)
        stderr = stderr_fobj.read()

        assert stdout == "1: hello\n2: world\n"
        assert stderr == "1: hello-x\n2: world-x\n"

        stdout_fobj.seek(0)
        stdout_fobj.truncate(0)
        stderr_fobj.seek(0)
        stderr_fobj.truncate(0)

        stdout, stderr = pman.run_verify(cmd, mix_output=True, join=False,
                                         output_fobjs=(stdout_fobj, stderr_fobj))
        assert sorted(stdout) == ["1: hello\n", "1: hello-x\n",
                                  "2: world\n", "2: world-x\n"]
        assert stderr == []

        stdout_fobj.seek(0)
        stdout = stdout_fobj.read()
        stderr_fobj.seek(0)
        stderr = stderr_fobj.read()

        assert sorted(stdout.splitlines()) == ["1: hello", "1: hello-x",
                                               "2: world", "2: world-x"]
        assert stderr == ""

def test_run_verify_cwd(params: CommonTestParamsTypedDict):
    """Test the 'cwd' argument of the 'run_verify()' method."""

    pman = params["pman"]

    for intsh in (True, False):
        cwd = "/"
        stdout, stderr = pman.run_verify("pwd", cwd=cwd, intsh=intsh)
        assert stdout == f"{cwd}\n"
        assert stderr == ""

        cwd = "/etc"
        stdout, stderr = pman.run_verify("pwd", cwd=cwd, intsh=intsh)
        assert stdout == f"{cwd}\n"
        assert stderr == ""

        # And verify that 'cwd' is not retained across calls.
        stdout, _ = pman.run_verify("pwd", intsh=intsh)
        assert stdout != f"{cwd}\n"

def test_run_verify_env(params: CommonTestParamsTypedDict):
    """Test the 'env' argument of the 'run_verify()' method."""

    pman = params["pman"]

    for intsh in (True, False):
        env = {"TEST_ENV_VAR": "test_value"}
        stdout, stderr = pman.run_verify("echo $TEST_ENV_VAR", env=env, intsh=intsh)
        assert stdout == "test_value\n"
        assert stderr == ""

        # Verify that the environment variable value is not retained across calls.
        stdout, stderr = pman.run_verify("echo $TEST_ENV_VAR", intsh=intsh)
        assert stdout == "\n"
        assert stderr == ""

        stdout, stderr = pman.run_verify("sh -c 'echo $TEST_ENV_VAR'", env=env, intsh=intsh)
        assert stdout == "test_value\n"
        assert stderr == ""

        # Verify that the environment variable value is not retained across calls.
        stdout, stderr = pman.run_verify("sh -c 'echo $TEST_ENV_VAR'", intsh=intsh)
        assert stdout == "\n"
        assert stderr == ""

        # And add 'cwd' to test that it works together with 'env'.
        cwd = "/etc"
        stdout, _ = pman.run_verify("sh -c 'echo $TEST_ENV_VAR; pwd'",
                                    cwd=cwd, env=env, intsh=intsh)
        assert stdout == f"test_value\n{cwd}\n"

def test_run_verify_newgrp(params: CommonTestParamsTypedDict):
    """Test the 'newgrp' argument of the 'run_verify()' method."""

    pman = params["pman"]

    pgid = Trivial.get_pgid(Trivial.get_pid())

    # Note, in case of a remote host, the 'newgrp' argument is useless, and the PGID of the remote
    # process will always be different from the PGID of the local process.

    for intsh in (True, False):
        stdout, stderr = pman.run_verify("ps -o pgid= -p $$", newgrp=False, intsh=intsh)
        if not pman.is_remote:
            assert cast(str, stdout).strip() == str(pgid)
            assert stderr == ""

        stdout, _ = pman.run_verify("ps -o pgid= -p $$", newgrp=True, intsh=intsh)
        if not pman.is_remote:
            assert cast(str, stdout).strip() != str(pgid)

def test_run_verify_fail(params: CommonTestParamsTypedDict):
    """Test the 'run_verify()' method with a failing command."""

    pman = params["pman"]
    python_path = pman.get_python_path()
    cmd = f"{python_path} {_HELLO_WORLD_CMD_EXIT_7}"

    with pytest.raises(Error) as excinfo:
        pman.run_verify(cmd)
    assert "exit code 7" in str(excinfo.value)
    assert "hello-x" in str(excinfo.value)

    cmd = "__this_command_should_not_exist__"
    with pytest.raises(ErrorNotFound):
        pman.run_verify(cmd)

def test_run_fail(params: CommonTestParamsTypedDict):
    """Test the 'run()' method. Cover 'get_cmd_failure_msg()' too."""

    # The 'run_verify()' method has already been tested, and it is a wrapper around the 'run()'
    # method. So test only the aspects of 'run()' that are not covered by the 'run_verify()' tests.

    pman = params["pman"]
    python_path = pman.get_python_path()
    cmd = f"{python_path} {_HELLO_WORLD_CMD_EXIT_7}"

    stdout, stderr, exitcode = pman.run(cmd)
    assert stdout == "1: hello\n2: world\n"
    assert stderr == "1: hello-x\n2: world-x\n"
    assert exitcode == 7

    errmsg = pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode, startmsg="Test")
    assert errmsg.startswith("Test\n")

    # And do the same with "join=False".
    stdout, stderr, exitcode = pman.run(cmd, join=False)
    assert stdout == ["1: hello\n", "2: world\n"]
    assert stderr == ["1: hello-x\n", "2: world-x\n"]
    assert exitcode == 7

    errmsg = pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode, startmsg="Test_")
    assert errmsg.startswith("Test_\n")

    errmsg = pman.get_cmd_failure_msg(cmd, stdout, stderr, exitcode)
    assert "hello-x" in errmsg

def test_run_async_wait(params: CommonTestParamsTypedDict):
    """Test the 'run_async()', 'poll()' and 'wait()' methods."""

    # The already tested 'run_verify()' method is based on 'run_async()' and then "wait for the
    # command to finish" call to 'wait()'. So a big part of the 'run_async()' functionality is
    # covered by the 'run_verify()' tests. Focus on testing 'run_async()' and 'wait()' methods with
    # use-cases that were not yet covered.

    pman = params["pman"]
    python_path = pman.get_python_path()

    cmd = f"{python_path} {_HELLO_WORLD_CMD}"
    for intsh in (True, False):
        proc = pman.run_async(cmd, intsh=intsh)

        res = proc.wait(lines=(1, 1))
        assert res.stdout == "1: hello\n"
        assert res.stderr == "1: hello-x\n"
        assert res.exitcode is None
        assert proc.poll() is None

        res = proc.wait(lines=(1, 1))
        assert res.stdout == "2: world\n"
        assert res.stderr == "2: world-x\n"

        res = proc.wait()
        assert res.stdout == ""
        assert res.stderr == ""
        assert res.exitcode == 0

        proc = pman.run_async(cmd, intsh=intsh)

        res = proc.wait(lines=(1, -1))
        assert res.stdout == "1: hello\n"
        assert res.stderr == ""
        assert res.exitcode is None

        res = proc.wait(lines=(-1, 1))
        assert res.stdout == ""
        assert res.stderr == "1: hello-x\n"

        res = proc.wait(lines=(1, -1))
        assert res.stdout == "2: world\n"
        assert res.stderr == ""
        assert res.exitcode is None

        res = proc.wait(lines=(-1, 1))
        assert res.stdout == ""
        assert res.stderr == "2: world-x\n"

        res = proc.wait()
        assert res.stdout == ""
        assert res.stderr == ""
        assert res.exitcode == 0
        assert proc.poll() == 0

        proc = pman.run_async(cmd, intsh=intsh)

        stdouts: list[str] = []
        res = proc.wait(lines=(0, 1), join=False)
        stdouts += res.stdout
        assert res.stderr == ["1: hello-x\n"]
        if len(stdouts) < 2:
            assert res.exitcode is None

        res = proc.wait(lines=(0, 1), join=False)
        stdouts += res.stdout
        assert res.stderr == ["2: world-x\n"]
        if len(stdouts) < 2:
            assert res.exitcode is None

        res = proc.wait(join=False)
        stdouts += res.stdout
        assert res.stderr == []
        assert res.exitcode == 0

        assert stdouts == ["1: hello\n", "2: world\n"]

    # Test running several async processes in parallel.
    proc1 = pman.run_async(cmd, intsh=False)
    proc2 = pman.run_async(cmd, intsh=True)
    proc3 = pman.run_async(cmd, intsh=False)

    res = proc1.wait(lines=(1, 1))
    assert res.stdout == "1: hello\n"
    assert res.stderr == "1: hello-x\n"
    assert res.exitcode is None

    res = proc2.wait(lines=(1, 0), join=False)
    assert res.stdout == ["1: hello\n"]
    assert res.exitcode is None

    res = proc3.wait(lines=(0, 1))
    assert res.stderr == "1: hello-x\n"
    assert res.exitcode is None

    res = proc1.wait()
    assert res.exitcode == 0
    res = proc2.wait()
    assert res.exitcode == 0
    res = proc3.wait()
    assert res.exitcode == 0

    # Test unusual 'lines' values.
    proc = pman.run_async(cmd)
    res = proc.wait(lines=(-1, -1))
    assert res.stdout == ""
    assert res.stderr == ""
    assert res.exitcode is None

    res = proc.wait(lines=(-1, 0))
    assert res.stdout == ""
    assert res.exitcode is None

    res = proc.wait(lines=(0, -1))
    assert res.stderr == ""

    res = proc.wait()
    assert res.exitcode == 0

    # Test running 'wait()' on a finished process.
    res = proc.wait()
    assert res.stdout == ""
    assert res.stderr == ""
    assert res.exitcode == 0

def test_mkdir(params: CommonTestParamsTypedDict):
    """Test the 'mkdir()', 'rmtree()', and 'is_dir()' methods."""

    pman = params["pman"]

    tmpdir = pman.mkdtemp()
    test_dir = tmpdir / "test_dir"

    pman.mkdir(test_dir)
    assert pman.is_dir(test_dir)

    # Test the 'parents' argument.
    test_dir = tmpdir / "test_dir1" / "test_dir2" / "test_dir3"
    pman.mkdir(test_dir, parents=True)
    assert pman.is_dir(test_dir)

    # Test the 'exist_ok' argument.
    pman.mkdir(test_dir, exist_ok=True)

    with pytest.raises(ErrorExists):
        pman.mkdir(test_dir, exist_ok=False)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_mksocket(params: CommonTestParamsTypedDict):
    """Test the 'mksocket()' and 'is_socket()' methods."""

    pman = params["pman"]

    tmpdir = pman.mkdtemp()
    test_socket = tmpdir / "test_socket"

    pman.mksocket(test_socket)

    # Test the 'exist_ok' argument.
    pman.mksocket(test_socket, exist_ok=True)
    with pytest.raises(ErrorExists):
        pman.mksocket(test_socket, exist_ok=False)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_mkfifo(params: CommonTestParamsTypedDict):
    """Test the 'mkfifo()' and 'is_fifo()' methods."""

    pman = params["pman"]

    tmpdir = pman.mkdtemp()
    test_fifo = tmpdir / "test_fifo"

    pman.mkfifo(test_fifo)
    assert pman.is_fifo(test_fifo)

    # Test the 'exist_ok' argument.
    pman.mkfifo(test_fifo, exist_ok=True)
    with pytest.raises(ErrorExists):
        pman.mkfifo(test_fifo, exist_ok=False)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_mkdtemp(params: CommonTestParamsTypedDict):
    """Test the 'mkdtemp()' method and 'rmtree()' methods."""

    pman = params["pman"]

    # Test creating a temporary.
    tmpdir = pman.mkdtemp()
    assert pman.is_dir(tmpdir)

    # Create a sub-directory in it to test that the directory is writable.
    subdir = tmpdir / "subdir"
    pman.mkdir(subdir)
    assert pman.is_dir(subdir)

    # Test creating a temporary with a prefix and a base directory.
    tmpdir1 = pman.mkdtemp(prefix="test_", basedir=subdir)
    assert str(tmpdir1.name).startswith("test_")
    assert str(tmpdir1).startswith(str(subdir))
    assert pman.is_dir(tmpdir1)

    # Delete the temporary directory (cleanup step).
    pman.rmtree(tmpdir)
    assert not pman.exists(tmpdir)

def test_open(params: CommonTestParamsTypedDict):
    """Test the 'open()', 'get_mtime()', and 'is_file()' methods."""

    pman = params["pman"]

    tmpdir = pman.mkdtemp()

    mtime = pman.get_mtime(tmpdir)
    assert isinstance(mtime, float)
    assert mtime > 0

    test_file = tmpdir / "test.txt"

    # Test opening a file for writing.
    with pman.open(test_file, "w") as fobj:
        fobj.write("Hello, world!")
        assert pman.is_file(test_file)

    assert pman.is_file(test_file)

    mtime = pman.get_mtime(test_file)
    assert isinstance(mtime, float)
    assert mtime > 0

    # Test opening a file for reading.
    with pman.open(test_file, "r") as fobj:
        assert fobj.read(6) == "Hello,"
        assert fobj.read(1) == " "
        assert fobj.read(6) == "world!"
        assert fobj.read(1) == ""
        assert fobj.read() == ""

    # Test binary mode.
    fobj = pman.open(test_file, "bw+")
    fobj.write(b"Hello, world!")
    assert pman.is_file(test_file)
    fobj.seek(0)
    assert fobj.read() == b"Hello, world!"
    assert fobj.read() == b""
    fobj.close()

    # Test truncate.
    with pman.open(test_file, "r+") as fobj:
        fobj.truncate(6)
        fobj.seek(0)
        assert fobj.read() == "Hello,"

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_get(params: CommonTestParamsTypedDict, tmp_path: Path):
    """Test the 'get()' method."""

    pman = params["pman"]

    # Test getting a file.
    remote_tmpdir = pman.mkdtemp()
    remote_src_file = remote_tmpdir / "test.txt"
    with pman.open(remote_src_file, "w") as fobj:
        fobj.write("Hello, dude!")

    local_dst_file = tmp_path / "test_copy.txt"
    pman.get(remote_src_file, local_dst_file)
    with open(local_dst_file, "r", encoding="utf-8") as fobj:
        assert fobj.read() == "Hello, dude!"

    # Cleanup step.
    pman.rmtree(remote_tmpdir)

def test_put(params: CommonTestParamsTypedDict, tmp_path: Path):
    """Test the 'put()' method."""

    pman = params["pman"]
    local_src_file = tmp_path / "test.txt"
    with open(local_src_file, "w", encoding="utf-8") as fobj:
        fobj.write("Hello, dude!")

    remote_tmpdir = pman.mkdtemp()
    remote_dst_file = remote_tmpdir / "test_copy.txt"
    pman.put(local_src_file, remote_dst_file)
    assert pman.is_file(remote_dst_file)

    with pman.open(remote_dst_file, "r") as fobj:
        assert fobj.read() == "Hello, dude!"

    # Cleanup step.
    pman.rmtree(remote_tmpdir)

def _create_test_dir(pman: ProcessManagerType, path: Path):
    """
    Create a test directory with a test sub-directory and test files.

    Args:
        pman: The process manager defining the host to create the test directory on.
        path: The path to the test directory.
    """

    pman.mkdir(path)

    subdir = path / "subdir"
    pman.mkdir(subdir)
    with pman.open(subdir/ "test.txt", "w") as fobj:
        fobj.write("Hello, test!")

    pman.mksocket(path / "test.socket")
    pman.mkfifo(path / "test.fifo")

def _check_test_dir(pman: ProcessManagerType, path: Path):
    """
    Check the contents of a test directory.

    Args:
        pman: The process manager defining the host to check the test directory on.
        path: The path to the test directory.
    """

    assert pman.is_dir(path)

    subdir = path / "subdir"
    assert pman.is_dir(subdir)
    assert pman.is_file(subdir / "test.txt")

    with pman.open(subdir / "test.txt", "r") as fobj:
        assert fobj.read() == "Hello, test!"

    assert pman.is_socket(path / "test.socket")
    assert pman.is_fifo(path / "test.fifo")

def test_rsync(params: CommonTestParamsTypedDict, tmp_path: Path):
    """Test the 'rsync()' method."""

    pman = params["pman"]

    if pman.is_remote:
        tmpdir = pman.mkdtemp()
    else:
        tmpdir = tmp_path

    # Create a test directory.
    src = tmpdir / "src"
    _create_test_dir(pman, src)
    _check_test_dir(pman, src)

    if not pman.is_remote:
        dst = tmpdir / "dst"
        pman.rsync(str(src) + "/", dst, remotesrc=False, remotedst=False)
        _check_test_dir(pman, dst)

        pman.rsync(src, dst, remotesrc=False, remotedst=False)
        _check_test_dir(pman, dst / src.name)

        # Check over-writing the destination directory.
        pman.rsync(src, dst, remotesrc=False, remotedst=False)
        _check_test_dir(pman, dst / src.name)

        # Local process manager supports only local-to-local rsync. There is nothing more to test.
        return

    # Test remote-to-remote rsync.
    dst = tmpdir / "dst"
    pman.rsync(str(src) + "/", dst, remotesrc=True, remotedst=True)
    _check_test_dir(pman, dst)

    pman.rsync(src, dst, remotesrc=True, remotedst=True)
    _check_test_dir(pman, dst / src.name)

    # Check over-writing the destination directory.
    pman.rsync(src, dst, remotesrc=True, remotedst=True)
    _check_test_dir(pman, dst / src.name)

    # Test remote-to-local rsync.
    dst = tmp_path / "dst"
    pman.rsync(str(src) + "/", dst, remotesrc=True, remotedst=False)
    with LocalProcessManager.LocalProcessManager() as lpman:
        _check_test_dir(lpman, dst)

    pman.rsync(src, dst, remotesrc=True, remotedst=False)
    with LocalProcessManager.LocalProcessManager() as lpman:
        _check_test_dir(lpman, dst)

    # Check over-writing the destination directory.
    pman.rsync(src, dst, remotesrc=True, remotedst=False)
    with LocalProcessManager.LocalProcessManager() as lpman:
        _check_test_dir(lpman, dst)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_read(params: CommonTestParamsTypedDict):
    """Test the 'read()' method."""

    pman = params["pman"]

    # Create a test file.
    tmpdir = pman.mkdtemp()
    test_file = tmpdir / "test.txt"
    with pman.open(test_file, "w") as fobj:
        fobj.write("Hello, world!")

    # Test reading the file.
    assert pman.read_file(test_file) == "Hello, world!"

    # Test the 'ErrorNonFound' exception.
    bogus_path = tmpdir / "bogus.txt"
    with pytest.raises(ErrorNotFound):
        pman.read_file(bogus_path)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_lsdir(params: CommonTestParamsTypedDict):
    """Test the 'lsdir()' method."""

    pman = params["pman"]

    # Create a test directory.
    tmpdir = pman.mkdtemp()
    test_dir = tmpdir / "test_dir"
    _create_test_dir(pman, test_dir)

    # Test listing the directory.
    count = 0
    for info in pman.lsdir(test_dir):
        count += 1
        if info["name"] == "subdir":
            assert stat.S_ISDIR(info["mode"])
        elif info["name"] == "test.socket":
            assert stat.S_ISSOCK(info["mode"])
        elif info["name"] == "test.fifo":
            assert stat.S_ISFIFO(info["mode"])
        else:
            assert False, f"Unexpected file name: {info['name']}"

        assert info["path"] == test_dir / info["name"]
        assert isinstance(info["ctime"], float)

    # Test the 'ErrorNotFound' exception.
    bogus_dir = test_dir / "bogus"
    with pytest.raises(ErrorNotFound):
        for info in pman.lsdir(bogus_dir):
            pass

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_unlink(params: CommonTestParamsTypedDict):
    """Test the 'unlink()' method."""

    pman = params["pman"]

    # Create a test file.
    tmpdir = pman.mkdtemp()
    test_dir= tmpdir / "tst_dir"
    _create_test_dir(pman, test_dir)

    test_file = test_dir / "subdir" / "test.txt"
    pman.unlink(test_file)
    assert not pman.is_file(test_file)

    test_file = test_dir / "test.socket"
    pman.unlink(test_file)
    assert not pman.is_socket(test_file)

    test_file = test_dir / "test.fifo"
    pman.unlink(test_file)
    assert not pman.is_fifo(test_file)

    # Cleanup step.
    pman.rmtree(tmpdir)

def test_abspath(params: CommonTestParamsTypedDict):
    """Test the 'abspath()' method."""

    pman = params["pman"]
    tmpdir = pman.mkdtemp()

    test_dir = tmpdir / "test_dir"
    pman.mkdir(test_dir)

    assert pman.abspath(test_dir) == test_dir
    assert pman.abspath(str(test_dir)) == test_dir
    assert pman.abspath(str(test_dir) + "/") == test_dir

    assert pman.abspath(test_dir / ".." / "test_dir") == test_dir
    assert pman.abspath(test_dir / "..") == tmpdir

    # Test the 'ErrorNotFound' exception.
    bogus_path = tmpdir / "bogus"
    with pytest.raises(ErrorNotFound):
        pman.abspath(bogus_path)
