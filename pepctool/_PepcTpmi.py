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
from pepclibs.helperlibs import Human
from pepctool import _PepcCommon

_LOG = logging.getLogger()

def _parse_tpmi_args(args):
    """Parse common TPMI command line arguments."""

    if args.register == "all":
        registers = "all"
    else:
        registers = args.register.split(",")

    if args.instance == "all":
        instances = "all"
    else:
        instances = _PepcCommon.parse_cpus_string(args.instance)

    if args.package is not None:
        package = int(args.package)
    else:
        if not args.addr:
            package = 0
        else:
            package = None

    return (args.addr, package, args.fname, instances, registers, args.bitfield)

def _ls_long(args, fname, tpmi_obj, prefix=""):
    """Print extra information about feature 'fname' (in case of the 'tpmi ls -l' command)."""

    # A dictionary with the info that will be printed.
    #   * first level key - package number.
    #   * second level key - PCI address.
    #   * value - instance numbers.
    info = {}

    for addr, package, instance in tpmi_obj.iter_feature(fname):
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

    tpmi_obj = Tpmi.Tpmi(pman)

    sdicts = tpmi_obj.get_known_features()
    if not sdicts:
        _LOG.info("Not supported TPMI features found")
    else:
        _LOG.info("Supported TPMI features")
        for sdict in sdicts:
            _LOG.info(" - %s: %s", sdict["name"], sdict["desc"].strip())
            if args.long:
                _ls_long(args, sdict["name"], tpmi_obj, prefix="   ")

    if args.all:
        fnames = tpmi_obj.get_unknown_features()
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

    tpmi_obj = Tpmi.Tpmi(pman=pman)

    addr, package, fname, instances, registers, bfname = _parse_tpmi_args(args)

    fdict = tpmi_obj.get_fdict(fname)

    if registers == "all":
        registers = fdict

    if instances == "all":
        instances = (tup[2] for tup in tpmi_obj.iter_feature(fname, addr=addr, package=package))

    for instance in instances:
        for regname in registers:
            value = tpmi_obj.read_register(fname, instance, regname, addr=addr, package=package)
            printed = False
            for fieldname, fieldinfo in fdict[regname]["fields"].items():
                if bfname not in ("all", fieldname):
                    continue

                if not printed:
                    printed = True
                    _LOG.info("%s[%d]: 0x%x", regname, instance, value)

                value = tpmi_obj.read_register(fname, instance, regname, addr=addr,
                                               package=package, bfname=fieldname)
                _LOG.info("  %s[%s]: %d", fieldname, fieldinfo["bits"], value)
                _LOG.info("    %s", fieldinfo["desc"])
