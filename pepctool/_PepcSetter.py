# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#         Antti Laakso <antti.laakso@intel.com>

"""
This module provides API for changing P-state and C-state properties.
"""

import sys
import contextlib
from pepctool import _PepcCommon
from pepclibs.helperlibs import ClassHelpers, YAML
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.PStates import ErrorFreqOrder

class _PropsSetter(ClassHelpers.SimpleCloseContext):
    """This class provides API for changing P-state and C-state properties."""

    def _set_prop_cpus(self, spinfo, pname, cpus, mnames, mnames_info):
        """Set property 'pname' and handle frequency properties ordering."""

        if pname not in spinfo:
            return

        try:
            mname = self._pobj.set_prop_cpus(pname, spinfo[pname], cpus=cpus, mnames=mnames)
            del spinfo[pname]
            mnames_info[pname] = mname
            return
        except ErrorFreqOrder as err:
            if pname not in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
                raise

            # Setting frequencies may be tricky because of the ordering constraints. Here is an
            # example illustrating why order matters. Suppose current min. and max. frequencies and
            # new min. and max. frequencies are as follows:
            #  ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #
            # Where the dotted line represents the horizontal frequency axis. Setting min. frequency
            # before max. frequency leads to a failure (more precisely, the 'ErrorFreqOrder'
            # exception). Indeed, at step #2 below, current minimum frequency would be set to a
            # value higher that current maximum frequency.
            #  1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #  2. ----------------- Cur. Max -------- Cur. Min -- New Max ----------> FAIL!
            #
            # To handle this situation, max. frequency should be set first.
            #  1. ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #  2. ---- Cur. Min --------------------- New Min --- Cur. Max --------->
            #  3. ----------------------------------- Cur. Min -- Cur. Max --------->
            #
            # Therefore, if both min. and max. frequencies should be changed, try changing them in
            # different order.

            freq_pname = pname
            if pname.startswith("min"):
                # Trying to set minimum frequency to a value higher than currently configured
                # maximum frequency.
                other_freq_pname = pname.replace("min", "max")
            elif pname.startswith("max"):
                other_freq_pname = pname.replace("max", "mim")
            else:
                raise Error(f"BUG: unexpected property {pname}") from err

            if other_freq_pname not in spinfo:
                raise

            for pnm in (other_freq_pname, freq_pname):
                mname = self._pobj.set_prop_cpus(pnm, spinfo[pnm], cpus=cpus, mnames=mnames)
                del spinfo[pnm]
                mnames_info[pnm] = mname

    def set_props(self, spinfo, cpus="all", mnames=None):
        """
        Set properties for CPUs 'cpus'. The arguments are as follows.
          * spinfo - a dictionary defining names of the properties to set and the values to set the
                     properties to.
          * cpus - CPU numbers to set the property for (all CPUs by default).
          * mnames - list of mechanism names allowed to be used for setting properties (default -
                     all mechanisms are allowed).
        """

        if self._msr:
            self._msr.start_transaction()

        # Remember the mechanism used for every option.
        mnames_info = {}
        # '_set_props()' needs to modify the dictionary, so create a copy for that.
        spinfo_copy = spinfo.copy()

        for pname in list(spinfo):
            self._set_prop_cpus(spinfo_copy, pname, cpus, mnames, mnames_info)

        if self._msr:
            self._msr.commit_transaction()

        if self._pcsprint:
            for pname in spinfo:
                mnames = (mnames_info[pname], )
                self._pcsprint.print_props((pname,), cpus, mnames=mnames, skip_ro=True,
                                           skip_unsupported=False, action="set to")

    @staticmethod
    def _validate_loaded_data(ydict, known_ykeys):
        """Validate data loaded from a YAML file into a 'ydict' dictionary."""

        if not isinstance(ydict, dict):
            raise Error(f"expected dictionary, got: '{type(ydict)}'")

        for ykey, yvals in ydict.items():
            if not isinstance(yvals, list):
                raise Error(f"expected 'list' type values for the key '{ykey}', got: "
                            f"'{type(yvals)}'")

            if ykey not in known_ykeys:
                all_pnames = ", ".join(known_ykeys)
                raise Error(f"unknown key '{ykey}', known keys are:\n  {all_pnames}")

            for yval in yvals:
                if not isinstance(yval, dict):
                    raise Error(f"expected list of dictionaries for the key '{ykey}', got list "
                                f"of: '{type(yval)}'")

                for key in ("value", "cpus"):
                    if key not in yval:
                        raise Error(f"did not find key '{key}' in the '{ykey}' sub-dictionary")

    def _restore_prop(self, pname, val, cpus):
        """Restore property 'pname' to value 'val' for CPUs 'cpus."""

        try:
            self._pobj.set_prop_cpus(pname, val, cpus=cpus)
            return
        except ErrorFreqOrder:
            if pname not in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
                raise

        # Setting frequency may be tricky because there are ordering constraints.
        if pname in {"min_freq", "max_freq"}:
            min_freq_pname = "min_freq"
            max_freq_pname = "max_freq"
        elif pname in ("min_uncore_freq", "max_uncore_freq"):
            min_freq_pname = "min_uncore_freq"
            max_freq_pname = "max_uncore_freq"
        else:
            self._pobj.set_prop_cpus(pname, val, cpus=cpus)
            return

        if pname.startswith("min_"):
            self._pobj.set_prop_cpus(max_freq_pname, "max", cpus=cpus)
            self._pobj.set_prop_cpus(min_freq_pname, val, cpus=cpus)
        elif pname.startswith("max_"):
            self._pobj.set_prop_cpus(min_freq_pname, "min", cpus=cpus)
            self._pobj.set_prop_cpus(max_freq_pname, val, cpus=cpus)

    def _restore_props(self, ydict):
        """Restore properties from a loaded YAML file and represented by 'ydict'."""

        if self._msr:
            self._msr.start_transaction()

        for pname, pinfos in ydict.items():
            for pinfo in pinfos:
                cpus = _PepcCommon.parse_cpus_string(pinfo["cpus"])
                self._restore_prop(pname, pinfo["value"], cpus)
                if self._pcsprint:
                    self._pcsprint.print_props((pname,), cpus, skip_ro=True, skip_unsupported=False,
                                               action="restored to")

        if self._msr:
            self._msr.commit_transaction()

    def __init__(self, pobj, cpuinfo, pcsprint, msr=None):
        """
        Initialize a class instance. The arguments are as follows.
          * pobj - a properties object (e.g., 'PStates') to print the properties for.
          * cpuinfo - a 'CPUInfo' object corresponding to the host the properties are read from.
          * pcsprint - a 'PStatesPrinter' or 'CStatesPrinter' class instance to use for reading and
                       printing the properties after they were set.
          * msr - an optional 'MSR.MSR()' object which will be used for transactions.
        """

        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._pcsprint = pcsprint
        self._msr = msr

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_msr", "_pcsprint", "_cpuinfo", "_pobj"))

class PStatesSetter(_PropsSetter):
    """This class provides API for changing P-states properties."""

    def restore(self, infile):
        """
        Load and set properties from a YAML file. The arguments are as follows:
          * infile - path to the properties YAML file ("-" means standard input).
        """

        if infile == "-":
            infile = sys.stdin

        ydict = YAML.load(infile)

        known_ykeys = set(self._pobj.props)
        self._validate_loaded_data(ydict, known_ykeys)

        self._restore_props(ydict)

class PowerSetter(_PropsSetter):
    """This class provides API for changing power settings."""

    def restore(self, infile):
        """
        Load and set properties from a YAML file. The arguments are as follows:
          * infile - path to the properties YAML file ("-" means standard input).
        """

        if infile == "-":
            infile = sys.stdin

        ydict = YAML.load(infile)

        known_ykeys = set(self._pobj.props)
        self._validate_loaded_data(ydict, known_ykeys)

        self._restore_props(ydict)

class CStatesSetter(_PropsSetter):
    """This class provides API for changing P-states properties."""

    def set_cstates(self, csnames="all", cpus="all", enable=True, mnames=None):
        """
        Enable or disable requestable C-states. The arguments are as follows.
          * csnames - C-state names to enable or disable (all C-states by default).
          * cpus - CPU numbers enable/disable C-states for (all CPUs by default).
          * enable - if 'True', enable C-states in 'csnames', otherwise disable them.
          * mnames - list of mechanism names allowed to be used for setting properties (default -
                     all mechanisms are allowed).
        """

        # pylint: disable=unused-argument
        if enable:
            self._pobj.enable_cstates(csnames=csnames, cpus=cpus)
        else:
            self._pobj.disable_cstates(csnames=csnames, cpus=cpus)

        self._pcsprint.print_cstates(csnames=csnames, cpus=cpus, skip_ro=True, action="set to")

    def _restore_cstates(self, ydict):
        """
        Restore C-states on/off status using information loaded from a YAML file and represented by
        the 'ydict' dictionary.
        """

        for csname, yvals in ydict.items():
            for yval in yvals:
                cpus = _PepcCommon.parse_cpus_string(yval["cpus"])
                value = yval["value"]
                if value == "on":
                    self._pobj.enable_cstates(csname, cpus=cpus)
                elif value == "off":
                    self._pobj.disable_cstates(csname, cpus=cpus)
                else:
                    raise Error(f"bad C-state {csname} on/off status value {value}, should be 'on' "
                                f"or 'off'")

                self._pcsprint.print_cstates(csnames=(csname,), cpus=cpus, skip_ro=True,
                                             action="set to")

    def restore(self, infile):
        """
        Load and set C-state settings and properties from a YAML file. The arguments are as follows:
          * infile - path to the properties YAML file ("-" means standard input).
        """

        csnames = set()
        with contextlib.suppress(ErrorNotSupported):
            for _, csinfo in self._pobj.get_cstates_info(csnames="all", cpus="all"):
                for csname in csinfo:
                    csnames.add(csname)

        if infile == "-":
            infile = sys.stdin

        ydict = YAML.load(infile)

        known_ykeys = set(self._pobj.props)
        known_ykeys.update(csnames)
        self._validate_loaded_data(ydict, known_ykeys)

        # Separate out C-states and properties information from 'ydict'.
        props_ydict = {}
        cs_ydict = {}
        for ykey, yval in ydict.items():
            if ykey in csnames:
                cs_ydict[ykey] = yval
            else:
                props_ydict[ykey] = yval

        self._restore_cstates(cs_ydict)
        self._restore_props(props_ydict)
