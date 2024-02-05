# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
This feature includes the "tpmi" 'pepc' command implementation.
"""

import logging
from pepclibs import Tpmi

_LOG = logging.getLogger()

def tpmi_ls_command(args, pman):
    """
    Implements the 'tpmi info' command. Arguments are as follows.
      * args - command line arguments.
      * pman - process manager.
    """

    tpmi_obj = Tpmi.Tpmi(pman)

    features, no_specs = tpmi_obj.get_features()
    if features:
        _LOG.info("Following features are fully supported:")
        txt = ", ".join(features)
        _LOG.info("  %s", txt)
    if no_specs and args.all:
        _LOG.info("Following features are supported by hardware, but have no spec data available:")
        txt = ", ".join(no_specs)
        _LOG.info("  %s", txt)
