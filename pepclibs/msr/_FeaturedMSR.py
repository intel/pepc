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

import typing
import copy
from typing import cast
from pepclibs import CPUModels
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.msr import MSR

if typing.TYPE_CHECKING:
    from typing import TypedDict, Sequence, Literal, Union, Generator, Protocol
    from pepclibs import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import ScopeNameType

    # The type of the feature value.
    FeatureValueType = Union[int, float, bool, str]

    _FeatureValsType = Union[dict[int, int], dict[float, int], dict[bool, int], dict[str, int]]
    _FeatureReversValsType = Union[dict[int, int], dict[int, float], dict[int, bool],
                                   dict[int, str]]

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
            - vals: A dictionary mapping user-friendly names to MSR values.
            - bits: The MSR bits range for the feature.
        """

        name: str
        sname: ScopeNameType
        iosname: ScopeNameType
        help: str
        type: str
        writable: bool
        cpuflags: set[str]
        vfms: set[int]
        vals: _FeatureValsType
        bits: tuple[int, int]

    class _ReadFeatureMethodType(Protocol):
        """
        The type for a feature get method.
        """

        def __call__(self, cpus: Sequence[int] | Literal["all"] = "all") -> \
                                        Generator[tuple[int, FeatureValueType], None, None]: ...

    class _WriteFeatureMethodType(Protocol):
        """
        The type for a feature set method.
        """

        def __call__(self, val: FeatureValueType, cpus: Sequence[int] | Literal["all"] = "all"): ...

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
            - vals: A dictionary mapping user-friendly names to MSR values.
            - bits: The MSR bits range for the feature.
        """

        name: str
        sname: ScopeNameType | None
        iosname: ScopeNameType | None
        help: str
        type: str
        writable: bool
        cpuflags: set[str]
        vfms: set[int]
        vals: _FeatureValsType | None
        bits: tuple[int, int] | None

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
        rvals: dict[int, FeatureValueType]
        vals_nocase: dict[str, int]
        rvals_nocase: dict[int, str]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def get_clx_ap_adjusted_msr_scope(cpuinfo: CPUInfo.CPUInfo) -> Literal["die", "package"]:
    """
    If the current platform is a Cascade Lake AP (CLX-AP), return "die", otherwise return
    "package".

    On CLX-AP platforms, which consist of two Cascade Lake-SP (CLX-SP) dies within a single
    package, most MSRs that have "package" scope on SKX or CLX platforms, have "die" scope on
    CLX-AP. This method helps to adjust the MSR scope accordingly.

    Args:
        cpuinfo: The CPU information object.

    Returns:
        "die" if the platform is CLX-AP (i.e., two dies in one package), otherwise "package".
    """

    vfm = cpuinfo.info["vfm"]
    if vfm == CPUModels.MODELS["SKYLAKE_X"]["vfm"] and len(cpuinfo.get_package_dies(package=0)) > 1:
        return "die"

    return "package"

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
                 pman: ProcessManagerType | None = None,
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
            ErrorNotSupported: If CPU vendor is not supported or if the CPU does not the MSR.
        """

        _LOG.debug("Initializing MSR %s (0x%x)", self.regname, self.regaddr)

        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_msr = msr is None

        # The user-visible features dictionary.
        self.features: dict[str, FeatureTypedDict] = {}
        # The partially initialized features dictionary, must be set by the sub-class.
        self._partial_features: dict[str, PartialFeatureTypedDict]
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

        fdict = copy.deepcopy(self._partial_features)
        if typing.TYPE_CHECKING:
            self._features = cast(dict[str, _FeatureTypedDict], fdict)
        else:
            self._features = fdict

        self._init_features_dict()

    def close(self):
        """Uninitialize the class object."""

        _LOG.debug("Closing MSR %s (0x%x)", self.regname, self.regaddr)

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
        Ensure that each feature in the 'self._features' dictionary contains all required keys,
        setting missing keys to their default values.
        """

        for finfo in self._features.values():
            if "writable" not in finfo:
                finfo["writable"] = True

            for cpu in self._cpuinfo.get_cpus():
                if finfo["supported"][cpu]:
                    # The 'feature' is supported by at least one CPU, continue initializing it.
                    break
            else:
                continue

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
                        name_str = cast(str, name)
                        name_str = name_str.lower()
                        finfo["vals_nocase"][name_str] = code
                        finfo["rvals_nocase"][code] = name_str

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

        if typing.TYPE_CHECKING:
            self.features = cast(dict[str, FeatureTypedDict], features_copy)
        else:
            self.features = features_copy

    def _init_features_dict(self):
        """
        Initialize the 'features' dictionary with platform-specific information. The sub-classes
        can re-define this method and call individual '_init_features_dict_*()' methods.
        """

        self._init_supported_flag()
        self._init_features_dict_defaults()
        self._init_public_features_dict()

    def validate_feature_supported(self, fname: str, cpus: Sequence[int] | Literal["all"] = "all"):
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

    def is_feature_supported(self,
                             fname: str,
                             cpus: Sequence[int] | Literal["all"] = "all") -> bool:
        """
        Check if a feature is supported by all specified CPUs.

        Args:
            fname: Name of the feature to check.
            cpus: CPU numbers to check, or "all" to check all CPUs.

        Returns:
            bool: True if the feature is supported for all specified CPUs, False otherwise.
        """

        result: bool = True
        try:
            self.validate_feature_supported(fname, cpus=cpus)
        except ErrorNotSupported:
            result = False

        _LOG.debug("Feature '%s' (%s) is %s on CPUs %s", fname, self.msr_bits_str(fname),
                   "supported" if result else "not supported", cpus)

        return result

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
            A string in the format "<name> (<address>) bits (<start>:<end>)" or
            "<name> <address> bit <n>".

        Example:
            "MSR_PLATFORM_INFO (0xce) bits 55:48"
        """

        self._check_fname(fname)

        bits = self._features[fname].get("bits")
        if bits:
            if bits[0] == bits[1]:
                bits_str = f" bit {bits[0]}"
            else:
                bits_str = f" bits {bits[0]}:{bits[1]}"
        else:
            bits_str = ""

        return f"{self.regname} {self.regaddr:#x}{bits_str}"

    def _normalize_feature_value(self, fname: str, val: FeatureValueType) -> int:
        """
        Validate and normalize a feature value.

        Args:
            fname: The name of the feature whose value is being normalized.
            val: The value to normalize.

        Returns:
            The normalized value suitable for writing to the MSR register.
        """

        finfo = self._features[fname]

        if not finfo.get("vals"):
            return int(val)

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
            vals_dict = cast(dict[str, int], finfo["vals"])
            return vals_dict[val_str]

        if "vals_nocase" in finfo and val_str.lower() in finfo["vals_nocase"]:
            return finfo["vals_nocase"][val_str.lower()]

        vals_str = ", ".join([str(v) for v in finfo["vals"]])
        raise Error(f"Bad value '{val}' for the '{finfo['name']}' feature, use one of:\n  "
                    f"{vals_str}")

    def read_feature(self,
                     fname: str,
                     cpus: Sequence[int] | Literal["all"] = "all") -> \
                                                Generator[tuple[int, FeatureValueType], None, None]:
        """
        Read the value of a feature from the MSR for given CPUs and yield the results.

        Args:
            fname: Name of the feature to read.
            cpus: CPU numbers to read from, or the special value "all" to select all CPUs.

        Yields:
            tuple: A tuple (cpu, val), where 'cpu' is the CPU number and 'val' is the value of the
                   feature read from that CPU.
        """

        self.validate_feature_supported(fname, cpus=cpus)

        read_method_name = f"_get_{fname}"
        read_method: _ReadFeatureMethodType | None = getattr(self, read_method_name, None)

        _LOG.debug("Reading feature '%s' (%s) on CPUs %s",
                   fname, self.msr_bits_str(fname), self._cpuinfo.cpus_to_str(cpus))

        if read_method:
            # pylint: disable=not-callable
            for cpu, val in read_method(cpus=cpus):
                yield cpu, val
        else:
            bits = self._features[fname]["bits"]
            for cpu, val in self._msr.read_bits(self.regaddr, bits, cpus=cpus,
                                                    iosname=self._features[fname]["iosname"]):
                if "rvals" in self._features[fname]:
                    val = self._features[fname]["rvals"][cast(int, val)]
                yield cpu, val

    def read_cpu_feature(self, fname: str, cpu: int) -> FeatureValueType:
        """
        Read the value of a feature from for a given CPU and return the result.

        Args:
            fname: Name of the feature to read.
            cpu: CPU number to read the feature from.

        Returns:
            The value of the requested feature for the specified CPU.
        """

        val = None
        for _, val in self.read_feature(fname, cpus=(cpu,)):
            pass

        return val

    def is_feature_enabled(self, fname: str, cpus: Sequence[int] | Literal["all"] = "all") -> \
                                                            Generator[tuple[int, bool], None, None]:
        """
        Check whether a boolean feature is enabled for specified CPUs.

        Args:
            fname: Name of the feature to check.
            cpus: CPUs to check the feature on. Special value "all" selects all CPUs.

        Yields:
            tuple: A tuple (cpu, enabled), where:
                cpu: CPU number the feature was read from.
                enabled: True if the feature is enabled, False otherwise.
        """

        self.validate_feature_supported(fname, cpus=cpus)

        if self._features[fname]["type"] != "bool":
            raise Error(f"Feature '{fname}' is not boolean, use 'read_feature()' instead")

        _LOG.debug("Checking if feature '%s' (%s) is enabled on CPUs %s",
                   fname, self.msr_bits_str(fname), self._cpuinfo.cpus_to_str(cpus))

        for cpu, val in self.read_feature(fname, cpus=cpus):
            enabled = val in {"on", "enabled"}
            yield cpu, enabled

    def is_cpu_feature_enabled(self, fname, cpu):
        """
        Check if a CPU feature is enabled for a CPU.

        Args:
            fname: Name of the feature to check.
            cpu: CPU number to check the feature on.

        Returns:
            True if the feature is enabled for the specified CPU, False otherwise.
        """

        enabled = None
        for _, enabled in self.is_feature_enabled(fname, cpus=(cpu,)):
            pass

        return enabled

    def write_feature(self,
                      fname: str,
                      val: FeatureValueType,
                      cpus: Sequence[int] | Literal["all"] = "all"):
        """
        Write a feature value for the specified CPUs.

        Args:
            fname: Name of the feature to write.
            val: The value to write.
            cpus: CPU numbers to write the feature on. Special value "all" selects all CPUs.
        """

        self.validate_feature_supported(fname, cpus=cpus)
        val = self._normalize_feature_value(fname, val)

        _LOG.debug("Writing feature '%s' (%s) on CPUs %s, value: %s",
                   fname, self.msr_bits_str(fname), self._cpuinfo.cpus_to_str(cpus), val)

        finfo = self._features[fname]
        if not finfo["writable"]:
            fullname = finfo["name"]
            raise Error(f"Feature '{fullname}' can not be modified{self._pman.hostmsg}, it is "
                        f"read-only")

        set_method_name = f"_set_{fname}"
        set_method: _WriteFeatureMethodType | None = getattr(self, set_method_name, None)
        if set_method:
            # pylint: disable=not-callable
            set_method(val, cpus=cpus)
        else:
            self._msr.write_bits(self.regaddr, finfo["bits"], val, cpus=cpus,
                                 iosname=finfo["iosname"])

    def write_cpu_feature(self, fname: str, val: FeatureValueType, cpu: int):
        """
        Write a feature value for a specified CPU.

        Args:
            fname: Name of the feature to write.
            val: The value to write.
            cpu: CPU number to write the feature for.
        """

        self.write_feature(fname, val, cpus=(cpu,))

    def enable_feature(self,
                       fname: str,
                       enable: bool | str,
                       cpus: Sequence[int] | Literal["all"] = "all"):
        """
        Enable or disable a boolean feature for specified CPUs.

        Args:
            fname: Name of the feature to enable or disable.
            enable: Enable the feature if  True, "on", or "enable"; disable the feature if False,
                    "off", or "disable".
            cpus: CPU numbers to enable or disable the feature for. Special value "all" selects
                  all CPUs.
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
        Enable or disable a boolean feature for a specified CPU.

        Args:
            fname: Name of the feature to enable or disable.
            enable: Enable the feature if  True, "on", or "enable"; disable the feature if False,
                    "off", or "disable".
            cpu: CPU number to enable or disable the feature for.
        """

        self.enable_feature(fname, enable, cpus=(cpu,))
