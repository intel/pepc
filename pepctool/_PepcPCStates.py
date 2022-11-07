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
from pepclibs.helperlibs import ClassHelpers, Human, YAML
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

class _PepcYaml():
    """
    This is a helper class for reading and writing pepc pstates and cstates information to YAML
    file.
    """

    def save(self, props, path): # pylint: disable=no-self-use
        """write aggregated properties to YAML -file."""

        try:
            YAML.dump(props, path)
        except Error as err:
            raise Error(f"failed to save properties to path: '{path}'\n{err}") from None

class PepcPCStates(ClassHelpers.SimpleCloseContext):
    """
    This class provides interface to set and print C-state and P-state properties.

    Public methods overview.
      * set multiple C-state or P-state properties for multiple CPUs: 'set_and_print_props()'.
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

    def _build_aggregate_pinfo(self, pinfo_iter, sprops="all"): # pylint: disable=no-self-use
        """
        Build the aggregated properties dictionary for properties in the 'pinfo_iter' iterator. The
        iterator must provide the (cpu, pinfo) tuples, just like 'CStates.get_props()' or
        'ReqCState.get_cstates_info()' do.

        The dictionary has the following format.

        { property1_name: { property1_name: { value1 : [ list of CPUs having value1],
                                              value2 : [ list of CPUs having value2],
                                              ... and so on of all values ...},
                            subprop1_name:  { value1 : [ list of CPUs having value1],
                                              value2 : [ list of CPUs having value2]
                                              ... and so on of all values ...},
                            ... and so on for all sub-properties ...},
          ... and so on for all properties ... }

          * property1_name - the first property name (e.g., 'pkg_cstate_limit').
          * subprop1_name - the first sub-property name (e.g., 'pkg_cstate_limit_locked').
          * value1, value2, etc - are all the different values for the property/sub-property (e.g.,
                                  'True' or 'True')

        In other words, the aggregate dictionary mapping of property/sub-property values to the list
        of CPUs having these values.

        The 'sprops' argument can be used to limit the sub-properties to only the names in 'sprops'.
        The 'sprops' value "all" will include all sub-properties and 'None' doesn't include any.
        """

        aggr_pinfo = {}

        for cpu, pinfo in pinfo_iter:
            for pname in pinfo:
                if pname not in aggr_pinfo:
                    aggr_pinfo[pname] = {}
                for key, val in pinfo[pname].items():
                    if key != pname:
                        if sprops is None:
                            continue
                        if sprops != "all" and key not in sprops:
                            continue

                    # Make sure 'val' is "hashable" and can be used as a dictionary key.
                    if isinstance(val, list):
                        if not val:
                            continue
                        val = ", ".join(val)
                    elif isinstance(val, dict):
                        if not val:
                            continue
                        val = ", ".join(f"{k}={v}" for k, v in val.items())

                    if key not in aggr_pinfo[pname]:
                        aggr_pinfo[pname][key] = {}
                    if val not in aggr_pinfo[pname][key]:
                        aggr_pinfo[pname][key][val] = []

                    aggr_pinfo[pname][key][val].append(cpu)

        return aggr_pinfo

    def _print_aggr_props(self, skip_unsupported=False, action=None):
        """Print the aggregate C-state or P-state properties information."""

        props = self._pcobj.props

        for pname, pinfo in self.aggr_props.items():
            for key, kinfo in pinfo.items():
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

    def _print_props(self, pnames, cpus, skip_unsupported=False, sprops="all", action=None):
        """Implements the 'print_props()'."""

        pinfo_iter = self._pcobj.get_props(pnames, cpus=cpus)
        self.aggr_props = self._build_aggregate_pinfo(pinfo_iter, sprops=sprops)
        self._print_aggr_props(skip_unsupported=skip_unsupported, action=action)

    def _get_props_for_saving(self):
        """
        Collect writable properties and return them as a dictionary suitable for saving in YAML
        format. The format is as follows.

        { property1_name: {value1 : range of CPUs having value1},
                          {value2 : range of CPUs having value2},
                           ...,
          property2_name: {value1 : range of CPUs having value1}
                           ...,
          ... and so on of all properties ...}

        The range of CPUs is output of 'Human.rangify()'.
        """

        props = self._pcobj.props
        result = {}

        for pname, pinfo in self.aggr_props.items():
            for key, kinfo in pinfo.items():
                writable = False
                if key in props:
                    writable = props[key].get("writable")
                elif "subprops" in props[pname]:
                    writable = props[pname]["subprops"].get("writable")

                if not writable:
                    continue

                result[key] = []
                for val, cpus in kinfo.items():
                    result[key].append({"value" : val, "cpus" : Human.rangify(cpus)})

        return result

    def print_props(self, pnames, cpus, skip_unsupported=False):
        """
        Read and print values of multiple properties for multiple CPUs. The argument are as follows.
          * pnames - property names as a list of strings. For property names, see 'PROPS' in
                     'PStates' and 'CStates' modules.
          * cpus - list of CPU numbers to print the property values for.
          * skip_unsupported - if 'True', do not print unsupported values.
        """
        self._print_props(pnames, cpus, skip_unsupported=skip_unsupported)

    def save_props(self, pnames, cpus, path):
        """
        Read values of multiple properties for multiple CPUs, and save them to file 'path'. The
        'pnames, and 'cpus' arguments are same as in 'print_props()'.'
        """

        pinfo_iter = self._pcobj.get_props(pnames, cpus=cpus)
        self.aggr_props = self._build_aggregate_pinfo(pinfo_iter, sprops="all")
        props = self._get_props_for_saving()
        self._yaml.save(props, path)

    def set_and_print_props(self, props, cpus):
        """
        Set and print multiple properties 'props' for multiple CPUs 'cpus'. The arguments are as
        follows.
          * props - A dictionary with property names as keys and property values as values.
          * cpus - list of CPU numbers to set the properties for.
        """

        self._pcobj.set_props(props, cpus)
        self._print_props(props, cpus, skip_unsupported=True, sprops=None, action="set to")

    def __init__(self, pman, pcobj, cpuinfo):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target system.
          * pcobj - the 'CStates' or 'PStates' object.
          * cpuinfo - the 'CPUInfo' object.
        """

        self._pman = pman
        self._pcobj = pcobj
        self._cpuinfo = cpuinfo

        self.aggr_props = {}
        self._yaml = _PepcYaml()

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, unref_attrs=("_pman", "_pcobj", "_cpuinfo"))

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

    def _print_aggr_cstates_info(self):
        """Prints aggregated requestable C-states information."""

        for csname, csinfo in self.aggr_rcsinfo.items():
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
            self.aggr_rcsinfo = self._build_aggregate_pinfo(csinfo_iter, sprops={"disable"})
            self._print_aggr_cstates_info()


    def print_cstates_info(self, csnames, pnames, cpus):
        """
        Print C-states information. The arguments are as follows.
          * csnames - list of requestable C-states.
          * pnames - list of C-state property names.
          * cpus - list of CPU numbers to print the properties for.
        """

        csinfo_iter = self._pcobj.get_cstates_info(csnames=csnames, cpus=cpus)
        sprops = {"disable", "latency", "residency"}
        self.aggr_rcsinfo = self._build_aggregate_pinfo(csinfo_iter, sprops=sprops)
        self._print_aggr_cstates_info()

        pinfo_iter = self._pcobj.get_props(pnames, cpus=cpus)
        self.aggr_props = self._build_aggregate_pinfo(pinfo_iter)
        self._print_aggr_props(skip_unsupported=True)

    def set_and_print_props(self, props, cpus):
        """
        Same as 'set_and_print_props()' in PepcPCStates, and will make use of caching feature of the
        'MSR' module.
        """

        self._get_msr().start_transaction()
        super().set_and_print_props(props, cpus)
        # Commit the transaction. This will flush all the change MSRs (if there were any).
        self._get_msr().commit_transaction()

    def __init__(self, pman, csobj, cpuinfo, msr=None):
        """
        The class constructor. The other except the 'msr' argument are same as in
        '_PepcPCStates.PepcPCState'. The 'msr' argument is as follows.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
        """

        super().__init__(pman, csobj, cpuinfo)

        self._msr = msr
        self._close_msr = msr is None

        self.aggr_rcsinfo = {}

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_msr"))

        super().close()
