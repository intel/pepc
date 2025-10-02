# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
The pepc project coding style pylint extention.
"""

from pylint.lint import PyLinter

def register(linter: PyLinter) -> None:
    """
    Register the pepc coding style pylint plugin.

    Args:
        linter: the 'PyLinter' object to register within.
    """

    pass
