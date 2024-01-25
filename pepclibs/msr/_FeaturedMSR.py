# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides the base class for "featured" MSRs, such as MSR_PKG_CST_CONFIG_CONTROL.

Terminology.
  * MSR feature scope - the functional scope of MSR feature, i.e., whether it is per-CPU, per-core,
                        per-package, etc.
  * MSR feature I/O scope - same as the scope in most cases. But in rare cases feature scope and its
                            I/O scope may be different. The I/O scop is defined by the observability
                            of MSR feature changes, not by its functional impact. For example, if
                            modifying an MSR feature from CPU X makes the modification visible on
                            all core siblings, the MSR feature has core scope. If the modification
                            is visible on all package siblings, the MSR feature has package scope.
                            Some MSRs may have, for example, core I/O scope, but impact the entire
                            package from the functional point of view (e.g., the package C-state
                            limit feature in MSR_PKG_CST_CONFIG_CONTROL).
  * MSR I/O scope - same as MSR feature I/O scope. Usually all features in an MSR have the same
                    scope, in which case the I/O scope references the entire MSR.
  * sname - (functional) scope.
  * iosname - I/O scope.
"""

import copy
import logging
from pepclibs import CPUModels, CPUInfo
from pepclibs.helperlibs import LocalProcessManager, Human, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
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
       * Check if feature is supported: 'is_cpu_feature_supported()'.
    3. Message formatting helpers.
       * Return string in form of 'MSR 0xABC bits (a:b)': msr_bits_str()
    """

    regaddr = None
    regname = None
    vendor = None

    def validate_feature_supported(self, fname, cpus="all"):
        """
        Validate that a feature is supported by all CPUs in 'cpus'. The arguments are as follows.
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

    def is_feature_supported(self, fname, cpus="all"):
        """
        Check if a feature is supported by all CPUs in 'cpus'. The arguments are as follows.
          * fname - name of the feature to check.
          * cpus - CPU numbers to check (same as in 'read_feature()').

        Return 'True' if the feature is supported on all CPUs, and 'False' otherwise.
        """

        try:
            self.validate_feature_supported(fname, cpus)
            return True
        except ErrorNotSupported:
            return False

    def is_cpu_feature_supported(self, fname, cpu):
        """
        Check if a feature is supported by CPU 'cpu'. The arguments are as follows.
          * fname - name of the feature to check.
          * cpu - the CPU number to check.

        Return 'True' if CPU 'cpu' supports the feature, and 'False' otherwise.
        """

        return self.is_feature_supported(fname, cpus=(cpu,))

    def _check_fname(self, fname):
        """Check if feature 'fname' is known."""

        if fname not in self._features:
            features_str = ", ".join(set(self._features))
            raise Error(f"unknown feature '{fname}', known features are: {features_str}")

    def msr_bits_str(self, fname):
        """
        Return a string including MSR register address and bits range for feature 'fname'. The
        arguments are as follows.
          * fname - name of the feature to return the MSR address and bits range for.

        Example of a string that could be returned: "MSR 0xABC bits (3:9)"
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

        The yielded tuples are '(cpu, val)'.
          * cpu - the CPU number the MSR was read from.
          * val - the feature value.
        """

        self.validate_feature_supported(fname, cpus=cpus)

        get_method_name = f"_get_{fname}"
        get_method = getattr(self, get_method_name, None)
        if get_method:
            for cpu, val in get_method(cpus=cpus):
                _LOG.debug("%s: read '%s' value '%s' from MSR %#x (%s) for CPU %s%s",
                           get_method_name, fname, val, self.regaddr, self.regname, cpu,
                           self._pman.hostmsg)
                yield cpu, val
        elif hasattr(self, "_get_feature"):
            for cpu, val in self._get_feature(fname, cpus=cpus):
                _LOG.debug("_get_feature: read '%s' value '%s' from MSR %#x (%s) for CPU %s%s",
                           fname, val, self.regaddr, self.regname, cpu, self._pman.hostmsg)
                yield cpu, val
        else:
            bits = self._features[fname]["bits"]
            for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus,
                                                iosname=self._features[fname]["iosname"]):
                if "rvals" in self._features[fname]:
                    val = self._features[fname]["rvals"][val]
                _LOG.debug("read_bits: read '%s' value '%s' from MSR %#x (%s) for CPU %s%s",
                           fname, val, self.regaddr, self.regname, cpu, self._pman.hostmsg)
                yield cpu, val

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

        self.validate_feature_supported(fname, cpus=cpus)
        val = self._normalize_feature_value(fname, val)

        finfo = self._features[fname]
        if not finfo["writable"]:
            fullname = finfo["name"]
            raise Error(f"feature '{fullname}' can not be modified{self._pman.hostmsg}, it is "
                        f"read-only")

        dbg_msg = ""
        if _LOG.getEffectiveLevel() == logging.DEBUG:
            cpus_str = Human.rangify(self._cpuinfo.normalize_cpus(cpus))
            dbg_msg = f"writing '{val}' to {fname}' in MSR {self.regaddr:#x} ({self.regname}) " \
                      f"for CPUs {cpus_str}{self._pman.hostmsg}"

        set_method_name = f"_set_{fname}"
        set_method = getattr(self, set_method_name, None)
        if set_method:
            _LOG.debug("%s: %s", set_method_name, dbg_msg)
            set_method(val, cpus=cpus)
        elif hasattr(self, "_set_feature"):
            _LOG.debug("_set_feature: %s", dbg_msg)
            self._set_feature(fname, val, cpus=cpus)
        else:
            _LOG.debug("write_bits: %s", dbg_msg)
            self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus=cpus,
                                 iosname=finfo["iosname"])

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

        supported = False
        cpumodel = self._cpuinfo.info["model"]

        for finfo in self._features.values():
            finfo["supported"] = {}

            if "cpumodels" in finfo and cpumodel not in finfo["cpumodels"]:
                for cpu in self._cpuinfo.get_cpus():
                    finfo["supported"][cpu] = False
                continue

            if "cpuflags" not in finfo:
                for cpu in self._cpuinfo.get_cpus():
                    supported = True
                    finfo["supported"][cpu] = True
            else:
                for cpu in self._cpuinfo.get_cpus():
                    cpuflags = self._cpuinfo.info["flags"][cpu]
                    finfo["supported"][cpu] = finfo["cpuflags"].issubset(cpuflags)
                    if finfo["supported"][cpu]:
                        supported = True

        if not supported:
            # None of the features are supported by this processor.
            raise ErrorNotSupported(f"MSR {self.regaddr:#x} ({self.regname}) is not supported"
                                    f"{self._pman.hostmsg} ({self._cpuinfo.cpudescr})")

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

    def _get_clx_ap_adjusted_msr_scope(self):
        """
        Return string "die" if the platform is a Cascade Lake AP (CLX-AP) and string "package"
        otherwise. The CLX-AP platform is special, because it basically has 2x CLX-SP dies in one
        package. So most MSRs that has "package" scope on SKX or CLX have "die" scope on CLX-AP.
        """

        model = self._cpuinfo.info["model"]
        if model == CPUModels.MODELS["SKYLAKE_X"]["model"] and \
           len(self._cpuinfo.get_dies(package=0)) > 1:
            return "die"
        return "package"

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
            raise ErrorNotSupported(f"unsupported MSR {self.regaddr:#x} ({self.regname}), it is "
                                    f"only available on {self.vendor} CPUs")

        if not self._msr:
            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman)

        self._set_baseclass_attributes()
        self._features = copy.deepcopy(self.features)
        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_msr", "_cpuinfo", "_pman",))
