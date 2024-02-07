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

    known, unknown = tpmi_obj.list_features()
    if known:
        _LOG.info("Supported TPMI features")
        for scan_info in known:
            _LOG.info(" - %s: %s", scan_info["name"], scan_info["desc"].strip())
    if unknown and args.all:
        _LOG.info("Unknown TPMI features (available%s, but no spec file found)", pman.hostmsg)
        txt = ", ".join(unknown)
        _LOG.info(" - %s", txt)
