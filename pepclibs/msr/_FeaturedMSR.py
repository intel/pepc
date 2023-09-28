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
from pepclibs.helperlibs import LocalProcessManager, Human, ClassHelpers
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

class FeaturedMSR(ClassHelpers.SimpleCloseContext):
    """
    This is the base class for "featured" MSRs, such as 'MSR_PKG_CST_CONFIG_CONTROL'.

    Public methods overview.

    1. Multiple CPUs.
       * Read/write feature: 'read_feature()', 'write_feature()'.
       * Enable/disable a feature: 'enable_feature()'.
       * Check if feature is enabled: 'is_feature_enabled()'.
       * Check if feature is supported: 'is_feature_supported()', validate_feature_supported()'.
    2. Single CPU.
       * Read/write feature: 'read_cpu_feature()', 'write_cpu_feature()'.
       * Enable/disable a feature: 'cpu_enable_feature()'.
       * Check if feature is enabled: 'is_cpu_feature_enabled()'.
       * Check if feature is supported: 'is_cpu_feature_supported()',
                                        'validate_cpu_feature_supported()'.
    3. Message formatting helpers.
       * Return string in form of 'MSR 0xABC bits (a:b)': msr_bits_str()
    """

    regaddr = None
    regname = None
    vendor = None

    def validate_feature_supported(self, fname, cpus="all"):
        """
        Validate if a feature is supported by all CPUs in 'cpus'.
          * fname - name of the feature to validate.
          * cpus - the CPUs to validate the feature for (same as in 'read_feature()').

        Raise 'ErrorNotSupported' exception if the feature is not supported by a CPU in 'cpus'.
        """

        if fname not in self._features:
            features_str = ", ".join(set(self._features))
            raise Error(f"unknown feature '{fname}', known features are: {features_str}")

        cpus = self._cpuinfo.normalize_cpus(cpus)

        supported_cpus = []
        unsupported_cpus = []
        for cpu in cpus:
            if self._features[fname]["supported"][cpu]:
                supported_cpus.append(cpu)
            else:
                unsupported_cpus.append(cpu)

        if unsupported_cpus:
            if not supported_cpus:
                raise ErrorNotSupported(f"{self._features[fname]['name']} is not supported on "
                                        f"{self._cpuinfo.cpudescr}")

            supported_cpus = Human.rangify(supported_cpus)
            unsupported_cpus = Human.rangify(unsupported_cpus)
            raise ErrorNotSupported(f"{self._features[fname]['name']} is not supported on CPUs "
                                    f"{unsupported_cpus}.\n{self._cpuinfo.cpudescr} supports "
                                    f"{self._features[fname]['name']} only on the following CPUs: "
                                    f"{supported_cpus}")

    def validate_cpu_feature_supported(self, fname, cpu):
        """Same as 'validate_feature_supported()' but for a single CPU."""

        self.validate_feature_supported(fname, cpus=(cpu, ))

    def is_feature_supported(self, fname, cpus="all"):
        """
        Same as 'validate_feature_supported()', except return 'False' if exception was raised,
        otherwise return 'True'.
        """

        try:
            self.validate_feature_supported(fname, cpus)
            return True
        except ErrorNotSupported:
            return False

    def is_cpu_feature_supported(self, fname, cpu):
        """Same as 'is_feature_supported()' but for a single CPU."""

        return self.is_feature_supported(fname, cpus=(cpu, ))

    def _check_fname(self, fname):
        """Check if feature 'fname' is known."""

        if fname not in self._features:
            features_str = ", ".join(set(self._features))
            raise Error(f"unknown feature '{fname}', known features are: {features_str}")

    def msr_bits_str(self, fname):
        """
        Return a string including MSR register address and bits range for feature 'fname'. The
        returned string looks like 'MSR 0xABC bits (a:b)'.
        """

        self._check_fname(fname)

        bits = self._features["fname"]["bits"]
        if bits[0] == bits[1]:
            bits_str = f"bit {bits[0]}"
        else:
            bits_str = f"bit {bits[0]:bits[1]}"

        return f"MSR {self.regaddr:x} bits {bits_str}"

    def _normalize_feature_value(self, fname, val):
        """
        Check that 'val' is a valid value for feature 'fname' and converts it to a value suitable
        for writing the MSR register.
        """

        finfo = self._features[fname]

        if not finfo.get("vals"):
            return val

        if "aliases" in finfo:
            if val in finfo["aliases"]:
                val = finfo["aliases"][val]
            elif val.lower() in finfo["aliases_nocase"]:
                val = finfo["aliases_nocase"][val.lower()]

        if finfo["type"] == "bool":
            # Treat boolean 'True' as "on", and 'False' as "off".
            if val is True:
                val = "on"
            elif val is False:
                val = "off"

        if val in finfo["vals"]:
            return finfo["vals"][val]

        if "vals_nocase" in finfo and val.lower() in finfo["vals_nocase"]:
            return finfo["vals_nocase"][val.lower()]

        vals = list(finfo["vals"]) + list(finfo.get("aliases", {}))
        vals_str = ", ".join(vals)
        raise Error(f"bad value '{val}' for the '{finfo['name']}' feature.\nUse one of: {vals_str}")

    def read_feature(self, fname, cpus="all"):
        """
        Read the MSR on CPUs in 'cpus', extract the values of the 'fname' feature, and yield the
        result. The arguments are as follows.
          * fname - name of the feature to read.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".

        The yielded tuples are '(cpunum, val)'.
          * cpunum - the CPU number the MSR was read from.
          * val - the feature value.
        """

        _LOG.debug("read feature '%s' from CPU(s) %s%s",
                   fname, Human.rangify(self._cpuinfo.normalize_cpus(cpus)), self._pman.hostmsg)

        self.validate_feature_supported(fname, cpus=cpus)

        get_method = getattr(self, f"_get_{fname}", None)
        if get_method:
            yield from get_method(cpus=cpus)
        elif hasattr(self, "_get_feature"):
            yield from self._get_feature(fname, cpus=cpus)
        else:
            bits = self._features[fname]["bits"]
            for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus,
                                                sname=self._features[fname]["sname"]):
                if "rvals" in self._features[fname]:
                    val = self._features[fname]["rvals"][val]
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

    def is_feature_enabled(self, fname, cpus="all"):
        """
        Check if feature 'fname' is enabled on CPUs in 'cpus'. The arguments are as follows.
          * fname - name of the feature to read and check.
          * cpus - the CPUs to read the feature from (same as in 'read_feature()').

        The yielded tuples are '(cpunum, enabled)'.
          * cpunum - the CPU number the MSR was read from.
          * enabled - 'True' if the feature is enabled, 'False' otherwise.
        """

        self.validate_feature_supported(fname, cpus=cpus)

        if self._features[fname]["type"] != "bool":
            raise Error(f"feature '{fname}' is not boolean, use 'read_feature()' instead")

        for cpu, val in self.read_feature(fname, cpus=cpus):
            enabled = val in {"on", "enabled"}
            yield (cpu, enabled)

    def is_cpu_feature_enabled(self, fname, cpu):
        """
        Check if CPU 'cpu' has feature 'fname' enabled. The arguments are as follows.
          * fname - name of the feature to read and check.
          * cpu - CPU number to read the feature from. Can be an integer or a string with an integer
                  number.

        Return 'True' if the feature is enabled, and 'False' otherwise.
        """

        enabled = None
        for _, enabled in self.is_feature_enabled(fname, cpus=(cpu,)):
            pass
        return enabled

    def write_feature(self, fname, val, cpus="all"):
        """
        For every CPU in 'cpus', modify the MSR by reading it, changing the 'fname' feature bits to
        the value corresponding to 'val', and writing it back. The arguments are as follows.
          * fname - name of the feature to set.
          * val - value to set the feature to.
          * cpus - the CPUs to write the feature to (same as in 'read_feature()').
        """

        _LOG.debug("set feature '%s' to value %s on CPU(s) %s%s", fname, val,
                   Human.rangify(self._cpuinfo.normalize_cpus(cpus)), self._pman.hostmsg)

        self.validate_feature_supported(fname, cpus=cpus)

        val = self._normalize_feature_value(fname, val)

        finfo = self._features[fname]
        if not finfo["writable"]:
            fullname = finfo["name"]
            raise Error(f"feature '{fullname}' can not be modified{self._pman.hostmsg}, it is "
                        f"read-only")

        set_method = getattr(self, f"_set_{fname}", None)
        if set_method:
            set_method(val, cpus=cpus)
        elif hasattr(self, "_set_feature"):
            self._set_feature(fname, val, cpus=cpus)
        else:
            self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus=cpus, sname=finfo["sname"])

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
                   'read_feature()').
        """

        self.validate_feature_supported(fname, cpus=cpus)

        if self._features[fname]["type"] != "bool":
            name = self._features[fname]["name"]
            raise Error(f"feature '{name}' is not boolean, use 'write_feature()' instead")

        if enable in {True, "on", "enable"}:
            val = "on"
        elif enable in {False, "off", "disable"}:
            val = "off"
        else:
            name = self._features[fname]["name"]
            good_vals = "True/False, 'on'/'off', 'enable'/'disable'"
            raise Error(f"bad value '{enable}' for a boolean feature '{name}', use: {good_vals}")

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

    def _init_supported_flag(self):
        """Initialize the 'supported' flag for all features."""

        cpumodel = self._cpuinfo.info["model"]

        for finfo in self._features.values():
            finfo["supported"] = {}

            if "cpumodels" in finfo and cpumodel not in finfo["cpumodels"]:
                for cpu in self._cpuinfo.get_cpus():
                    finfo["supported"][cpu] = False
                continue

            if "cpuflags" not in finfo:
                for cpu in self._cpuinfo.get_cpus():
                    finfo["supported"][cpu] = True
            else:
                for cpu in self._cpuinfo.get_cpus():
                    cpuflags = self._cpuinfo.info["flags"][cpu]
                    finfo["supported"][cpu] = finfo["cpuflags"].issubset(cpuflags)

    def _init_features_dict_defaults(self):
        """
        Walk through each feature in the 'self._features' dictionary and make sure that all the
        necessary keys are present. Set the missing keys to their default values.
          * writable - a flag indicating whether this feature can be modified. Default is 'True'.
          * rvals - the reverse values map.
        """

        for finfo in self._features.values():
            for cpu in self._cpuinfo.get_cpus():
                if finfo["supported"][cpu]:
                    # The 'feature' is supported by at least one CPU, continue initializing it.
                    break
            else:
                continue

            if "writable" not in finfo:
                finfo["writable"] = True

            if "vals" in finfo:
                # Build the reverse dictionary for 'vals'.
                finfo["rvals"] = {}
                for name, code in finfo["vals"].items():
                    finfo["rvals"][code] = name

                if finfo["type"] in ("bool", "dict"):
                    # Build a lowercase version of 'vals' and 'rvals' for case-insensitive matching.
                    finfo["vals_nocase"] = {}
                    finfo["rvals_nocase"] = {}
                    for name, code in finfo["vals"].items():
                        name = name.lower()
                        finfo["vals_nocase"][name] = code
                        finfo["rvals_nocase"][code] = name

            if "aliases" in finfo:
                finfo["aliases_nocase"] = {}
                for alias, name in finfo["aliases"].items():
                    finfo["aliases_nocase"][alias.lower()] = name

    def _init_public_features_dict(self):
        """Create the public version of the features dictionary ('self.features')."""

        self.features = copy.deepcopy(self._features)

        # Remove flags we do not want the user to access from 'self.features'.
        for finfo in self.features.values():
            del finfo["supported"]
            if "rvals" in finfo:
                del finfo["rvals"]
            if "vals_nocase" in finfo:
                del finfo["vals_nocase"]
                del finfo["rvals_nocase"]
            if "aliases_nocase" in finfo:
                del finfo["aliases_nocase"]

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        self._init_supported_flag()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def _set_baseclass_attributes(self):
        """
        This method must be provided by the sub-class and it must initialized the following
        attributes:
          * self._features - the private features dictionary.
          * self.regaddr - the featured MSR address.
          * self.regname = the featured MSR name.

        Note: this base class will create a copy of the 'self._features' dictionary provided by the
        sub-class, and then will mangle it (e.g., add the "supported" flag).
        """

        # pylint: disable=unused-argument
        raise Error("BUG: sub-class did not define the '_set_baseclass_attributes()' method")

    def __new__(cls, **kwargs):
        """The class constructor."""

        # When 'cpuinfo' argument is passed, optimize by validating that the CPU vendor is
        # supported, before initializing the entire class.
        if "cpuinfo" in kwargs and cls.vendor != kwargs["cpuinfo"].info["vendor"]:
            raise ErrorNotSupported(f"unsupported MSR {cls.regaddr:#x} ({cls.regname}), it's only "
                                    f"available on {cls.vendor} CPUs")

        return super(FeaturedMSR, cls).__new__(cls)

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        # The user-visible features dictionary.
        self.features = {}
        # The private version of the 'self.features' dictionary.
        self._features = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
            if self._cpuinfo.info["vendor"] != self.vendor:
                raise ErrorNotSupported(f"unsupported MSR {self.regaddr:#x} ({self.regname}), it's "
                                        f"only available on {self.vendor} CPUs")

        if not self._msr:
            self._msr = MSR.MSR(pman=self._pman, cpuinfo=self._cpuinfo)

        self._set_baseclass_attributes()
        self._features = copy.deepcopy(self.features)
        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_msr", "_cpuinfo", "_pman",))
