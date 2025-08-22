# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>

"""
Provides API for changing properties.
"""

from pepctool import _PepcCommon
from pepclibs.helperlibs import ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorBadOrder

class _PropsSetter(ClassHelpers.SimpleCloseContext):
    """Provide API for changing properties."""

    def _set_prop_sname(self, spinfo, pname, optar, mnames, mnames_info):
        """Set property 'pname'."""

        if pname not in spinfo:
            return

        mname = _PepcCommon.set_prop_sname(self._pobj, pname, optar, spinfo[pname]["val"],
                                           mnames=mnames)
        del spinfo[pname]
        mnames_info[pname] = mname

    def set_props(self, spinfo, optar, mnames=None):
        """
        Set properties for CPUs 'cpus'. The arguments are as follows.
          * spinfo - a dictionary defining names of the properties to set and the values to set the
                     properties to.
          * optar - an '_OpTarget.OpTarget()' object representing the CPUs, cores, modules, etc to
                    set the properties for.
          * mnames - list of mechanism names allowed to be used for setting properties (default -
                     all mechanisms are allowed).
        """

        # Remember the mechanism used for every option.
        mnames_info = {}
        # '_set_props()' needs to modify the dictionary, so create a copy for that.
        spinfo_copy = spinfo.copy()

        # Translate values without unit to the default units.
        for pname, pname_info in spinfo.items():
            if "default_unit" not in pname_info:
                continue

            try:
                val = Trivial.str_to_num(pname_info["val"])
            except Error:
                # Not a number, which means there is unit specified.
                continue

            # Append the default unit.
            spinfo_copy[pname]["val"] = str(val) + pname_info["default_unit"]

        if self._sysfs_io:
            self._sysfs_io.start_transaction()
        if self._msr:
            self._msr.start_transaction()

        for pname in list(spinfo):
            self._set_prop_sname(spinfo_copy, pname, optar, mnames, mnames_info)

        if self._msr:
            self._msr.commit_transaction()
        if self._sysfs_io:
            self._sysfs_io.commit_transaction()

        if self._pcsprint:
            for pname in spinfo:
                mnames = (mnames_info[pname], )
                self._pcsprint.print_props((pname,), optar, mnames=mnames, skip_ro=True,
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

                for key in ("value",):
                    if key not in yval:
                        raise Error(f"did not find key '{key}' in the '{ykey}' sub-dictionary")

                sname_keys = ("CPU", "die", "package")
                found = []
                for key in sname_keys:
                    if key in yval:
                        found.append(key)

                if len(found) == 0:
                    raise Error(f"did not find one of the following keys in the '{ykey}' "
                                f"sub-dictionary: {', '.join(sname_keys)}")
                if len(found) > 1:
                    raise Error(f"found multiple scope name keys in the '{ykey}' sub-dictionary, "
                                f"expected only one of {', '.join(sname_keys)}")

    @staticmethod
    def _set_prop(pobj, pname, sname, val, nums):
        """Set property 'pname' using the method suitable for scope 'sname'."""

        if sname == "CPU":
            pobj.set_prop_cpus(pname, val, nums)
        elif sname == "die":
            pobj.set_prop_dies(pname, val, nums)
        elif sname == "package":
            pobj.set_prop_packages(pname, val, nums)

    def __init__(self, pman, pobj, cpuinfo, pcsprint, msr=None, sysfs_io=None):
        """
        Initialize a class instance. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * pobj - a properties object (e.g., 'PStates') to print the properties for.
          * cpuinfo - a 'CPUInfo' object corresponding to the host the properties are read from.
          * pcsprint - a 'PStatesPrinter' or 'CStatesPrinter' class instance to use for reading and
                       printing the properties after they were set.
          * msr - an optional 'MSR.MSR()' object which will be used for transactions.
          * sysfs_io - an optional '_SysfsIO.SysfsIO()' object which will be used for transactions.
        """

        self._pman = pman
        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._pcsprint = pcsprint
        self._msr = msr
        self._sysfs_io = sysfs_io

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_sysfs_io", "_msr", "_pcsprint", "_cpuinfo", "_pobj",
                                              "_pman"))

class PStatesSetter(_PropsSetter):
    """Provide API for changing P-states properties."""

    def _set_prop_sname(self, spinfo, pname, optar, mnames, mnames_info):
        """Set property 'pname' and handle frequency properties ordering."""

        try:
            super()._set_prop_sname(spinfo, pname, optar, mnames, mnames_info)
            return
        except ErrorBadOrder as err:
            if pname not in {"min_freq", "max_freq", "min_uncore_freq", "max_uncore_freq"}:
                raise

            # Setting frequencies may be tricky because of the ordering constraints. Here is an
            # example illustrating why order matters. Suppose current min. and max. frequencies and
            # new min. and max. frequencies are as follows:
            #  ---- Cur. Min --- Cur. Max -------- New Min --- New Max ---------->
            #
            # Where the dotted line represents the horizontal frequency axis. Setting min. frequency
            # before max. frequency leads to a failure (more precisely, the 'ErrorBadOrder'
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
                mname = _PepcCommon.set_prop_sname(self._pobj, pnm, optar, spinfo[pnm]["val"],
                                                   mnames=mnames)
                del spinfo[pnm]
                mnames_info[pnm] = mname

class PMQoSSetter(_PropsSetter):
    """Provides API for changing PM QoS properties."""

class CStatesSetter(_PropsSetter):
    """Provide API for changing C-states properties."""

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
