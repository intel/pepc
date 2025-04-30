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

from pathlib import Path
from typing import Generator, cast
import pytest
import common
from common import CommonTestParamsTypedDict
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

@pytest.fixture(name="params", scope="module")
def get_params(hostspec) -> Generator[CommonTestParamsTypedDict, None, None]:
    """
    Generate a dictionary with testing parameters.

    This function establishes a connection to the process manager (pman) 
    for the given host specification and builds a dictionary of parameters 
    required for testing.

    Args:
        hostspec: Host specification used to establish the connection.

    Yields:
        A dictionary containing testing parameters.
    """

    with common.get_pman(hostspec) as pman:
        params = common.build_params(pman)
        yield params

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
    """Test the 'run_async()' and 'wait()' methods."""

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

        res = proc.wait(lines=(1, 1))
        assert res.stdout == "2: world\n"
        assert res.stderr == "2: world-x\n"

        res = proc.wait()
        assert res.stdout == ""
        assert res.stderr == ""
        assert res.exitcode == 0

        proc = pman.run_async(cmd, intsh=intsh)

        stdouts = []
        res = proc.wait(lines=(0, 1), join=False)
        stdouts += cast(list[str], res.stdout)
        assert res.stderr == ["1: hello-x\n"]
        if len(stdouts) < 2:
            assert res.exitcode is None

        res = proc.wait(lines=(0, 1), join=False)
        stdouts += cast(list[str], res.stdout)
        assert res.stderr == ["2: world-x\n"]
        if len(stdouts) < 2:
            assert res.exitcode is None

        res = proc.wait(join=False)
        stdouts += cast(list[str], res.stdout)
        assert res.stderr == []
        assert res.exitcode == 0

        assert stdouts == ["1: hello\n", "2: world\n"]
