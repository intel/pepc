# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Provide the base class for sub-classes emulating sysfs, procfs, and debugfs files."""

class EmulFileBase:
    """Base class for sub-classes emulating sysfs, procfs, and debugfs files."""

    def open(self, mode):
        """Create a file in the temporary directory and return the file object with 'mode'."""
        raise NotImplementedError()

    def __init__(self, path):
        """
        Class constructor. Arguments are as follows:
         * path - emulated path of the file.
        """
        self.path = path
