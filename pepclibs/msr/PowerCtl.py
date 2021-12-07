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

import copy
import logging
from pepclibs import CPUInfo
from pepclibs.msr import MSR
from pepclibs.helperlibs import Procs, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = logging.getLogger()

# The Power Control Model Specific Register.
MSR_POWER_CTL = 0x1FC
C1E_ENABLE = 1
CSTATE_PREWAKE_DISABLE = 30

# Description of CPU features controlled by the the Power Control MSR.
#
# Note 1: consider using the 'PowerCtl.features' dicionary instead of this one.
# Note 2, the "scope" names have to be the same as "level" names in 'CPUInfo'.
FEATURES = {
    "cstate_prewake" : {
        "name" : "C-state prewake",
        "enabled" : 0,
        "bitnr" : CSTATE_PREWAKE_DISABLE,
        "cpumodels" : [CPUInfo.INTEL_FAM6_ICELAKE_X, CPUInfo.INTEL_FAM6_ICELAKE_D],
        "choices" : ["on", "off"],
        "scope": "package",
        "help" : f"""When enabled, the CPU will start exiting the C6 idle state in advance, prior to
                     the next local APIC timer event. This CPU feature is controlled by MSR
                     {MSR_POWER_CTL:#x}, bit {CSTATE_PREWAKE_DISABLE}.""",
    },
    "c1e_autopromote" : {
        "name" : "C1E autopromote",
        "enabled" : 1,
        "bitnr" : C1E_ENABLE,
        "choices" : ["on", "off"],
        "scope": "package",
        "help" : f"""When enabled, the CPU automatically converts all C1 requests to C1E requests.
                     This CPU feature is controlled by MSR {MSR_POWER_CTL:#x}, bit {C1E_ENABLE}.""",
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

        if feature not in self.features:
            features_str = ", ".join(set(self.features))
            raise Error(f"unknown feature '{feature}', known features are: {features_str}")

        finfo = self.features[feature]
        if finfo["supported"]:
            return

        model = self._lscpu_info["model"]
        fmt = "%s (CPU model %#x)"
        cpus_str = "\n* ".join([fmt % (CPUInfo.CPU_DESCR[model], model) for model in \
                                finfo["cpumodels"]])
        msg = f"The '{finfo['name']}' feature is not supported{self._proc.hostmsg} - CPU " \
              f"'{self._lscpu_info['vendor']}, (CPU model {hex(model)})' is not supported.\n" \
              f"The currently supported CPU models are:\n* {cpus_str}"
        raise ErrorNotSupported(msg)

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
        bitval = int(bool(MSR.bit_mask(self.features[feature]["bitnr"]) & regval))
        return self.features[feature]["enabled"] == bitval

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
        enable = self.features[feature]["enabled"] == enable
        self._msr.toggle_bit(MSR_POWER_CTL, self.features[feature]["bitnr"], enable, cpus=cpus)

    def _create_features_dict(self):
        """Create an extended version of the 'FEATURES' dictionary."""

        features = copy.deepcopy(FEATURES)

        # Add the "supported" flag.
        for finfo in features.values():
            if not "cpumodels" in finfo:
                # No CPU models list, which means that "all models".
                finfo["supported"] = True
            else:
                cpu_model = self._lscpu_info["model"]
                finfo["supported"] = cpu_model in finfo["cpumodels"]

        return features

    def __init__(self, proc=None, cpuinfo=None, lscpu_info=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * lscpu_info - CPU information generated by 'CPUInfo.get_lscpu_info()'.
        """

        if not proc:
            proc = Procs.Proc()

        self._proc = proc
        self._lscpu_info = lscpu_info
        self._cpuinfo = cpuinfo

        self.featres = None
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

        self.features = self._create_features_dict()
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
