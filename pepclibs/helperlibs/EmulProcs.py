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

class EmulProc():
    """
    Emulated version of the 'Proc' class in the 'pepclibs.helperlibs.Procs' module. The class is
    used for testing purposes.
    """

    def open(self, path, mode):
        """Create and return emulated file object."""

        if path in self._files and not self._files[path].closed:
            return self._files[path]

        if "b" in mode:
            self._files[path] = io.BytesIO()
        else:
            self._files[path] = io.StringIO()

        return self._files[path]

    def __init__(self):
        """Initialize the emulated 'Proc' class instance."""

        # Opened files.
        self._files = {}
