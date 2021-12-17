# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

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

        raise ErrorNotSupported(f"The '{finfo['name']}' feature is not supported on "
                                f"{self._cpuinfo.cpudescr}{self._proc.hostmsg}")

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

        enable = finfo["vals"]["enabled"] == val
        bitnr = finfo["bits"][0]
        self._msr.toggle_bit(self.msr_addr, bitnr, enable, cpus=cpus)

    def _get_feature_bool(self, feature, cpu):
        """Returns value of a boolean feature 'feature'."""

        regval = self._msr.read(self.msr_addr, cpu=cpu)
        bitnr = self.features[feature]["bits"][0]
        bitval = int(bool(MSR.bit_mask(bitnr) & regval))

        return self.features[feature]["vals"]["enabled"] == bitval

    def feature_supported(self, feature):
        """
        Returns 'True' if feature 'feature' is supported by the platform, returns 'False' otherwise.
        """

        try:
            self._check_feature_support(feature)
            return True
        except ErrorNotSupported:
            return False

    def set_feature(self, feature, val, cpus="all"):
        """
        Set feature 'feature' value to 'val' for CPUs 'cpus'. The arguments are as follows.
          * feature - name of the feature to set.
          * val - value to set the feature to.
          * cpus - the CPUs to set the feature for (same as in 'CPUIdle.get_cstates_info()').
        """

        if _LOG.getEffectiveLevel() == logging.DEBUG:
            if self.features[feature]["type"] == "bool":
                enable_str = "enable" if val else "disable"
                msg = f"{enable_str} feature '{feature}'"
            else:
                msg = f"set feature '{feature}' value to {val}"

            cpus_range = Human.rangify(self._cpuinfo.normalize_cpus(cpus))
            _LOG.debug("%s on CPU(s) %s%s", msg, cpus_range, self._proc.hostmsg)

        self._check_feature_support(feature)

        if self.features[feature]["type"] == "bool":
            self._set_feature_bool(feature, val, cpus)
        else:
            # The sub-class is supposed to implement the special method.
            set_method = getattr(self, f"_set_{feature}")
            set_method(val, cpus=cpus)

    def feature_enabled(self, feature, cpu):
        """
        Just a limited version of 'get_feature()', accepts only boolean features, returns 'True' if
        the feature is enabled, returns 'False' otherwise. This method exists only because for some
        users this method name a bit more self-documenting. Indeed, compare:
          * if msr_reg.feature_enabled(): do_something()
          * if msr_reg.get_feature(): do_something()
        """

        self._check_feature_support(feature)

        if self.features[feature]["type"] == "bool":
            return self._get_feature_bool(feature, cpu)

        raise Error(f"feature '{feature}' is not boolean, use 'get_feature()' instead")

    def get_feature(self, feature, cpu):
        """
        Returns value of feature 'feature for CPU 'cpu'. The arguments are as follows.
          * feature - name of the feature to get.
          * cpus - CPU number to get the feature for.

        In case of a boolean "on/off" type of feature, return 'True' if the feature is enabled, and
        'False' otherwise.
        """

        self._check_feature_support(feature)

        if self.features[feature]["type"] == "bool":
            return self._get_feature_bool(feature, cpu)

        # The sub-class is supposed to implement the special method.
        get_method = getattr(self, f"_get_{feature}")
        return get_method(cpu)

    def _init_features_dict(self):
        """
        Intitialize the 'featrues' dictionary with the following platform-specific information.
          * Add the 'supported' flag inidcating whether the platform supports the feature.
        """

        self.features = features = copy.deepcopy(self.features)

        # Add the "supported" flag.
        for finfo in features.values():
            if not "cpumodels" in finfo:
                # No CPU models list, assumed the feature is supported.
                finfo["supported"] = True
            else:
                cpumodel = self._cpuinfo.info["model"]
                finfo["supported"] = cpumodel in finfo["cpumodels"]

    def _set_baseclass_attributes(self):
        """
        This method must be provided by the sub-class and it must initialized the following
        attributes:
          * self.features - the features dictionary.
          * self.msr_addr - the featured MSR address.
          * self.msr_name = the featured MSR name.
        """

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        if not proc:
            proc = Procs.Proc()

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self.features = None
        self.msr_addr = None
        self.msr_name = None

        self._set_baseclass_attributes()

        if not self._proc:
            self._proc = Procs.Proc()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        if not self._msr:
            self._msr = MSR.MSR(proc=self._proc)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported {self._cpuinfo.descr}{self._proc.hostmsg}, "
                                    f"model-specific register {self.msr_addr:#x} ({self.msr_name}) "
                                    f"is available only on Intel CPUs.")

        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_msr", "_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close_{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
