
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#         Antti Laakso <antti.laakso@intel.com>

"""
This module provides API for printing properties.
"""

import sys
import logging
from pepclibs.helperlibs import ClassHelpers, Human, YAML
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = logging.getLogger()

class _PropsPrinter(ClassHelpers.SimpleCloseContext):
    """The base class for printing properties."""

    def _print(self, msg):
        """Print message 'msg'."""

        if self._fobj:
            self._fobj.write(msg)
        else:
            _LOG.info(msg)

    def _fmt_cpus(self, cpus):
        """Formats and returns a string describing CPU numbers in the 'cpus' list."""

        cpus_range = Human.rangify(cpus)
        if len(cpus) == 1:
            msg = f"CPU {cpus_range}"
        else:
            msg = f"CPUs {cpus_range}"

        allcpus = self._cpuinfo.get_cpus()
        if set(cpus) == set(allcpus):
            msg += " (all CPUs)"
        else:
            pkgs, rem_cpus = self._cpuinfo.cpus_div_packages(cpus)
            if pkgs and not rem_cpus:
                # CPUs in 'cpus' are actually the packages in 'pkgs'.
                pkgs_range = Human.rangify(pkgs)
                if len(pkgs) == 1:
                    msg += f" (package {pkgs_range})"
                else:
                    msg += f" (packages {pkgs_range})"

        return msg

    def _print_prop_human(self, prop, val, action=None, cpus=None, prefix=None):
        """Format and print a message about property 'prop' in the "human" format."""

        if cpus is None or (prop["sname"] == "global" and not prop["writable"]):
            sfx = ""
        else:
            cpus = self._fmt_cpus(cpus)
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
        self._print(msg)

    def _do_print_aggr_pinfo_human(self, aggr_pinfo, skip_unsupported=False, action=None,
                                   prefix=None):
        """A helper for '_print_aggr_pinfo_human()' implementing the printing part."""

        props = self._pobj.props

        printed = 0
        for pname, pinfo in aggr_pinfo.items():
            for key, kinfo in pinfo.items():
                for val, cpus in kinfo.items():
                    # Distinguish between properties and sub-properties.
                    if key in props:
                        if skip_unsupported and val is None:
                            continue
                        self._print_prop_human(props[pname], val, cpus=cpus, action=action,
                                               prefix=prefix)
                    else:
                        if val is None:
                            # Just skip unsupported sub-property instead of printing something like
                            # "Package C-state limit aliases: not supported on CPUs 0-11".
                            continue

                        # Print sub-properties with a prefix and exclude CPU information, because it
                        # is the same as in the (parent) property, which has already been printed.
                        prop = props[pname]["subprops"][key]
                        self._print_prop_human(prop, val, cpus=cpus, action=action, prefix=prefix)
                    printed += 1

        return printed

    def _print_aggr_pinfo_human(self, aggr_pinfo, group=False, skip_unsupported=False, action=None):
        """
        Print properties in the "human" format. The arguments are as follows.
          * aggr_pinfo - the aggregate properties information dictionary.
          * group - whether to group properties by the source (sysfs, MSR, etc) when printing.
          * skip_unsupported - same as in 'print_props()'.
          * action - same as in 'print_props()'.
        """

        grouped = {}
        if not group:
            prefix = None
            grouped = {None : aggr_pinfo}
        else:
            prefix = " - "
            for pname, info in aggr_pinfo.items():
                for source in self._pobj.props[pname]["mechanisms"]:
                    if source not in grouped:
                        grouped[source] = {pname : info}
                    else:
                        grouped[source][pname] = info

        printed = 0
        for source, pinfos in grouped.items():
            if source:
                self._print(f"Source: {self._pobj.mechanism_to_human(source)}")
            printed += self._do_print_aggr_pinfo_human(pinfos,
                                                       skip_unsupported=skip_unsupported,
                                                       action=action, prefix=prefix)
        return printed

    def _yaml_dump(self, info):
        """Dump dictionary 'info' in YAML format."""

        fobj = self._fobj
        if not fobj:
            fobj = sys.stdout

        YAML.dump(info, fobj)

    def _print_aggr_pinfo_yaml(self, aggr_pinfo, skip_unsupported=False):
        """Print the aggregate properties information in YAML format."""

        yaml_pinfo = {}

        for pinfo in aggr_pinfo.values():
            for key, kinfo in pinfo.items():
                for val, cpus in kinfo.items():
                    if val is None:
                        if skip_unsupported:
                            continue
                        val = "not supported"

                    if key not in yaml_pinfo:
                        yaml_pinfo[key] = []
                    yaml_pinfo[key].append({"value" : val, "cpus" : Human.rangify(cpus)})

        self._yaml_dump(yaml_pinfo)
        return len(yaml_pinfo)

    @staticmethod
    def _build_aggr_pinfo(pinfo_iter, spnames="all"):
        """
        Build the aggregate properties dictionary. The arguments are as follows.
          * pinfo_iter - an iterator yielding '(cpu, pinfo)' tuples, just like 'CStates.get_props()'
                         of 'ReqCState.get_cstates_info()' do.
          * spnames - names of sub-properties of the 'pname' property that should also be printed.
                      Value "all" will include all sub-properties and value 'None' won't include
                      any.

        The aggregate properties dictionary has the following format.

        { property1_name: { property1_name: { value1 : [ list of CPUs having value1],
                                                value2 : [ list of CPUs having value2],
                                                ... and so on of all values ...},
                            subprop1_name:  { value1 : [ list of CPUs having value1],
                                                value2 : [ list of CPUs having value2]
                                                ... and so on of all values ...},
                            ... and so on for all sub-properties ...},
            ... and so on for all properties ... }

            * property1_name - the first property name (e.g., 'pkg_cstate_limit').
            * subprop1_name - the first sub-property name (e.g., 'pkg_cstate_limit_lock').
            * value1, value2, etc - all the different values for the property/sub-property
                                    (e.g., 'True' or 'True')

        In other words, the aggregate dictionary mapping of property/sub-property values to the list
        of CPUs having these values.
        """

        aggr_pinfo = {}

        for cpu, pinfo in pinfo_iter:
            for pname in pinfo:
                if pname not in aggr_pinfo:
                    aggr_pinfo[pname] = {}
                for key, val in pinfo[pname].items():
                    if key != pname:
                        if spnames is None:
                            continue
                        if spnames != "all" and key not in spnames:
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

    def _normalize_pnames(self, pnames, skip_ro=False):
        """Validate property names in 'pnames' and return a normalized list."""

        if pnames == "all":
            pnames = list(self._pobj.props)
        else:
            for pname in pnames:
                if pname not in self._pobj.props:
                    raise Error(f"unknown property name '{pname}'")

        if not skip_ro:
            return pnames
        return [pname for pname in pnames if self._pobj.props[pname]["writable"]]

    def print_props(self, pnames="all", cpus="all", skip_ro=False, skip_unsupported=True,
                    action=None):
        """
        Read and print properties. The arguments are as follows.
          * pnames - names of the property to read and print (all properties by default).
          * cpus - CPU numbers to read and print the property for (all CPUs by default).
          * skip_unsupported - if 'True', unsupported properties are skipped. Otherwise a "property
                               is not supported" message is printed.
          * skip_ro - if 'False', read-only properties and sub-properties information will be
                      printed, otherwise they will be skipped.
          * action - an optional action word to include into the messages (nothing by default). For
                     example, if 'action' is "set to", the messages will be like "property <pname>
                     set to <value>". Applicable only to the "human" format.
        Returns the printed properties count.
        """

        group = pnames == "all"
        pnames = self._normalize_pnames(pnames, skip_ro=skip_ro)

        # All sub-properties are assumed to be read-only. Therefore, when read-only properties
        # should be skipped, set 'spnames' to 'None', which means "do not include sub-properties".
        spnames = None if skip_ro else "all"

        pinfo_iter = self._pobj.get_props(pnames, cpus=cpus)
        aggr_pinfo = self._build_aggr_pinfo(pinfo_iter, spnames=spnames)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group,
                                                skip_unsupported=skip_unsupported, action=action)
        return self._print_aggr_pinfo_yaml(aggr_pinfo, skip_unsupported=skip_unsupported)

    def __init__(self, pobj, cpuinfo, fobj=None, fmt="human"):
        """
        Initialize a class instance. The arguments are as follows.
          * obj - a 'PStates', 'CStates' or 'Power' object to print the properties for.
          * cpuinfo - a 'CPUInfo' object corresponding to the host the properties are read from.
          * fobj - a file object to print the output to (standard output by default).
          * fmt - the printing format.

        The following formats are supported.
          * human - a human-friendly, human-readable print format.
          * yaml - print in YAML format.
        """

        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._fobj = fobj
        self._fmt = fmt

        formats = {"human", "yaml"}
        if self._fmt not in formats:
            formats = ", ".join(formats)
            raise Error(f"unsupported format '{self._fmt}', supported formats are: {formats}")

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_fobj", "_cpuinfo", "_pobj"))

class PStatesPrinter(_PropsPrinter):
    """This class provides API for printing P-states information."""

class PowerPrinter(_PropsPrinter):
    """This class provides API for printing power information."""

class CStatesPrinter(_PropsPrinter):
    """This class provides API for printing C-states information."""

    def _adjust_aggr_pinfo_pcs_limit(self, aggr_pinfo, cpus):
        """
        The aggregate properties information dictionary 'aggr_pinfo' includes the 'pkg_cstate_limit'
        property. This property is read/write in case the corresponding MSR is unlocked, and it is
        R/O if the MSR is locked. The goal of this method is to remove all the "lock" CPUs from
        the 'pkg_cstate_limit' key of 'aggr_pinfo'.
        """

        pcsl_info = aggr_pinfo["pkg_cstate_limit"]["pkg_cstate_limit"]
        if set(pcsl_info) == { None }:
            # The 'pkg_cstate_limit' property is not supported, nothing to do.
            return aggr_pinfo

        locked_cpus = set()
        # Get all locked CPUs.
        for cpu, pinfo in self._pobj.get_props(("pkg_cstate_limit", ), cpus=cpus):
            if pinfo["pkg_cstate_limit"]["pkg_cstate_limit_lock"] == "on":
                locked_cpus.add(cpu)

        if not locked_cpus:
            # There are no locked CPUs, nothing to do.
            return aggr_pinfo

        if len(locked_cpus) == len(cpus):
            # All CPUs are locked, "pkg_cstate_limit" is considered read-only, and is removed.
            del aggr_pinfo["pkg_cstate_limit"]
            return aggr_pinfo

        new_pcsl_info = {}
        for key, _cpus in pcsl_info.items():
            new_cpus = []
            for cpu in _cpus:
                if cpu not in locked_cpus:
                    new_cpus.append(cpu)
            if new_cpus:
                new_pcsl_info[key] = new_cpus

        aggr_pinfo["pkg_cstate_limit"]["pkg_cstate_limit"] = new_pcsl_info
        return aggr_pinfo

    def _print_val_msg(self, val, name=None, cpus=None, prefix=None, suffix=None, action=None):
        """Format and print a message about 'name' and its value 'val'."""

        if cpus is None:
            sfx = ""
        else:
            cpus = self._fmt_cpus(cpus)
            sfx = f" for {cpus}"

        if suffix is not None:
            sfx = sfx + suffix

        if name is not None:
            pfx = f"{name}: "
        else:
            pfx = ""

        if action:
            pfx += f"{action} "

        msg = pfx
        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        elif cpus is not None:
            val = f"'{val}'"

        msg += f"{val}{sfx}"
        self._print(msg)

    def _print_aggr_rcsinfo_human(self, aggr_rcsinfo, action=None):
        """Print the aggregate C-states information in the "human" format."""

        printed = 0
        for csname, csinfo in aggr_rcsinfo.items():
            if "disable" not in csinfo:
                # Do not print the C-state if it's enabled/disabled status is unknown.
                continue

            printed += 1
            for val, cpus in csinfo["disable"].items():
                val = "off" if val else "on"
                self._print_val_msg(val, name=csname, cpus=cpus, action=action)

            for key, kinfo in csinfo.items():
                if key == "latency":
                    name = "expected latency"
                    suffix = " us"
                elif key == "residency":
                    name = "target residency"
                    suffix = " us"
                elif key == "desc":
                    name = "description"
                    suffix = None
                else:
                    continue

                for val, cpus in kinfo.items():
                    self._print_val_msg(val, name=name, prefix=" - ", suffix=suffix)

        return printed

    def _print_aggr_rcsinfo_yaml(self, aggr_rcsinfo):
        """Print the aggregate C-states information in YAML format."""

        yaml_rcsinfo = {}

        for csname, csinfo in aggr_rcsinfo.items():
            for key, kinfo in csinfo.items():
                for val, cpus in kinfo.items():
                    if key == "disable":
                        val = "off" if val else "on"

                    if csname not in yaml_rcsinfo:
                        yaml_rcsinfo[csname] = []

                    yaml_rcsinfo[csname].append({"value" : val, "cpus" : Human.rangify(cpus)})

        self._yaml_dump(yaml_rcsinfo)
        return len(yaml_rcsinfo)

    def print_props(self, pnames="all", cpus="all", skip_ro=False, skip_unsupported=True,
                    action=None):
        """
        Read and print properties. The arguments are the same as in '_PropsPrinter.print_props()'.
        """

        group = pnames == "all"
        pnames = self._normalize_pnames(pnames, skip_ro=skip_ro)

        # All sub-properties are assumed to be read-only. Therefore, when read-only properties
        # should be skipped, set 'spnames' to 'None', which means "do not include sub-properties".
        spnames = None if skip_ro else "all"

        pinfo_iter = self._pobj.get_props(pnames, cpus=cpus)
        aggr_pinfo = self._build_aggr_pinfo(pinfo_iter, spnames=spnames)

        if skip_ro and "pkg_cstate_limit" in aggr_pinfo:
            # Special case: the package C-state limit option is read-write in general, but if it is
            # locked, it is effectively read-only. Since 'skip_ro' is 'True', we need to adjust
            # 'aggr_pinfo'.
            aggr_pinfo = self._adjust_aggr_pinfo_pcs_limit(aggr_pinfo, cpus)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group,
                                                skip_unsupported=skip_unsupported, action=action)
        return self._print_aggr_pinfo_yaml(aggr_pinfo, skip_unsupported=skip_unsupported)

    def print_cstates(self, csnames="all", cpus="all", skip_ro=False, action=None):
        """
        Read and print information about requestable C-states. The arguments are as follows.
          * csnames - C-state names to print information about (all C-states by default).
          * cpus - CPU numbers to read and print C-state information for (all CPUs by default).
          * skip_ro - skip printing read-only information, print only modifiable information.
          * action - an optional action word to include into the messages (nothing by default). For
                     example, if 'action' is "set to", the messages will be like "property <pname>
                     set to <value>". Applicable only to the "human" format.
        Returns the printed requestable C-states count.
        """

        if skip_ro:
            spnames = {"disable"}
        else:
            spnames = {"disable", "latency", "residency", "desc"}

        csinfo_iter = self._pobj.get_cstates_info(csnames=csnames, cpus=cpus)

        try:
            aggr_rcsinfo = self._build_aggr_pinfo(csinfo_iter, spnames=spnames)
        except ErrorNotSupported as err:
            _LOG.warning(err)
            _LOG.info("C-states are not supported")
            return 0

        if self._fmt == "human":
            return self._print_aggr_rcsinfo_human(aggr_rcsinfo, action=action)

        return self._print_aggr_rcsinfo_yaml(aggr_rcsinfo)
