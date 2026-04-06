# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide types and protocol classes defining the interfaces of process manager and process objects.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from typing import NamedTuple, Protocol

if typing.TYPE_CHECKING:
    from typing import IO, Generator, Literal, TypedDict

    class LsdirTypedDict(TypedDict):
        """
        A directory entry information dictionary.

        Attributes:
            name: The name of the directory entry (a file, a directory, etc).
            path: The full path to the directory entry.
            mode: The mode (permissions) of the directory entry.
            ctime: The creation time of the directory entry in seconds since the epoch.
        """

        name: str
        path: Path
        mode: int
        ctime: float

    LsdirSortbyType = Literal["none", "ctime", "alphabetic", "natural"]

class ProcWaitResultJoinType(NamedTuple):
    """
    The result of the 'run_join()' method for a process with joined output lines.

    Attributes:
        stdout: The standard output of the process as a single string. The tailing newline is
                not stripped.
        stderr: The standard error of the process as a single string. The tailing newline is
                not stripped.
        exitcode: The exit code of the process. Can be 'None' if the process is still running.
    """

    stdout: str
    stderr: str
    exitcode: int | None

class ProcWaitResultNoJoinType(NamedTuple):
    """
    The result of the 'run_nojoin()' method for a process with non-joined output lines.

    Attributes:
        stdout: The standard output of the process as a list of strings lines. The tailing
                newline is not stripped.
        stderr: The standard error of the process as a list of strings lines. The tailing
                newline is not stripped.
        exitcode: The exit code of the process. Can be 'None' if the process is still running.
    """

    stdout: list[str]
    stderr: list[str]
    exitcode: int | None

class ProcWaitResultType(NamedTuple):
    """
    The result of the 'wait()' method for a process.

    Attributes:
        stdout: The standard output of the process. Can be a single string or a list of strings
                lines. The tailing newline is not stripped.
        stderr: The standard error of the process. Can be a single string or a list of strings
                lines. The tailing newline is not stripped.
        exitcode: The exit code of the process. Can be an integer or None if the process is still
                  running.
    """

    stdout: str | list[str]
    stderr: str | list[str]
    exitcode: int | None

# Protocol methods require '...' after docstrings to satisfy Pylance. But Pylint flags this as
# unnecessary '...', so disable the "unnecessary-ellipsis" warning for the entire file.
# pylint: disable=unnecessary-ellipsis

class ProcessProtocol(Protocol):
    """Protocol describing the public interface of a process object."""

    exitcode: int | None
    cmd: str
    real_cmd: str

    def wait(self,
             timeout: int | float | None = ...,
             capture_output: bool = ...,
             output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
             lines: tuple[int, int] = ...,
             join: bool = ...) -> ProcWaitResultType:
        """Refer to 'ProcessBase.wait()'."""
        ...

    def poll(self) -> int | None:
        """Refer to 'ProcessBase.poll()'."""
        ...

    def get_cmd_failure_msg(self,
                            stdout: str | list[str],
                            stderr: str | list[str],
                            exitcode: int | None,
                            timeout: int | float | None = ...,
                            startmsg: str = ...,
                            failed: bool = ...) -> str:
        """Refer to 'ProcessBase.get_cmd_failure_msg()'."""
        ...

    def close(self) -> None:
        """Refer to 'ProcessBase.close()'."""
        ...

    def __enter__(self) -> ProcessProtocol:
        """Refer to 'ProcessBase.__enter__()'."""
        ...

    def __exit__(self, *args: object) -> None:
        """Refer to 'ProcessBase.__exit__()'."""
        ...

class ProcessManagerProtocol(Protocol):
    """Protocol describing the public interface of a process manager object."""

    is_remote: bool
    is_emulated: bool
    hostname: str
    hostmsg: str

    def run_async(self,
                  cmd: str | Path,
                  cwd: str | Path | None = ...,
                  intsh: bool = ...,
                  stdin: IO | None = ...,
                  stdout: IO | None = ...,
                  stderr: IO | None = ...,
                  env: dict[str, str] | None = ...,
                  newgrp: bool = ...,
                  su: bool = ...) -> ProcessProtocol:
        """Refer to 'ProcessManagerBase.run_async()'."""
        ...

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = ...,
            capture_output: bool = ...,
            mix_output: bool = ...,
            join: bool = ...,
            output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
            cwd: str | Path | None = ...,
            intsh: bool = ...,
            env: dict[str, str] | None = ...,
            newgrp: bool = ...,
            su: bool = ...) -> ProcWaitResultType:
        """Refer to 'ProcessManagerBase.run()'."""
        ...

    def run_join(self,
                 cmd: str | Path,
                 timeout: int | float | None = ...,
                 capture_output: bool = ...,
                 mix_output: bool = ...,
                 output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
                 cwd: str | Path | None = ...,
                 intsh: bool = ...,
                 env: dict[str, str] | None = ...,
                 newgrp: bool = ...,
                 su: bool = ...) -> ProcWaitResultJoinType:
        """Refer to 'ProcessManagerBase.run_join()'."""
        ...

    def run_nojoin(self,
                   cmd: str | Path,
                   timeout: int | float | None = ...,
                   capture_output: bool = ...,
                   mix_output: bool = ...,
                   output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
                   cwd: str | Path | None = ...,
                   intsh: bool = ...,
                   env: dict[str, str] | None = ...,
                   newgrp: bool = ...,
                   su: bool = ...) -> ProcWaitResultNoJoinType:
        """Refer to 'ProcessManagerBase.run_nojoin()'."""
        ...

    def run_verify(self,
                   cmd: str | Path,
                   timeout: int | float | None = ...,
                   capture_output: bool = ...,
                   mix_output: bool = ...,
                   join: bool = ...,
                   output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
                   cwd: str | Path | None = ...,
                   intsh: bool = ...,
                   env: dict[str, str] | None = ...,
                   newgrp: bool = ...,
                   su: bool = ...) -> tuple[str | list[str], str | list[str]]:
        """Refer to 'ProcessManagerBase.run_verify()'."""
        ...

    def run_verify_join(self,
                        cmd: str | Path,
                        timeout: int | float | None = ...,
                        capture_output: bool = ...,
                        mix_output: bool = ...,
                        output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
                        cwd: str | Path | None = ...,
                        intsh: bool = ...,
                        env: dict[str, str] | None = ...,
                        newgrp: bool = ...,
                        su: bool = ...) -> tuple[str, str]:
        """Refer to 'ProcessManagerBase.run_verify_join()'."""
        ...

    def run_verify_nojoin(self,
                          cmd: str | Path,
                          timeout: int | float | None = ...,
                          capture_output: bool = ...,
                          mix_output: bool = ...,
                          output_fobjs: tuple[IO[str] | None, IO[str] | None] = ...,
                          cwd: str | Path | None = ...,
                          intsh: bool = ...,
                          env: dict[str, str] | None = ...,
                          newgrp: bool = ...,
                          su: bool = ...) -> tuple[list[str], list[str]]:
        """Refer to 'ProcessManagerBase.run_verify_nojoin()'."""
        ...

    def is_superuser(self) -> bool:
        """Refer to 'ProcessManagerBase.is_superuser()'."""
        ...

    def has_passwdless_sudo(self) -> bool:
        """Refer to 'ProcessManagerBase.has_passwdless_sudo()'."""
        ...

    def rsync(self,
              src: str | Path,
              dst: str | Path,
              opts: str = ...,
              remotesrc: bool = ...,
              remotedst: bool = ...) -> None:
        """Refer to 'ProcessManagerBase.rsync()'."""
        ...

    def get(self, src: str | Path, dst: str | Path) -> None:
        """Refer to 'ProcessManagerBase.get()'."""
        ...

    def put(self, src: str | Path, dst: str | Path) -> None:
        """Refer to 'ProcessManagerBase.put()'."""
        ...

    def get_cmd_failure_msg(self,
                            cmd: str | Path,
                            stdout: str | list[str],
                            stderr: str | list[str],
                            exitcode: int | None,
                            timeout: int | float | None = ...,
                            startmsg: str = ...,
                            failed: bool = ...) -> str:
        """Refer to 'ProcessManagerBase.get_cmd_failure_msg()'."""
        ...

    def open(self, path: str | Path, mode: str, su: bool = ...) -> IO[str]:
        """Refer to 'ProcessManagerBase.open()'."""
        ...

    def openb(self, path: str | Path, mode: str, su: bool = ...) -> IO[bytes]:
        """Refer to 'ProcessManagerBase.openb()'."""
        ...

    def read_file(self, path: Path | str) -> str:
        """Refer to 'ProcessManagerBase.read_file()'."""
        ...

    def get_python_path(self) -> Path:
        """Refer to 'ProcessManagerBase.get_python_path()'."""
        ...

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""
        ...

    def mkdir(self,
              dirpath: str | Path,
              parents: bool = ...,
              exist_ok: bool = ...) -> None:
        """Refer to 'ProcessManagerBase.mkdir()'."""
        ...

    def mksocket(self, path: str | Path, exist_ok: bool = ...) -> None:
        """Refer to 'ProcessManagerBase.mksocket()'."""
        ...

    def mkfifo(self, path: str | Path, exist_ok: bool = ...) -> None:
        """Refer to 'ProcessManagerBase.mkfifo()'."""
        ...

    def lsdir(self,
              path: str | Path,
              sort_by: LsdirSortbyType = ...,
              reverse: bool = ...,
              su: bool = ...) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase.lsdir()'."""
        ...

    def exists(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.exists()'."""
        ...

    def is_file(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_file()'."""
        ...

    def is_dir(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_dir()'."""
        ...

    def is_exe(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_exe()'."""
        ...

    def is_socket(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_socket()'."""
        ...

    def is_fifo(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_fifo()'."""
        ...

    def get_mtime(self, path: str | Path) -> float:
        """Refer to 'ProcessManagerBase.get_mtime()'."""
        ...

    def unlink(self, path: str | Path) -> None:
        """Refer to 'ProcessManagerBase.unlink()'."""
        ...

    def rmtree(self, path: str | Path) -> None:
        """Refer to 'ProcessManagerBase.rmtree()'."""
        ...

    def abspath(self, path: str | Path) -> Path:
        """Refer to 'ProcessManagerBase.abspath()'."""
        ...

    def mkdtemp(self,
                prefix: str = ...,
                basedir: str | Path | None = ...) -> Path:
        """Refer to 'ProcessManagerBase.mkdtemp()'."""
        ...

    def get_envar(self, envar: str) -> str | None:
        """Refer to 'ProcessManagerBase.get_envar()'."""
        ...

    def which(self,
              program: str | Path,
              must_find: bool = ...) -> Path | None:
        """Refer to 'ProcessManagerBase.which()'."""
        ...

    def close(self) -> None:
        """Refer to 'ProcessManagerBase.close()'."""
        ...

    def __enter__(self) -> ProcessManagerProtocol:
        """Refer to 'ProcessManagerBase.__enter__()'."""
        ...

    def __exit__(self, *args: object) -> None:
        """Refer to 'ProcessManagerBase.__exit__()'."""
        ...
