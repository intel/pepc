# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
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
from typing import cast
import contextlib
from pepclibs import _PropsClassBase
from pepclibs.PStatesVars import PROPS
from pepclibs.helperlibs import Human, ClassHelpers, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed

# pylint: disable-next=unused-import
from pepclibs._PropsClassBase import ErrorTryAnotherMechanism, ErrorUsePerCPU

if typing.TYPE_CHECKING:
    from typing import NoReturn, Generator, Union, Sequence
    from pepclibs.PropsTypes import PropertyValueType
    from pepclibs.msr import MSR, FSBFreq
    from pepclibs import _CPUFreqSysfs, _CPUFreqCPPC, _CPUFreqMSR
    from pepclibs import _SysfsIO, EPP, EPB
    from pepclibs.CPUInfo import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.PropsTypes import MechanismNameType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class PStates(_PropsClassBase.PropsClassBase):
    """
    This class provides API for managing platform settings related to P-states. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object for the target system. If not provided, a local process
                  manager is created.
            cpuinfo: The CPU information object ('CPUInfo.CPUInfo()'). If not provided, one is
                     created.
            msr: The MSR access object ('MSR.MSR()'). If not provided, one is created.
            sysfs_io: The sysfs access object ('_SysfsIO.SysfsIO()'). If not provided, one is
                      created.
            enable_cache: Enable property caching if True.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._eppobj: EPP.EPP | None = None
        self._epbobj: EPB.EPB | None = None
        self._fsbfreq: FSBFreq.FSBFreq | None = None

        self._cpufreq_sysfs_obj: _CPUFreqSysfs.CPUFreqSysfs | None = None
        self._cpufreq_cppc_obj: _CPUFreqCPPC.CPUFreqCPPC | None = None
        self._cpufreq_msr_obj: _CPUFreqMSR.CPUFreqMSR | None= None

        self._perf2freq: dict[int, int] = {}

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_eppobj", "_epbobj", "_fsbfreq", "_cpufreq_sysfs_obj", "_cpufreq_cppc_obj",
                       "_cpufreq_msr_obj")
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

    def _get_cpufreq_cppc_obj(self) -> _CPUFreqCPPC.CPUFreqCPPC:
        """
        Get an 'CPUFreqCPPC' object.

        Returns:
            An instance of '_CPUFreqCPPC.CPUFreqCPPC'.
        """

        if not self._cpufreq_cppc_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreqCPPC

            sysfs_io = self._get_sysfs_io()
            self._cpufreq_cppc_obj = _CPUFreqCPPC.CPUFreqCPPC(cpuinfo=self._cpuinfo,
                                                              pman=self._pman, sysfs_io=sysfs_io,
                                                              enable_cache=self._enable_cache)
        return self._cpufreq_cppc_obj

    def _get_cpufreq_msr_obj(self) -> _CPUFreqMSR.CPUFreqMSR:
        """
        Get an 'CPUFreqMSR' object.

        Returns:
            An instance of '_CPUFreqMSR.CPUFreqMSR'.
        """

        if not self._cpufreq_msr_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreqMSR

            msr = self._get_msr()
            self._cpufreq_msr_obj = _CPUFreqMSR.CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman,
                                                           msr=msr, enable_cache=self._enable_cache)
        return self._cpufreq_msr_obj

    def _get_epp(self,
                 cpus: AbsNumsType,
                 mname: MechanismNameType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield EPP values for the specified CPUs using the specified mechanism.

        Args:
            cpus: CPU numbers to retrieve EPP values for.
            mname: Mechanism name to use for retrieving EPP values.

        Yields:
            Tuple of (cpu, val), where 'cpu' is th CPU number and 'val' is its EPP value.

        Notes:
            - The reason why the yield EPP values are strings is because the corresponding sysfs
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
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its EPB value.
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
            Tuple of (cpu, status), where 'cpu' is the CPU number and 'status' is its HWP status.
        """

        if mname != "msr":
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        cpufreq_obj = self._get_cpufreq_msr_obj()
        yield from cpufreq_obj.get_hwp(cpus=cpus)

    def _get_cppc_freq(self,
                       pname: str,
                       cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield frequency values for the specified CPUs using the CPPC mechanism.

        Args:
            pname: Property name to retrieve (e.g., "base_freq").
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_cppc_obj()

        if pname == "base_freq":
            yield from cpufreq_obj.get_base_freq(cpus)
        elif pname == "max_turbo_freq":
            yield from cpufreq_obj.get_max_freq_limit(cpus)
        elif pname == "min_oper_freq":
            yield from cpufreq_obj.get_min_freq_limit(cpus)
        else:
            raise Error(f"BUG: Unexpected property {pname}")

    def _get_min_oper_freq(self,
                           cpus: AbsNumsType,
                           mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum operating frequency for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve minimum operating frequency for.
            mname: Name of the mechanism to use ('msr' or 'cppc').

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its minimum operating
            frequency.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_min_oper_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("min_oper_freq", cpus)
            return

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

    def _get_max_turbo_freq(self,
                            cpus: AbsNumsType,
                            mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum turbo frequency for the specified CPUs using the given
        mechanism.

        Args:
            cpus: CPU numbers to retrieve maximum turbo frequency for.
            mname: Name of the mechanism to use ('msr' or 'cppc').

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its maximum turbo
            frequency.
        """

        if mname == "msr":
            cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from cpufreq_obj.get_max_turbo_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("max_turbo_freq", cpus)
            return

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

    def _get_base_freq(self,
                       cpus: AbsNumsType,
                       mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for the specified CPUs using the given mechanism.

        Args:
            cpus: CPU numbers to retrieve base frequency for.
            mname: Name of the mechanism to use for retrieving the base frequency: are 'sysfs',
                   'msr', and 'cppc'.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its base frequency.
        """

        if mname == "sysfs":
            sysfs_cpufreq_obj = self._get_cpufreq_sysfs_obj()
            yield from sysfs_cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "msr":
            msr_cpufreq_obj = self._get_cpufreq_msr_obj()
            yield from msr_cpufreq_obj.get_base_freq(cpus)
            return

        if mname == "cppc":
            yield from self._get_cppc_freq("base_freq", cpus)
            return

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
        else:
            raise Error(f"BUG: Unexpected CPU frequency property {pname}")

    def _get_freq_msr(self,
                      pname: str,
                      cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum or maximum CPU frequency for the specified CPUs using the MSR
        mechanism.

        Args:
            pname: The property to retrieve. Must be either "min_freq" or "max_freq".
            cpus: CPU numbers to retrieve frequency values for.

        Yields:
            Tuples of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency in Hz.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            yield from cpufreq_obj.get_min_freq(cpus)
        elif pname == "max_freq":
            yield from cpufreq_obj.get_max_freq(cpus)
        else:
            raise Error(f"BUG: Unexpected CPU frequency property {pname}")

    def _get_freq(self,
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

        if mname == "sysfs":
            yield from self._get_freq_sysfs(pname, cpus)
            return

        if mname == "msr":
            yield from self._get_freq_msr(pname, cpus)
            return

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

    def _get_freq_limit(self,
                        pname: str,
                        cpus: AbsNumsType,
                        mname: MechanismNameType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequency limits for the specified CPUs using the sysfs mechanism.

        Args:
            pname: Property name to retrieve ("min_freq_limit" or "max_freq_limit").
            cpus: CPU numbers to retrieve frequency values for.
            mname: Name of the mechanism to use for retrieving the frequency limits.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its frequency limit in
            Hz.
        """

        if mname != "sysfs":
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        yield from self._get_freq_sysfs(pname, cpus)

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
            if self._cpuinfo.info["vendor"] != "GenuineIntel":
                raise
            # Fall back to 100MHz bus clock speed.
            for cpu in cpus:
                yield cpu, 100000000
        else:
            for cpu, bclk in fsbfreq.read_feature("fsb", cpus=cpus):
                # Convert MHz to Hz.
                yield cpu, int(bclk * 1000000)

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
            if self._cpuinfo.info["vendor"] != "GenuineIntel":
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
                raise ErrorNotSupported("Only 'intel_pstate' was verified to accept any frequency "
                                        "value that is multiple of bus clock")

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

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            for cpu, val in self._get_fsbfreq().read_feature("fsb", cpus=cpus):
                yield cpu, int(val * 1000000)
            return

        if mname == "doc":
            try:
                self._get_fsbfreq()
            except ErrorNotSupported:
                if self._cpuinfo.info["vendor"] != "GenuineIntel":
                    raise ErrorNotSupported(f"Unsupported CPU model '{self._cpuinfo.cpudescr}"
                                            f"{self._pman.hostmsg}") from None
                for cpu in cpus:
                    # Modern Intel platforms use 100MHz bus clock.
                    yield cpu, 100000000
                return
            raise ErrorTryAnotherMechanism(f"Use the 'msr' mechanism for {self._cpuinfo.cpudescr}")

        raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        yield from cpufreq_obj.get_available_governors(cpus)

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """Refer to '_PropsClassBase._get_prop_cpus()'."""

        _LOG.debug("Getting property '%s' using mechanism '%s', cpus: %s",
                   pname, mname, self._cpuinfo.cpus_to_str(cpus))

        if pname == "epp":
            yield from self._get_epp(cpus, mname)
        elif pname == "epb":
            yield from self._get_epb(cpus, mname)
        elif pname == "hwp":
            yield from self._get_hwp(cpus, mname)
        elif pname == "min_oper_freq":
            yield from self._get_min_oper_freq(cpus, mname)
        elif pname == "max_turbo_freq":
            yield from self._get_max_turbo_freq(cpus, mname)
        elif pname == "base_freq":
            yield from self._get_base_freq(cpus, mname)
        elif pname in {"min_freq", "max_freq"}:
            yield from self._get_freq(pname, cpus, mname)
        elif pname in {"min_freq_limit", "max_freq_limit"}:
            yield from self._get_freq_limit(pname, cpus, mname)
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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

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
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        cpufreq_obj = self._get_cpufreq_sysfs_obj()
        cpufreq_obj.set_governor(governor, cpus=cpus)
        return "sysfs"

    def _set_freq_prop_cpus_msr(self, pname: str, freq: int, cpus: AbsNumsType):
        """
        Set the 'min_freq' or 'max_freq' CPU frequency property to the specified value for the given
        CPUs.

        Args:
            pname: Name of the property to set ('min_freq' or 'max_freq').
            freq: Frequency value to set, in Hz.
            cpus: CPU numbers to apply the frequency setting to.
        """

        cpufreq_obj = self._get_cpufreq_msr_obj()

        if pname == "min_freq":
            cpufreq_obj.set_min_freq(freq, cpus)
        elif pname == "max_freq":
            cpufreq_obj.set_max_freq(freq, cpus)
        else:
            raise Error(f"BUG: Unexpected CPU frequency property {pname}")

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

        freq = cast(int, err.expected)

        if err.actual is None:
            raise Error("BUG: Read frequency is not set in the 'ErrorVerifyFailed' object")

        read_freq = cast(int, err.actual)

        if err.cpu is None:
            raise Error("BUG: CPU number is not set in the 'ErrorVerifyFailed' object")
        cpu = err.cpu

        msg = str(err)

        with contextlib.suppress(Error):
            _frequencies = self._get_cpu_prop_mnames("frequencies", cpu,
                                                     self._props["frequencies"]["mnames"])
            frequencies = cast(list[int], _frequencies)

            frequencies_set = set(frequencies)
            if freq not in frequencies_set and read_freq in frequencies_set:
                fvals = ", ".join([Human.num2si(v, unit="Hz", decp=4) for v in frequencies])
                freq_human = Human.num2si(freq, unit="Hz", decp=4)
                msg += f".\n  Linux kernel CPU frequency driver does not support " \
                       f"{freq_human}, use one of the following values instead:\n  {fvals}"

        with contextlib.suppress(Error):
            if self._get_cpu_prop_mnames("turbo", cpu, self._props["turbo"]["mnames"]) == "off":
                _base_freq = self._get_cpu_prop_mnames("base_freq", cpu,
                                                       self._props["base_freq"]["mnames"])
                base_freq = cast(int, _base_freq)

                if base_freq and freq > base_freq:
                    base_freq_str = Human.num2si(base_freq, unit="Hz", decp=4)
                    msg += f".\n  Hint: turbo is disabled, base frequency is {base_freq_str}, " \
                           f"and this may be the limiting factor."

        err.msg = msg
        raise err

    def _set_freq_prop_cpus_sysfs(self, pname: str, freq: int, cpus: AbsNumsType):
        """
        Set the minimum or maximum CPU frequency property for the specified CPUs.

        Args:
            pname: Name of the property to set ('min_freq' or 'max_freq').
            freq: Frequency value to set, in Hz.
            cpus: CPU numbers to apply the frequency setting to.
        """

        cpufreq_obj = self._get_cpufreq_sysfs_obj()

        try:
            if pname == "min_freq":
                cpufreq_obj.set_min_freq(freq, cpus)
            elif pname == "max_freq":
                cpufreq_obj.set_max_freq(freq, cpus)
            else:
                raise Error(f"BUG: Unexpected CPU frequency property {pname}")
        except ErrorVerifyFailed as err:
            self._handle_write_and_read_freq_mismatch(err)

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
            Tuple (cpu, val), where 'cpu' is the CPU number and 'val' is the resolved frequency in
            Hz.
        """

        if freq == "min":
            _iterator = self._get_prop_cpus_mnames("min_freq_limit", cpus, ("sysfs",))
            if typing.TYPE_CHECKING:
                iterator = cast(Generator[tuple[int, int], None, None], _iterator)
            else:
                iterator = _iterator
            yield from iterator
        elif freq == "max":
            _iterator = self._get_prop_cpus_mnames("max_freq_limit", cpus, ("sysfs",))
            if typing.TYPE_CHECKING:
                iterator = cast(Generator[tuple[int, int], None, None], _iterator)
            else:
                iterator = _iterator
            yield from iterator
        elif freq in {"base", "hfm", "P1"}:
            _iterator = self._get_prop_cpus_mnames("base_freq", cpus, ("sysfs", "msr", "cppc"))
            if typing.TYPE_CHECKING:
                iterator = cast(Generator[tuple[int, int], None, None], _iterator)
            else:
                iterator = _iterator
            yield from iterator
        elif freq == "Pm":
            _iterator = self._get_prop_cpus_mnames("min_oper_freq", cpus, ("msr",))
            if typing.TYPE_CHECKING:
                iterator = cast(Generator[tuple[int, int], None, None], _iterator)
            else:
                iterator = _iterator
            yield from iterator
        else:
            for cpu in cpus:
                yield cpu, cast(int, freq)

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
            mname: Mechanism to use for setting the frequency (e.g., "sysfs" or "msr").
        """

        if mname == "sysfs":
            set_freq_method = self._set_freq_prop_cpus_sysfs
        elif mname == "msr":
            set_freq_method = self._set_freq_prop_cpus_msr
        else:
            raise Error(f"BUG: Unexpected mechanism '{mname}'")

        freq2cpus: dict[int, list[int]] = {}

        for (cpu, new_freq) in self._get_numeric_cpu_freq(val, cpus):
            if new_freq not in freq2cpus:
                freq2cpus[new_freq] = []
            freq2cpus[new_freq].append(cpu)

        for new_freq, freq_cpus in freq2cpus.items():
            set_freq_method(pname, new_freq, freq_cpus)

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
        """Refer to '_PropsClassBase._set_prop_cpus()'."""

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
            self._set_turbo(cast(bool, val), cpus, mname)
        elif pname == "intel_pstate_mode":
            self._set_intel_pstate_mode(cast(str, val), cpus, mname)
        elif pname == "governor":
            self._set_governor(cast(str, val), cpus, mname)
        elif pname in ("min_freq", "max_freq"):
            if typing.TYPE_CHECKING:
                _val = cast(Union[str, int], val)
            else:
                _val = val
            self._set_cpu_freq(pname, _val, cpus, mname)
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
