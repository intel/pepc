# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Emulated version or the 'LocalProcessManager' module for testing purposes."""

# pylint: disable=protected-access
# pylint: disable=arguments-differ
# pylint: disable=arguments-renamed

import io
import types
import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers, YAML
from pepclibs.helperlibs._ProcessManagerBase import ProcResult
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound

_LOG = logging.getLogger()

def _get_err_prefix(fobj, method):
    """Return the error message prefix."""
    return f"method '{method}()' failed for {fobj.name}"

def populate_rw_file(path, data):
    """Create text file 'path' and write 'data' into it."""

    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    with open(path, "w", encoding="utf-8") as fobj:
        try:
            fobj.write(data)
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to write into file '{path}':\n{msg}") from err

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
    An process manager which pretends that it runs commands, but in reality it just returns
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

    def _sysfs_write(self, fobj, path, mode):
        """
        Sysfs files needs special handling when written to. This method ensure the emulated sysfs
        file behavior is same as in real hardware.
        """

        def _aspm_write(self, data):
            """
            Method for writing and mimicking sysfs ASPM policy file update.
            For example, writing "powersave" to the file will result in the following file contents:
            "default performance [powersave] powersupersave"
            """

            line = fobj._policies.replace(data, f"[{data}]")
            self.seek(0)
            self._orig_write(line)

        def _truncate_write(self, data):
            """
            Method for writing and mimicking sysfs files.
            For example, writing "Performance" to sysfs 'scaling_governor' file will result in the
            file containing only "Performance", irrelevant what the file contained before writing.
            """

            self.truncate(len(data))
            self.seek(0)
            self._orig_write(data)

        if path.startswith("/sys/"):
            if "w" in mode:
                raise Error("BUG: use 'r+' mode when opening sysfs virtual files.")

            if mode != "r+":
                return

            if path.endswith("pcie_aspm/parameters/policy"):
                policies = fobj.read().strip()
                fobj._policies = policies.replace("[", "").replace("]", "")
                fobj._orig_write = fobj.write
                fobj.write = types.MethodType(_aspm_write, fobj)

            else:
                fobj._orig_write = fobj.write
                fobj.write = types.MethodType(_truncate_write, fobj)

    def _msr_seek(self, fobj, path):
        """
        MSR files needs special handling when seeked. This method ensure the emulated behavior is
        same as in real hardware.
        """

        def _seek_offset(self, offset, whence=0):
            """
            Method for mimicking MSR seek().
            MSR register address are offset by 8 bytes, meaning register address 10 is 80 bytes from
            start of file.
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
        Does not really run commands, just pretends running them and returns the pre-defined output
        values. Works only for a limited set of known commands. If the command is not known, raises
        'ErrorNotSupported'.

        Refer to 'ProcessManagerBase.run_verify()' for more information.
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
        Similarly to 'run_verify()', emulates a pre-defined set of commands. Refer to
        'ProcessManagerBase.run_verify()' for more information.
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

    def _open_rw(self, path, mode):
        """Create a file in the temporary directory and return the file object."""

        tmppath = self._get_basepath() / str(path).strip("/")

        # Disabling buffering is only allowed in binary mode.
        if "b" in mode:
            buffering = 0
            encoding = None
        else:
            buffering = -1
            encoding = "utf-8"

        errmsg = f"cannot open file '{path}' with mode '{mode}': "
        try:
            # pylint: disable=consider-using-with
            fobj = open(tmppath, mode, buffering=buffering, encoding=encoding)
        except PermissionError as err:
            msg = Error(err).indent(2)
            raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
        except FileNotFoundError as err:
            msg = Error(err).indent(2)
            raise ErrorNotFound(f"{errmsg}\n{msg}") from None
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"{errmsg}\n{msg}") from None

        # Make sure methods of 'fobj' always raise the 'Error' exceptions.
        fobj = ClassHelpers.WrapExceptions(fobj, get_err_prefix=_get_err_prefix)
        self._ofiles[path] = fobj
        return fobj

    def _open_ro(self, path, mode): # pylint: disable=unused-argument
        """Return an emulated read-only file object using a 'StringIO' object."""

        def _ro_write(self, data):
            """Write method for emulating RO file."""
            raise Error("not writable")

        fobj = io.StringIO(self._ro_files[path])
        fobj.write = types.MethodType(_ro_write, fobj)
        return fobj

    def open(self, path, mode):
        """Create a file in the temporary directory and return the file object."""

        path = str(path)
        if path in self._ro_files:
            fobj = self._open_ro(path, mode)
        else:
            fobj = self._open_rw(path, mode)
            self._sysfs_write(fobj, path, mode)

        self._msr_seek(fobj, path)
        self._ofiles[path] = fobj
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
                    raise Error(f"unexpected line format, expected <path>{sep}<value>, received\n" \
                                f"{line}")

                # Create file in temporary directory. For example:
                # Emulated path: /sys/devices/system/cpu/cpu0/
                # Real path: /tmp/emulprocs_861089_0s3hy8ye/sys/devices/system/cpu/cpu0/
                path = split[0]
                data = split[1]

                if finfo.get("readonly"):
                    self._ro_files[path] = data
                else:
                    path = self._get_basepath() / path.lstrip("/")
                    populate_rw_file(path, data)

    def _init_directories(self, finfos, datapath):
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
                raise Error(f"unexpected line format in file '{datapath}', expected <path>{sep1}" \
                            f"<reg_value_pairs>, received\n{line}")

            path = split[0].strip()
            reg_val_pairs = split[1].split()

            data = {}
            for reg_val_pair in reg_val_pairs:
                regaddr, regval = reg_val_pair.split(sep2)

                if len(split) != 2:
                    raise Error(f"unexpected register-value format in file '{datapath}', " \
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
            src = datapath / module / finfo["path"].lstrip("/")

            try:
                with open(src, "r", encoding="utf-8") as fobj:
                    data = fobj.read()
            except ErrorNotFound:
                continue

            if finfo.get("readonly"):
                self._ro_files[finfo["path"]] = data
            else:
                path = self._get_basepath() / finfo["path"].lstrip("/")
                populate_rw_file(path, data)

    def init_testdata(self, module, datapath):
        """Initialize the testdata for module 'module' from directory 'datapath'."""

        confpath = datapath / f"{module}.yaml"
        if not confpath.exists():
            raise ErrorNotSupported(f"testdata configuration for module '{module}' not found " \
                                    f"({confpath}).")

        config = YAML.load(confpath)

        if "directories" in config:
            self._init_directories(config["directories"], datapath)

        if "commands" in config:
            self._init_commands(config["commands"], datapath)

        if "inlinefiles" in config:
            self._init_inline_files(config["inlinefiles"], datapath)

        if "msrs" in config:
            self._init_msrs(config["msrs"], datapath)

        if "files" in config:
            self._init_files(config["files"], datapath, module)

        self.datapath = datapath

    def mkdir(self, dirpath, parents=False, exist_ok=False):
        """
        Create a directory. Refer to '_ProcessManagerBase.ProcessManagerBase().mkdir()' for more
        information.
        """

        dirpath = self._get_basepath() / str(dirpath).lstrip("/")
        super().mkdir(dirpath, parents=parents, exist_ok=exist_ok)

    def exists(self, path):
        """Returns 'True' if path 'path' exists."""

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().exists(path)

    def is_file(self, path):
        """Return 'True' if path 'path' exists an it is a regular file."""

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_file(path)

    def is_dir(self, path):
        """Return 'True' if path 'path' exists an it is a directory."""

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_dir(path)

    def is_exe(self, path):
        """Return 'True' if path 'path' exists an it is an executable file."""

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_exe(path)

    def is_socket(self, path):
        """Return 'True' if path 'path' exists an it is a Unix socket file."""

        path = Path(self._get_basepath() / str(path).lstrip("/"))
        return super().is_socket(path)

    def mkdtemp(self, prefix=None, basedir=None):
        """
        Create a temporary directory. Refer to '_ProcessManagerBase.ProcessManagerBase().mkdtemp()'
        for more information.
        """

        path = self._get_basepath()
        if basedir:
            path = path / basedir

        temppath = super().mkdtemp(prefix=prefix, basedir=path)
        return temppath.relative_to(self._get_basepath())

    def __init__(self, hostname=None):
        """Initialize the class instance."""

        super().__init__()

        if hostname:
            self.hostname = hostname
        else:
            self.hostname = "emulated local host"
        self.hostmsg = f" on '{self.hostname}'"
        self.is_remote = False

        self.datapath = None
        # Opened files.
        self._ofiles = {}
        # Data for emulated read-only files.
        self._ro_files = {}
        self._cmds = {}
        self._basepath = None

    def close(self):
        """Stop emulation."""

        if getattr(self, "_files", None):
            for _, fobj in self._ofiles.items():
                fobj.close()
            self._ofiles = None

        if getattr(self, "_basepath", None):
            with contextlib.suppress(Error):
                super().rmtree(self._basepath)

        with contextlib.suppress(Exception):
            super().close()
