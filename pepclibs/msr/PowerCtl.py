# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides API for managing settings in MSR 0x1FC (MSR_POWER_CTL). This is a
model-specific register found on many Intel platforms.
"""

import logging
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.helperlibs import Procs, Human
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

_LOG = logging.getLogger()

# Power control Model Specific Register.
MSR_POWER_CTL = 0x1FC
C1E_ENABLE = 1
CSTATE_PREWAKE_DISABLE = 30
# Indicates whether dynamic switching is enabled in power perf tuning algorithm. Available on ICX.
PWR_PERF_TUNING_ENABLE_DYN_SWITCHING = 33

# Map of features available on various CPU models.
# Note, the "scope" names have to be the same as "level" names in 'CPUInfo'.
FEATURES = {
    "cstate_prewake" : {
        "name" : "C-state prewake",
        "enabled" : 0,
        "bitnr" : CSTATE_PREWAKE_DISABLE,
        "cpumodels" : [CPUInfo.INTEL_FAM6_ICELAKE_X, CPUInfo.INTEL_FAM6_ICELAKE_D],
        "choices" : ["on", "off"],
        "scope": "package",
        "help" : f"""When enabled, exit from C-state will start prior next event. This is possible
                     only if time of next event is known, for example in case of local APIC timers.
                     This command toggles MSR {MSR_POWER_CTL:#x}, bit {CSTATE_PREWAKE_DISABLE}.""",
    },
    "c1e_autopromote" : {
        "name" : "C1E autopromote",
        "enabled" : 1,
        "bitnr" : C1E_ENABLE,
        "choices" : ["on", "off"],
        "scope": "package",
        "help" : f"""When enabled, the CPU automatically converts all C1 requests into C1E requests.
                     This command toggles MSR {MSR_POWER_CTL:#x}, bit {C1E_ENABLE}.""",
    },
}

class PowerCtl:
    """
    This class provides API for managing settings in MSR 0x1FC (MSR_POWER_CTL). This is a
    model-specific register found on many Intel platforms.
    """

    def _check_feature_support(self, feature):
        """
        Check if CPU model of host 'self._proc' supports the feature 'feature'. The 'feature'
        argument is one of the keys in the 'FEATURES' dictionary. Raise 'ErrorNotSupported' if the
        feature is not supported.
        """

        model = self._lscpu_info["model"]
        feature = FEATURES[feature]

        if "cpumodels" in feature and model not in feature["cpumodels"]:
            fmt = "%s (CPU model %#x)"
            cpus_str = "\n* ".join([fmt % (CPUInfo.CPU_DESCR[model], model) for model in \
                                    feature["cpumodels"]])
            raise ErrorNotSupported(f"The '{feature['name']}' feature is not supported"
                                    f"{self._proc.hostmsg} - CPU '{self._lscpu_info['vendor']}, "
                                    f"(CPU model {hex(model)})' is not supported.\nThe supported "
                                    f"CPU models are:\n* {cpus_str}")

    def feature_supported(self, feature):
        """
        Returns 'True' if feature 'feature' is supported, returns 'False' otherwise. The 'feature'
        argument is one of the keys in the 'FEATURES' dictionary.
        """

        try:
            self._check_feature_support(feature)
            return True
        except ErrorNotSupported as err:
            _LOG.debug(err)
            return False

    def feature_enabled(self, feature, cpu):
        """
        Returns 'True' if the feature 'feature' is enabled for CPU 'cpu', otherwise returns 'False'.
        The 'feature' argument is one of the keys in 'FEATURES' dictionary.
        """

        self._check_feature_support(feature)
        regval = self._msr.read(MSR_POWER_CTL, cpu=cpu)
        bitval = int(bool(MSR.bit_mask(FEATURES[feature]["bitnr"]) & regval))
        return FEATURES[feature]["enabled"] == bitval

    def set_feature(self, feature, enable: bool, cpus="all"):
        """
        Enable or disable feature 'feature' for CPUs 'cpus'. The 'feature' argument is one of the
        keys in 'FEATURES' dictionary. The 'cpus' argument is the same as the 'cpus' argument of the
        'CPUIdle.get_cstates_info()' function - please, refer to the 'CPUIdle' module for the exact
        format description.
        """

        if _LOG.getEffectiveLevel() == logging.DEBUG:
            enable_str = "enable" if enable else "disable"
            cpus_range = Human.rangify(self._cpuinfo.get_cpu_list(cpus))
            _LOG.debug("%s feature '%s' on CPU(s) %s%s",
                       enable_str, feature, cpus_range, self._proc.hostmsg)

        self._check_feature_support(feature)
        enable = FEATURES[feature]["enabled"] == enable
        self._msr.toggle_bit(MSR_POWER_CTL, FEATURES[feature]["bitnr"], enable, cpus=cpus)

    def __init__(self, proc=None, lscpu_info=None, cpuinfo=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * lscpu_info - CPU information generated by 'CPUInfo.get_lscpu_info()'.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
        """

        if not proc:
            proc = Procs.Proc()

        self._proc = proc
        self._lscpu_info = lscpu_info
        self._cpuinfo = cpuinfo

        self._msr = None

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        if self._lscpu_info is None:
            self._lscpu_info = CPUInfo.get_lscpu_info(proc=self._proc)

        if self._lscpu_info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported CPU model '{self._lscpu_info['vendor']}', "
                                    f"model-specific register {hex(MSR_POWER_CTL)} (MSR_POWER_CTL) "
                                    f"is not available{self._proc.hostmsg}. MSR_POWER_CTL is "
                                    f"available only on Intel platforms")

        self._msr = MSR.MSR(proc=self._proc, cpuinfo=self._cpuinfo)

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_proc", None):
            self._proc = None
        if getattr(self, "_msr", None):
            self._msr.close()
            self._msr = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
