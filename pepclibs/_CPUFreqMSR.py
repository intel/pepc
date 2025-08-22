# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability for reading and modifying CPU frequency settings via the 'MSR_HWP_REQUEST'
model-specific register (MSR).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import Generator, cast, Literal
import contextlib
from pepclibs import CPUInfo, CPUModels
from pepclibs._PropsClassBaseTypes import AbsNumsType
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Human
from pepclibs.helperlibs.Exceptions import ErrorNotSupported, ErrorOutOfRange, ErrorBadOrder

if typing.TYPE_CHECKING:
    from pepclibs.msr import MSR, FSBFreq, PMEnable, HWPRequest, HWPRequestPkg, PlatformInfo
    from pepclibs.msr import TurboRatioLimit, HWPCapabilities
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# A CPU frequency sysfs file type. Possible values:
#   - "min": a minimum CPU frequency file
#   - "max": a maximum CPU frequency file
#   - "current": a current CPU frequency file
_SysfsFileType = Literal["min", "max", "current"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqMSR(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and modify CPU frequency settings on Intel platforms supporting the
    'MSR_HWP_REQUEST' model-specific register (MSR).

    Public Methods:
        - get_min_freq(cpus): Yield (cpu, value) pairs for the minimum CPU frequency.
        - get_max_freq(cpus): Yield (cpu, value) pairs for the maximum CPU frequency.
        - set_min_freq(freq, cpus): Set the minimum frequency for specified CPUs.
        - set_max_freq(freq, cpus): Set the maximum frequency for specified CPUs.
        - get_base_freq(cpus): Yield (cpu, value) pairs for the base frequency.
        - get_min_oper_freq(cpus): Yield (cpu, value) pairs for the minimum operating frequency.
        - get_max_eff_freq(cpus): Yield (cpu, value) pairs for the maximum efficiency frequency.
        - get_max_turbo_freq(cpus): Yield (cpu, value) pairs for the maximum turbo frequency.
        - get_hwp(cpus): Yield (cpu, value) pairs indicating HWP on/off status.

    Notes:
        Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid and
        online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object for MSR access. Will be created if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access, used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo

        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._fsbfreq: FSBFreq.FSBFreq | None = None
        self._pmenable: PMEnable.PMEnable | None = None
        self._hwpreq: HWPRequest.HWPRequest | None = None
        self._hwpreq_pkg: HWPRequestPkg.HWPRequestPkg | None = None
        self._hwpcap: HWPCapabilities.HWPCapabilities | None = None
        self._platinfo: PlatformInfo.PlatformInfo | None = None
        self._trl: TurboRatioLimit.TurboRatioLimit | None = None

        self._pcore_cpus: set[int] = set()

        # Performance to frequency factor.
        self._perf_to_freq_factor: int = 0

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

        if self._cpuinfo.info["hybrid"]:
            self._init_scaling_factor()
            hybrid_cpus = self._cpuinfo.get_hybrid_cpus()
            self._pcore_cpus = set(hybrid_cpus["pcore"])

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_trl", "_platinfo", "_fsbfreq", "_pmenable", "_hwpreq", "_hwpreq_pkg",
                       "_hwpcap", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_msr(self) -> MSR.MSR:
        """
        Return an instance of the 'MSR.MSR' class.

        Returns:
            An initialized 'MSR.MSR' object.
        """

        if not self._msr:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_fsbfreq(self) -> FSBFreq.FSBFreq:
        """
        Return an instance of the 'FSBFreq.FSBFreq' class.

        Returns:
            The an initialized 'FSBFreq.FSBFreq' object.
        """

        if not self._fsbfreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import FSBFreq

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_pmenable(self) -> PMEnable.PMEnable:
        """
        Return an instance of the 'PMEnable.PMEnable' class.

        Returns:
            The an initialized 'PMEnable.PMEnable' object.
        """

        if not self._pmenable:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import PMEnable

            msr = self._get_msr()
            self._pmenable = PMEnable.PMEnable(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._pmenable

    def _get_bclks(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the bus clock speed for specified CPUs.

        Args:
            cpus: CPU numbers to get the bus clock speed for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the bus
            clock speed in Hz.

        Raises:
            ErrorNotSupported: If the CPU vendor is not Intel.
        """

        try:
            fsbfreq = self._get_fsbfreq()
        except ErrorNotSupported:
            if self._cpuinfo.info["vendor"] != "GenuineIntel":
                raise
            # Fall back to 100MHz bus clock speed.
            for cpu in cpus:
                yield cpu, 100000000
        else:
            for cpu, bclk in fsbfreq.read_feature("fsb", cpus=cpus):
                # Convert MHz to Hz.
                yield cpu, int(bclk * 1000000)

    def _get_bclk(self, cpu):
        """
        Retrieve the bus clock speed for the specified CPU.

        Args:
            cpu: CPU number to get the bus clock speed for.

        Returns:
            The bus clock speed in Hz for the given CPU.

        Raises:
            ErrorNotSupported: If the CPU vendor is not Intel.
        """

        _, val = next(self._get_bclks((cpu,)))
        return val

    def _get_hwpreq(self) -> HWPRequest.HWPRequest:
        """
        Return an instance of the 'HWPRequest.HWPRequest' class.

        Returns:
            The an initialized 'HWPRequest.HWPRequest' object.
        """

        if not self._hwpreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequest

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self) -> HWPRequestPkg.HWPRequestPkg:
        """
        Return an instance of the 'HWPRequestPkg.HWPRequestPkg' class.

        Returns:
            The an initialized 'HWPRequestPkg.HWPRequestPkg' object.
        """

        if not self._hwpreq_pkg:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequestPkg

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)

        return self._hwpreq_pkg

    def _perf_to_freq(self, cpu: int, perf: int, bclk: int) -> int:
        """
        Convert performance level units to CPU frequency in Hz.

        On non-hybrid Intel platforms, MSR registers such as 'MSR_HWP_REQUEST' use frequency ratio
        units (CPU frequency in Hz divided by 100 MHz bus clock). On hybrid Intel platforms (e.g.,
        Alder Lake), the MSRs operate with abstract performance level units on P-cores. This
        function handles both cases and returns the corresponding CPU frequency.

        Args:
            cpu: The CPU number.
            perf: The performance level value to convert to frequency.
            bclk: Bus clock frequency in Hz.

        Returns:
            CPU frequency in Hz.
        """

        if self._cpuinfo.info["hybrid"] and cpu in self._pcore_cpus:
            # In HWP mode, the Linux 'intel_pstate' driver changes CPU frequency by programming
            # 'MSR_HWP_REQUEST'.
            # On many Intel platforms,the MSR is programmed in terms of frequency ratio (frequency
            # divided by 100MHz). But on hybrid Intel platform (e.g., Alder Lake), the MSR works in
            # terms of platform-dependent abstract performance units on P-cores. Convert the
            # performance units to CPU frequency in Hz.
            freq = perf * self._perf_to_freq_factor

            # Round the frequency down to bus clock.
            # * Why rounding? CPU frequency changes in bus-clock increments.
            # * Why rounding down? Following how Linux 'intel_pstate' driver example.
            return freq - (freq % bclk)

        return perf * bclk

    def _get_freq_msr(self,
                      ftype: _SysfsFileType,
                      cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum or maximum CPU frequency for specified CPUs.

        Args:
            ftype: The CPU frequency sysfs file type.
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding minimum or maximum frequency in Hz.

        Raises:
            ErrorNotSupported: If the 'MSR_HWP_REQUEST' model specific register is not supported.
        """

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{ftype}_perf"

        run_again = False
        yielded_cpus = set()

        hwpreq = self._get_hwpreq()
        hwpreq_iter = hwpreq.read_feature(feature_name, cpus=cpus)
        bclks_iter = self._get_bclks(cpus)
        for (cpu1, bclk), (cpu2, perf) in zip(bclks_iter, hwpreq_iter):
            assert cpu1 == cpu2

            perf = cast(int, perf)
            if hwpreq.is_cpu_feature_pkg_controlled(feature_name, cpu1):
                run_again = True
                break
            yielded_cpus.add(cpu1)

            freq = self._perf_to_freq(cpu1, perf, bclk)
            _LOG.debug("Read CPU %d frequency from %s (%#x): %d Hz. Perf = %d, bclk = %d",
                       cpu1, hwpreq.regname, hwpreq.regaddr, freq, perf, bclk )
            yield cpu1, freq

        if not run_again:
            # Nothing uses package control, nothing more to do.
            return

        left_cpus = []
        for cpu in cpus:
            if cpu not in yielded_cpus:
                left_cpus.append(cpu)

        hwpreq_pkg = self._get_hwpreq_pkg()
        hwpreq_iter = hwpreq.read_feature(feature_name, cpus=left_cpus)
        hwpreq_pkg_iter = hwpreq_pkg.read_feature(feature_name, cpus=left_cpus)
        bclks_iter = self._get_bclks(left_cpus)

        iterator = zip(bclks_iter, hwpreq_iter, hwpreq_pkg_iter)
        for (_, bclk), (cpu1, perf), (cpu2, perf_pkg) in iterator:
            assert cpu1 == cpu2
            perf = cast(int, perf)
            perf_pkg = cast(int, perf_pkg)

            if hwpreq.is_cpu_feature_pkg_controlled(feature_name, cpu1):
                val = perf_pkg
            else:
                val = perf

            freq = self._perf_to_freq(cpu1, val, bclk)
            _LOG.debug("Read CPU %d frequency from %s (%#x): %d Hz. Perf = %d, bclk = %d",
                       cpu1, hwpreq_pkg.regname, hwpreq_pkg.regaddr, freq, perf, bclk )
            yield cpu1, freq

    def get_min_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum CPU frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding minimum frequency in Hz.

        Raises:
            ErrorNotSupported: If the 'MSR_HWP_REQUEST' model specific register is not supported.
        """

        yield from self._get_freq_msr("min", cpus)

    def get_max_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum CPU frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding maximum frequency in Hz.

        Raises:
            ErrorNotSupported: If the 'MSR_HWP_REQUEST' model specific register is not supported.
        """

        yield from self._get_freq_msr("max", cpus)

    def _validate_freq(self, freq: int, ftype: _SysfsFileType, cpus: AbsNumsType):
        """
        Validate that a CPU frequency value is within the acceptable range.

        Args:
            freq: The CPU frequency value to validate, in Hz.
            ftype: The CPU frequency sysfs file type.
            cpus: CPU numbers to validate the frequency for.

        Raises:
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        min_limit_iter = self.get_min_oper_freq(cpus)
        max_limit_iter = self.get_max_turbo_freq(cpus)

        for (cpu, min_freq_limit), (_, max_freq_limit) in zip(min_limit_iter, max_limit_iter):
            if freq < min_freq_limit or freq > max_freq_limit:
                name = f"{ftype} CPU {cpu} frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                min_limit_str = Human.num2si(min_freq_limit, unit="Hz", decp=4)
                max_limit_str = Human.num2si(max_freq_limit, unit="Hz", decp=4)
                raise ErrorOutOfRange(f"{name} value of '{freq_str}' for is out of range"
                                      f"{self._pman.hostmsg}, must be within [{min_limit_str}, "
                                      f"{max_limit_str}]")

        if ftype == "min":
            for cpu, max_freq in self._get_freq_msr("max", cpus):
                if freq > max_freq:
                    name = f"{ftype} CPU {cpu} frequency"
                    freq_str = Human.num2si(freq, unit="Hz", decp=4)
                    max_freq_str = Human.num2si(max_freq, unit="Hz", decp=4)
                    raise ErrorBadOrder(f"{name} value of '{freq_str}' is greater than the "
                                        f"currently configured max frequency of {max_freq_str}")
        else:
            for cpu, min_freq in self._get_freq_msr("min", cpus):
                if freq < min_freq:
                    name = f"{ftype} CPU {cpu} frequency"
                    freq_str = Human.num2si(freq, unit="Hz", decp=4)
                    min_freq_str = Human.num2si(min_freq, unit="Hz", decp=4)
                    raise ErrorBadOrder(f"{name} value of '{freq_str}' is less than the currently "
                                        f"configured min frequency of {min_freq_str}")

    def _set_freq_msr(self, freq: int, ftype: _SysfsFileType, cpus: AbsNumsType):
        """
        Set the CPU frequency for specified CPUs using the 'MSR_HWP_REQUEST' model specific
        register.

        Args:
            freq: The frequency value to set, in Hz.
            ftype: The CPU frequency sysfs file type.
            cpus: CPU numbers to set the frequency for.

        Raises:
            ErrorNotSupported: If disabling package control via 'MSR_HWP_REQUEST' is not supported.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{ftype}_perf"

        hwpreq = self._get_hwpreq()

        # Disable package control.
        pkg_control_cpus = []
        with contextlib.suppress(ErrorNotSupported):
            for cpu, enabled in hwpreq.is_feature_enabled("pkg_control"):
                if enabled:
                    pkg_control_cpus.append(cpu)
            hwpreq.write_feature(f"{feature_name}_valid", "on", cpus=pkg_control_cpus)

        self._validate_freq(freq, ftype, cpus)

        # Prepare the values dictionary, which maps each value to the list of CPUs to write this
        # value to.
        vals: dict[int, list[int]] = {}
        for cpu, bclk in self._get_bclks(cpus):
            if cpu in self._pcore_cpus:
                perf = int((freq + self._perf_to_freq_factor - 1) / self._perf_to_freq_factor)
            else:
                perf = freq // bclk
            if perf not in vals:
                vals[perf] = []
            vals[perf].append(cpu)

        for val, val_cpus in vals.items():
            hwpreq.write_feature(feature_name, val, cpus=val_cpus)

    def set_min_freq(self, freq: int, cpus: AbsNumsType):
        """
        Set minimum frequency for CPUs in 'cpus' via the 'MSR_HWP_REQUEST' model specific register.

        Args:
            freq: The minimum frequency value to set, in Hz.
            cpus: CPU numbers to set minimum frequency for.

        Raises:
            ErrorNotSupported: If setting the frequency via 'MSR_HWP_REQUEST' is not supported.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        self._set_freq_msr(freq, "min", cpus)

    def set_max_freq(self, freq: int, cpus: AbsNumsType):
        """
        Set maximum frequency for CPUs in 'cpus' via the 'MSR_HWP_REQUEST' model specific register.

        Args:
            freq: The maximum frequency value to set, in Hz.
            cpus: CPU numbers to set maximum frequency for.

        Raises:
            ErrorNotSupported: If setting the frequency via 'MSR_HWP_REQUEST' is not supported.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        self._set_freq_msr(freq, "max", cpus)

    def _get_hwpcap(self) -> HWPCapabilities.HWPCapabilities:
        """
        Return an instance of the 'HWPCapabilities.HWPCapabilities' class.

        Returns:
            The an initialized 'HWPCapabilities.HWPCapabilities' object.
        """

        if not self._hwpcap:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPCapabilities

            msr = self._get_msr()
            self._hwpcap = HWPCapabilities.HWPCapabilities(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)

        return self._hwpcap

    def _get_platinfo(self) -> PlatformInfo.PlatformInfo:
        """
        Return an instance of the 'PlatformInfo.PlatformInfo' class.

        Returns:
            The an initialized 'PlatformInfo.PlatformInfo' object.
        """

        if not self._platinfo:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import PlatformInfo

            msr = self._get_msr()
            self._platinfo = PlatformInfo.PlatformInfo(pman=self._pman, cpuinfo=self._cpuinfo,
                                                       msr=msr)
        return self._platinfo

    def _get_trl(self) -> TurboRatioLimit.TurboRatioLimit:
        """
        Return an instance of the 'TurboRatioLimit.TurboRatioLimit' class.

        Returns:
            The an initialized 'TurboRatioLimit.TurboRatioLimit' object.
        """

        if not self._trl:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import TurboRatioLimit

            msr = self._get_msr()
            self._trl = TurboRatioLimit.TurboRatioLimit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=msr)
        return self._trl

    def _get_platinfo_freq(self,
                           fname: str,
                           cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency for the specified CPUs using the 'MSR_PLATFORM_INFO' model
        specific register.

        Args:
            fname: Name of the feature to read from 'MSR_PLATFORM_INFO'.
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding frequency in Hz.
        """

        if not cpus:
            return

        platinfo = self._get_platinfo()
        bclks_iter = self._get_bclks(cpus)
        platinfo_iter = platinfo.read_feature(fname, cpus=cpus)

        for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, platinfo_iter):
            assert cpu1 == cpu2
            ratio = cast(int, ratio)
            yield cpu1, ratio * bclk

    def _get_hwpcap_freq(self,
                         fname: str,
                         cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency for the specified CPUs using the 'MSR_HPW_CAPABILITIES'
        model specific register.

        Args:
            fname: Name of the feature to read from 'MSR_HWP_CAPABILITIES'.
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuples of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding frequency in Hz.
        """

        if not cpus:
            return

        hwpcap = self._get_hwpcap()
        bclks_iter = self._get_bclks(cpus)
        hwpcap_iter = hwpcap.read_feature(fname, cpus=cpus)

        for (cpu1, bclk), (cpu2, perf) in zip(bclks_iter, hwpcap_iter):
            assert cpu1 == cpu2
            perf = cast(int, perf)
            yield cpu1, self._perf_to_freq(cpu1, perf, bclk)

    def get_base_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.

        Raises:
            ErrorNotSupported: If MSRs are not supported.
        """

        yielded = False
        try:
            for cpu, freq in self._get_hwpcap_freq("base_perf", cpus):
                yielded = True
                yield cpu, freq
        except ErrorNotSupported:
            if yielded:
                raise
        else:
            return

        yield from self._get_platinfo_freq("max_non_turbo_ratio", cpus)

    def get_min_oper_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum operating frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum operating frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the minimum
            operating frequency in Hz.

        Raises:
            ErrorNotSupported: If MSRs are not supported.
        """

        yield from self._get_platinfo_freq("min_oper_ratio", cpus)

    def get_max_eff_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum efficiency frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum efficiency frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            efficiency frequency in Hz.

        Raises:
            ErrorNotSupported: If MSRs are not supported.
        """

        yielded = False
        try:
            for cpu, freq in self._get_hwpcap_freq("eff_perf", cpus):
                yielded = True
                yield cpu, freq
        except ErrorNotSupported:
            if yielded:
                raise
        else:
            return

        yield from self._get_platinfo_freq("max_eff_ratio", cpus)

    def _get_max_turbo_freq_trl(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Yield (cpu, frequency) tuples by reading the maximum turbo frequency from the
        'MSR_TURBO_RATIO_LIMIT' register for the specified CPUs.

        Retrieve and yield the maximum turbo frequency for specified CPUs as follows:
          - Attempt to read the 'max_1c_turbo_ratio' feature for each CPU.
          - If not supported, fall back to reading the 'max_g0_turbo_ratio' feature.

        Args:
            cpus: CPU numbers to get the maximum turbo frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            turbo frequency in Hz.

        Raises:
            ErrorNotSupported: If 'MSR_TURBO_RATIO_LIMIT' is not supported.
        """

        if not cpus:
            return

        yielded = False
        trl = self._get_trl()
        trl_iter = trl.read_feature("max_1c_turbo_ratio", cpus=cpus)
        bclks_iter = self._get_bclks(cpus)

        try:
            for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, trl_iter):
                assert cpu1 == cpu2
                ratio = cast(int, ratio)
                yielded = True
                yield cpu1, ratio * bclk
        except ErrorNotSupported as err1:
            if yielded:
                raise
            trl_iter = trl.read_feature("max_g0_turbo_ratio", cpus=cpus)
            bclks_iter = self._get_bclks(cpus)
            try:
                # In this case 'MSR_TURBO_RATIO_LIMIT' encodes max. turbo ratio for groups of cores.
                # We can safely assume that group 0 will correspond to max. 1-core turbo, so we do
                # not need to look at 'MSR_TURBO_RATIO_LIMIT1'.
                for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, trl_iter):
                    assert cpu1 == cpu2
                    ratio = cast(int, ratio)
                    yield cpu1, ratio * bclk
            except ErrorNotSupported as err2:
                _LOG.warn_once("Module 'TurboRatioLimit' doesn't support "
                               "'MSR_TURBO_RATIO_LIMIT' for CPU '%s'%s\nPlease, contact project "
                               "maintainers.", self._cpuinfo.cpudescr, self._pman.hostmsg)
                raise ErrorNotSupported(f"{err1}\n{err2}") from err2

    def get_max_turbo_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum 1-core turbo frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum 1-core turbo frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            1-core turbo frequency in Hz.

        Raises:
            ErrorNotSupported: If the MSRs are not supported.
        """

        yielded = False
        try:
            for cpu, freq in self._get_hwpcap_freq("max_perf", cpus):
                yielded = True
                yield cpu, freq
        except ErrorNotSupported:
            if yielded:
                raise
        else:
            return

        yield from self._get_max_turbo_freq_trl(cpus)

    def get_hwp(self, cpus: AbsNumsType) -> Generator[tuple[int, bool], None, None]:
        """
        Yield the hardware power management (HWP) status for specified CPUs.

        Args:
            cpus: CPU numbers to get the HWP status for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is the HWP status (True if
            HWP is enabled, False otherwise).

        Raises:
            ErrorNotSupported: If the platform does not support HWP.
        """

        pmenable = self._get_pmenable()
        yield from pmenable.is_feature_enabled("hwp", cpus=cpus)

    def _init_scaling_factor(self):
        """
        Initialize the performance-to-frequency scaling factor for hybrid platforms.
        """

        if self._cpuinfo.info["vfm"] in CPUModels.CPU_GROUPS["METEORLAKE"]:
            self._perf_to_freq_factor = 80000000
        elif self._cpuinfo.info["vfm"] in CPUModels.CPU_GROUPS["LUNARLAKE"]:
            self._perf_to_freq_factor = 86957000
        else:
            # ADL and RPL.
            self._perf_to_freq_factor = 78741000
