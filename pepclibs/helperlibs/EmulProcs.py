#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Emulated version or the 'Procs' module for testing purposes."""

import contextlib
from pepclibs.helperlibs import FSHelpers, Trivial
from pepclibs.helperlibs._Common import ProcResult
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

class EmulProc():
    """
    Emulated version of the 'Proc' class in the 'pepclibs.helperlibs.Procs' module. The class is
    used for testing purposes.
    """

    def _get_cmd_result(self, cmd):
        """Return pre-defined value for the command 'cmd'."""

        if cmd not in self._cmds:
            raise ErrorNotSupported(f"unsupported command: '{cmd}'")

        return self._cmds[cmd]

    def run_verify(self, cmd, **kwargs): # pylint: disable=unused-argument
        """
        Emulates 'Proc.run_verify()' for pre-defined set of commands. If command is not known,
        raises an 'ErrorNotSupported' exception.
        """

        return (self._get_cmd_result(cmd), "")

    def run(self, cmd, **kwargs): # pylint: disable=unused-argument
        """Same as 'run_verify()', but emulates the 'Proc.run()' command."""

        return ProcResult(stdout=self._get_cmd_result(cmd), stderr="", exitcode=0)

    def open(self, path, mode):
        """Create file in temporary directory and return the file object."""

        tmppath = self._basepath / str(path).strip("/")

        self._files[path] = open(tmppath, mode, buffering=0)  # pylint: disable=consider-using-with

        return self._files[path]

    def init_testdata(self, datapath):
        """Initialize emulated commands and the output the commands will produce."""

        self._cmds = {}
        cmdinfo = (("lscpu --physical --all -p=socket,node,core,cpu,online", "lscpu_info_cpus.txt"),
                   ("lscpu", "lscpu_info.txt"),)
        for cmd, datafile in cmdinfo:
            with contextlib.suppress(Exception), open(datapath / datafile) as fobj:
                self._cmds[cmd] = fobj.readlines()

        for cmd, value in (("test -e '/dev/cpu/0/msr'", ""), ):
            self._cmds[cmd] = value

    def __init__(self):
        """Initialize the emulated 'Proc' class instance."""

        self.hostname = "emulated local host"
        self.hostmsg = f" on '{self.hostname}'"

        # Opened files.
        self._files = {}
        self._cmds = {}
        pid = Trivial.get_pid()
        self._basepath = FSHelpers.mktemp(prefix=f"emulprocs_{pid}_")

        self.is_remote = False

    def close(self):
        """Stop emulation."""

        if getattr(self, "_files", None):
            for _, fobj in self._files.items():
                fobj.close()
            self._files = None

        if getattr(self, "_basepath", None):
            with contextlib.suppress(OSError):
                FSHelpers.rm_minus_rf(self._basepath)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the turntime context."""
        self.close()
