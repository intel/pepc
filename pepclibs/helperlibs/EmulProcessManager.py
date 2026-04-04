# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

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
    - Base directory: A temporary directory created at initialization. Some emulated files are
      backed by real files under this directory.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from pepclibs.helperlibs.emul import _EmulFile
from pepclibs.helperlibs.emul.EmulCommon import EMUL_CONFIG_FNAME
from pepclibs.msr._SimpleMSR import _CPU_BYTEORDER

if typing.TYPE_CHECKING:
    from typing import Generator, TypedDict, IO, cast, Final
    from pepclibs.helperlibs._ProcessManagerTypes import LsdirTypedDict, LsdirSortbyType
    from pepclibs.helperlibs.emul.EmulCommon import _EDConfMSRTypedDict, _EDConfSysfsTypedDict
    from pepclibs.helperlibs.emul.EmulCommon import _EDConfProcfsTypedDict, _EDConfTypedDict

    class _EMDTypedDict(TypedDict, total=False):
        """
        The main emulation data dictionary that holds all emulated resources.

        Attributes:
            files: Dictionary mapping absolute paths of emulated files (e.g.,
                   "/sys/devices/system/cpu/online", "/dev/cpu/0/msr") to corresponding emulated
                   file objects (e.g., 'EmulFile' instances).
        """

        files: dict[str, _EmulFile.EmulFileType]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

_DEFAULT_HOSTNAME: Final[str] = "emulated_host"

class EmulProcessManager(LocalProcessManager.LocalProcessManager):
    """
    A process manager that emulates a System Under Test (SUT) for testing purposes.

    A mock implementation of a process manager designed for unit testing. Instead of accessing the
    real SUT filesystem, files are emulated - some are served from a temporary base directory
    populated with emulation data, while others may be maintained purely in memory.

    Note: After creating an instance, call 'init_emul_data()' with a dataset path to load the
          emulation data before using any other methods.
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

    def _get_inlinefile_lines(self, filepath: Path) -> Generator[str, None, None]:
        """
        Iterate over non-empty, non-comment lines in an inlinefile format data file.

        Args:
            filepath: Path to the inlinefile to read.

        Yields:
            Lines with leading/trailing whitespace stripped, excluding empty lines and comment
            lines.
        """

        try:
            with open(filepath, "r", encoding="utf-8") as fobj:
                for line in fobj:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        yield line
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to read file '{filepath}':\n{errmsg}") from err

    def _iter_files_recursive(self, dirpath: Path) -> Generator[Path, None, None]:
        """
        Recursively iterate over all files in a directory tree.

        Args:
            dirpath: Path to the directory to traverse.

        Yields:
            Path objects for each regular file found in the directory tree.
        """

        try:
            for root, _, files in os.walk(dirpath):
                for filename in files:
                    yield Path(root) / filename
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to traverse directory '{dirpath}':\n{errmsg}") from err

    def _process_procfs(self, yinfo: _EDConfProcfsTypedDict):
        """
        Create emulated procfs files from procfs emulation data.

        Args:
            yinfo: Procfs configuration dictionary.
        """

        procfs_dir_path = self._dataset_path / yinfo["dirname"]
        rw_patterns = yinfo.get("rw_patterns", [])

        # Note: Directories are automatically created by 'EmulFileBase', so iterate only files.
        for filepath in self._iter_files_recursive(procfs_dir_path):
            # Example path values:
            #   filepath:   /dataset_path/proc/cpuinfo
            #   relpath:    cpuinfo
            #   proc_path:  /proc/cpuinfo
            relpath = filepath.relative_to(procfs_dir_path)
            proc_path = f"/{yinfo['dirname']}/{relpath}"
            try:
                with open(filepath, "r", encoding="utf-8") as fobj:
                    data = fobj.read()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read '{filepath}':\n{errmsg}") from err

            readonly = not any(re.search(regex, proc_path) for regex in rw_patterns)
            emul_file = _EmulFile.get_emul_file(proc_path, self._basepath, data=data,
                                                readonly=readonly)
            self._emd["files"][proc_path] = emul_file

    def _process_sysfs_inlinefiles(self, yinfo: _EDConfSysfsTypedDict):
        """
        Create emulated sysfs files from inline sysfs emulation data.

        Args:
            yinfo: Sysfs configuration dictionary.
        """

        inlinefile_path = self._dataset_path / yinfo["dirname"] / yinfo["inlinefiles"]

        for line in self._get_inlinefile_lines(inlinefile_path):
            # Format: <mode>|<sysfs_path>|<value>.
            parts = line.split("|", 2)
            if len(parts) != 3:
                raise Error(f"Unexpected line format in file '{inlinefile_path}':\n  "
                            f"Expected <mode>|<path>|<value>, received:\n'{line}'")

            mode, path, data = parts
            if mode not in ("ro", "rw"):
                raise Error(f"Unexpected mode '{mode}' in file '{inlinefile_path}':\n  "
                            f"Expected 'ro' or 'rw', received:\n'{line}'")

            readonly = mode == "ro"

            # Note about lstrip(): 'path' is an absolute path starting with '/'. If not stripped,
            # joining it with the base path would ignore the base path.
            dirpath = (self._basepath / path.lstrip("/")).parent
            try:
                dirpath.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to create directory '{dirpath}':\n{errmsg}") from err

            emul_file = _EmulFile.get_emul_file(path, self._basepath, data=data, readonly=readonly)
            self._emd["files"][path] = emul_file

    def _process_sysfs_rcopy(self, yinfo: _EDConfSysfsTypedDict):
        """
        Create emulated sysfs files from recursively copied sysfs directories.

        Args:
            yinfo: Sysfs configuration dictionary.
        """

        rcopy = yinfo.get("rcopy", {})
        if not rcopy:
            return

        sysfs_dir_path = self._dataset_path / yinfo["dirname"]
        rw_patterns = rcopy.get("rw_patterns", [])

        for relpath in rcopy.get("paths", []):
            # Example path values:
            #   relpath:        "kernel/debug/tpmi-0000:80:03.1"
            #   rcopy_base:     "/dataset_path/sys/kernel/debug/tpmi-0000:80:03.1"
            rcopy_base = sysfs_dir_path / relpath
            if not rcopy_base.exists():
                cfgfile_path = self._dataset_path / EMUL_CONFIG_FNAME
                raise Error(f"Path '{relpath}' specified in '{cfgfile_path}' does not exist")

            # Note: Directories are automatically created by 'EmulFileBase', so iterate only files.
            for filepath in self._iter_files_recursive(rcopy_base):
                # Example path values:
                #   filepath:   /dataset_path/sys/kernel/debug/tpmi-0000:80:03.1/tpmi-id-0c/mem_dump
                #   relpath:    kernel/debug/tpmi-0000:80:03.1/tpmi-id-0c/mem_dump
                #   sysfs_path: /sys/kernel/debug/tpmi-0000:80:03.1/tpmi-id-0c/mem_dump
                relpath = filepath.relative_to(sysfs_dir_path)
                sysfs_path = f"/{yinfo['dirname']}/{relpath}"
                try:
                    with open(filepath, "r", encoding="utf-8") as fobj:
                        data = fobj.read()
                except OSError as err:
                    errmsg = Error(str(err)).indent(2)
                    raise Error(f"Failed to read '{filepath}':\n{errmsg}") from err

                readonly = not any(re.search(regex, sysfs_path) for regex in rw_patterns)
                emul_file = _EmulFile.get_emul_file(sysfs_path, self._basepath, data=data,
                                               readonly=readonly)
                self._emd["files"][sysfs_path] = emul_file

    def _process_sysfs(self, yinfo: _EDConfSysfsTypedDict):
        """
        Create emulated sysfs files from sysfs emulation data.

        Args:
            yinfo: Sysfs configuration dictionary.
        """

        self._process_sysfs_inlinefiles(yinfo)
        self._process_sysfs_rcopy(yinfo)

    def _process_msrs(self, yinfo: _EDConfMSRTypedDict):
        """
        Create emulated MSR device files from the dataset.

        Args:
            yinfo: the 'msr' section of the emulation data configuration dictionary.
        """

        msr_dir_path = self._dataset_path / yinfo["dirname"]
        if not msr_dir_path.exists():
            return

        inlinefile_path = msr_dir_path / yinfo["filename"]

        # Parsed MSR data organized by CPU: {cpu: {addr: value}}.
        cpu_addr_val: dict[int, dict[int, bytes]] = {}

        for line in self._get_inlinefile_lines(inlinefile_path):
            split = line.split(":", 1)
            if len(split) != 2:
                raise Error(f"Unexpected line format in file '{inlinefile_path}':\n  "
                            f"Expected <hex_addr>:<cpu_val_pairs>, received:\n{line}")

            addr = Trivial.str_to_int(split[0], base=16, what="MSR address")
            pairs = split[1].split()

            for pair in pairs:
                cpu_str, regval_str = pair.split("|", 1)
                cpu = Trivial.str_to_int(cpu_str, what="CPU number")
                value = Trivial.str_to_int(regval_str, base=16, what="MSR register value")

                if cpu not in cpu_addr_val:
                    cpu_addr_val[cpu] = {}
                elif addr in cpu_addr_val[cpu]:
                    raise Error(f"Duplicate CPU {cpu} and MSR address {addr:#x} in file "
                                f"'{inlinefile_path}': Line:\n{line}")

                cpu_addr_val[cpu][addr] = int.to_bytes(value, 8, byteorder=_CPU_BYTEORDER)

        for cpu, addr2val in cpu_addr_val.items():
            path = f"/dev/cpu/{cpu}/msr"
            emul_file = _EmulFile.get_emul_file(path, self._basepath, data=addr2val)
            self._emd["files"][path] = emul_file

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
        """

        self._dataset_path = dspath

        _yml = YAML.load(self._dataset_path / EMUL_CONFIG_FNAME)
        if typing.TYPE_CHECKING:
            ydict = cast(_EDConfTypedDict, _yml)
        else:
            ydict = _yml

        self._init_emul_data(ydict)

    def run_async(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_async()'."""
        raise NotImplementedError("EmulProcessManager.run_async()")

    def run(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run()'."""
        raise NotImplementedError("EmulProcessManager.run()")

    def run_join(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_join()'."""
        raise NotImplementedError("EmulProcessManager.run_join()")

    def run_nojoin(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_nojoin()'."""
        raise NotImplementedError("EmulProcessManager.run_nojoin()")

    def run_verify(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_verify()'."""
        raise NotImplementedError("EmulProcessManager.run_verify()")

    def run_verify_join(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_verify_join()'."""
        raise NotImplementedError("EmulProcessManager.run_verify_join()")

    def run_verify_nojoin(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.run_verify_nojoin()'."""
        raise NotImplementedError("EmulProcessManager.run_verify_nojoin()")

    def rsync(self, *args, **kwargs):
        """Refer to 'ProcessManagerBase.rsync()'."""
        raise NotImplementedError("EmulProcessManager.rsync()")

    def get(self, src: str | Path, dst: str | Path):
        """Refer to 'ProcessManagerBase.get()'."""
        raise NotImplementedError("EmulProcessManager.get()")

    def put(self, src: str | Path, dst: str | Path):
        """Refer to 'ProcessManagerBase.put()'."""
        raise NotImplementedError("EmulProcessManager.put()")

    def _open(self, path: str | Path, mode: str) -> IO:
        """Refer to 'ProcessManagerBase._open()'."""

        _LOG.debug("Opening file '%s' with mode '%s'", path, mode)

        path = str(path)
        if path in self._emd["files"]:
            return self._emd["files"][path].open(mode)

        raise ErrorNotFound(f"File '{path}' not found in emulated filesystem{self.hostmsg}")

    def get_python_path(self) -> Path:
        """Refer to 'ProcessManagerBase.get_python_path()'."""
        raise NotImplementedError("EmulProcessManager.get_python_path()")

    def time_time(self) -> float:
        """Refer to 'ProcessManagerBase.time_time()'."""
        raise NotImplementedError("EmulProcessManager.time_time()")

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkdir()'."""
        raise NotImplementedError("EmulProcessManager.mkdir()")

    def mksocket(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mksocket()'."""
        raise NotImplementedError("EmulProcessManager.mksocket()")

    def mkfifo(self, path: str | Path, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkfifo()'."""
        raise NotImplementedError("EmulProcessManager.mkfifo()")

    def lsdir(self,
              path: str | Path,
              sort_by: LsdirSortbyType = "none",
              reverse: bool = False) -> Generator[LsdirTypedDict, None, None]:
        """Same as 'ProcessManagerBase.lsdir()', but rebase 'path' to the base directory."""

        rebased_path = self._basepath / str(path).lstrip("/")

        for entry in super().lsdir(rebased_path, sort_by=sort_by, reverse=reverse):
            entry["path"] = entry["path"].relative_to(self._basepath)
            yield entry

    def exists(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.exists()', but rebase 'path' to the base directory."""

        path = str(path)
        if path in self._emd["files"]:
            return True

        rebased_path = self._basepath / path.lstrip("/")
        return super().exists(rebased_path)

    def is_file(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_file()', but rebase 'path' to the base directory."""

        path = str(path)
        if path in self._emd["files"]:
            return True

        rebased_path = self._basepath / path.lstrip("/")
        return super().is_file(rebased_path)

    def is_dir(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_dir()', but rebase 'path' to the base directory."""

        rebased_path = self._basepath / str(path).lstrip("/")
        return super().is_dir(rebased_path)

    def is_exe(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_exe()', but rebase 'path' to the base directory."""

        rebased_path = self._basepath / str(path).lstrip("/")
        return super().is_exe(rebased_path)

    def is_socket(self, path: str | Path) -> bool:
        """Same as 'ProcessManagerBase.is_socket()', but rebase 'path' to the base directory."""

        rebased_path = self._basepath / str(path).lstrip("/")
        return super().is_socket(rebased_path)

    def is_fifo(self, path: str | Path) -> bool:
        """Refer to 'ProcessManagerBase.is_fifo()'."""
        raise NotImplementedError("EmulProcessManager.is_fifo()")

    def get_mtime(self, path: str | Path) -> float:
        """Refer to 'ProcessManagerBase.get_mtime()'."""
        raise NotImplementedError("EmulProcessManager.get_mtime()")

    def unlink(self, path: str | Path):
        """Refer to 'ProcessManagerBase.unlink()'."""
        raise NotImplementedError("EmulProcessManager.unlink()")

    def rmtree(self, path: str | Path):
        """Refer to 'ProcessManagerBase.rmtree()'."""
        raise NotImplementedError("EmulProcessManager.rmtree()")

    def abspath(self, path: str | Path) -> Path:
        """Refer to 'ProcessManagerBase.abspath()'."""
        raise NotImplementedError("EmulProcessManager.abspath()")

    def mkdtemp(self, prefix: str = "", basedir: str | Path | None = None) -> Path:
        """Refer to 'ProcessManagerBase.mkdtemp()'."""
        raise NotImplementedError("EmulProcessManager.mkdtemp()")

    def get_envar(self, envar: str) -> str | None:
        """Refer to 'ProcessManagerBase.get_envar()'."""
        raise NotImplementedError("EmulProcessManager.get_envar()")

    def which(self, program: str | Path, must_find: bool = True):
        """Refer to 'ProcessManagerBase.which()'."""
        raise NotImplementedError("EmulProcessManager.which()")
