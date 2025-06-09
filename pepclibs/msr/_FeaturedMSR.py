# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Base class for accessing Model-Specific Register (MSR) features.

Terminology:
    - MSR feature scope (sname): The functional scope of an MSR feature - whether it applies
        per-CPU, per-core, per-package, etc.
    - MSR feature I/O scope (iosname): The I/O scope of the feature. Typically the same as the
        functional scope, but may be different for some MSRs. More information:
        https://github.com/intel/pepc/blob/main/docs/misc-msr-scope.md
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import copy
from typing import TypedDict, Literal, Union, cast
from pepclibs import CPUModels, CPUInfo
from pepclibs.CPUInfo import AbsNumsType
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.ProcessManager import ProcessManagerType
from pepclibs.msr import MSR

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class FeatureTypedDict(TypedDict, total=False):
    """
    Typed dictionary for MSR feature information.

    Keys:
        - name: The feature name.
        - sname: The functional scope name of the feature.
        - iosname: The I/O scope name for the feature.
        - help: A short description of the feature.
        - type: The feature type (e.g., "int", "str", etc.).
        - writable: Whether the feature can be modified (default is 'True').
        - cpuflags: A set of CPU flags that must be present for the feature to be supported.
        - vfms: A list of valid VFM values for the feature.
        - bits: The MSR bits range for the feature.
        - vals: A dictionary mapping user-friendly names to MSR values.
    """

    name: str
    sname: str
    iosname: str
    help: str
    type: str
    writable: bool
    cpuflags: set[str]
    vfms: list[str]
    bits: tuple[int, int]
    vals: dict[str, int]

FeatureValueType = Union[int, float, bool]

class PartialFeatureTypedDict(TypedDict, total=False):
    """
    Partially initialized MSR feature information. May include 'None' values for some keys.

    Keys:
        - name: The feature name.
        - sname: The functional scope name of the feature.
        - iosname: The I/O scope name for the feature.
        - help: A short description of the feature.
        - type: The feature type (e.g., "int", "str", etc.).
        - writable: Whether the feature can be modified (default is 'True').
        - cpuflags: A set of CPU flags that must be present for the feature to be supported.
        - vfms: A list of valid VFM values for the feature.
        - bits: The MSR bits range for the feature.
        - vals: A dictionary mapping user-friendly names to MSR values.
    """

    name: str
    sname: str | None
    iosname: str | None
    help: str
    type: str
    writable: bool
    cpuflags: set[str]
    vfms: list[str]
    bits: tuple[int, int]
    vals: dict[str, int]

class _FeatureTypedDict(FeatureTypedDict, total=False):
    """
    Internal version of feature information dictionary.

    Keys:
        - supported: A dictionary indicating whether the feature is supported on each CPU.
        - rvals: A dictionary mapping MSR values to user-friendly names.
        - vals_nocase: A case-insensitive version of 'vals'.
        - rvals_nocase: A case-insensitive version of 'rvals'.
    """

    supported: dict[int, bool]
    rvals: dict[int, str]
    vals_nocase: dict[str, int]
    rvals_nocase: dict[int, str]

class FeaturedMSR(ClassHelpers.SimpleCloseContext):
    """
    Base class for accessing Model-Specific Register (MSR) features.

    Public Methods Overview:
        1. Multiple CPUs:
            - Read/write feature: 'read_feature()', 'write_feature()'
            - Enable/disable feature: 'enable_feature()'
            - Check if feature is enabled: 'is_feature_enabled()'
            - Check if feature is supported: 'is_feature_supported()',
                                             'validate_feature_supported()'
        2. Single CPU:
            - Read/write feature: 'read_cpu_feature()', 'write_cpu_feature()'
            - Enable/disable feature: 'enable_cpu_feature()'
            - Check if feature is enabled: 'is_cpu_feature_enabled()'
            - Check if feature is supported: 'is_cpu_feature_supported()'
        3. Message Formatting Helpers:
            - Return string in the form "MSR 0xABC bits (a:b)": 'msr_bits_str()'
    """

    regaddr: int = 0
    regname: str = "<UNDEFINED>"
    vendor: str = "<UNDEFINED VENDOR>"

    def __init__(self,
                 cpuinfo: CPUInfo.CPUInfo,
                 pman: ProcessManagerType | None=None,
                 msr: MSR.MSR | None = None):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object.
            pman: The Process manager object that defines the host to run the measurements on. If
                  not provided, a local process manager will be used.
            msr: An optional 'MSR.MSR()' object to use for writing to the MSR register. If not
                 provided, a new MSR object will be created.

        Raises:
            ErrorNotSupported: If CPU vendor is not supported.
        """

        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_msr = msr is None

        # The user-visible features dictionary.
        self.features: dict[str, FeatureTypedDict] = {}
        # The private version of the 'self.features' dictionary.
        self._features: dict[str, _FeatureTypedDict] = {}

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        if self._cpuinfo.info["vendor"] != self.vendor:
            raise ErrorNotSupported(f"Unsupported MSR {self.regaddr:#x} ({self.regname}), it is "
                                    f"only available on {self.vendor} CPUs")

        if msr:
            self._msr = msr
        else:
            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman)

        self._set_baseclass_attributes()
        self._features = cast(dict[str, _FeatureTypedDict], copy.deepcopy(self.features))
        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_msr", "_pman",)
        unref_attrs = ("_cpuinfo",)
        ClassHelpers.close(self, close_attrs=close_attrs, unref_attrs=unref_attrs)

    def _init_supported_flag(self):
        """Initialize the 'supported' flag for all features."""

        supported = False
        vfm = self._cpuinfo.info["vfm"]

        for finfo in self._features.values():
            finfo["supported"] = {}

            if "vfms" in finfo and vfm not in finfo["vfms"]:
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
        Ensure that each feature in the 'self._features' dictionary contains all required keys, setting
        missing keys to their default values.
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

                if finfo["type"] in ("bool", "str"):
                    # Build a lowercase version of 'vals' and 'rvals' for case-insensitive matching.
                    finfo["vals_nocase"] = {}
                    finfo["rvals_nocase"] = {}
                    for name, code in finfo["vals"].items():
                        name = name.lower()
                        finfo["vals_nocase"][name] = code
                        finfo["rvals_nocase"][code] = name

    def _init_public_features_dict(self):
        """
        Create and initialize the public version of the features dictionary.
        """

        features_copy = copy.deepcopy(self._features)

        # Remove flags we do not want the user to access from 'self.features'.
        for finfo in features_copy.values():
            del finfo["supported"]
            if "rvals" in finfo:
                del finfo["rvals"]
            if "vals_nocase" in finfo:
                del finfo["vals_nocase"]
                del finfo["rvals_nocase"]

        self.features = cast(dict[str, FeatureTypedDict], features_copy)

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
        This method must be implemented by the sub-class. It should initialize the following
        attributes:
            - self._features: Set the private features dictionary describing the MSR features.
            - self.regaddr: Set the address of the featured MSR.
            - self.regname: Set the name of the featured MSR.

        Raises:
            NotImplementedError: If the sub-class does not implement this method.
        """

        raise NotImplementedError("BUG: sub-class did not define the '_set_baseclass_attributes()' "
                                  "method")

    def _get_clx_ap_adjusted_msr_scope(self) -> Literal["die", "package"]:
        """
        If the current platform is a Cascade Lake AP (CLX-AP), return "die", otherwise return
        "package".

        On CLX-AP platforms, which consist of two Cascade Lake-SP (CLX-SP) dies within a single package,
        most MSRs that have "package" scope on SKX or CLX platforms, have "die" scope on CLX-AP.
        This method helps to adjust the MSR scope accordingly.

        Returns:
            str: "die" if the platform is CLX-AP (i.e., two dies in one package), otherwise "package".
        """

        vfm = self._cpuinfo.info["vfm"]
        if vfm == CPUModels.MODELS["SKYLAKE_X"]["vfm"] and \
           len(self._cpuinfo.get_package_dies(package=0)) > 1:
            return "die"
        return "package"

    def validate_feature_supported(self, fname: str, cpus: AbsNumsType | Literal["all"] = "all"):
        """
        Validate that a feature is supported by all specified CPUs.

        Args:
            fname: Name of the feature to validate.
            cpus: CPU numbers to validate the feature support for. The default value is "all", which
                  means all CPUs.

        Raises:
            ErrorNotSupported: If the feature is not supported on one or more of the specified CPUs.
        """

        if fname not in self._features:
            features_str = ", ".join(set(self._features))
            raise Error(f"Unknown feature '{fname}', known features are: {features_str}")

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

            supported_str = Trivial.rangify(supported_cpus)
            unsupported_str = Trivial.rangify(unsupported_cpus)
            raise ErrorNotSupported(f"{self._features[fname]['name']} is not supported on CPUs "
                                    f"{unsupported_str}.\n{self._cpuinfo.cpudescr} supports "
                                    f"{self._features[fname]['name']} only on the following CPUs: "
                                    f"{supported_str}")

    def is_feature_supported(self, fname: str, cpus: AbsNumsType | Literal["all"] = "all") -> bool:
        """
        Check if a feature is supported by all specified CPUs.

        Args:
            fname: Name of the feature to check.
            cpus: CPU numbers to check, or "all" to check all CPUs.

        Returns:
            bool: True if the feature is supported on all specified CPUs, False otherwise.
        """

        try:
            self.validate_feature_supported(fname, cpus=cpus)
            return True
        except ErrorNotSupported:
            return False

    def is_cpu_feature_supported(self, fname: str, cpu: int) -> bool:
        """
        Check if a specific CPU supports a given feature.

        Args:
            fname: Name of the feature to check for support.
            cpu: CPU number to check for feature support.

        Returns:
            bool: True if the specified CPU supports the feature, False otherwise.
        """

        return self.is_feature_supported(fname, cpus=(cpu,))

    def _check_fname(self, fname: str):
        """
        Verify that the provided feature name exists in the list of known features.

        Args:
            fname: Name of the feature to check.

        Raises:
            Error: If the feature name is not recognized, raises an error listing all known
                   features.
        """

        if fname not in self._features:
            features_str = ", ".join(set(self._features))
            raise Error(f"Unknown feature '{fname}', known features are: {features_str}")

    def msr_bits_str(self, fname: str) -> str:
        """
        Return a string describing the MSR register address and bit range for the specified feature.

        Args:
            fname: Name of the feature for which to return the description.

        Returns:
            A string in the format "MSR 0x<address> bits (<start>:<end>)" or "MSR 0x<address> bit
            <n>".

        Example:
            "MSR 0xABC bits 3:9"
            "MSR 0xABC bit 5"
        """

        self._check_fname(fname)

        bits = self._features["fname"]["bits"]
        if bits[0] == bits[1]:
            bits_str = f"bit {bits[0]}"
        else:
            bits_str = f"bit {bits[0]:bits[1]}"

        return f"MSR {self.regaddr:x} bits {bits_str}"

    def _normalize_feature_value(self, fname: str, val: FeatureValueType) -> FeatureValueType:
        """
        Check that 'val' is a valid value for feature 'fname' and converts it to a value suitable
        for writing the MSR register.
        """

        finfo = self._features[fname]

        if not finfo.get("vals"):
            return val

        if finfo["type"] == "bool":
            # Treat boolean 'True' as "on", and 'False' as "off".
            if val is True:
                val_str = "on"
            elif val is False:
                val_str = "off"
            else:
                val_str = str(val)
        else:
            val_str = str(val)

        if val_str in finfo["vals"]:
            return finfo["vals"][val_str]

        if "vals_nocase" in finfo and val_str.lower() in finfo["vals_nocase"]:
            return finfo["vals_nocase"][val_str.lower()]

        vals = list(finfo["vals"])
        vals_str = ", ".join(vals)
        raise Error(f"Bad value '{val}' for the '{finfo['name']}' feature, use one of:\n  "
                    f"{vals_str}")

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

        The yielded tuples are '(cpu, enabled)'.
          * cpu - the CPU number the MSR was read from.
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
        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            cpus_str = Trivial.rangify(self._cpuinfo.normalize_cpus(cpus))
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
