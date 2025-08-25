# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
A process manager that emulates a SUT for testing purposes.

Provide the 'EmulProcessManager' class, a subclass of 'LocalProcessManager' that pretends to execute
commands on a SUT, but performs local operations, returning pre-defined results based on test data
previously collected from a real SUT using the 'tdgen' tool.

Terminology:
    - Test Data: Data collected from real SUTs, stored in the "test" sub-directory, used to emulate
      results of commands and file I/O operations.
    - Data Set: A directory containing test data for a single SUT.
    - Emulation Data (emd): Processed version of test data, either stored in memory or in a
      temporary directory on the local file-system.
"""

# TODO: rework this file, make it more readable. Modernize it and add type annotations.
from  __future__ import annotations # Remove when switching to Python 3.10+.

import contextlib
from pathlib import Path
from typing import Generator, TypedDict, NamedTuple, cast, Sequence
from pepclibs.helperlibs import Logging, LocalProcessManager, Trivial, YAML
from pepclibs.helperlibs._ProcessManagerBase import ProcWaitResultType, LsdirTypedDict
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.emul import _EmulFile

class _TestDataInlineDirsTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing inline directories in the YAML configuration.

    Attributes:
        dirname: Name of the sub-directory within the dataset containing the inline directories
                 file.
        filename: The inline directories file name. Contains a list of directory paths to
                  emulate.
    """

    dirname: str
    filename: str

class _TestDataCommandsTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing command results in the YAML configuration.

    Attributes:
        command: The emulated command, including options.
        dirname: Name of the sub-directory within the dataset containing standard error and standard
                 output of the emulated command.
    """

    command: str
    dirname: str

class _TestDataInlineFilesTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing inline files in the YAML configuration.

    Attributes:
        dirname: Name of the sub-directory within the dataset containing the inline files
                 file.
        filename: The inline files file name. Contains a list of file paths and their values.
        separator: The separator used in the inline files file to separate paths and values.
        readonly: Whether the inline files are read-only.
    """

    dirname: str
    filename: str
    separator: str
    readonly: bool

class _TestDataMSRsTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing MSRs in the YAML configuration.

    Attributes:
        dirname: Name of the sub-directory within the dataset containing the MSRs file.
        filename: The MSRs file name. Contains a list of MSR device node paths, MSR addresses and
                  their values.
        addresses: List of MSR addresses included in the MSR file.
        separator1: The separator used in the MSRs file to separate MSR device node paths and the
                    MSR values.
        separator2: The separator used in the MSRs file to separate MSR addresses and MSR values.
    """

    dirname: str
    filename: str
    addresses: list[int]
    separator1: str
    separator2: str

class _TestDataFilesTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing files in the YAML configuration.

    Attributes:
        path: The emulated file path. There is a file in the dataset category sub-directory with the
              same relative path, it includes the emulated file contents.
        readonly: Whether the emulated file is read-only.
    """

    path: str
    readonly: bool

class _TestDataDirectoriesTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing empty directories in the YAML configuration.

    Attributes:
        path: The emulated empty directory path.
    """

    path: str
    readonly: bool

class _TestDataYAMLTypedDict(TypedDict, total=False):
    """
    Typed dictionary describing the YAML configuration for test data.

    Attributes:
        inlinedirs: List of inline directories configurations.
        commands: List of command configurations.
        inlinefiles: List of inline files configurations.
        msrs: List of MSR configurations.
        files: List of file configurations.
    """

    inlinedirs: list[_TestDataInlineDirsTypedDict]
    commands: list[_TestDataCommandsTypedDict]
    inlinefiles: list[_TestDataInlineFilesTypedDict]
    msrs: list[_TestDataMSRsTypedDict]
    files: list[_TestDataFilesTypedDict]
    directories: list[_TestDataDirectoriesTypedDict]

class _EmulCmdResultType(NamedTuple):
    """
    Type for emulation command execution results.

    Attributes:
        stdout: The standard output of the command.
        stderr: The standard error of the command.
        exitcode: The exit code of the command.
    """

    stdout: list[str]
    stderr: list[str]
    exitcode: int

class _EmulDataTypedDict(TypedDict, total=False):
    """
    A typed dictionary for the emulation data.
    """

    cmds: dict[str, _EmulCmdResultType]
    files: dict[str, _EmulFile.EmulFileType]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class EmulProcessManager(LocalProcessManager.LocalProcessManager):
    """
    A process manager that emulates a System Under Test (SUT) for testing purposes.

    A mock implementation of a process manager designed for unit testing. Instead of executing real
    commands or interacting with the actual filesystem, return pre-defined results. Instead of
    writing the real SUT filesystem, manipulate files and directories in memory or within a
    temporary directory (the base directory).

    Key Features:
        - Emulate command execution by returning pre-defined stdout/stderr for supported commands.
        - Filesystem-related methods (e.g., mkdir, lsdir, is_file) operate relative to the base
          directory (which is just a temporary directory), not the real local filesystem.
          So all file and directory operations are sandboxed within the base directory.
        - The emulation data (emd) are intialized and populated from the test data.
    """

    def __init__(self, hostname: str | None = None):
        """
        Initialize a class instance.

        Args:
            hostname: Name of the emulated host to use in messages.
        """

        super().__init__()

        if hostname:
            self.hostname = hostname
        else:
            self.hostname = "emulated local host"

        self.hostmsg = f" on '{self.hostname}'"
        self.is_remote = False

        pid = Trivial.get_pid()
        self._basepath: Path | None = super().mkdtemp(prefix=f"emulprocs_{pid}_")

        # The emulation data dictionary.
        self._emd: _EmulDataTypedDict = {"cmds": {}, "files": {}}

    def __del__(self):
        """The class destructor."""

        # Remove the emulation data in the temporary directory.
        basepath: Path | None = getattr(self, "_basepath", None)
        if basepath is not None:
            self._basepath = None
            with contextlib.suppress(Error, OSError):
                super().rmtree(basepath)

    def close(self):
        """Stop emulation."""

        if self._basepath:
            with contextlib.suppress(Error):
                super().rmtree(self._basepath)

        with contextlib.suppress(Exception):
            super().close()

    def _get_predefined_result(self, cmd, join=True):
        """Return pre-defined value for the command 'cmd'."""

        if cmd not in self._emd["cmds"]:
            raise ErrorNotSupported(f"unsupported command: '{cmd}'")

        result = self._emd["cmds"][cmd]
        if join:
            stdout, stderr = "".join(result.stdout), "".join(result.stderr)
        else:
            stdout, stderr = result.stdout, result.stderr

        return stdout, stderr

    def _extract_path(self, cmd):
        """
        Parse command 'cmd' and find if it includes path which is also emulated. Returns the path if
        found, otherwise returns 'None'.
        """

        for split in cmd.split():
            if Path(self._basepath / split).exists():
                return split
            for strip_chr in ("'/", "\"/"):
                if Path(self._basepath / split.strip(strip_chr)).exists():
                    return split.strip(strip_chr)

        return None

    def _rebase_cmd(self, cmd):
        """
        Modify command 'cmd' so that it is run against emulated files. Returns 'None' if the command
        doesn't include any paths, or paths are not emulated.
        """

        if str(self._basepath) in cmd:
            return cmd

        path = self._extract_path(cmd)
        if path:
            rebased_cmd = cmd.replace(path, f"{self._basepath}/{str(path).lstrip('/')}")
            return rebased_cmd

        return None

    def run_verify(self, cmd, join=True, **kwargs):
        """
        Emulate running command 'cmd' and verifying the result. The arguments are as follows.
          * cmd - the command to run (only a pre-defined set of commands is supported).
          * join - whether the output of the command should be returned as a single string or as a
                   list of lines (trailing newlines are not stripped).
          * kwargs - the other arguments. Please, refer to '_ProcessManagerBase.run_verify()' for
                     the details.

        Pretend running the 'cmd' command return the pre-defined output data. Accept only a limited
        set of known commands, raise 'ErrorNotSupported' for any unknown command.
        """

        # pylint: disable=unused-argument,arguments-differ
        _LOG.debug("running the following emulated command:\n%s", cmd)

        try:
            return self._get_predefined_result(cmd, join=join)
        except ErrorNotSupported:
            cmd = self._rebase_cmd(cmd)
            if cmd:
                return super().run_verify(cmd, join=join, **kwargs)
            raise

    def run(self, cmd, join=True, **kwargs) -> ProcWaitResultType: # pylint: disable=unused-argument
        """
        Emulate running command 'cmd'. The arguments are as follows.
          * cmd - the command to run (only a pre-defined set of commands is supported).
          * join - whether the output of the command should be returned as a single string or as a
                   list of lines (trailing newlines are not stripped).
          * kwargs - the other arguments. Please, refer to '_ProcessManagerBase.run_verify()' for
                     the details.

        Pretend running the 'cmd' command return the pre-defined output data. Accept only a limited
        set of known commands, raise 'ErrorNotSupported' for any unknown command.
        """

        # pylint: disable=unused-argument,arguments-differ
        _LOG.debug("running the following emulated command:\n%s", cmd)

        try:
            stdout, stderr = self._get_predefined_result(cmd, join=join)
        except ErrorNotSupported:
            cmd = self._rebase_cmd(cmd)
            if cmd:
                return super().run(cmd, join=join, **kwargs)
            raise

        return ProcWaitResultType(stdout=stdout, stderr=stderr, exitcode=0)

    def open(self, path, mode):
        """
        Open a file on the at 'path' and return a file-like object. The arguments are as follows.
          * path - path to the file to open.
          * mode - the same as in the standard python 'open()'.

        Open a file at path 'path' relative to the emulation base directory. Create it if necessary.
        """

        _LOG.debug("Opening file '%s' with mode '%s'", path, mode)

        path = str(path)
        if path in self._emd["files"]:
            return self._emd["files"][path].open(mode)

        return _EmulFile.get_emul_file(path, self._basepath).open(mode)

    def _process_inlinedirs(self, infos: Sequence[_TestDataInlineDirsTypedDict], dspath: Path):
        """
        Create emulated directories from the "inline directories" emulation data.

        Args:
            infos: A collection of inline directories configuration dictionaries.
            dspath: The dataset path.
        """

        for info in infos:
            filepath = dspath / info["dirname"] / info["filename"]

            try:
                with open(filepath, "r", encoding="utf-8") as fobj:
                    lines = fobj.readlines()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read inline directories configuration file '{filepath}':\n"
                            f"{errmsg}") from err

            for line in lines:
                dirpath = self._basepath / line.strip().lstrip("/")
                try:
                    dirpath.mkdir(parents=True, exist_ok=True)
                except OSError as err:
                    errmsg = Error(str(err)).indent(2)
                    raise Error(f"Failed to create emulated directory '{dirpath}':\n"
                                f"{errmsg}") from err

    def _process_inlinefiles(self, infos: list[_TestDataInlineFilesTypedDict], dspath: Path):
        """
        Create emulated files from "inline files" emulation data.

        Args:
            infos: A collection of inline files configuration dictionaries.
            dspath: The dataset path.
        """

        for info in infos:
            filepath = dspath / info["dirname"] / info["filename"]

            try:
                with open(filepath, "r", encoding="utf-8") as fobj:
                    lines = fobj.readlines()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read inline files configuration file '{filepath}':\n"
                            f"{errmsg}") from err

            sep = info["separator"]

            for line in lines:
                split = line.split(sep)

                if len(split) != 2:
                    raise Error(f"Unexpected line format in '{filepath}':\n"
                                f"  Expected <path>{sep}<value>, received '{line}'")

                path = split[0]
                data = split[1]

                # Note about lstrip(): it is required because 'path' is an absolute path starting
                # with '/'. If not stripped, joining it with the base path would ignore the base
                # path. For example, Path("/tmp") / "/sys" results in "/sys" instead of "/tmp/sys".
                dirpath = self._basepath / path.lstrip("/")
                dirpath = dirpath.parent

                try:
                    dirpath.mkdir(parents=True, exist_ok=True)
                except OSError as err:
                    errmsg = Error(str(err)).indent(2)
                    raise Error(f"Failed to create directory '{dirpath}':\n{errmsg}") from err

                emul = _EmulFile.get_emul_file(path, self._basepath, data=data,
                                               readonly=info["readonly"])
                self._emd["files"][path] = emul

    def _process_commands(self, infos: list[_TestDataCommandsTypedDict], dspath: Path):
        """
        Read and save emulated commands stdout and stderr from "commands" emulation data.

        Args:
            infos: A collection of commands configuration dictionaries.
            dspath: The dataset path.
        """

        for info in infos:
            dirpath = dspath / info["dirname"]

            try:
                path = dirpath / "stdout.txt"
                with open(path, encoding="utf-8") as fobj:
                    stdout = fobj.readlines()
                path = dirpath / "stderr.txt"
                with open(path, encoding="utf-8") as fobj:
                    stderr = fobj.readlines()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read '{path}':\n{errmsg}") from err

            result = _EmulCmdResultType(stdout=stdout, stderr=stderr, exitcode=0)
            self._emd["cmds"][info["command"]] = result

    def _process_msrs(self, info: _TestDataMSRsTypedDict, filepath: Path):
        """
        Create emulated MSR device files from MSR emulation data.

        Args:
            info: MSR configuration dictionary.
            dspath: The dataset path.
        """

        filepath = filepath / info["dirname"] / info["filename"]

        try:
            with open(filepath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to read emulated MSR data from '{filepath}':\n{errmsg}") from err

        sep1 = info["separator1"]
        sep2 = info["separator2"]

        for line in lines:
            split = line.split(sep1)

            if len(split) != 2:
                raise Error(f"Unexpected line format in file '{filepath}':\n  "
                            f"Expected <path>{sep1}<reg_value_pairs>, received '{line}'")

            path = split[0]
            reg_val_pairs = split[1].split()

            data: dict[int, bytes] = {}
            for reg_val_pair in reg_val_pairs:
                regaddr_str, regval_str = reg_val_pair.split(sep2)

                if len(split) != 2:
                    raise Error(f"Unexpected register-value format in file '{filepath}':\n  "
                                f"Expected <regaddr>{sep2}<value>, received '{line}'")

                regaddr = int(regaddr_str)
                regval = int(regval_str, 16)
                data[regaddr] = int.to_bytes(regval, 8, byteorder="little")

            emul = _EmulFile.get_emul_file(path, self._basepath, data=data)
            self._emd["files"][path] = emul

    def _process_files(self, infos: list[_TestDataFilesTypedDict], catpath: Path):
        """
        Create emulated files from the emulation data.

        Args:
            infos: A collection of files configuration dictionaries.
            catpath: The category path (a sub-directory in the dataset path).
        """

        for info in infos:
            filepath = catpath / info["path"].lstrip("/")

            try:
                with open(filepath, "r", encoding="utf-8") as fobj:
                    data = fobj.read()
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to read '{filepath}':\n{errmsg}") from err

            emul = _EmulFile.get_emul_file(info["path"], self._basepath, data=data,
                                           readonly=info["readonly"])
            self._emd["files"][info["path"]] = emul

    def _process_directories(self, infos: list[_TestDataDirectoriesTypedDict]):
        """
        Create emulated directories from the emulation data.

        Args:
            infos: A collection of directories configuration dictionaries.
        """

        for info in infos:
            dirpath = self._basepath / info["path"].lstrip("/")

            try:
                dirpath.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to create directory '{dirpath}':\n{errmsg}") from err

    def _process_test_data_category(self, yaml_path: Path):
        """
        Process a test data category configuration file and initialize related emulation data.

        Args:
            yaml_path: Path to the YAML configuration file describing the test data category.
        """

        yaml = cast(_TestDataYAMLTypedDict, YAML.load(yaml_path))
        dspath = yaml_path.parent

        if "inlinedirs" in yaml:
            self._process_inlinedirs(yaml["inlinedirs"], dspath)

        if "inlinefiles" in yaml:
            self._process_inlinefiles(yaml["inlinefiles"], dspath)

        if "commands" in yaml:
            self._process_commands(yaml["commands"], dspath)

        if "msrs" in yaml:
            self._process_msrs(yaml["msrs"], dspath)

        if "files" in yaml:
            self._process_files(yaml["files"], dspath / yaml_path.stem)

        if "directories" in yaml:
            self._process_directories(yaml["directories"])

    def init_emul_data(self, dspath: Path):
        """
        Load a dataset and initialize the emulation data.

        Args:
          dspath: Path to the dataset directory to load.

        Test data is organized as follows:
            - test_data_root/
              - common/
              - common.yaml
            - dataset1/
              - category1.yaml
              - category1/
              - category2.yaml
              - category2/
              ...
            - dataset2/
              ...

        Each dataset represents a System Under Test (SUT). The 'common' directory contains data shared
        across all datasets. Within each dataset, data is divided into multiple categories, each
        described by a YAML file and a corresponding sub-directory containing the actual data.

        Originally, categories matched pepc Python modules, but this mapping is no longer strict.
        Categories now simply group related test data.
        """

        # TODO: Instead of eagerly building all emulation data up front, construct it lazily and
        # only for the components that are actually required.

        # Load the shared test data from the 'common' directory located in the parent of the dataset.
        yaml_path = dspath.parent / "common" / "common.yaml"
        self._process_test_data_category(yaml_path)

        for yaml_path in dspath.iterdir():
            if not str(yaml_path).endswith(".yaml"):
                continue
            self._process_test_data_category(yaml_path)

    def mkdir(self, dirpath: str | Path, parents: bool = False, exist_ok: bool = False):
        """Refer to 'ProcessManagerBase.mkdir()'."""

        dirpath = self._basepath / str(dirpath).lstrip("/")
        super().mkdir(dirpath, parents=parents, exist_ok=exist_ok)

    def lsdir(self, path: str | Path) -> Generator[LsdirTypedDict, None, None]:
        """Refer to 'ProcessManagerBase.lsdir()'."""

        emul_path = Path(self._basepath / str(path).lstrip("/"))

        for entry in super().lsdir(emul_path):
            entry["path"] = entry["path"].relative_to(self._basepath)
            yield entry

    def exists(self, path):
        """
        Check if a file-system object at 'path' exists. The arguments are as follows.
          * path - the path to check.

        Return 'True' if path 'path' exists.
        """

        path = str(path)
        if path in self._emd["files"]:
            return True

        emul_path = Path(self._basepath / path.lstrip("/"))
        return super().exists(emul_path)

    def is_file(self, path):
        """
        Check if a file-system object at 'path' is a regular file. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a regular file, return 'False' otherwise.
        """

        path = str(path)
        if path in self._emd["files"]:
            return True

        emul_path = Path(self._basepath / path.lstrip("/"))
        return super().is_file(emul_path)

    def is_dir(self, path):
        """
        Check if a file-system object at 'path' is a directory. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a directory, return 'False' otherwise.
        """

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_dir(path)

    def is_exe(self, path):
        """
        Check if a file-system object at 'path' is a an executable file. The arguments are as
        follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is an executable file, return 'False' otherwise.
        """

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_exe(path)

    def is_socket(self, path):
        """
        Check if a file-system object at 'path' is a socket file. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a socket file, return 'False' otherwise.
        """

        path = Path(self._basepath / str(path).lstrip("/"))
        return super().is_socket(path)

    def mkdtemp(self, prefix: str | None  = None, basedir: str | Path | None = None) -> Path:
        """
        Create a temporary directory and return its path. The arguments are as follows.
          * prefix - specifies the temporary directory name prefix.
          * basedir - path to the base directory where the temporary directory should be created.
        """

        path = self._basepath
        if basedir:
            path = path / basedir

        temppath = super().mkdtemp(prefix=prefix, basedir=path)
        return temppath.relative_to(self._basepath)
