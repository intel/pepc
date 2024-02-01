# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Emulated version or the 'LocalProcessManager' module for testing purposes."""

# pylint: disable=protected-access
# pylint: disable=arguments-differ
# pylint: disable=arguments-renamed

import types
import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs import LocalProcessManager, Trivial, YAML, _EmulFile
from pepclibs.helperlibs._ProcessManagerBase import ProcResult
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = logging.getLogger()

def _populate_sparse_file(path, data):
    """Create sparse file 'path' and write sparse data 'data' into it."""

    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    try:
        with open(path, "wb") as fobj:
            for offset, value in data.items():
                fobj.seek(offset)
                fobj.write(value)
    except OSError as err:
        msg = Error(err).indent(2)
        raise Error(f"failed to prepare sparse file '{path}':\n{msg}") from err

class EmulProcessManager(LocalProcessManager.LocalProcessManager):
    """
    A process manager which pretends that it runs commands, but in reality it just returns
    pre-defined command output. This class is used for testing purposes.
    """

    def _get_predefined_result(self, cmd, join=True):
        """Return pre-defined value for the command 'cmd'."""

        if cmd not in self._cmds:
            raise ErrorNotSupported(f"unsupported command: '{cmd}'")

        stdout, stderr = self._cmds[cmd]
        if join:
            stdout = "".join(stdout)
            stderr = "".join(stderr)

        return (stdout, stderr)

    def _get_basepath(self):
        """Return path to the temporary directory where all the emulated files should be created."""

        if not self._basepath:
            pid = Trivial.get_pid()
            self._basepath = super().mkdtemp(prefix=f"emulprocs_{pid}_")

        return self._basepath

    def _set_seek_method(self, fobj, path):
        """
        Some files needs special 'seek()' handling. Replace the 'seek()' method of 'fobj' with a
        custom method in order to properly emulate the behavior of the file in 'path'.
        """

        def _seek_offset(self, offset, whence=0):
            """
            Mimic '/dev/msr/*' files' 'seek()' behavior. MSR register address are offset by 8 bytes,
            meaning register address 10 is 80 bytes from start of file.
            """
            self._orig_seek(offset * 8, whence)

        if path.endswith("/msr"):
            fobj._orig_seek = fobj.seek
            fobj.seek = types.MethodType(_seek_offset, fobj)

    def _extract_path(self, cmd):
        """
        Parse command 'cmd' and find if it includes path which is also emulated. Returns the path if
        found, otherwise returns 'None'.
        """

        basepath = self._get_basepath()

        for split in cmd.split():
            if Path(basepath / split).exists():
                return split
            for strip_chr in ("'/", "\"/"):
                if Path(basepath / split.strip(strip_chr)).exists():
                    return split.strip(strip_chr)

        return None

    def _rebase_cmd(self, cmd):
        """
        Modify command 'cmd' so that it is run against emulated files. Returns 'None' if the command
        doesn't include any paths, or paths are not emulated.
        """

        basepath = self._get_basepath()
        if str(basepath) in cmd:
            return cmd

        path = self._extract_path(cmd)
        if path:
            rebased_cmd = cmd.replace(path, f"{basepath}/{str(path).lstrip('/')}")
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

    def run(self, cmd, join=True, **kwargs): # pylint: disable=unused-argument
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

        return ProcResult(stdout=stdout, stderr=stderr, exitcode=0)

    def open(self, path, mode):
        """
        Open a file on the at 'path' and return a file-like object. The arguments are as follows.
          * path - path to the file to open.
          * mode - the same as in the standard python 'open()'.

        Open a file at path 'path' relative to the emulation base directory. Create it if necessary.
        """

        path = str(path)
        if path in self._emuls:
            return self._emuls[path].open(mode)

        if path in self._ro_files:
            fobj = _EmulFile.open_ro(self._ro_files[path], mode)
        else:
            fobj = _EmulFile.open_rw(path, mode, self._get_basepath())

        self._set_seek_method(fobj, path)
        return fobj

    def _init_commands(self, cmdinfos, datapath):
        """
        Initialize commands described by the 'cmdinfos' dictionary. Read the stdout/stderr data of
        the commands from 'datapath' and save them in 'self._cmds'.
        """

        for cmdinfo in cmdinfos:
            commandpath = datapath / cmdinfo["dirname"]

            with open(commandpath / "stdout.txt", encoding="utf-8") as fobj:
                stdout = fobj.readlines()
            with open(commandpath / "stderr.txt", encoding="utf-8") as fobj:
                stderr = fobj.readlines()

            self._cmds[cmdinfo["command"]] = (stdout, stderr)

    def _init_default_files(self):
        """Initialize default files that should exist for any emulated platform."""

        # Create '/proc/mounts' as a read only file.
        txt = "debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,relatime 0 0"
        self._ro_files["/proc/mounts"] = txt

    def _init_inline_files(self, finfos, datapath):
        """
        Inline files are defined in text file where single line defines path and content for single
        emulated file. Initialize predefined data for emulated files defined by dictionary 'finfos'.
        """

        for finfo in finfos:
            filepath = datapath / finfo["dirname"] / finfo["filename"]

            with open(filepath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()

            for line in lines:
                sep = finfo["separator"]
                split = line.split(sep)

                if len(split) != 2:
                    raise Error(f"unexpected line format, expected <path>{sep}<value>, received\n"
                                f"{line}")

                finfo["path"] = split[0]
                finfo["data"] = split[1]

                emul = _EmulFile.EmulFile(finfo, datapath, self._get_basepath)
                self._emuls[emul.path] = emul

    def _init_inline_dirs(self, finfos, datapath):
        """
        Directories are defined as paths in a text file. Create emulated directories as defined by
        dictionary 'finfos'.
        """

        for finfo in finfos:
            filepath = datapath / finfo["dirname"] / finfo["filename"]

            with open(filepath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()

            for line in lines:
                path = self._get_basepath() / line.strip().lstrip("/")
                if not path.exists():
                    path.mkdir(parents=True)

    def _init_msrs(self, msrinfo, datapath):
        """
        MSR values are defined in text file where single line defines path used to access MSR values
        and address value pairs. Initialize predefined data for emulated MSR files defined by
        dictionary 'msrinfo'.
        """

        datapath = datapath / msrinfo["dirname"] / msrinfo["filename"]

        try:
            with open(datapath, "r", encoding="utf-8") as fobj:
                lines = fobj.readlines()
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to read emulated MSR data from file '{datapath}':\n{msg}") from err

        sep1 = msrinfo["separator1"]
        sep2 = msrinfo["separator2"]

        for line in lines:
            split = line.split(sep1)

            if len(split) != 2:
                raise Error(f"unexpected line format in file '{datapath}', expected <path>{sep1}"
                            f"<reg_value_pairs>, received\n{line}")

            path = split[0].strip()
            reg_val_pairs = split[1].split()

            data = {}
            for reg_val_pair in reg_val_pairs:
                regaddr, regval = reg_val_pair.split(sep2)

                if len(split) != 2:
                    raise Error(f"unexpected register-value format in file '{datapath}', "
                                f"expected <regaddr>{sep2}<value>, received\n{line}")

                regaddr = int(regaddr)
                regval = int(regval, 16)

                # MSR register address are offset by 8 bytes.
                data[regaddr * 8] = int.to_bytes(regval, 8, byteorder="little")

            path = self._get_basepath() / path.lstrip("/")
            _populate_sparse_file(path, data)

    def _init_files(self, finfos, datapath, module):
        """Initialize plain files, which are just copies of the original files."""

        for finfo in finfos:
            emul = _EmulFile.EmulFile(finfo, datapath, self._get_basepath, module)
            self._emuls[emul.path] = emul

    def _init_directories(self, finfos, datapath, module):
        """Initialize directories."""

        for finfo in finfos:
            src = datapath / module / finfo["path"].lstrip("/")
            if not src.exists() or src.is_dir():
                path = self._get_basepath() / finfo["path"].lstrip("/")
                path.mkdir(parents=True)
            else:
                self._init_files((finfo,), datapath, module)

    def init_testdata(self, module, datapath):
        """Initialize the testdata for module 'module' from directory 'datapath'."""

        if module in self._modules:
            return

        if module == "CPUInfo":
            # CPUInfo uses '/sys/devices/system/cpu/online' file, on emulated system the file is
            # constructed using per-CPU '/sys/devices/system/cpu/cpu*/online' files that belong to
            # CPUOnline.
            self.init_testdata("CPUOnline", datapath)

        self._modules.add(module)

        confpath = datapath / f"{module}.yaml"
        if not confpath.exists():
            raise ErrorNotSupported(f"testdata configuration for module '{module}' not found "
                                    f"({confpath})")

        config = YAML.load(confpath)

        self._init_default_files()

        if "inlinedirs" in config:
            self._init_inline_dirs(config["inlinedirs"], datapath)

        if "commands" in config:
            self._init_commands(config["commands"], datapath)

        if "inlinefiles" in config:
            self._init_inline_files(config["inlinefiles"], datapath)

        if "msrs" in config:
            self._init_msrs(config["msrs"], datapath)

        if "files" in config:
            self._init_files(config["files"], datapath, module)

        if "recursive_copy" in config:
            self._init_directories(config["recursive_copy"], datapath, module)

        self.datapath = datapath

    def mkdir(self, dirpath, parents=False, exist_ok=False):
        """
        Create a directory. The a arguments are as follows.
          * dirpath - path to the directory to create.
          * parents - if 'True', the parent directories are created as well.
          * exist_ok - if the directory already exists, this method raises an exception if
                       'exist_ok' is 'True', and it returns without an error if 'exist_ok' is
                       'False'.

        Create a directory at 'dirpath' relative to the emulation base directory.
        """

        dirpath = self._get_basepath() / str(dirpath).lstrip("/")
        super().mkdir(dirpath, parents=parents, exist_ok=exist_ok)

    def lsdir(self, path, must_exist=True):
        """
        List directory entries at 'path'. The arguments are as follows.
          * path - path to list the directory entries at.
          * must_exist - same as in '_ProcessManagerBase.ProcessManagerBase().lsdir()'.

        Yield a ('name', 'path', 'mode') tuple for every directory entry in 'path' (relative to the
        emulation base directory). More information in
        '_ProcessManagerBase.ProcessManagerBase().lsdir()'.
        """

        emul_path = Path(self._get_basepath() / str(path).lstrip("/"))
        yield from super().lsdir(emul_path, must_exist=must_exist)

    def exists(self, path):
        """
        Check if a file-system object at 'path' (relative to the emulation base directory) exists.
        The arguments are as follows.
          * path - the path to check.

        Return 'True' if path 'path' exists.
        """

        emul_path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().exists(emul_path) or path in self._ro_files

    def is_file(self, path):
        """
        Check if a file-system object at 'path' (relative to the emulation base directory) is a
        regular file. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a regular file, return 'False' otherwise.
        """

        emul_path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_file(emul_path) or path in self._ro_files

    def is_dir(self, path):
        """
        Check if a file-system object at 'path' (relative to the emulation base directory) is a
        directory. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a directory, return 'False' otherwise.
        """

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_dir(path)

    def is_exe(self, path):
        """
        Check if a file-system object at 'path' (relative to the emulation base directory) is a
        an executable file. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is an executable file, return 'False' otherwise.
        """

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_exe(path)

    def is_socket(self, path):
        """
        Check if a file-system object at 'path' (relative to the emulation base directory) is a
        socket file. The arguments are as follows.
          * path - the path to check.

        Return 'True' 'path' exists and it is a socket file, return 'False' otherwise.
        """

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_socket(path)

    def mkdtemp(self, prefix=None, basedir=None):
        """
        Create a temporary directory. The arguments are as follows.
          * prefix - specifies the temporary directory name prefix.
          * basedir - path to the base directory where the temporary directory should be created.

        Create a temporary file at 'basdir' path relative to the emulation base directory. Return
        the path to the created temporary file.
        """

        path = self._get_basepath()
        if basedir:
            path = path / basedir

        temppath = super().mkdtemp(prefix=prefix, basedir=path)
        return temppath.relative_to(self._get_basepath())

    def __init__(self, hostname=None):
        """
        Initialize a class instance. The arguments are as follows.
          * hostname - name of the host to emulate.
        """

        super().__init__()

        if hostname:
            self.hostname = hostname
        else:
            self.hostname = "emulated local host"
        self.hostmsg = f" on '{self.hostname}'"
        self.is_remote = False

        self.datapath = None
        # Data for emulated read-only files.
        self._ro_files = {}
        self._cmds = {}
        self._basepath = None
        # Set of all modules that were initialized.
        self._modules = set()
        # A dictionary mapping paths to emulated file objects.
        self._emuls = {}

    def close(self):
        """Stop emulation."""

        if self._basepath:
            with contextlib.suppress(Error):
                super().rmtree(self._basepath)

        with contextlib.suppress(Exception):
            super().close()
