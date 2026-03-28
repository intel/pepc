# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
A process manager that emulates a SUT for testing purposes.

Provide the 'EmulProcessManager' class, a subclass of 'LocalProcessManager' that pretends to execute
commands on a SUT, but performs local operations, returning pre-defined results based on emulation
data previously collected from a real SUT using the 'tdgen' tool.

Terminology:
    - Emulation data: The data collected from a real SUT (command outputs, file contents, MSR
                      values, etc.) used to emulate results of commands and file I/O operations.
    - Emulation dataset: A directory containing emulation data for a single SUT. Also referred to as
      just "dataset" when the context is clear.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.emul import _EmulFile
from pepclibs.helperlibs.emul.EmulCommon import EMUL_CONFIG_FNAME
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType

if typing.TYPE_CHECKING:
    from typing import Generator, TypedDict, IO, cast, Final
    from pepclibs.helperlibs._ProcessManagerBase import LsdirTypedDict, LsdirSortbyType
    from pepclibs.helperlibs.emul.EmulCommon import _EDConfMSRTypedDict, _EDConfSysfsTypedDict
    from pepclibs.helperlibs.emul.EmulCommon import _EDConfProcfsTypedDict, _EDConfTypedDict

    class _EMDTypedDict(TypedDict, total=False):
        """
        The main emulation data dictionary that holds all emulated resources.

        Attributes:
            files: Dictionary mapping absolute paths of emulated files (e.g.,
                   "/sys/devices/system/cpu/online", "/dev/cpu/0/msr") to corresponding emulated
                   file objects.
        """

        files: dict[str, _EmulFile.EmulFileType]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

_DEFAULT_HOSTNAME: Final[str] = "emulated_host"

class EmulProcessManager(LocalProcessManager.LocalProcessManager):
    """
    A process manager that emulates a System Under Test (SUT) for testing purposes.

    A mock implementation of a process manager designed for unit testing. Instead of writing the
    real SUT filesystem, manipulate files and directories in memory or within local filesystem.
    """

    def __init__(self, hostname: str = _DEFAULT_HOSTNAME):
        """
        Initialize a class instance.

        Args:
            hostname: Name of the emulated host to use in messages.
        """

        super().__init__()

        self.hostname = hostname
        self.hostmsg = f" on '{self.hostname}'"
        self.is_remote = False
        self.is_emulated = True

        pid = Trivial.get_pid()

        self._basepath: Path = super().mkdtemp(prefix=f"emulprocs_{pid}_")
        self._basepath_removed = False
        self._dataset_path: Path

        # The emulation data dictionary.
        self._emd: _EMDTypedDict = {"files": {}}

    def __del__(self):
        """The class destructor."""

        if getattr(self, "_basepath_removed", True):
            return

        # Remove the emulation data in the temporary directory.
        self._basepath_removed = True

        with contextlib.suppress(Exception):
            super().rmtree(self._basepath)

    def close(self):
        """Stop emulation."""

        self._basepath_removed = True

        with contextlib.suppress(Exception):
            super().rmtree(self._basepath)

        with contextlib.suppress(Exception):
            super().close()

    def _process_procfs(self, info: _EDConfProcfsTypedDict):
        """
        Create emulated procfs files from procfs emulation data.

        Args:
            info: Procfs configuration dictionary.
        """

        procfs_dir = self._dataset_path / info["dirname"]
        rw_patterns = info.get("rw_patterns", [])
        for filepath in procfs_dir.rglob("*"):
            if not filepath.is_file():
                continue
            relpath = filepath.relative_to(self._dataset_path)
            proc_path = f"/{relpath}"
            try:
                with open(filepath, "r", encoding="utf-8") as fobj:
                    data = fobj.read()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read '{filepath}':\n{errmsg}") from err
            readonly = not any(re.search(regex, proc_path) for regex in rw_patterns)
            emul = _EmulFile.get_emul_file(proc_path, self._basepath, data=data, readonly=readonly)
            self._emd["files"][proc_path] = emul

    def _process_sysfs(self, info: _EDConfSysfsTypedDict):
        """
        Create emulated sysfs files from sysfs emulation data.

        Args:
            info: Sysfs configuration dictionary.
        """

        filepath = self._dataset_path / info["dirname"] / info["inlinefiles"]
        try:
            with open(filepath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to read emulated sysfs data from '{filepath}':\n"
                        f"{errmsg}") from err

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Format: <ro|rw>|<sysfs_path>|<value>.
            parts = line.split("|", 2)
            if len(parts) != 3:
                raise Error(f"Unexpected line format in file '{filepath}':\n  "
                            f"Expected <ro|rw>|<path>|<value>, received '{line}'")

            mode, path, data = parts
            if mode not in ("ro", "rw"):
                raise Error(f"Unexpected mode '{mode}' in file '{filepath}':\n  "
                            f"Expected 'ro' or 'rw', received '{line}'")

            readonly = mode == "ro"

            # Note about lstrip(): 'path' is an absolute path starting with '/'. If not stripped,
            # joining it with the base path would ignore the base path.
            dirpath = (self._basepath / path.lstrip("/")).parent
            try:
                dirpath.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to create directory '{dirpath}':\n{errmsg}") from err

            emul = _EmulFile.get_emul_file(path, self._basepath, data=data, readonly=readonly)
            self._emd["files"][path] = emul

        sysfs_dir = self._dataset_path / info["dirname"]
        rcopy = info.get("rcopy", {})
        rw_patterns = rcopy.get("rw_patterns", [])
        for relpath in rcopy.get("paths", []):
            rcopy_base = sysfs_dir / relpath
            if not rcopy_base.exists():
                continue
            for filepath in rcopy_base.rglob("*"):
                if not filepath.is_file():
                    continue
                relpath = filepath.relative_to(sysfs_dir)
                sysfs_path = f"/{info['dirname']}/{relpath}"
                try:
                    with open(filepath, "r", encoding="utf-8") as fobj:
                        data = fobj.read()
                except OSError as err:
                    errmsg = Error(str(err)).indent(2)
                    raise Error(f"Failed to read '{filepath}':\n{errmsg}") from err
                readonly = not any(re.search(regex, sysfs_path) for regex in rw_patterns)
                emul = _EmulFile.get_emul_file(sysfs_path, self._basepath, data=data,
                                               readonly=readonly)
                self._emd["files"][sysfs_path] = emul

    def _process_msrs(self, info: _EDConfMSRTypedDict):
        """
        Create emulated MSR device files from MSR emulation data.

        Args:
            info: MSR configuration dictionary.
        """

        dirpath = self._dataset_path / info["dirname"]
        if not dirpath.exists():
            return

        filepath = dirpath / info["filename"]
        try:
            with open(filepath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to read emulated MSR data from '{filepath}':\n{errmsg}") from err

        data_by_cpu: dict[int, dict[int, bytes]] = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            split = line.split(":", 1)
            if len(split) != 2:
                raise Error(f"Unexpected line format in file '{filepath}':\n  "
                            f"Expected <hex_addr>:<cpu_val_pairs>, received '{line}'")

            regaddr = int(split[0], 16)
            cpu_val_pairs = split[1].split()

            for cpu_val_pair in cpu_val_pairs:
                cpu_str, regval_str = cpu_val_pair.split("|", 1)
                cpu = int(cpu_str)
                regval = int(regval_str, 16)
                if cpu not in data_by_cpu:
                    data_by_cpu[cpu] = {}
                data_by_cpu[cpu][regaddr] = int.to_bytes(regval, 8, byteorder="little")

        for cpu, data in data_by_cpu.items():
            path = f"/dev/cpu/{cpu}/msr"
            emul = _EmulFile.get_emul_file(path, self._basepath, data=data)
            self._emd["files"][path] = emul

    def _init_emul_data(self, ydict: _EDConfTypedDict):
        """
        Initialize the emulation data from the configuration dictionary.

        Args:
            ydict: The emulation data configuration dictionary (the YAML configuration file loaded
                   as a Python dictionary).
        """

        if "msr" in ydict:
            self._process_msrs(ydict["msr"])

        if "sysfs" in ydict:
            self._process_sysfs(ydict["sysfs"])

        if "procfs" in ydict:
            self._process_procfs(ydict["procfs"])

    def init_emul_data(self, dspath: Path):
        """
        Load an emulation dataset and initialize the emulation data.

        Args:
          dspath: Path to the dataset directory to load.

        Each dataset directory contains a single 'config.yml' file that describes all emulation
        data for a System Under Test (SUT):
            - dataset1/
              - config.yml          # Main configuration file
              - msr/                # MSR register data
              - sys/                # Sysfs file data
              - proc/               # Procfs file data
              ...
            - dataset2/
              ...

        The 'config.yml' file contains top-level sections ('msr', 'sysfs', 'procfs', etc.) that
        describe how to load and configure emulated files from their respective sub-directories.

        This method eagerly loads all emulation data from the configuration file and prepares the
        emulated filesystem structure in the temporary base directory.

        Note: A TODO exists to implement lazy loading, where data would only be loaded when
              actually accessed, improving initialization performance for tests that use only
              a subset of the emulation data.
        """

        # TODO: Instead of eagerly building all emulation data up front, construct it lazily and
        # only for the components that are actually required.

        self._dataset_path = dspath

        _yml = YAML.load(self._dataset_path / EMUL_CONFIG_FNAME)
        if typing.TYPE_CHECKING:
            ydict = cast(_EDConfTypedDict, _yml)
        else:
            ydict = _yml

        self._init_emul_data(ydict)

    def _extract_path(self, cmd: str) -> str:
        """
        Parse the command string and search for a path that exists within the base directory.

        Args:
            cmd: Command string to parse and search for an emulated path in.

        Returns:
            The path found in the command if it exists under the base path, otherwise an empty
            string.
        """

        for split in cmd.split():
            if Path(self._basepath / split).exists():
                return split
            for strip_chr in ("'/", "\"/"):
                if Path(self._basepath / split.strip(strip_chr)).exists():
                    return split.strip(strip_chr)

        return ""

    def _rebase_cmd(self, cmd: str) -> str | None:
        """
        Modify a command to reference emulated files by rebasing paths in the command. If the
        command contains a path that can be emulated, replace it with the corresponding path under
        the base emulation directory.

        Args:
            cmd: The command to rebase.

        Returns:
            The rebased command if a path is found in the emulation data, otherwise None.
        """

        # At the moment only a single path substitution is implemented.
        path_str = self._extract_path(cmd)
        if not path_str:
            return None
        return cmd.replace(path_str, f"{self._basepath}/{path_str.lstrip('/')}")

    def run(self,
            cmd: str | Path,
            timeout: int | float | None = None,
            capture_output: bool = True,
            mix_output: bool = False,
            join: bool = True,
            output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
            cwd: str | Path | None = None,
            intsh: bool | None = None,
            env: dict[str, str] | None = None,
            newgrp: bool = False) -> ProcWaitResultType:
        """
        Run command 'cmd' by rebasing any emulated paths and executing locally.

        The arguments and return value are the same as 'ProcessManagerBase.run()'.
        """

        cmd = str(cmd)

        _LOG.debug("Running the following emulated command:\n%s", cmd)

        rebased_cmd = self._rebase_cmd(cmd)
        if rebased_cmd is None:
            raise ErrorNotSupported(f"Unsupported command: '{cmd}'")

        return super().run(rebased_cmd, timeout=timeout, capture_output=capture_output,
                           mix_output=mix_output, join=join, output_fobjs=output_fobjs,
                           cwd=cwd, intsh=intsh, env=env, newgrp=newgrp)

    def run_verify(self,
                   cmd: str | Path,
                   timeout: int | float | None = None,
                   capture_output: bool = True,
                   mix_output: bool = False,
                   join: bool = True,
                   output_fobjs: tuple[IO[str] | None, IO[str] | None] = (None, None),
                   cwd: str | Path | None = None,
                   intsh: bool | None = None,
                   env: dict[str, str] | None = None,
                   newgrp: bool = False) -> tuple[str | list[str], str | list[str]]:
        """
        Run command 'cmd' by rebasing any emulated paths and executing locally.

        The arguments and return value are the same as 'ProcessManagerBase.run_verify()'.
        """

        cmd = str(cmd)

        _LOG.debug("Running the following emulated command:\n%s", cmd)

        rebased_cmd = self._rebase_cmd(cmd)
        if rebased_cmd is None:
            raise ErrorNotSupported(f"Unsupported command: '{cmd}'")

        # Avoid running 'super().run_verify()', because it calls 'run()' of this class.
        result = super().run(rebased_cmd, timeout=timeout, capture_output=capture_output,
                             mix_output=mix_output, join=join, output_fobjs=output_fobjs,
                             cwd=cwd, intsh=intsh, env=env, newgrp=newgrp)
        if result.exitcode == 0:
            return (result.stdout, result.stderr)

        msg = self.get_cmd_failure_msg(cmd, result.stdout, result.stderr, result.exitcode,
                                    timeout=timeout)
        raise Error(msg)

    def _open(self, path: str | Path, mode: str) -> IO:
        """Same as 'ProcessManagerBase.open()', but rebase 'path' to the base directory."""

        _LOG.debug("Opening file '%s' with mode '%s'", path, mode)

        path = str(path)
        if path in self._emd["files"]:
            return self._emd["files"][path].open(mode)

        return _EmulFile.get_emul_file(path, self._basepath).open(mode)

    def open(self, path: str | Path, mode: str) -> IO[str]:
        """Refer to 'ProcessManagerBase.open()'."""

        mode = self._open_mode_adjust(mode)
        return self._open(path, mode)

    def openb(self, path: str | Path, mode: str) -> IO[bytes]:
        """Refer to 'ProcessManagerBase.openb()'."""

        mode = self._openb_mode_adjust(mode)
        return self._open(path, mode)

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """Same as 'ProcessManagerBase.mkdir()', but rebase 'path' to the base directory."""

        dirpath = self._basepath / str(dirpath).lstrip("/")
        super().mkdir(dirpath, parents=parents, exist_ok=exist_ok)

    def lsdir(self,
              path: str | Path,
              sort_by: LsdirSortbyType = "none",
              reverse: bool = False) -> Generator[LsdirTypedDict, None, None]:
        """Same as 'ProcessManagerBase.lsdir()', but rebase 'path' to the base directory."""

        emul_path = Path(self._basepath / str(path).lstrip("/"))

        for entry in super().lsdir(emul_path, sort_by=sort_by, reverse=reverse):
            entry["path"] = entry["path"].relative_to(self._basepath)
            yield entry

    def exists(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.exists()', but rebase 'path' to the base directory."""

        path = str(path)
        if path in self._emd["files"]:
            return True

        emul_path = Path(self._basepath / path.lstrip("/"))
        return super().exists(emul_path)

    def is_file(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_file()', but rebase 'path' to the base directory."""

        path = str(path)
        if path in self._emd["files"]:
            return True

        emul_path = Path(self._basepath / path.lstrip("/"))
        return super().is_file(emul_path)

    def is_dir(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_dir()', but rebase 'path' to the base directory."""

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_dir(path)

    def is_exe(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_exe()', but rebase 'path' to the base directory."""

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_exe(path)

    def is_socket(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_socket()', but rebase 'path' to the base directory."""

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_socket(path)

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """
        Same as 'ProcessManagerBase.mkdtemp()', but create the temporary directory under the
        emulated files' base directory.
        """

        path = self._basepath
        if basedir:
            path = path / basedir

        temppath = super().mkdtemp(prefix=prefix, basedir=path)
        return temppath.relative_to(self._basepath)
