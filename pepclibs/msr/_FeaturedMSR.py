# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides the base class for "featured" MSRs, such as 'MSR_PKG_CST_CONFIG_CONTROL'.
"""

import copy
import logging
from pepclibs.helperlibs import Procs, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs import CPUInfo
from pepclibs.msr import MSR

_LOG = logging.getLogger()

# Map of features available on various CPU models. Must be defined by sub-classes and describe every
# supported feature.
#
# * This is only the initial, general definition. Many things are platform-dependent, so full
#   dictionary is available the 'features' attribute of the featured MSR classes (e.g.,
#   'PCStateConfigCtl.features').
# * Sub-classes do not necessary implement all features available in the MSR register.
FEATURES = {}

class FeaturedMSR:
    """
    This is the base class for "featured" MSRs, such as 'MSR_PKG_CST_CONFIG_CONTROL'.

    Public methods overview.

    1. Multiple CPUs.
       * Read/write feature: 'read_feature()', 'write_feature()'.
       * Enable/disable a feature: 'enable_feature()'.
       * Check if feature is enabled: 'feature_enabled()'.
    2. Single CPU.
       * Read/write feature: 'read_cpu_feature()', 'write_cpu_feature()'.
       * Enable/disable a feature: 'cpu_enable_feature()'.
       * Check if feature is enabled: 'cpu_feature_enabled()'.
       * Check if feature is supported: 'cpu_feature_supported()'.
    """

    def _check_feature_support(self, fname):
        """
        Check if CPU model of host 'self._proc' supports the feature 'fname'. Raises
        'ErrorNotSupported' if the feature is not supported.
        """

        if fname not in self.features:
            features_str = ", ".join(set(self.features))
            raise Error(f"unknown feature '{fname}', known features are: {features_str}")

        if self._features[fname]["supported"]:
            return

        finfo = self.features[fname]
        raise ErrorNotSupported(f"the '{finfo['name']}' feature is not supported on "
                                f"{self._cpuinfo.cpudescr}{self._proc.hostmsg}")

    def _normalize_feature_value(self, feature, val):
        """
        Check that 'val' is a valid value fore feature 'feature' and converts it to a value suitable
        for writing the MSR register.
        """

        finfo = self.features[feature]

        if not finfo.get("vals"):
            return val

        val = str(val).lower()

        if "aliases" in finfo and val in finfo["aliases"]:
            val = finfo["aliases"][val]

        if val in finfo["vals"]:
            return finfo["vals"][val]

        vals = list(finfo["vals"]) + list(finfo.get("aliases", {}))
        vals_str = ", ".join(vals)
        raise Error(f"bad value '{val}' for the '{finfo['name']}' feature.\nUse one of: {vals_str}")

    def read_feature(self, fname, cpus="all"):
        """
        Read the MSR on CPUs in 'cpus', extract the values of the 'fname' feature, and yield the
        result. The arguments are as follows.
          * fname - name of the feature to read.
          * cpus - the CPUs to read the feature from (same as in 'CPUIdle.get_cstates_info()').

        The yielded tuples are '(cpunum, val)'.
          * cpunum - the CPU number the MSR was read from.
          * val - the feature value.
        """

        _LOG.debug("read feature '%s' from CPU(s) %s%s",
                   fname, Human.rangify(self._cpuinfo.normalize_cpus(cpus)), self._proc.hostmsg)

        self._check_feature_support(fname)

        get_method = getattr(self, f"_get_{fname}", None)
        if get_method:
            yield from get_method(cpus=cpus)
        else:
            bits = self.features[fname]["bits"]
            for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus):
                if "rvals" in self.features[fname]:
                    val = self.features[fname]["rvals"][val]
                yield (cpu, val)

    def read_cpu_feature(self, fname, cpu):
        """
        Read the MSR for CPU 'cpu', extract the value of the 'fname' feature, and return the result.
        The arguments are as follows.
          * fname - name of the feature to read.
          * cpu - CPU number to read the feature from. Can be an integer or a string with an integer
                  number.
        """

        val = None
        for _, val in self.read_feature(fname, cpus=(cpu,)):
            pass

        return val

    def feature_enabled(self, fname, cpus="all"):
        """
        Read the MSR and check if feature 'fname' is enabled on CPUs in 'cpus'. The arguments are as
        follows.
          * fname - name of the feature to read and check.
          * cpus - the CPUs to read the feature from (same as in 'CPUIdle.get_cstates_info()').

        Yields tuples of '(cpunum, enabled)'.
          * cpunum - the CPU number the feature was read from.
          * enabled - 'True' if the feature is enabled, 'False' otherwise.
        """

        self._check_feature_support(fname)

        if self.features[fname]["type"] != "bool":
            raise Error(f"feature '{fname}' is not boolean, use 'read_feature()' instead")

        for cpu, val in self.read_feature(fname, cpus=cpus):
            enabled = val in {"on", "enabled"}
            yield (cpu, enabled)

    def cpu_feature_enabled(self, fname, cpu):
        """
        Read the MSR and check if feature 'fname' is enabled on CPU 'cpu'. Returns 'True' if the
        feature is enabled, and 'False' otherwise. The arguments are as follows.
          * fname - name of the feature to read and check.
          * cpu - CPU number to read the feature from. Can be an integer or a string with an integer
                  number.
        """

        for _, enabled in self.feature_enabled(fname, cpus=(cpu,)):
            return enabled

    def write_feature(self, fname, val, cpus="all"):
        """
        For every CPU in 'cpus', modify the MSR by reading it, changing the 'fname' feature bits to
        the value corresponding to 'val', and writing it back. The arguments are as follows.
          * fname - name of the feature to set.
          * val - value to set the feature to.
          * cpus - the CPUs to write the feature to (same as in 'CPUIdle.get_cstates_info()').
        """

        _LOG.debug("set feature '%s' to value %s on CPU(s) %s%s", fname, val,
                   Human.rangify(self._cpuinfo.normalize_cpus(cpus)), self._proc.hostmsg)

        self._check_feature_support(fname)
        val = self._normalize_feature_value(fname, val)

        finfo = self.features[fname]

        if not finfo["writable"]:
            raise Error(f"'{fname}' is can not be modified, it is read-only")

        set_method = getattr(self, f"_set_{fname}", None)
        if set_method:
            set_method(val, cpus=cpus)
        else:
            self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus=cpus)

    def write_cpu_feature(self, fname, val, cpu):
        """
        Modify the MSR on CPU 'cpu' by reading it, changing the 'fname' feature bits to the value
        corresponding to 'val', and writing it back. The arguments are as follows.
          * fname - name of the feature to set.
          * val - value to set the feature to.
          * cpu - CPU number to write the feature to. Can be an integer or a string with an integer
                  number.
        """

        self.write_feature(fname, val, cpus=(cpu,))

    def enable_feature(self, fname, enable, cpus="all"):
        """
        Modify the MSR by enabling or disabling feature 'fname' on CPUs in 'cpus'. The arguments
        are as follows.
          * fname - name of the feature to enable or disable.
          * enable - enable the feature if 'True', disable otherwise.
          * cpus - the CPUs to enable or disable the feature on (same as in
                   'CPUIdle.get_cstates_info()').
        """

        self._check_feature_support(fname)

        if self.features[fname]["type"] != "bool":
            raise Error(f"feature '{fname}' is not boolean, use 'write_feature()' instead")

        val = "on" if enable else "off"
        self.write_feature(fname, val, cpus=cpus)

    def enable_cpu_feature(self, fname, enable, cpu):
        """
        Modify the MSR by enabling or disabling feature 'fname' on CPU 'cpu'. The arguments are as
        follows.
          * fname - name of the feature to enable or disable.
          * enable - enable the feature if 'True', disable otherwise.
          * cpu - CPU number to enable or disable the feature on. Can be an integer or a string with
                  an integer number.
        """

        self.enable_feature(fname, enable, cpus=(cpu,))

    def cpu_feature_supported(self, fname, cpu): # pylint: disable=unused-argument
        """
        Returns 'True' if feature 'fname' is supported by the platform on CPU 'cpu', returns 'False'
        otherwise.
        """

        # In current implementation we assume that all CPUs are the same and whether the feature is
        # supported per-platform. But in the future this may not be the case (e.g., on hybrid
        # platforms).

        try:
            self._check_feature_support(fname)
            return True
        except ErrorNotSupported:
            return False

    def _init_supported_flag(self):
        """Initialize the 'supported' flag for all features in the 'self._features' dictionary."""

        for fname, finfo in self.features.items():
            # By default let's assume the feature is supported by this CPU.
            self._features[fname]["supported"] = True

            if "cpuflags" in finfo:
                # Make sure that current CPU has all the required CPU flags.
                available_cpuflags = set(self._cpuinfo.info["flags"])
                for cpuflag in finfo["cpuflags"]:
                    if cpuflag not in available_cpuflags:
                        self._features[fname]["supported"] = False

            if "cpumodels" in finfo:
                # Check if current CPU model is supported by the feature.
                cpumodel = self._cpuinfo.info["model"]
                self._features[fname]["supported"] = cpumodel in finfo["cpumodels"]

    def _init_features_dict_defaults(self):
        """
        Walk through each feature in the 'self.features' dictionary and make sure that all the
        necessary keys are present. Set the missing keys to their default values.
          * writable - a flag indicating whether this feature can be modified. Default is 'True'.
        """

        for fname, finfo in self.features.items():
            if not self._features[fname]["supported"]:
                continue

            if "writable" not in finfo:
                finfo["writable"] = True

            if "vals" in finfo:
                # Build the reverse dictionary for 'vals'.
                finfo["rvals"] = {}
                for name, code in finfo["vals"].items():
                    finfo["rvals"][code] = name

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        self._init_supported_flag()
        self._init_features_dict_defaults()

    def _set_baseclass_attributes(self):
        """
        This method must be provided by the sub-class and it must initialized the following
        attributes:
          * self.features - the features dictionary.
          * self.regaddr - the featured MSR address.
          * self.regname = the featured MSR name.
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
        self._features = {}
        self.regaddr = None
        self.regname = None

        self._set_baseclass_attributes()

        if not self._proc:
            self._proc = Procs.Proc()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        if not self._msr:
            self._msr = MSR.MSR(proc=self._proc)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported {self._cpuinfo.descr}{self._proc.hostmsg}, "
                                    f"model-specific register {self.regaddr:#x} ({self.regname}) "
                                    f"is available only on Intel CPUs.")

        self.features = copy.deepcopy(self.features)

        # The '_features' dictionary is an additional per-feature storage of various "private"
        # pieces of information, which we do not want users to access directly. For example, we
        # store the 'supported' flag in '_features'. It may become per-CPU at some point, and we
        # want users to call 'cpu_feature_supported()' to check if the feature is supported.
        for fname in self.features:
            self._features[fname] = {}

        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""

        for attr in ("_msr", "_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
