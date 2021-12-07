# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides implements the base class for "featured" MSRs, such as
'MSR_PKG_CST_CONFIG_CONTROL'.
"""

import copy
import logging
from pepclibs.helperlibs import Procs, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo
from pepclibs.msr import MSR

_LOG = logging.getLogger()

class FeaturedMSR:
    """
    This is the base class for featured MSRs, such as 'MSR_PKG_CST_CONFIG_CONTROL'.
    """

    def _check_feature_support(self, feature):
        """
        Check if CPU model of host 'self._proc' supports the feature 'feature'. Raises
        'ErrorNotSupported' if the feature is not supported.
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

    def _set_feature_bool(self, feature, val, cpus):
        """
        Enable or disable feature 'feature' for CPUs 'cpus'. Value 'val' can be boolean or
        string "on" or "off".
        """

        finfo = self.features[feature]
        if isinstance(val, str):
            val = val == "on"
        else:
            val = bool(val)

        enable = finfo["enabled"] == val
        self._msr.toggle_bit(self.msr_addr, finfo["bitnr"], enable, cpus=cpus)

    def set_feature(self, feature, val, cpus="all"):
        """
        Set feature 'feature' value to 'val' for CPUs 'cpus'. The 'feature' argument is one of the
        keys in 'self.features' dictionary. The 'cpus' argument is the same as the 'cpus' argument
        of the 'CPUIdle.get_cstates_info()' function - please, refer to the 'CPUIdle' module for the
        exact format description.
        """

        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if "enabled" in self.features[feature]:
                enable_str = "enable" if val else "disable"
                msg = f"{enable_str} feature '{feature}'"
            else:
                msg = f"set feature '{feature}' value to {val}"

            cpus_range = Human.rangify(self._cpuinfo.get_cpu_list(cpus))
            _LOG.debug("%s on CPU(s) %s%s", msg, cpus_range, self._proc.hostmsg)

        self._check_feature_support(feature)

        if "enabled" in self.features[feature]:
            self._set_feature_bool(feature, val, cpus)
        else:
            # The sub-class is supposed to implement the special method.
            set_method = getattr(self, f"_set_{feature}")
            set_method(val, cpus=cpus)

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
        The 'feature' argument is one of the keys in 'self.features' dictionary. Raises an error if
        the feature cannot be switched simply on or off.
        """

        self._check_feature_support(feature)
        if "enabled" not in self.features[feature]:
            raise Error("feature '{feature}' doesn't support boolean enabled/disabled status")

        regval = self._msr.read(self.msr_addr, cpu=cpu)
        bitval = int(bool(MSR.bit_mask(self.features[feature]["bitnr"]) & regval))
        return self.features[feature]["enabled"] == bitval

    def _create_features_dict(self):
        """
        Create an extended version of the 'self.featrues' dictionary. Add the 'supported' flag
        for each feature, which indicates if the platform supports the feature.
        """

        features = copy.deepcopy(self.features)

        # Add the "supported" flag.
        for finfo in features.values():
            if not "cpumodels" in finfo:
                # No CPU models list, which means that "all models".
                finfo["supported"] = True
            else:
                cpu_model = self._lscpu_info["model"]
                finfo["supported"] = cpu_model in finfo["cpumodels"]

        return features

    def _set_attributes(self):
        """
        This method must be provided by the sub-class and it must initialized the following
        attributes:
          * self.features - the features dictionary.
          * self.msr_addr - the featured MSR address.
          * self.msr_name = the featured MSR name.
        """

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
        self._cpuinfo = cpuinfo
        self._lscpu_info = lscpu_info

        self._set_attributes()

        self.features = None
        self.msr_addr = None
        self.msr_name = None
        self._msr = None

        if self._lscpu_info is None:
            self._lscpu_info = CPUInfo.get_lscpu_info(proc=self._proc)

        if self._lscpu_info["vendor"] != "GenuineIntel":
            msg = f"unsupported CPU model '{self._lscpu_info['vendor']}', model-specific " \
                  f"register {hex(self.msr_addr)} ({self.msr_name}) is not " \
                  f"available{self._proc.hostmsg}. {self.msr_name} is available only on Intel " \
                  f"platforms."
            raise ErrorNotSupported(msg)

        if self._lscpu_info["model"] not in CPUInfo.CPU_DESCR:
            raise ErrorNotSupported(f"unsupported CPU model '{self._lscpu_info['vendor']}'"
                                    f"{self._proc.hostmsg}")

        self.features = self._create_features_dict()
        self._msr = MSR.MSR(proc=self._proc)

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
