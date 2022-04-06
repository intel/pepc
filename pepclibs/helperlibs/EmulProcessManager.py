#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Emulated version or the 'LocalProcessManager' module for testing purposes."""

import io
import types
import logging
import contextlib
from pepclibs.helperlibs import _ProcessManagerBase, FSHelpers, Trivial, WrapExceptions, YAML
from pepclibs.helperlibs._ProcessManagerBase import ProcResult
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound

_LOG = logging.getLogger()

# The exceptions to handle when dealing with file I/O.
_EXCEPTIONS = (OSError, IOError, BrokenPipeError)

def _get_err_prefix(fobj, method):
    """Return the error message prefix."""
    return "method '%s()' failed for %s" % (method, fobj.name)

def populate_rw_file(path, data):
    """Create text file 'path' and write 'data' into it."""

    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    with open(path, "w") as fobj:
        try:
            fobj.write(data)
        except OSError as err:
            raise Error(f"failed to write into file '{path}':\n{err}") from err

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
        raise Error(f"failed to prepare sparse file '{path}':\n{err}") from err

class EmulProcessManager(_ProcessManagerBase.ProcessManagerBase):
    """
    An process manager which pretends that it runs commands, but in reality it just returns
    pre-defined command output. This class is used for testing purposes.
    """

    def _get_cmd_result(self, cmd):
        """Return pre-defined value for the command 'cmd'."""

        if cmd not in self._cmds:
            raise ErrorNotSupported(f"unsupported command: '{cmd}'")

        return self._cmds[cmd]

    def _get_basepath(self):
        """Return path to the temporary directory where all the emulated files should be created."""

        if not self._basepath:
            pid = Trivial.get_pid()
            self._basepath = FSHelpers.mktemp(prefix=f"emulprocs_{pid}_")

        return self._basepath

    def run_verify(self, cmd, **kwargs):
        """
        Does not really run commands, just pretends running them and returns the pre-dfined output
        values. Works only for a limited set of known commands. If the command is not known, raises
        'ErrorNotSupported'.

        Refer to 'ProcessManagerBase.run_verify()' for more information.
        """

        # pylint: disable=unused-argument,arguments-differ
        _LOG.debug("running the following emulated command:\n%s", cmd)

        return self._get_cmd_result(cmd)

    def run(self, cmd, **kwargs): # pylint: disable=unused-argument
        """
        Similarly to 'run_verify()', emulates a pre-defined set of commands. Refer to
        'ProcessManagerBase.run_verify()' for more information.
        """

        # pylint: disable=unused-argument,arguments-differ
        _LOG.debug("running the following emulated command:\n%s", cmd)

        stdout, stderr = self._get_cmd_result(cmd)
        return ProcResult(stdout=stdout, stderr=stderr, exitcode=0)

    def _open_rw(self, path, mode):
        """Create a file in the temporary directory and return the file object."""

        tmppath = self._get_basepath() / str(path).strip("/")

        # Disabling buffering is only allowed in binary mode.
        if "b" in mode:
            buffering = 0
        else:
            buffering = -1

        errmsg = f"cannot open file '{path}' with mode '{mode}': "
        try:
            fobj = open(tmppath, mode, buffering=buffering)  # pylint: disable=consider-using-with
        except PermissionError as err:
            raise ErrorPermissionDenied(f"{errmsg}{err}") from None
        except FileNotFoundError as err:
            raise ErrorNotFound(f"{errmsg}{err}") from None
        except OSError as err:
            raise Error(f"{errmsg}{err}") from None

        # Make sure methods of 'fobj' always raise the 'Error' exceptions.
        fobj = WrapExceptions.WrapExceptions(fobj, exceptions=_EXCEPTIONS,
                                             get_err_prefix=_get_err_prefix)
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

        self._ofiles[path] = fobj
        return fobj

    def _init_commands(self, cmdinfos, datapath):
        """
        Initialize commands described by the 'cmdinfos' dictionary. Read the stdout/stderr data of
        the commands from 'datapath' and save them in 'self._cmds'.
        """

        for cmdinfo in cmdinfos:
            commandpath = datapath / cmdinfo["dirname"]

            with open(commandpath / "stdout.txt") as fobj:
                stdout = fobj.readlines()
            with open(commandpath / "stderr.txt") as fobj:
                stderr = fobj.readlines()

            self._cmds[cmdinfo["command"]] = (stdout, stderr)

    def _init_inline_files(self, finfos, datapath):
        """
        Inline files are defined in text file where single line defines path and content for single
        emulated file. Initialize predefined data for emulated files defined by dictionary 'finfos'.
        """

        for finfo in finfos:
            filepath = datapath / finfo["dirname"] / finfo["filename"]

            with open(filepath, "r") as fobj:
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
                data = split[1].strip()

                if finfo.get("readonly"):
                    self._ro_files[path] = data
                else:
                    path = self._get_basepath() / path.lstrip("/")
                    populate_rw_file(path, data)

    def _init_msrs(self, msrinfo, datapath):
        """
        MSR values are defined in text file where single line defines path used to access MSR values
        and address value pairs. Initialize predefined data for emulated MSR files defined by
        dictionary 'msrinfo'.
        """

        datapath = datapath / msrinfo["dirname"] / msrinfo["filename"]

        try:
            with open(datapath, "r") as fobj:
                lines = fobj.readlines()
        except OSError as err:
            raise Error(f"failed to read emulated MSR data from file '{datapath}':\n{err}") from err

        sep = msrinfo["separator1"]
        for line in lines:
            split = line.split(sep)

            if len(split) != 2:
                raise Error(f"unexpected line format in file '{datapath}', expected <path>{sep}" \
                            f"<reg_value_pairs>, received\n{line}")

            path = split[0].strip()
            reg_val_pairs = split[1].split()

            data = {}
            for reg_val_pair in reg_val_pairs:
                regaddr, regval = reg_val_pair.split(msrinfo["separator2"])

                if len(split) != 2:
                    raise Error(f"unexpected register-value format in file '{datapath}', " \
                                f"expected <path>{msrinfo['separator2']}<value>, received\n{line}")

                regaddr = int(regaddr)
                regval = int(regval, 16)

                data[regaddr] = int.to_bytes(regval, 8, byteorder="little")

            path = self._get_basepath() / path.lstrip("/")
            _populate_sparse_file(path, data)

    def init_testdata(self, module, datapath):
        """Initialize the testdata for module 'module' from directory 'datapath'."""

        confpath = datapath / f"{module}.yaml"
        if not confpath.exists():
            raise ErrorNotSupported(f"testdata configuration for module '{module}' not found " \
                                    f"({confpath}).")

        config = YAML.load(confpath)

        if "commands" in config:
            self._init_commands(config["commands"], datapath)

        if "inlinefiles" in config:
            self._init_inline_files(config["inlinefiles"], datapath)

        if "msrs" in config:
            self._init_msrs(config["msrs"], datapath)

    def __init__(self):
        """Initialize the emulated 'LocalProcessManager' class instance."""

        super().__init__()

        self.hostname = "emulated local host"
        self.hostmsg = f" on '{self.hostname}'"
        self.is_remote = False

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
            with contextlib.suppress(OSError):
                FSHelpers.rm_minus_rf(self._basepath)

        with contextlib.suppress(Exception):
            super().close()
