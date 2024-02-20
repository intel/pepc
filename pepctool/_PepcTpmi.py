# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
Implement the 'pepc tpmi' command.
"""

import logging
from pepclibs import Tpmi

_LOG = logging.getLogger()

def tpmi_ls_command(args, pman):
    """
    Implement the 'tpmi ls' command. The arguments are as follows.
      * args - command line arguments.
      * pman - the process manager object that defines the target host.
    """

    tpmi_obj = Tpmi.Tpmi(pman)

    known = tpmi_obj.get_known_features()
    if known:
        _LOG.info("Supported TPMI features")
        for sdict in known:
            _LOG.info(" - %s: %s", sdict["name"], sdict["desc"].strip())

    if args.all:
        unknown = tpmi_obj.get_unknown_features()
        if unknown and args.all:
            _LOG.info("Unknown TPMI features (available%s, but no spec file found)", pman.hostmsg)
            txt = ", ".join(hex(fid) for fid in unknown)
            _LOG.info(" - %s", txt)
