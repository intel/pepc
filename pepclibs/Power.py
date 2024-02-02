# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module provides API for managing platform settings related to power.
"""

from pepclibs import _PropsClassBase
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed

# Make the exception class be available for users.
from pepclibs._PropsClassBase import ErrorUsePerCPU # pylint: disable=unused-import

# This dictionary describes the CPU properties this module supports.
#
# While this dictionary is user-visible and can be used, it is not recommended, because it is not
# complete. This dictionary is extended by 'Power' objects. Use the full dictionary via
# 'Power.props'.
PROPS = {
    "tdp" : {
        "name" : "TDP",
        "unit" : "W",
        "type" : "float",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "ppl1" : {
        "name" : "RAPL PPL1",
        "unit" : "W",
        "type" : "float",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl1_enable" : {
        "name" : "RAPL PPL1",
        "type" : "bool",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl1_clamp" : {
        "name" : "RAPL PPL1 clamping",
        "type" : "bool",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl1_window" : {
        "name" : "RAPL PPL1 time window",
        "unit" : "s",
        "type" : "float",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : False,
    },
    "ppl2" : {
        "name" : "RAPL PPL2",
        "unit" : "W",
        "type" : "float",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl2_enable" : {
        "name" : "RAPL PPL2",
        "type" : "bool",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl2_clamp" : {
        "name" : "RAPL PPL2 clamping",
        "type" : "bool",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : True,
    },
    "ppl2_window" : {
        "name" : "RAPL PPL2 time window",
        "unit" : "s",
        "type" : "float",
        "sname": "package",
        "mnames" : ("msr", ),
        "writable" : False,
    },
}

class Power(_PropsClassBase.PropsClassBase):
    """
    This class provides API for managing platform settings related to power. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def _get_pplobj(self):
        """Returns a 'PackagePowerLimit.PackagePowerLimit()' object."""

        if not self._pplobj:
            from pepclibs.msr import PackagePowerLimit # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._pplobj = PackagePowerLimit.PackagePowerLimit(pman=self._pman,
                                                               cpuinfo=self._cpuinfo, msr=msr)

        return self._pplobj

    def _get_ppiobj(self):
        """Returns a 'PackagePowerInfo.PackagePowerInfo()' object."""

        if not self._ppiobj:
            from pepclibs.msr import PackagePowerInfo # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._ppiobj = PackagePowerInfo.PackagePowerInfo(pman=self._pman,
                                                             cpuinfo=self._cpuinfo, msr=msr)

        return self._ppiobj

    @staticmethod
    def _pname2fname(pname):
        """Get 'PackagePowerLimit' class feature name by property name."""

        return pname.replace("ppl", "limit")

    def _get_prop_cpus(self, pname, cpus, mname):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, 'val' is property 'pname' value for CPU
        'cpu'. Use mechanism 'mname'.
        """

        assert mname == "msr"

        if pname.startswith("ppl"):
            fname = self._pname2fname(pname)
            pplobj = self._get_pplobj()
            yield from pplobj.read_feature(fname, cpus=cpus)
        else:
            ppiobj = self._get_ppiobj()
            yield from ppiobj.read_feature(pname, cpus=cpus)

    def _validate_ppl(self, pname, val, cpus):
        """
        Validate that the new PPL1 or PPL2 value 'val' is within reasonable limits.

        Even though accourding to Intel SDM, the min. and max. PPL values could be acquired from an
        MSR, this method does not use it because it does not seem to provide reasonable numbers on
        some platforms.
        """

        name = self._props[pname]["name"]
        check_pname = "ppl2" if pname == "ppl1" else "ppl1"
        fval = float(val)

        iterator = zip(self._get_prop_cpus_mnames("tdp", cpus),
                       self._get_prop_cpus_mnames(check_pname, cpus))
        for (cpu, tdp), (_, check_ppl_val) in iterator:
            if pname == "ppl1":
                minval = tdp / 8
                maxval = tdp
                if fval > check_ppl_val:
                    raise Error(f"cannot set CPU{cpu} {name} to {fval}W{self._pman.hostmsg} - it "
                                f"is higher than current RAPL PPL2 value {check_ppl_val}W")
            else:
                # Apply a reasonable limit for PPL2. This is empirical limit, based on general
                # observations.
                minval = tdp / 8
                maxval = tdp * 4
                if fval < check_ppl_val:
                    raise Error(f"cannot set CPU{cpu} {name} to {fval}W{self._pman.hostmsg} - it "
                                f"is lower than current RAPL PPL1 value {check_ppl_val}W")

            if fval > maxval or fval < minval:
                raise Error(f"cannot set CPU{cpu} {name} to {val}W{self._pman.hostmsg} - it is out "
                            f"of range ({minval}W-{maxval}W) for CPU{cpu}{self._pman.hostmsg}")

    def _do_set_prop(self, pname, val, cpus):
        """Implements '_set_prop_cpus()'."""

        if pname in ("ppl1", "ppl2"):
            self._validate_ppl(pname, val, cpus)

        fname = self._pname2fname(pname)
        self._get_pplobj().write_feature(fname, val, cpus=cpus)

    def _set_prop_cpus(self, pname, val, cpus, mname):
        """Set property 'pname' to value 'val' for CPUs in 'cpus'. Use mechanism 'mname'."""

        if mname != "msr":
            raise Error(f"BUG: unsupported mechanism '{mname}'")

        name = self._props[pname]["name"]

        try:
            self._do_set_prop(pname, val, cpus)
        except ErrorVerifyFailed as err:
            if pname in ("ppl1_enable", "ppl2_enable"):
                state = "enab" if val else "disab"
                errmsg = f"failed to {state}le {name}. Keep in mind some platforms " \
                         f"forbid {state}ling {name}."
                raise ErrorVerifyFailed(errmsg) from err
            raise

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)
        self._pplobj = None
        self._ppiobj = None

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_pplobj", "_ppiobj",))

        super().close()
