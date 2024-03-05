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
from pepclibs.helperlibs import Human, Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

def _ls_long(fname, tpmi, prefix=""):
    """Print extra information about feature 'fname' (in case of the 'tpmi ls -l' command)."""

    # A dictionary with the info that will be printed.
    #   * first level key - package number.
    #   * second level key - PCI address.
    #   * value - instance numbers.
    info = {}

    for addr, package, instance in tpmi.iter_feature(fname):
        if package not in info:
            info[package] = {}
        if addr not in info[package]:
            info[package][addr] = set()
        info[package][addr].add(instance)

    for package in sorted(info):
        pfx1 = prefix + "- "
        pfx2 = prefix + "  "

        for addr in sorted(info[package]):
            _LOG.info("%sPCI address: %s", pfx1, addr)
            pfx1 = pfx2 + "- "
            pfx2 += "  "

            _LOG.info("%sPackage: %s", pfx2, package)

            instances = Human.rangify(info[package][addr])
            _LOG.info("%sInstances: %s", pfx2, instances)

def tpmi_ls_command(args, pman):
    """
    Implement the 'tpmi ls' command. The arguments are as follows.
      * args - command line arguments.
      * pman - the process manager object that defines the target host.
    """

    tpmi = Tpmi.Tpmi(pman)

    sdicts = tpmi.get_known_features()
    if not sdicts:
        _LOG.info("Not supported TPMI features found")
    else:
        _LOG.info("Supported TPMI features")
        for sdict in sdicts:
            _LOG.info(" - %s: %s", sdict["name"], sdict["desc"].strip())
            if args.long:
                _ls_long(sdict["name"], tpmi, prefix="   ")

    if args.all:
        fnames = tpmi.get_unknown_features()
        if fnames and args.all:
            _LOG.info("Unknown TPMI features (available%s, but no spec file found)", pman.hostmsg)
            txt = ", ".join(hex(fid) for fid in fnames)
            _LOG.info(" - %s", txt)

def tpmi_read_command(args, pman):
    """
    Implement the 'tpmi read' command. The arguments are as follows.
      * args - command line arguments.
      * pman - the process manager object that defines the target host.
    """

    tpmi = Tpmi.Tpmi(pman=pman)
    fdict = tpmi.get_fdict(args.fname)

    if not args.addrs:
        addrs = [addr for addr, _, _ in tpmi.iter_feature(args.fname)]
    else:
        addrs = Trivial.split_csv_line(args.addrs, dedup=True)

    if not args.instances:
        instances = [inst for _, _, inst in tpmi.iter_feature(args.fname, addrs=addrs)]
        instances = Trivial.list_dedup(instances)
    else:
        instances = Trivial.split_csv_line_int(args.instances, dedup=True,
                                               what="TPMI instance numbers")

    if not args.register:
        if args.bfname:
            raise Error("--bfname requires '--register' to be specified")
        registers = list(fdict)
    else:
        registers = Trivial.split_csv_line(args.register, dedup=True)

    for addr in addrs:
        for instance in instances:
            for regname in registers:
                value = tpmi.read_register(args.fname, addr, instance, regname)
                printed = False
                for bfname, fieldinfo in fdict[regname]["fields"].items():
                    if args.bfname not in (None, bfname):
                        continue

                    if not printed:
                        printed = True
                        _LOG.info("%s[%d]: 0x%x", regname, instance, value)

                    value = tpmi.read_register(args.fname, addr, instance, regname,
                                               bfname=bfname)
                    _LOG.info("  %s[%s]: %d", bfname, fieldinfo["bits"], value)
                    _LOG.info("    %s", fieldinfo["desc"])
