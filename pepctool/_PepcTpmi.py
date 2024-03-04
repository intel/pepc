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

        if len(info) > 1:
            _LOG.info("%sPackage: %s", pfx1, package)
            pfx1 = pfx2 + "- "
            pfx2 += "  "

        for addr in sorted(info[package]):
            _LOG.info("%sPCI address: %s", pfx1, addr)
            pfx1 = pfx2 + "- "
            pfx2 += "  "

            instances = Human.rangify(info[package][addr])
            _LOG.info("%sInstances: %s", pfx1, instances)

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

    if args.package is not None:
        package = int(args.package)
    else:
        if not args.addrs:
            package = 0
        else:
            package = None

    tpmi = Tpmi.Tpmi(pman=pman)
    fdict = tpmi.get_fdict(args.fname)

    if package is None:
        packages = None
    else:
        packages = (package,)

    if not args.addrs:
        addrs = [tup[0] for tup in tpmi.iter_feature(args.fname)]
    else:
        addrs = Trivial.split_csv_line(args.addr, dedup=True)

    if args.register == "all":
        registers = list(fdict)
    else:
        Trivial.split_csv_line(args.registers, dedup=True)

    if args.instance == "all":
        instances = (tup[2] for tup in tpmi.iter_feature(args.fname, addrs=addrs,
                                                         packages=packages))
    else:
        Trivial.split_csv_line_int(args.registers, dedup=True, what="TPMI instance numbers")

    for addr in addrs:
        for instance in instances:
            for regname in registers:
                value = tpmi.read_register(args.fname, instance, regname, addr=addr,
                                        package=package)
                printed = False
                for fieldname, fieldinfo in fdict[regname]["fields"].items():
                    if args.bitfield not in ("all", fieldname):
                        continue

                    if not printed:
                        printed = True
                        _LOG.info("%s[%d]: 0x%x", regname, instance, value)

                    value = tpmi.read_register(args.fname, instance, regname, addr=addr,
                                            package=package, bfname=fieldname)
                    _LOG.info("  %s[%s]: %d", fieldname, fieldinfo["bits"], value)
                    _LOG.info("    %s", fieldinfo["desc"])
