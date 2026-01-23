# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of retrieving and setting P-state related properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pepclibs import _PropsClassBase
from pepclibs.PStatesVars import PROPS
from pepclibs.helperlibs import Human, ClassHelpers, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed

from pepclibs._PropsClassBase import ErrorTryAnotherMechanism

if typing.TYPE_CHECKING:
    from typing import Generator, cast, Sequence, NoReturn, Union
    from pepclibs.msr import MSR, FSBFreq, PlatformInfo
    from pepclibs import _CPUFreqSysfs, _CPPCSysfs, _HWPMSR
    from pepclibs import _SysfsIO, EPP, EPB, CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs._PropsTypes import PropertyValueType, MechanismNameType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class PStates(_PropsClassBase.PropsClassBase):
    """
    Provide API for managing platform settings related to P-states. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """Refer to 'PropsClassBase.__init__()'."""

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._eppobj: EPP.EPP | None = None
        self._epbobj: EPB.EPB | None = None
        self._fsbfreq: FSBFreq.FSBFreq | None = None
        self._platinfo: PlatformInfo.PlatformInfo | None = None

        self._cpufreq_sysfs_obj: _CPUFreqSysfs.CPUFreqSysfs | None = None
        self._cppc_sysfs_obj: _CPPCSysfs.CPPCSysfs | None = None
        self._hwp_msr_obj: _HWPMSR.HWPMSR | None = None

        self._perf2freq: dict[int, int] = {}

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_eppobj", "_epbobj", "_platinfo", "_fsbfreq", "_cpufreq_sysfs_obj",
                       "_cppc_sysfs_obj", "_hwp_msr_obj")
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()

    def _get_fsbfreq(self) -> FSBFreq.FSBFreq:
        """
        Get an 'FSBFreq' object.

        Returns:
            An instance of 'FSBFreq.FSBFreq'.
        """

        if not self._fsbfreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import FSBFreq

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_platinfo(self) -> PlatformInfo.PlatformInfo:
        """
        Get an 'PlatformInfo' object.

        Returns:
            An instance of 'PlatformInfo.PlatformInfo'.
        """

        if not self._platinfo:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import PlatformInfo

            msr = self._get_msr()
            self._platinfo = PlatformInfo.PlatformInfo(pman=self._pman, cpuinfo=self._cpuinfo,
                                                       msr=msr)

        return self._platinfo

    def _get_eppobj(self) -> EPP.EPP:
        """
        Get an 'EPP' object.

        Returns:
            An instance of 'EPP.EPP'.
        """

        if not self._eppobj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import EPP

            msr = self._get_msr()
            self._eppobj = EPP.EPP(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._eppobj

    def _get_epbobj(self) -> EPB.EPB:
        """
        Get an 'EPB' object.

        Returns:
            An instance of 'EPB.EPB'.
        """

        if not self._epbobj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import EPB

            msr = self._get_msr()
            self._epbobj = EPB.EPB(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr,
                                   enable_cache=self._enable_cache)

        return self._epbobj

    def _get_cpufreq_sysfs_obj(self) -> _CPUFreqSysfs.CPUFreqSysfs:
        """
        Get an 'CPUFreqSysfs' object.

        Returns:
            An instance of '_CPUFreqSysfs.CPUFreqSysfs'.
        """

        if not self._cpufreq_sysfs_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreqSysfs

            msr = self._get_msr()
            sysfs_io = self._get_sysfs_io()
            self._cpufreq_sysfs_obj = _CPUFreqSysfs.CPUFreqSysfs(cpuinfo=self._cpuinfo,
                                                                 pman=self._pman,
                                                                 msr=msr, sysfs_io=sysfs_io,
                                                                 enable_cache=self._enable_cache)
        return self._cpufreq_sysfs_obj

    def _get_cppc_sysfs_obj(self) -> _CPPCSysfs.CPPCSysfs:
        """
        Get a 'CPPCSysfs' object.

        Returns:
            An instance of '_CPPCSysfs.CPPCSysfs'.
        """

        if not self._cppc_sysfs_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPPCSysfs

            sysfs_io = self._get_sysfs_io()
            self._cppc_sysfs_obj = _CPPCSysfs.CPPCSysfs(cpuinfo=self._cpuinfo, pman=self._pman,
                                                        sysfs_io=sysfs_io,
                                                        enable_cache=self._enable_cache)
        return self._cppc_sysfs_obj

    def _get_hwp_msr_obj(self) -> _HWPMSR.HWPMSR:
        """
        Get an 'HWPMSR' object.

        Returns:
            An instance of '_HWPMSR.HWPMSR'.
        """

        if not self._hwp_msr_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _HWPMSR

            msr = self._get_msr()
            self._hwp_msr_obj = _HWPMSR.HWPMSR(cpuinfo=self._cpuinfo, pman=self._pman, msr=msr,
                                               enable_cache=self._enable_cache)
        return self._hwp_msr_obj

    def _get_bclks_cpus(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield bus clock speed for the specified CPUs using the MSR mechanism.

        Args:
            cpus: CPU numbers to retrieve bus clock speed for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is the bus clock speed in
            Hz.
        """

        try:
            fsbfreq = self._get_fsbfreq()
        except ErrorNotSupported:
            if not self._is_intel:
                raise
            # Fall back to 100MHz bus clock speed.
            for cpu in cpus:
                yield cpu, 100000000
        else:
            for cpu, bclk in fsbfreq.read_feature_int("fsb", cpus=cpus):
                # Convert MHz to Hz.
                yield cpu, bclk * 1000000

    def _get_bclks_dies(self, dies: RelNumsType) -> Generator[tuple[int, int, int], None, None]:
        """
        Retrieve and yield bus clock speed for the specified dies using the MSR mechanism.

        Args:
            dies: Dictionary mapping package numbers to collections of die numbers.

        Yields:
            Tuples of (package, die, val), where 'package' is the package number, 'die' is the die
            number, and 'val' is the bus clock speed in Hz for the specified die.
        """

        try:
            self._get_fsbfreq()
        except ErrorNotSupported:
            if not self._is_intel:
                raise
            # Fall back to 100MHz bus clock speed.
            for package, pkg_dies in dies.items():
                for die in pkg_dies:
                    yield package, die, 100000000
        else:
            # Only legacy platforms support 'MSR_FSB_FREQ'.
            raise Error("BUG: Not implemented, contact project maintainers")

    def _get_bclk(self, cpu: int) -> int:
        """
        Return the bus clock speed in Hz for the specified CPU.

        Args:
            cpu: CPU number.

        Returns:
            Bus clock speed in Hz.
        """

        _, val = next(self._get_bclks_cpus((cpu,)))
        return val

    def _get_epp(self,
                 cpus: AbsNumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield EPP values for the specified CPUs using the specified mechanism.

        Args:
            cpus: CPU numbers to retrieve EPP values for.
            mname: Mechanism name to use for retrieving EPP values.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its EPP value.

        Notes:
            - The reason why the yielded EPP values are strings is because the corresponding sysfs
              file may contain a policy name, which is a string, or a numeric value, which is also
              yielded as a string for simplicity.
        """

        for cpu, val, _ in self._get_eppobj().get_vals(cpus=cpus, mnames=(mname,)):
            yield cpu, val

    def _get_epb(self,
                 cpus: AbsNumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield EPB values for the specified CPUs using the specified mechanism.

        Args:
            cpus: CPU numbers to retrieve EPB values for.
            mname: Mechanism name to use for retrieving EPB values.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its EPB value.
        """

        for cpu, val, _ in self._get_epbobj().get_vals(cpus=cpus, mnames=(mname,)):
            yield cpu, val

    def _get_hwp(self,
                 cpus: AbsNumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, bool], None, None]:
        """
        Retrieve and yield the hardware power management (HWP) status for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve HWP status for.
            mname: Mechanism name to use for retrieving the HWP status.

        Yields:
            Tuples of (cpu, status), where 'cpu' is the CPU number and 'status' is its HWP status.
        """

        if mname != "msr":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'hwp'")

        hwp_msr_obj = self._get_hwp_msr_obj()
        yield from hwp_msr_obj.get_hwp(cpus=cpus)

    def _get_freq_sysfs(self,
                        pname: str,
                        cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency values for the specified CPUs using the sysfs mechanism.

        Depending on the 'pname' argument, yield either the minimum, maximum, minimum limit, or
        maximum limit CPU frequency for the given CPUs.

        Args:
            pname: Name of the property to retrieve. Supported values are "min_freq", "max_freq",
                   "min_freq_limit", and "max_freq_limit".
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        elif pname == "min_freq_limit":
            yield from cpufreq_obj.get_min_freq_limit(cpus)
        elif pname == "max_freq_limit":
            yield from cpufreq_obj.get_max_freq_limit(cpus)
        elif pname == "base_freq":
            yield from cpufreq_obj.get_base_freq(cpus)
        else:
            raise Error(f"BUG: Unexpected CPU frequency property '{pname}'")

    def _get_base_freq(self,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for the specified CPUs using the given mechanism.

        Args:
            cpus: CPU numbers to retrieve base frequency for.
            mname: Name of the mechanism to use for retrieving the base frequency.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its base frequency.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'base_freq'")

        yield from self._get_freq_sysfs("base_freq", cpus)

    def _get_fixed_base_freq(self,
                             cpus: AbsNumsType,
                             mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the fixed base frequency for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve fixed base frequency for.
            mname: Name of the mechanism to use for retrieving the fixed base frequency.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its fixed base
            frequency.
        """

        if mname != "msr":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'fixed_base_freq'")

        platinfo = self._get_platinfo()

        platinfo_iter = platinfo.read_feature_int("max_non_turbo_ratio", cpus=cpus)
        bclks_iter = self._get_bclks_cpus(cpus)

        iter_zip = zip(platinfo_iter, bclks_iter)
        if typing.TYPE_CHECKING:
            iterator = cast(Generator[tuple[tuple[int, int], tuple[int, int]], None, None],
                            iter_zip)
        else:
            iterator = iter_zip

        for (cpu, base_freq), (_, bclk) in iterator:
            # 'base_freq' is given in MHz, convert it to Hz.
            yield cpu, base_freq * bclk

    def _get_min_max_freq(self,
                          pname: str,
                          cpus: AbsNumsType,
                          mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum or maximum CPU frequency for the specified CPUs using the
        specified mechanism.

        Args:
            pname: Name of the property to retrieve. Supported values are "min_freq", "max_freq".
            cpus: CPU numbers to retrieve frequency values for.
            mname: Name of the mechanism to use for retrieving the frequency (e.g., "sysfs").

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property '{pname}'")

        yield from self._get_freq_sysfs(pname, cpus)

    def _get_min_max_freq_limit(self,
                                pname: str,
                                cpus: AbsNumsType,
                                mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield min or max CPU frequency limits for the specified CPUs using the
        specified mechanism.

        Args:
            pname: Property name to retrieve ("min_freq_limit" or "max_freq_limit").
            cpus: CPU numbers to retrieve frequency values for.
            mname: Name of the mechanism to use for retrieving the frequency limits.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency limit in
            Hz.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property '{pname}'")

        yield from self._get_freq_sysfs(pname, cpus)

    def _get_frequencies_intel(self,
                               cpus: AbsNumsType) -> Generator[tuple[int, list[int]], None, None]:
        """
        Retrieve and yield available CPU frequencies for the specified CPUs using the 'intel_pstate'
        driver.

        Args:
            cpus: CPU numbers to retrieve frequencies for.

        Yields:
            Tuple of (cpu, freqs), where 'cpu' is the CPU number and 'freqs' is a list of available
            frequencies in Hz for that CPU.

        Raises:
            ErrorNotSupported: If the CPU frequency driver is not 'intel_pstate'.
        """

        driver_iter = self._get_prop_cpus_mnames("driver", cpus, self._props["driver"]["mnames"])
        min_freq_iter = self._get_prop_cpus_mnames("min_freq", cpus,
                                                   self._props["min_freq"]["mnames"])
        max_freq_iter = self._get_prop_cpus_mnames("max_freq", cpus,
                                                   self._props["max_freq"]["mnames"])
        bclks_iter = self._get_bclks_cpus(cpus)

        iter_zip = zip(driver_iter, min_freq_iter, max_freq_iter, bclks_iter)
        if typing.TYPE_CHECKING:
            iterator = cast(Generator[tuple[tuple[int, str], tuple[int, int], tuple[int, int],
                                    tuple[int, int]], None, None], iter_zip)
        else:
            iterator = iter_zip

        for (cpu, driver), (_, min_freq), (_, max_freq), (_, bclk) in iterator:
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"Unsupported driver '{driver}': Only 'intel_pstate' was "
                                        f"verified to accept any frequency value that is multiple "
                                        f"of bus clock")

            freqs: list[int] = []
            freq = min_freq
            while freq <= max_freq:
                freqs.append(freq)
                freq += bclk

            yield cpu, freqs

    def _get_frequencies(self,
                         cpus: AbsNumsType,
                         mname: MechanismNameType) -> Generator[tuple[int, list[int]], None, None]:
        """
        Retrieve and yield available CPU frequencies for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve frequencies for.
            mname: Name of the mechanism to use for retrieving frequencies.

        Yields:
            Tuples of (cpu, freqs), where 'cpu' is the CPU number and 'freqs' is a list of available
            frequencies in Hz for that CPU.
        """

        if mname == "sysfs":
            cpufreq_obj = self._get_cpufreq_sysfs_obj()
            for cpu, freq in cpufreq_obj.get_available_frequencies(cpus):
                yield cpu, freq
            return

        if mname == "doc":
            yield from self._get_frequencies_intel(cpus)
            return

        raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'frequencies'")

    def _get_bus_clock(self,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the bus clock speed for the specified CPUs using the given mechanism.

        Args:
            cpus: CPU numbers to retrieve bus clock speed for.
            mname: Name of the mechanism to use for retrieving the bus clock speed.

        Yields:
            Tuples of (cpu, bus_clock_speed), where 'cpu' is the CPU identifier and
            'bus_clock_speed' is the bus clock speed in Hz.

        Raises:
            ErrorNotSupported: If the mechanism is not supported for the CPU model or vendor.
            ErrorTryAnotherMechanism: If the 'doc' mechanism is not available and 'msr' should be
                                      used.
        """

        if mname == "msr":
            for cpu, val in self._get_fsbfreq().read_feature_int("fsb", cpus=cpus):
                yield cpu, val * 1000000
        elif mname == "doc":
            try:
                self._get_fsbfreq()
            except ErrorNotSupported:
                if not self._is_intel:
                    raise ErrorNotSupported(f"Unsupported CPU model '{self._cpuinfo.cpudescr}"
                                            f"{self._pman.hostmsg}") from None
                for cpu in cpus:
                    # Modern Intel platforms use 100MHz bus clock.
                    yield cpu, 100000000
                return
            raise ErrorTryAnotherMechanism(f"Use the 'msr' mechanism for {self._cpuinfo.cpudescr}")
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'bus_clock'")

    def _get_cppc_perf_or_freq(self,
                               pname: str,
                               cpus: AbsNumsType,
                               mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPPC performance or frequency values for the specified CPUs.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve CPPC performance or frequency values for.
            mname: Name of the mechanism to use for retrieving CPPC performance or frequency values
                   (must be "sysfs").

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its CPPC
            performance or frequency value.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property '{pname}'")

        cppc_sysfs_obj = self._get_cppc_sysfs_obj()
        if pname == "cppc_lowest_perf":
            yield from cppc_sysfs_obj.get_lowest_perf(cpus)
        elif pname == "cppc_lowest_nonlinear_perf":
            yield from cppc_sysfs_obj.get_lowest_nonlinear_perf(cpus)
        elif pname == "cppc_guaranteed_perf":
            yield from cppc_sysfs_obj.get_guaranteed_perf(cpus)
        elif pname == "cppc_nominal_perf":
            yield from cppc_sysfs_obj.get_nominal_perf(cpus)
        elif pname == "cppc_highest_perf":
            yield from cppc_sysfs_obj.get_highest_perf(cpus)
        elif pname == "cppc_nominal_freq":
            yield from cppc_sysfs_obj.get_nominal_freq(cpus)
        else:
            raise Error(f"BUG: Unexpected CPPC property '{pname}'")

    def _get_hwp_perf(self,
                      pname: str,
                      cpus: AbsNumsType,
                      mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield HWP performance values for the specified CPUs.

        Args:
            pname: Name of the property to retrieve.
            cpus: CPU numbers to retrieve HWP performance values for.
            mname: Name of the mechanism to use for retrieving HWP performance values (must be
                   "msr").

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its HWP
            performance value.
        """

        if mname != "msr":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property '{pname}'")

        hwp_msr_obj = self._get_hwp_msr_obj()

        if pname == "hwp_lowest_perf":
            yield from hwp_msr_obj.get_lowest_perf(cpus)
        elif pname == "hwp_efficient_perf":
            yield from hwp_msr_obj.get_efficient_perf(cpus)
        elif pname == "hwp_guaranteed_perf":
            yield from hwp_msr_obj.get_guaranteed_perf(cpus)
        elif pname == "hwp_highest_perf":
            yield from hwp_msr_obj.get_highest_perf(cpus)
        else:
            raise Error(f"BUG: Unexpected HWP property '{pname}'")

    def _get_turbo(self,
                   cpus: AbsNumsType,
                   mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the turbo status (on/off) for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve turbo status for.
            mname: Name of the mechanism to use for retrieving turbo status.

        Yields:
            Tuples of (cpu, status), where 'cpu' is the CPU number and 'status' is its turbo status
            ("on" or "off").
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'turbo'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_turbo(cpus)

    def _get_driver(self,
                    cpus: AbsNumsType,
                    mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the Linux CPU frequency driver name for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve driver names for.
            mname: Name of the mechanism to use for retrieving driver names.

        Yields:
            Tuples of (cpu, driver), where 'cpu' is the CPU number and 'driver' is its driver name.
            The driver name is obtained from the sysfs interface.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'driver'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_driver(cpus)

    def _get_intel_pstate_mode(self,
                               cpus: AbsNumsType,
                               mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the 'intel_pstate' mode name for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve 'intel_pstate' mode names for.
            mname: Name of the mechanism to use for retrieving 'intel_pstate' mode names.

        Yields:
            Tuples of (cpu, mode), where 'cpu' is the CPU number and 'mode' is its 'intel_pstate'
            mode name. The mode name is obtained from the sysfs interface.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'intel_pstate_mode'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_intel_pstate_mode(cpus)

    def _get_governor(self,
                      cpus: AbsNumsType,
                      mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the current CPU frequency governor for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve governor names for.
            mname: Name of the mechanism to use for retrieving governor names.

        Yields:
            Tuples of (cpu, governor), where 'cpu' is the CPU number and 'governor' is its current
            CPU frequency governor. The governor name is obtained from the sysfs interface.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'governor'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_governor(cpus)

    def _get_governors(self,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, list[str]], None, None]:
        """
        Retrieve and yield available CPU frequency governors for the specified CPUs.

        Args:
            cpus: CPU numbers to retrieve available governors for.
            mname: Name of the mechanism to use for retrieving governor names.

        Yields:
            Tuples of (cpu, governors), where 'cpu' is the CPU number and 'governors' is a list of
            available governor names (strings).
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'governors'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_available_governors(cpus)

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """Refer to 'PropsClassBase._get_prop_cpus()'."""

        _LOG.debug("Getting property '%s' using mechanism '%s', cpus: %s",
                   pname, mname, self._cpuinfo.cpus_to_str(cpus))

        if pname == "epp":
            yield from self._get_epp(cpus, mname)
        elif pname == "epb":
            yield from self._get_epb(cpus, mname)
        elif pname == "hwp":
            yield from self._get_hwp(cpus, mname)
        elif pname == "base_freq":
            yield from self._get_base_freq(cpus, mname)
        elif pname == "fixed_base_freq":
            yield from self._get_fixed_base_freq(cpus, mname)
        elif pname in {"min_freq", "max_freq"}:
            yield from self._get_min_max_freq(pname, cpus, mname)
        elif pname in {"min_freq_limit", "max_freq_limit"}:
            yield from self._get_min_max_freq_limit(pname, cpus, mname)
        elif pname == "frequencies":
            yield from self._get_frequencies(cpus, mname)
        elif pname == "bus_clock":
            yield from self._get_bus_clock(cpus, mname)
        elif pname == "turbo":
            yield from self._get_turbo(cpus, mname)
        elif pname == "driver":
            yield from self._get_driver(cpus, mname)
        elif pname == "intel_pstate_mode":
            yield from self._get_intel_pstate_mode(cpus, mname)
        elif pname == "governor":
            yield from self._get_governor(cpus, mname)
        elif pname == "governors":
            yield from self._get_governors(cpus, mname)
        elif pname in {"cppc_lowest_perf", "cppc_lowest_nonlinear_perf", "cppc_guaranteed_perf",
                       "cppc_nominal_perf", "cppc_highest_perf", "cppc_nominal_freq"}:
            yield from self._get_cppc_perf_or_freq(pname, cpus, mname)
        elif pname in {"hwp_lowest_perf", "hwp_efficient_perf", "hwp_guaranteed_perf",
                       "hwp_highest_perf"}:
            yield from self._get_hwp_perf(pname, cpus, mname)
        else:
            raise Error(f"BUG: Unknown property '{pname}'")

    def _set_turbo(self, enable: bool, cpus: AbsNumsType, mname: MechanismNameType):
        """
        Enable or disable turbo mode for the specified CPUs.

        Args:
            enable: Whether to enable (True) or disable (False) turbo mode.
            cpus: CPU numbers to set turbo mode for.
            mname: Name of the mechanism to use for setting turbo mode.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'turbo'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_turbo(enable, cpus=cpus)

    def _set_intel_pstate_mode(self, mode: str, cpus: AbsNumsType, mname: MechanismNameType):
        """
        Set the 'intel_pstate' driver mode for the specified CPUs.

        Args:
            mode: Name of the mode to set (e.g., "powersave", "performance").
            cpus: CPU numbers to set the mode for.
            mname: Name of the mechanism to use for setting the mode.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'intel_pstate_mode'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_intel_pstate_mode(mode, cpus=cpus)

    def _set_governor(self,
                      governor: str,
                      cpus: AbsNumsType,
                      mname: MechanismNameType) -> MechanismNameType:
        """
        Set the CPU frequency governor for the specified CPUs.

        Args:
            governor: Name of the governor to set (e.g., "performance", "powersave").
            cpus: CPUs to apply the governor setting to.
            mname: Name of the mechanism to use for setting the governor.

        Returns:
            The name of the mechanism used to set the governor (e.g., "sysfs").
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property 'governor'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_governor(governor, cpus=cpus)
        return "sysfs"

    def _handle_write_and_read_freq_mismatch(self, err: ErrorVerifyFailed) -> NoReturn:
        """
        Handle mismatches between written and read CPU frequency values in sysfs.

        Args:
            err: The exception object containing the error details.

        Raises:
            ErrorVerifyFailed: always raised to indicate the mismatch, includes a detailed message.
        """

        if err.expected is None:
            raise Error("BUG: Frequency is not set in the 'ErrorVerifyFailed' object")

        if typing.TYPE_CHECKING:
            freq = cast(int, err.expected)
            read_freq = cast(int, err.actual)
        else:
            freq = err.expected
            read_freq = err.actual

        if err.actual is None:
            raise Error("BUG: Read frequency is not set in the 'ErrorVerifyFailed' object")

        if err.cpu is None:
            raise Error("BUG: CPU number is not set in the 'ErrorVerifyFailed' object")
        cpu = err.cpu

        msg = str(err)

        with contextlib.suppress(Error):
            _frequencies = self._get_cpu_prop_mnames("frequencies", cpu,
                                                     self._props["frequencies"]["mnames"])
            if typing.TYPE_CHECKING:
                frequencies = cast(list[int], _frequencies)
            else:
                frequencies = _frequencies

            frequencies_set = set(frequencies)
            if freq not in frequencies_set and read_freq in frequencies_set:
                fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                freq_human = Human.num2si(freq, unit="Hz", decp=4)
                msg += f".\n  Linux kernel CPU frequency driver does not support " \
                       f"{freq_human}, use one of the following values instead:\n  {fvals}"

        with contextlib.suppress(Error):
            if self._get_cpu_prop_mnames("turbo", cpu, self._props["turbo"]["mnames"]) == "off":
                base_freq = self._get_cpu_prop_mnames_int("base_freq", cpu,
                                                          self._props["base_freq"]["mnames"])

                if base_freq and freq > base_freq:
                    base_freq_str = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f".\n  Hint: turbo is disabled, base frequency is {base_freq_str}, " \
                           f"and this may be the limiting factor."

        err.msg = msg
        raise err

    def _get_numeric_cpu_freq(self,
                              freq: str | int,
                              cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Convert the user-provided frequency value to a numeric frequency in Hz. If the user-provided
        value is a special string (e.g., "max", "min", "base"), resolve it to the corresponding
        numeric frequency.

        Args:
            freq: Frequency value or special string (e.g., "max", "min", "base").
            cpus: CPU numbers to resolve the frequency for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is the resolved frequency
            in Hz.
        """

        if freq == "min":
            yield from self._get_prop_cpus_mnames_int("min_freq_limit", cpus, ("sysfs",))
        elif freq == "max":
            yield from self._get_prop_cpus_mnames_int("max_freq_limit", cpus, ("sysfs",))
        elif freq in {"base", "hfm"}:
            yield from self._get_prop_cpus_mnames_int("base_freq", cpus, ("sysfs",))
        else:
            if typing.TYPE_CHECKING:
                freq = cast(int, freq)
            for cpu in cpus:
                yield cpu, freq

    def _set_cpu_freq(self,
                      pname: str,
                      val: str | int,
                      cpus: AbsNumsType,
                      mname: MechanismNameType):
        """
        Set a CPU frequency property for specified CPUs using the given mechanism.

        Args:
            pname: Name of the frequency property to set (e.g., "min_freq" or "max_freq").
            val: The target frequency value to set. Can be a numeric value or a special string
                 (e.g., "max", "min", "base").
            cpus: CPU numbers to apply the frequency setting to.
            mname: Mechanism to use for setting the frequency.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}' for property '{pname}'")

        freq2cpus: dict[int, list[int]] = {}

        for (cpu, new_freq) in self._get_numeric_cpu_freq(val, cpus):
            if new_freq not in freq2cpus:
                freq2cpus[new_freq] = []
            freq2cpus[new_freq].append(cpu)

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        for new_freq, freq_cpus in freq2cpus.items():
            try:
                if pname == "min_freq":
                    cpufreq_obj.set_min_freq(new_freq, freq_cpus)
                elif pname == "max_freq":
                    cpufreq_obj.set_max_freq(new_freq, freq_cpus)
                else:
                    raise Error(f"BUG: Unexpected CPU frequency property {pname}")
            except ErrorVerifyFailed as err:
                self._handle_write_and_read_freq_mismatch(err)

    def _handle_epp_set_exception(self,
                                  val: str,
                                  mname: MechanismNameType,
                                  err: Error) -> str | None:
        """
        Handle a situation where setting the Energy Performance Preference (EPP) fails. The goal is
        to improve the error message to help the user understand the reason for the failure.

        Args:
            val: The attempted EPP value.
            mname: Name of the mechanism to use for setting EPP.
            err: The exception object raised during the EPP set attempt.

        Returns:
            A string with a detailed error message, None if the error message was not improved.
        """

        # Newer Linux kernels with intel_pstate driver in active mode forbid changing EPP to
        # anything but 0 or "performance". Provide a helpful error message for this special case.

        if mname != "sysfs":
            return None
        if val in ("0", "performance"):
            return None
        if not hasattr(err, "cpu"):
            return None

        cpus = [err.cpu]
        _, driver = next(self._get_prop_cpus_mnames("driver", cpus,
                                                    self._props["driver"]["mnames"]))
        if driver != "intel_pstate":
            return None
        _, mode = next(self._get_prop_cpus_mnames("intel_pstate_mode", cpus,
                                                  self._props["intel_pstate_mode"]["mnames"]))
        if mode != "active":
            return None
        _, governor = next(self._get_prop_cpus_mnames("governor", cpus,
                                                      self._props["governor"]["mnames"]))
        if governor != "performance":
            return None

        return f"{err}\nThe 'performance' governor of the 'intel_pstate' driver sets EPP to 0 " \
               f"(performance) and does not allow for changing it."

    def _set_prop_cpus(self,
                       pname: str,
                       val: PropertyValueType,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]):
        """Refer to 'PropsClassBase._set_prop_cpus()'."""

        _LOG.debug("Setting property '%s' to value '%s' using mechanism '%s', cpus: %s",
                   pname, val, mname, self._cpuinfo.cpus_to_str(cpus))

        if pname == "epp":
            try:
                self._get_eppobj().set_vals(val, cpus=cpus, mnames=(mname,))
            except Error as err:
                msg = self._handle_epp_set_exception(str(val), mname, err)
                if msg is None:
                    raise
                raise type(err)(msg) from err
        elif pname == "epb":
            self._get_epbobj().set_vals(val, cpus=cpus, mnames=(mname,))
        elif pname == "turbo":
            if typing.TYPE_CHECKING:
                _turbo_val = cast(bool, val)
            else:
                _turbo_val = val
            self._set_turbo(_turbo_val, cpus, mname)
        elif pname == "intel_pstate_mode":
            if typing.TYPE_CHECKING:
                _mode_val = cast(str, val)
            else:
                _mode_val = val
            self._set_intel_pstate_mode(_mode_val, cpus, mname)
        elif pname == "governor":
            if typing.TYPE_CHECKING:
                _governor_val = cast(str, val)
            else:
                _governor_val = val
            self._set_governor(_governor_val, cpus, mname)
        elif pname in ("min_freq", "max_freq"):
            if typing.TYPE_CHECKING:
                _freq_val = cast(Union[str, int], val)
            else:
                _freq_val = val
            self._set_cpu_freq(pname, _freq_val, cpus, mname)
        else:
            raise Error(f"BUG: Unsupported property '{pname}'")

    def _set_sname(self, pname: str):
        """
        Set the scope name ('sname') for the specified property.

        Args:
            pname: The name of the property for which to set the scope name.
        """

        prop = self._props[pname]
        if prop["sname"]:
            return

        if pname == "epb":
            epbobj = self._get_epbobj()
            prop["sname"] = epbobj.sname
        elif pname == "bus_clock":
            try:
                fsbfreq = self._get_fsbfreq()
                prop["sname"] = fsbfreq.features["fsb"]["sname"]
            except ErrorNotSupported:
                prop["sname"] = "global"
        else:
            raise Error(f"BUG: Unsupported property '{pname}'")

        prop["iosname"] = prop["sname"]
        self.props[pname]["sname"] = prop["sname"]
