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

import io
import contextlib
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
        """Create and return emulated file object."""

        if path in self._files and not self._files[path].closed:
            return self._files[path]

        if "b" in mode:
            self._files[path] = io.BytesIO()
        else:
            self._files[path] = io.StringIO()

        return self._files[path]

    def init_testdata(self, datapath):
        """Initialize emulated commands and the output the commands will produce."""

        self._cmds = {}
        for cmd, datafile in (("lscpu --all -p=socket,node,core,cpu,online", "lscpu_info_cpus.txt"),
                              ("lscpu", "lscpu_info.txt"), ):
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

        self.is_remote = False
