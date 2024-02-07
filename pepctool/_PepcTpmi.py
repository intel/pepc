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
    Implement the 'tpmi sl' command. The arguments are as follows.
      * args - command line arguments.
      * pman - the process manager object that defines the target host.
    """

    tpmi_obj = Tpmi.Tpmi(pman)

    known_fnames, unknown_fids = tpmi_obj.list_features()
    if known_fnames:
        _LOG.info("Supported TPMI features")
        txt = ", ".join(known_fnames)
        _LOG.info("  %s", txt)
    if unknown_fids and args.all:
        _LOG.info("Unknown TPMI features (supported%s, but no spec file found):", pman.hostmsg)
        txt = ", ".join(unknown_fids)
        _LOG.info("  %s", txt)
