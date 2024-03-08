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

import sys
import logging
from pepclibs import Tpmi
from pepclibs.helperlibs import Human, Trivial, YAML
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

def _ls_long(fname, tpmi, prefix=""):
    """Print extra information about feature 'fname' (in case of the 'tpmi ls -l' command)."""

    # A dictionary with the info that will be printed.
    #   * first level key - package number.
    #   * second level key - PCI address.
    #   * regval - instance numbers.
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

def _tpmi_read_command_print(tpmi, info):
    """Print the 'tpmi read' commnad output from the pre-populated dictionary 'info'."""

    pfx = "- "
    nopfx = "  "
    for fname, feature_info in info.items():
        pfx_indent = 0
        _LOG.info("%sTPMI feature: %s", " " * pfx_indent + pfx, fname)

        fdict = tpmi.get_fdict(fname)
        for addr, addr_info in feature_info.items():
            pfx_indent = 2
            _LOG.info("%sPCI address: %s", " " * pfx_indent + pfx, addr)
            _LOG.info("%sPackage: %d", " " * pfx_indent + nopfx, addr_info["package"])

            for instance, instance_info in addr_info["instances"].items():
                pfx_indent = 4
                _LOG.info("%sInstance: %d", " " * pfx_indent + pfx, instance)

                for regname, reginfo in instance_info.items():
                    pfx_indent = 6
                    _LOG.info("%s%s: %#x", " " * pfx_indent + pfx, regname, reginfo["value"])

                    if "fields" not in reginfo:
                        continue

                    for bfname, bfval in reginfo["fields"].items():
                        bfinfo = fdict[regname]["fields"][bfname]
                        pfx_indent = 8
                        _LOG.info("%s%s[%s]: %d",
                                  " " * pfx_indent + pfx, bfname, bfinfo["bits"], bfval)

def tpmi_read_command(args, pman):
    """
    Implement the 'tpmi read' command. The arguments are as follows.
      * args - command line arguments.
      * pman - the process manager object that defines the target host.
    """

    if not args.registers and args.bfnames:
        raise Error("'--bfname' requires '--register' to be specified")

    tpmi = Tpmi.Tpmi(pman=pman)

    if args.fnames:
        fnames = Trivial.split_csv_line(args.fnames, dedup=True)
    else:
        fnames = [sdict["name"] for sdict in tpmi.get_known_features()]

    addrs = None
    if args.addrs:
        addrs = Trivial.split_csv_line(args.addrs, dedup=True)
        addrs = set(addrs)

    packages = None
    if args.packages:
        packages = Trivial.split_csv_line_int(args.packages, dedup=True, what="package numbers")

    instances = None
    if args.instances:
        instances = Trivial.split_csv_line_int(args.instances, dedup=True,
                                               what="TPMI instance numbers")

    regnames = None
    if args.registers:
        regnames = Trivial.split_csv_line(args.registers, dedup=True)

    bfnames = None
    if args.bfnames:
        bfnames = Trivial.split_csv_line(args.bfnames, dedup=True)

    # Prepare all the information to print in the 'info' dictionary.
    info = {}
    for fname in fnames:
        info[fname] = {}

        fdict = tpmi.get_fdict(fname)

        if not args.registers:
            # Read all registers except for the reserved ones.
            regnames = [regname for regname in fdict if not regname.startswith("RESERVED")]

        for addr, package, instance in tpmi.iter_feature(fname, addrs=addrs, packages=packages,
                                                         instances=instances):
            if addr not in info[fname]:
                info[fname][addr] = {"package": package, "instances": {}}

            assert instance not in info[fname][addr]["instances"]
            info[fname][addr]["instances"][instance] = {}

            for regname in regnames:
                regval = tpmi.read_register(fname, addr, instance, regname)

                assert regname not in info[fname][addr]["instances"][instance]
                bfinfo = {}
                reginfo = {"value": regval, "fields": bfinfo}
                info[fname][addr]["instances"][instance][regname] = reginfo

                if not args.bfnames:
                    bfnames = fdict[regname]["fields"]

                for bfname in bfnames:
                    if bfname.startswith("RESERVED"):
                        continue

                    bfval = tpmi.get_bitfield(regval, fname, regname, bfname)
                    bfinfo[bfname] = bfval

                if not bfinfo:
                    # No bit fields information, probably all of them are reserved. Delete the
                    # entire "fields" key so that it does not show up in the output.
                    del reginfo["fields"]

    if not info:
        raise Error("BUG: no matches")

    if args.yaml:
        YAML.dump(info, sys.stdout)
    else:
        _tpmi_read_command_print(tpmi, info)

def tpmi_write_command(args, pman):
    """
    Implements the 'tpmi write' command. Arguments are as follows.
      * args - command line arguments.
      * pman - process manager.
    """

    tpmi = Tpmi.Tpmi(pman=pman)

    addrs = None
    if args.addrs:
        addrs = Trivial.split_csv_line(args.addrs, dedup=True)

    packages = None
    if args.packages:
        packages = Trivial.split_csv_line_int(args.packages, dedup=True, what="package numbers")

    instances = None
    if args.instances:
        instances = Trivial.split_csv_line_int(args.instances, dedup=True,
                                               what="TPMI instance numbers")

    value = Trivial.str_to_int(args.value, what="value to write")

    if args.bfname:
        bfname_str = f", bit field '{args.bfname}'"
        val_str = f"{value}"
    else:
        bfname_str = ""
        val_str = f"{value:#x}"


    for addr, package, instance in tpmi.iter_feature(args.fname, addrs=addrs, packages=packages,
                                                     instances=instances):
        tpmi.write_register(value, args.fname, addr, instance, args.regname, bfname=args.bfname)

        _LOG.info("Wrote '%s' to TPMI register '%s'%s (feature '%s', device '%s', package %d, "
                  "instance %d)", val_str, args.regname, bfname_str, args.fname, addr, package,
                  instance)
