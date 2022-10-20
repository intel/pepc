# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
#  Authors: Antti Laakso <antti.laakso@intel.com>
#           Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module implements the 'PepcPCStates' class, which handles 'pepc' P-state and C-state commands.
"""

import logging
from pepctool import _PepcCommon
from pepclibs.msr import MSR
from pepclibs.helperlibs import ClassHelpers, Human

_LOG = logging.getLogger()

class PepcPCStates(ClassHelpers.SimpleCloseContext):
    """
    This class provides interface to set and print C-state and P-state properties.

    Public methods overview.
      * set multiple C-state or P-state properties for multiple CPUs: 'set_props()'.
      * print multiple C-state or P-state properties for multiple CPUs: 'print_props()'.
    """

    def _print_prop_msg(self, prop, val, action=None, cpus=None, prefix=None):
        """Format and print a message about a property 'prop'."""

        if cpus is None or (prop["sname"] == "global" and not prop["writable"]):
            sfx = ""
        else:
            cpus = _PepcCommon.fmt_cpus(cpus, self._cpuinfo)
            sfx = f" for {cpus}"

        msg = f"{prop['name']}: "

        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        else:
            unit = prop.get("unit")
            if unit:
                if val > 9999:
                    val = Human.largenum(val)
                val = f"{val}{unit}"
            if sfx:
                val = f"'{val}'"

        if action is not None:
            msg += f"{action} "

        msg += f"{val}{sfx}"
        _LOG.info(msg)

    def _print_aggr_props(self, aggr_pinfo, skip_unsupported=False, action=None):
        """Print the aggregate C-state or P-state properties information."""

        props = self._pcobj.props

        for pname in aggr_pinfo:
            for key, kinfo in aggr_pinfo[pname].items():
                for val, cpus in kinfo.items():
                    # Distinguish between properties and sub-properties.
                    if key in props:
                        if skip_unsupported and val is None:
                            continue
                        self._print_prop_msg(props[pname], val, cpus=cpus, action=action)
                    else:
                        if val is None:
                            # Just skip unsupported sub-property instead of printing something like
                            # "Package C-state limit aliases: not supported on CPUs 0-11".
                            continue

                        # Print sub-properties with a prefix and exclude CPU information, because it
                        # is the same as in the (parent) property, which has already been printed.
                        prop = props[pname]["subprops"][key]
                        self._print_prop_msg(prop, val, cpus=cpus, action=action)

    def _get_aggr_pinfo(self, props, cpus):
        """Read properties 'props' and build and return aggregated property dictionary."""

        pinfo_iter = self._pcobj.get_props(props, cpus=cpus)
        return _PepcCommon.build_aggregate_pinfo(pinfo_iter)

    def set_props(self, props, cpus):
        """
        Set multiple properties 'props' for multiple CPUs 'cpus'. The arguments are as follows.
          * props - A dictionary with property names as keys and property values as values.
          * cpus - list of CPU numbers to set the properties for.
        """

        self._pcobj.set_props(props, cpus)
        aggr_pinfo = self._get_aggr_pinfo(props, cpus)
        self._print_aggr_props(aggr_pinfo, skip_unsupported=True, action="set to")

    def print_props(self, pnames, cpus, skip_unsupported=False):
        """
        Read and print values of multiple properties for multiple CPUs. The argument are as follows.
          * pnames - property names as a list of strings. For property names, see 'PROPS' in
                     'PStates' and 'CStates' modules.
          * cpus - list of CPU numbers to print the property values for.
          * skip_unsupported - if 'True', do not print unsupported values.
        """

        aggr_pinfo = self._get_aggr_pinfo(pnames, cpus)
        self._print_aggr_props(aggr_pinfo, skip_unsupported=skip_unsupported)

    def __init__(self, pcobj, cpuinfo):
        """
        The class constructor. The arguments are as follows.
          * pcobj - the 'CStates' or 'PStates' object.
          * cpuinfo - the 'CPUInfo' object.
        """

        self._pcobj = pcobj
        self._cpuinfo = cpuinfo

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, unref_attrs=("_pcobj", "_cpuinfo"))

class PepcCStates(PepcPCStates):
    """Class for handling the 'pepc cstates' options."""

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo)

        return self._msr

    def _fmt_csnames(self, csnames): # pylint: disable=no-self-use
        """Formats and returns the C-states list string, which can be used in messages."""

        if csnames == "all":
            msg = "all C-states"
        else:
            if len(csnames) == 1:
                msg = "C-state "
            else:
                msg = "C-states "
            msg += ",".join(csnames)

        return msg

    def _print_aggr_cstates_info(self, aggr_csinfo):
        """Prints aggregated requestable C-states information."""

        for csname, csinfo in aggr_csinfo.items():
            for key, kinfo in csinfo.items():
                for val, val_cpus in kinfo.items():
                    if key == "disable":
                        val = "off" if val else "on"
                        _PepcCommon.print_val_msg(val, self._cpuinfo, name=csname, cpus=val_cpus)
                    else:
                        if key == "latency":
                            name = "expected latency"
                        elif key == "residency":
                            name = "target residency"

                        # The first line starts with C-state name, align the second line nicely
                        # using the prefix. The end result is expected to be like this:
                        #
                        # POLL: 'on' for CPUs 0-15
                        # POLL: 'off' for CPUs 16-31
                        #       - expected latency: '0' us
                        prefix = " " * (len(csname) + 2) + "- "
                        suffix = " us"
                        _PepcCommon.print_val_msg(val, self._cpuinfo, name=name, prefix=prefix,
                                                  suffix=suffix)

    def handle_enable_disable_opts(self, opts, cpus):
        """Handle the '--enable' and '--disable' options of the 'cstates config' command."""

        print_cstates = False

        for optname, optval in opts.items():
            if not optval:
                # No value means that we should print the C-states information.
                print_cstates = True
                continue

            method = getattr(self._pcobj, f"{optname}_cstates")
            toggled = method(csnames=optval, cpus=cpus)

            # The 'toggled' dictionary is indexed with CPU number. But we want to print a single
            # line for all CPU numbers that have the same toggled C-states list. Build a "reversed"
            # version of the 'toggled' dictionary for these purposes.
            revdict = {}
            for cpu, csinfo in toggled.items():
                key = ",".join(csinfo["csnames"])
                if key not in revdict:
                    revdict[key] = []
                revdict[key].append(cpu)

            for cstnames, cpunums in revdict.items():
                cstnames = cstnames.split(",")
                _LOG.info("%sd %s on %s", optname.title(), self._fmt_csnames(cstnames),
                                          _PepcCommon.fmt_cpus(cpunums, self._cpuinfo))

        if print_cstates:
            csinfo_iter = self._pcobj.get_cstates_info(csnames="all", cpus=cpus)
            aggr_csinfo = _PepcCommon.build_aggregate_pinfo(csinfo_iter, sprops={"disable"})
            self._print_aggr_cstates_info(aggr_csinfo)

    def print_requestable_cstates_info(self, csnames, cpus):
        """Prints requestable C-states information."""

        csinfo_iter = self._pcobj.get_cstates_info(csnames=csnames, cpus=cpus)
        sprops = {"disable", "latency", "residency"}
        aggr_csinfo = _PepcCommon.build_aggregate_pinfo(csinfo_iter, sprops=sprops)
        self._print_aggr_cstates_info(aggr_csinfo)

    def set_props(self, props, cpus):
        """
        Same as 'set_props()' in PepcPCStates, and will make use of caching feature of the 'MSR'
        module.
        """

        self._get_msr().start_transaction()
        super().set_props(props, cpus)
        # Commit the transaction. This will flush all the change MSRs (if there were any).
        self._get_msr().commit_transaction()

    def __init__(self, pman, csobj, cpuinfo, msr=None):
        """
        The class constructor. The 'csobj' and 'cpuinfo' are same as in '_PepcPCStates.PepcPCState',
        and other arguments are as follows.
          * pman - the process manager object that defines the target system.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        super().__init__(csobj, cpuinfo)

        self._pman = pman
        self._msr = msr

        self._close_msr = msr is None

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_msr"), unref_attrs=("_pman"))
