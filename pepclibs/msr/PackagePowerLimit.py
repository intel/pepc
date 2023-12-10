# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module provides API to MSR 0x610 (MSR_PKG_POWER_LIMIT).
"""

from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

# The Package Power Limit Model Specific Register.
MSR_PKG_POWER_LIMIT = 0x610

# CPU models supporting the "Package Power Limit" MSR.
_PPL_CPUS = CPUInfo.GNRS +         \
            CPUInfo.EMRS +         \
            CPUInfo.METEORLAKES +  \
            CPUInfo.SPRS +         \
            CPUInfo.RAPTORLAKES +  \
            CPUInfo.ALDERLAKES +   \
            CPUInfo.ROCKETLAKES +  \
            CPUInfo.TIGERLAKES +   \
            CPUInfo.ICELAKES +     \
            CPUInfo.COMETLAKES +   \
            CPUInfo.KABYLAKES +    \
            CPUInfo.CANNONLAKES +  \
            CPUInfo.SKYLAKES +     \
            CPUInfo.BROADWELLS +   \
            CPUInfo.HASWELLS +     \
            CPUInfo.IVYBRIDGES +   \
            CPUInfo.SANDYBRIDGES + \
            CPUInfo.WESTMERES +    \
            CPUInfo.TREMONTS +     \
            CPUInfo.GOLDMONTS +    \
            CPUInfo.PHIS

# Description of CPU features controlled by the Package Power Limit MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "limit1": {
        "name": "Package power limit #1",
        "sname": "package",
        "help": """Average power usage limit of the package domain corresponding to time
                   window #1.""",
        "cpumodels": _PPL_CPUS,
        "type": "float",
        "bits": (14, 0),
    },
    "limit1_enable": {
        "name": "Enable package power limit #1",
        "sname": "package",
        "help": """Enable/disable RAPL package power limit #1.""",
        "cpumodels": _PPL_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (15, 15),
    },
    "limit1_clamp": {
        "name": "Enable package power clamping for limit #1",
        "sname": "package",
        "help": """Clamp the package power usage to specified limit during time window #1.
                   This may result in the system running below the requested frequency/voltage.""",
        "cpumodels": _PPL_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (16, 16),
    },
    "limit1_window": {
        "name": "Time window for power limit #1",
        "sname": "package",
        "help": """Time window for package power limit #1: the system makes sure that average
                   package power over the time window does not exceed power limit #1.""",
        "cpumodels": _PPL_CPUS,
        "type": "float",
        "bits": (23, 17),
        "writable": False,
    },
    "limit2": {
        "name": "Package power limit #2",
        "sname": "package",
        "help": """Average power usage limit of the package domain corresponding to time
                   window #2.""",
        "cpumodels": _PPL_CPUS,
        "type": "float",
        "bits": (46, 32),
    },
    "limit2_enable": {
        "name": "Enable package power limit #2",
        "sname": "package",
        "help": """Enable/disable RAPL package power limit #2.""",
        "cpumodels": _PPL_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (47, 47),
    },
    "limit2_clamp": {
        "name": "Enable package power clamping for limit #2",
        "sname": "package",
        "help": """Clamp the package power usage to specified limit during time window #2.
                   This may result in the system running below the requested frequency/voltage.""",
        "cpumodels": _PPL_CPUS,
        "type": "bool",
        "vals": {"on": 1, "off": 0},
        "bits": (48, 48),
    },
    "limit2_window": {
        "name": "Time window for power limit #2",
        "sname": "package",
        "help": """Time window for package power limit #2: the system makes sure that average
                   package power over the time window does not exceed power limit #2.""",

        "cpumodels": _PPL_CPUS,
        "type": "float",
        "bits": (55, 49),
        "writable": False,
    },
}

class PackagePowerLimit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x610 (MSR_PKG_POWER_LIMIT).
    """

    regaddr = MSR_PKG_POWER_LIMIT
    regname = "MSR_PKG_POWER_LIMIT"
    vendor = "GenuineIntel"

    def _get_unitobj(self):
        """Returns a 'RaplPowerUnit.RaplPowerUnit()' object."""

        if not self._unitobj:
            from pepclibs.msr import RaplPowerUnit # pylint: disable=import-outside-toplevel
            self._unitobj = RaplPowerUnit.RaplPowerUnit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=self._msr)

        return self._unitobj

    def _get_units(self, unitname):
        """Returns the named system unit value."""

        cpu = self._cpuinfo.get_cpus()[0]
        return self._get_unitobj().read_cpu_feature(unitname, cpu)

    def _get_power_units(self):
        """Returns the system 'power units' value in Watts."""

        if not self._power_units:
            self._power_units = self._get_units("power_units")
        return self._power_units

    def _get_time_units(self):
        """Returns the system 'time units' value in Seconds."""

        if not self._time_units:
            self._time_units = self._get_units("time_units")
        return self._time_units

    def _val_to_window(self, val):
        """Helper method to convert a given bit field to time window in seconds."""

        y = self._msr.get_bits(val, (4, 0))
        z = self._msr.get_bits(val, (6, 5))

        return pow(2, y) * (1 + z / 4) * self._get_time_units()

    def _get_feature(self, fname, cpus="all"):
        """Returns the value for a feature."""

        bits = self._features[fname]["bits"]

        for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus,
                                            sname=self._features[fname]["sname"]):
            if fname.endswith("_window"):
                val = self._val_to_window(val)
            elif fname in ("limit1", "limit2"):
                val = val * self._get_power_units()
            elif "rvals" in self._features[fname]:
                val = self._features[fname]["rvals"][val]

            yield (cpu, val)

    def _set_limit(self, finfo, val, cpus="all"):
        """Helper method to set the given package power limit in Watts."""

        val = int(float(val) / self._get_power_units())
        self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus, sname=finfo["sname"])

    def _set_feature(self, fname, val, cpus="all"):
        """Sets the value of a feature."""

        finfo = self._features[fname]

        # On some platforms the "enable" and "clamp" bits cannot be modified. For example, we
        # observed that on a Cascade Lake Xeon CPU: the 'enable' bit cannot be cleared (set to
        # "off"). The MSR write operation succeeds, but the bit does not change (says "on"). Pass
        # 'verify=True' to detect if the change was successful.
        if fname.endswith("_clamp") or fname.endswith("_enable"):
            self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus, verify=True,
                                 sname=finfo["sname"])
        elif fname in ("limit1", "limit2"):
            self._set_limit(finfo, val, cpus)
        else:
            raise Error(f"BUG: feature {fname} is not supported")

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        self._unitobj = None
        self._power_units = None
        self._time_units = None

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_unitobj",))

        super().close()
