# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability for reading and modifying CPU frequency settings via the Linux kernel CPU
frequency subsystem sysfs interface.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs import CPUInfo, _SysfsIO
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial, KernelVersion
from pepclibs.helperlibs import Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorVerifyFailed
from pepclibs.helperlibs.Exceptions import ErrorOutOfRange, ErrorBadOrder

if typing.TYPE_CHECKING:
    from typing import Generator, Literal
    from pepclibs import _CPUFreqMSR
    from pepclibs.msr import MSR
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType

    # A CPU frequency sysfs file type. Possible values:
    #   - "min": a minimum CPU frequency file
    #   - "max": a maximum CPU frequency file
    #   - "current": a current CPU frequency file
    _SysfsFileType = Literal["min", "max", "current"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and modify CPU frequency settings via the Linux "cpufreq" sysfs
    interface.

    Public Methods and Arguments:
        - get_min_freq(cpus): Retrieve the minimum CPU frequency for specified CPUs.
        - get_max_freq(cpus): Retrieve the maximum CPU frequency for specified CPUs.
        - set_min_freq(freq, cpus): Set the minimum CPU frequency for specified CPUs.
        - set_max_freq(freq, cpus): Set the maximum CPU frequency for specified CPUs.
        - get_cur_freq(cpus): Retrieve the current CPU frequency for specified CPUs.
        - get_min_freq_limit(cpus): Retrieve the minimum CPU frequency limit for specified CPUs.
        - get_max_freq_limit(cpus): Retrieve the maximum CPU frequency limit for specified CPUs.
        - get_available_frequencies(cpus): Retrieve the list of available CPU frequencies for
                                           specified CPUs.
        - get_base_freq(cpus): Retrieve the base frequency for specified CPUs.
        - get_driver(cpus): Retrieve the CPU frequency driver name for specified CPUs.
        - get_intel_pstate_mode(cpus): Retrieve the 'intel_pstate' driver mode for specified CPUs.
        - set_intel_pstate_mode(mode, cpus): Set the 'intel_pstate' driver mode for specified CPUs.
        - get_turbo(cpus): Retrieve the turbo mode status for specified CPUs.
        - set_turbo(enable, cpus): Enable or disable turbo mode for specified CPUs.
        - get_governor(cpus): Retrieve the CPU frequency governor for specified CPUs.
        - get_available_governors(cpus): Retrieve the list of available governors for specified
                                         CPUs.
        - set_governor(governor, cpus): Set the CPU frequency governor for specified CPUs.

    Notes:
        Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid and
        online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True,
                 verify: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object, used only in some error cases to provide additional details in
                 error messages. Will be created on demand if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access, used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
            verify: Enable verification of values writted to sysfs files. The file contents are
                    verified by reading the file back and comparing the values.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo
        self._msr = msr
        self._sysfs_io: _SysfsIO.SysfsIO
        self._enable_cache = enable_cache
        self._verify = verify
        self._path_cache: dict[str, dict[int, dict[bool, Path]]] = {}

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_sysfs_io = sysfs_io is None

        self._cpufreq_msr_obj: _CPUFreqMSR.CPUFreqMSR | None = None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        # Kernel version running on the target system.
        self._kver: str | None = None
        # The warning about the disabled E-cores bug was printed.
        self._check_no_ecores_bug = True

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

        if not sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)
        else:
            self._sysfs_io = sysfs_io

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_sysfs_io", "_msr", "_cpufreq_msr_obj", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _warn_no_ecores_bug(self):
        """
        Warn about a known kernel bug affecting hybrid systems with disabled E-cores.

        Prior to Linux kernel version 6.5, a bug existed that caused incorrect CPU frequency
        reporting on hybrid-capable systems (e.g., Intel Alder Lake) when all E-cores were
        disabled. This method checks if the current system is affected by this bug and, if so,
        prints a warning message. The bug was fixed in kernel commit
        '0fcfc9e51990246a9813475716746ff5eb98c6aa'.
        """

        if not self._check_no_ecores_bug:
            return
        if not self._cpuinfo.info["hybrid"]:
            return

        hybrid_cpus = self._cpuinfo.get_hybrid_cpus()
        if hybrid_cpus["ecore"] or hybrid_cpus["pcore"]:
            return

        if not self._kver:
            try:
                self._kver = KernelVersion.get_kver(pman=self._pman)
            except Error as err:
                _LOG.warning("Failed to detect kernel version%s:\n%s",
                             self._pman.hostmsg, err.indent(2))
                self._check_no_ecores_bug = False
                return

        if KernelVersion.kver_ge(self._kver, "6.5"):
            self._check_no_ecores_bug = False
            return

        # It is possible that there are E-cores, but they are offline. To avoid false-positives,
        # warn only if there are no offline CPUs.
        if self._cpuinfo.get_offline_cpus():
            return

        self._check_no_ecores_bug = False
        _LOG.warning("Kernel version%s is %s, and the processor is hybrid with no E-cores or all "
                     "E-cores disabled.\nKernel versions prior to 6.5 have a bug: sysfs CPU "
                     "frequency files have incorrect numbers on systems like this.\nThe fix is in "
                     "Linux kernel commit '0fcfc9e51990246a9813475716746ff5eb98c6aa'.",
                     {self._pman.hostmsg}, {self._kver})

    def _get_msr(self) -> MSR.MSR:
        """Return an instance of 'MSR.MSR'."""

        if not self._msr:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_cpufreq_msr_obj(self) -> _CPUFreqMSR.CPUFreqMSR:
        """Return an instance of 'CPUFreqMSR' class."""

        if not self._cpufreq_msr_obj:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _CPUFreqMSR

            msr = self._get_msr()
            self._cpufreq_msr_obj = _CPUFreqMSR.CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman,
                                                           msr=msr, enable_cache=self._enable_cache)
        return self._cpufreq_msr_obj

    def _get_policy_sysfs_path(self, cpu: int, fname: str) -> Path:
        """
        Construct and return the sysfs path for a specific cpufreq policy file.

        Args:
            cpu: CPU number for which to construct the policy path.
            fname: Name of the file within the policy directory.

        Returns:
            Full path to the specified cpufreq policy file.
        """

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / fname

    def _get_cpu_freq_sysfs_path(self,
                                 ftype: _SysfsFileType,
                                 cpu: int,
                                 limit: bool = False) -> Path:
        """
        Return the sysfs file path for a CPU frequency read or write operation. Use paths cache to
        avoid recomputing the paths.

        Args:
            ftype: The CPU frequency sysfs file type.
            cpu: CPU number for which to get the path.
            limit: Whether to use the "limit" file or the "scaling" file.

        Returns:
            The sysfs file path for the specified CPU and other parameters.
        """

        if ftype not in self._path_cache:
            self._path_cache[ftype] = {}
        if cpu not in self._path_cache[ftype]:
            self._path_cache[ftype][cpu] = {}

        if limit in self._path_cache[ftype][cpu]:
            return self._path_cache[ftype][cpu][limit]

        fname = "scaling_" + ftype + "_freq"
        prefix = "cpuinfo_" if limit else "scaling_"
        fname = prefix + ftype + "_freq"

        path = self._get_policy_sysfs_path(cpu, fname)
        self._path_cache[ftype][cpu][limit] = path
        return path

    def _get_freq_sysfs(self,
                        ftype: _SysfsFileType,
                        cpus: AbsNumsType,
                        limit: bool = False) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequencies from the Linux "cpufreq" sysfs files for specified CPUs.

        Args:
            ftype: The CPU frequency sysfs file type.
            cpus: CPU numbers to get the frequency for.
            limit: Whether to use the "limit" file or the "scaling" sysfs file for reading the
                   frequency.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            frequency in Hz.
        """

        self._warn_no_ecores_bug()

        for cpu in cpus:
            path = self._get_cpu_freq_sysfs_path(ftype, cpu, limit=limit)
            freq = self._sysfs_io.read_int(path, what=f"{ftype} frequency for CPU {cpu}")
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_min_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum CPU frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the minimum
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("min", cpus)

    def get_max_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum CPU frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus)

    def get_cur_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the current CPU frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the current frequency for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the current
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("current", cpus)

    def get_min_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum CPU frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum frequency limit for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the minimum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("min", cpus, limit=True)

    def get_max_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum CPU frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum frequency limit for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus, limit=True)

    def _validate_freq(self, freq: int, ftype: _SysfsFileType, cpu: int):
        """
        Validate that a CPU frequency value is within the acceptable range.

        Args:
            freq: The CPU frequency value to validate, in Hz.
            ftype: The CPU frequency sysfs file type.
            cpu: CPU number to validate the frequency for.

        Raises:
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        path = self._get_cpu_freq_sysfs_path("min", cpu, limit=True)
        min_freq_limit = self._sysfs_io.read_int(path, what=f"min frequency limit for CPU {cpu}")
        min_freq_limit *= 1000

        path = self._get_cpu_freq_sysfs_path("max", cpu, limit=True)
        max_freq_limit = self._sysfs_io.read_int(path, what=f"max frequency limit for CPU {cpu}")
        max_freq_limit *= 1000

        if freq < min_freq_limit or freq > max_freq_limit:
            name = f"{ftype} CPU {cpu} frequency"
            freq_str = Human.num2si(freq, unit="Hz", decp=4)
            min_limit_str = Human.num2si(min_freq_limit, unit="Hz", decp=4)
            max_limit_str = Human.num2si(max_freq_limit, unit="Hz", decp=4)
            raise ErrorOutOfRange(f"{name} value of '{freq_str}' is out of range, must be within "
                                  f"[{min_limit_str},{max_limit_str}]")

        if ftype == "min":
            path = self._get_cpu_freq_sysfs_path("max", cpu)
            max_freq = self._sysfs_io.read_int(path, what=f"max frequency for CPU {cpu}") * 1000

            if freq > max_freq:
                name = f"{ftype} CPU {cpu} frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                max_freq_str = Human.num2si(max_freq, unit="Hz", decp=4)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is greater than the currently "
                                    f"configured max frequency of {max_freq_str}")
        else:
            path = self._get_cpu_freq_sysfs_path("min", cpu)
            min_freq = self._sysfs_io.read_int(path, what=f"min frequency for CPU {cpu}") * 1000

            if freq < min_freq:
                name = f"{ftype} CPU {cpu} frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                min_freq_str = Human.num2si(min_freq, unit="Hz", decp=4)
                raise ErrorBadOrder(f"{name} value of '{freq_str}' is less than the currently "
                                    f"configured min frequency of {min_freq_str}")

    def _set_freq_sysfs(self, freq: int, ftype: _SysfsFileType, cpus: AbsNumsType):
        """
        Set the CPU frequency for the specified CPUs using the Linux "cpufreq" sysfs interface.

        Args:
            freq: Target CPU frequency in Hz.
            ftype: The CPU frequency sysfs file type.
            cpus: CPU numbers to set the frequency for.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
            ErrorVerifyFailed: If the frequency could not be set or verified after retries. The
                               exception object will have an additional 'cpu' attribute indicating
                               the CPU number that failed, the 'expected' attribute will contain the
                               expected value, and the 'actual' attribute will contain the actual
                               value read from sysfs.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        self._warn_no_ecores_bug()

        what = f"{ftype} CPU frequency"
        retries = 0
        sleep = 0.0

        for cpu in cpus:
            self._validate_freq(freq, ftype, cpu)

            if self._verify:
                cpu_info = self._cpuinfo.info
                if cpu_info["vendor"] == "GenuineIntel" and "hwp" in cpu_info["flags"][cpu]:
                    # On some Intel platforms with HWP enabled the change does not happen
                    # immediately. Retry few times.
                    retries = 2
                    sleep = 0.1

            path = self._get_cpu_freq_sysfs_path(ftype, cpu)

            try:
                if not self._verify:
                    self._sysfs_io.write_int(path, freq // 1000, what=what)
                else:
                    self._sysfs_io.write_verify_int(path, freq // 1000, what=what, retries=retries,
                                                    sleep=sleep)
            except ErrorVerifyFailed as err:
                setattr(err, "cpu", cpu)
                raise err

    def set_min_freq(self, freq: int, cpus: AbsNumsType):
        """
        Set the minimum CPU frequency for the specified CPUs using the Linux "cpufreq" sysfs
        interfaces.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: CPU numbers to set the frequency for.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
            ErrorVerifyFailed: If the frequency could not be set or verified after retries. The
                               exception object will have an additional 'cpu' attribute indicating
                               the CPU number that failed, the 'expected' attribute will contain the
                               expected value, and the 'actual' attribute will contain the actual
                               value read from sysfs.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        self._set_freq_sysfs(freq, "min", cpus)

    def set_max_freq(self, freq, cpus):
        """
        Set the maximum CPU frequency for the specified CPUs using the Linux "cpufreq" sysfs
        interfaces.

        Args:
            freq: The frequency value to set, in Hz.
            cpus: CPU numbers to set the frequency for.

        Raises:
            ErrorNotSupported: If the CPU frequency sysfs file does not exist.
            ErrorVerifyFailed: If the frequency could not be set or verified after retries. The
                               exception object will have an additional 'cpu' attribute indicating
                               the CPU number that failed, the 'expected' attribute will contain the
                               expected value, and the 'actual' attribute will contain the actual
                               value read from sysfs.
            ErrorOutOfRange: If the CPU frequency value is outside the allowed range.
            ErrorBadOrder: If min. CPU frequency is greater than max. CPU frequency and vice versa.
        """

        self._set_freq_sysfs(freq, "max", cpus)

    def get_available_frequencies(self,
                                  cpus: AbsNumsType) -> Generator[tuple[int, list[int]],
                                                                  None, None]:
        """
        Yield available CPU frequencies specified CPUs. Frequencies are read from the
        'scaling_available_frequencies' sysfs file, which is typically provided by the
        'acpi-cpufreq' driver.

        Args:
            cpus: CPU numbers to get the list of available frequencies for.

        Yields:
            Tuple of (cpu, frequencies), where 'cpu' is the CPU number and 'frequencies' is a sorted
            list of available frequencies in Hz.

        Raises:
            ErrorNotSupported: If the frequencies sysfs file is not present.
        """

        for cpu in cpus:
            path = self._get_policy_sysfs_path(cpu, "scaling_available_frequencies")
            val = self._sysfs_io.read(path, what="available CPU frequencies")

            freqs: list[int] = []
            for freq_str in val.split():
                try:
                    freq = Trivial.str_to_int(freq_str, what="CPU frequency value")
                    freqs.append(freq * 1000)
                except Error as err:
                    raise Error(f"Bad contents of file '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err

            yield cpu, sorted(freqs)

    def _get_base_freq_intel_pstate(self,
                                    cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs using the 'intel_pstate' driver.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.
        """

        for cpu in cpus:
            path = self._get_policy_sysfs_path(cpu, "base_frequency")
            freq = self._sysfs_io.read_int(path, what=f"base frequency for CPU {cpu}")
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def _get_base_freq_bios_limit(self,
                                  cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs using the 'bios_limit' sysfs file.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.
        """

        for cpu in cpus:
            path = self._sysfs_base / f"cpu{cpu}/cpufreq/bios_limit"
            freq = self._sysfs_io.read_int(path, what=f"base frequency for CPU {cpu}")
            # On Intel systems that support turbo, the 'bios_limit' file includes the turbo
            # activation frequency, which is base frequency + 1MHz. So we need to subtract 1MHz from
            # the value read from the 'bios_limit' file to get the actual base frequency.
            if freq % 10000:
                freq -= 1000
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_base_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the base frequency sysfs files do not exist.
        """

        yielded_cpus = set()
        try:
            for cpu, val in self._get_base_freq_intel_pstate(cpus):
                yielded_cpus.add(cpu)
                yield cpu, val
        except ErrorNotSupported as err1:
            left_cpus = []
            for cpu in cpus:
                if cpu not in yielded_cpus:
                    left_cpus.append(cpu)
            try:
                yield from self._get_base_freq_bios_limit(left_cpus)
            except ErrorNotSupported as err2:
                raise ErrorNotSupported(f"{err1}\n{err2}") from err2

    def get_driver(self, cpus: AbsNumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the Linux CPU frequency driver name for specified CPUs.

        Args:
            cpus: CPU numbers to get the driver name for.

        Yields:
            Tuple of (cpu, driver_name) where 'cpu' is the CPU number and 'driver_name' is the Linux
            CPU frequency driver name for that CPU.

        Raises:
            ErrorNotSupported: If the driver information cannot be determined.
        """

        what = "CPU frequency driver name"

        for cpu in cpus:
            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_driver"
            try:
                name = self._sysfs_io.read(path, what=what)
            except ErrorNotSupported:
                # The 'intel_pstate' driver may be in the 'off' mode, in which case the
                # 'scaling_driver' sysfs file does not exist. So just check if the 'intel_pstate'
                # sysfs directory exists.
                if not self._pman.exists(self._sysfs_base / "intel_pstate"):
                    raise
                name = "intel_pstate"
            else:
                # The 'intel_pstate' driver calls itself 'intel_pstate' when it is in active mode,
                # and 'intel_cpufreq' when it is in passive mode. But we always report the
                # 'intel_pstate' name, because reporting 'intel_cpufreq' is confusing for users.
                if name == "intel_cpufreq":
                    name = "intel_pstate"

            yield cpu, name

    def get_intel_pstate_mode(self,
                              cpus: AbsNumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the 'intel_pstate' driver mode for specified CPUs.

        Args:
            cpus: CPU numbers to get the 'intel_pstate' driver mode for.

        Yields:
            Tuple (cpu, mode), where 'cpu' is the CPU number and 'mode' is the current
            'intel_pstate' driver mode for that CPU.

        Raises:
            ErrorNotSupported: If the driver is not 'intel_pstate' for a CPU.
        """

        what = "'intel_pstate' driver mode"
        path = self._sysfs_base / "intel_pstate" / "status"

        for cpu, driver in self.get_driver(cpus):
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"Failed to get 'intel_pstate' driver mode for CPU "
                                        f"{cpu}{self._pman.hostmsg}: current driver is '{driver}'")
            mode = self._sysfs_io.read(path, what=what)
            yield cpu, mode

    def set_intel_pstate_mode(self, mode: str, cpus: AbsNumsType):
        """
        Set the operational mode of the 'intel_pstate' driver to one of the supported modes:
        "active", "passive", or "off".

        Args:
            mode: The desired 'intel_pstate' driver mode ("active", "passive", or "off").
            cpus: CPU numbers to set the 'intel_pstate' driver mode for.

        Raises:
            ErrorNotSupported: If the current driver is not 'intel_pstate', or it does not support
                               changing to the specified mode (e.g., if attempting to set the mode
                               to "off" when HWP is enabled).
        """

        modes = ("active", "passive", "off")
        if mode not in modes:
            modes_str = ", ".join(modes)
            raise Error(f"bad 'intel_pstate' mode '{mode}', use one of: {modes_str}")

        what = "'intel_pstate' driver mode"
        path = self._sysfs_base / "intel_pstate" / "status"

        driver_iter = self.get_driver(cpus)
        mode_iter = self.get_intel_pstate_mode(cpus)

        for (cpu, driver), (_, curmode) in zip(driver_iter, mode_iter):
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"Failed to set 'intel_pstate' driver mode to '{mode}' for "
                                        f"CPU {cpu}{self._pman.hostmsg}: current driver is "
                                        f"'{driver}'")

            try:
                self._sysfs_io.write(path, mode, what=what)
            except Error as err:
                if mode != "off":
                    raise

                if curmode == "off":
                    # When 'intel_pstate' driver is 'off', writing 'off' again errors out. Ignore
                    # the error.
                    continue

                # Setting 'intel_pstate' driver mode to "off" is only possible in non-HWP (legacy)
                # mode. Check for this situation and try to provide a helpful error message.
                try:
                    cpufreq_obj = self._get_cpufreq_msr_obj()
                    _, hwp = next(cpufreq_obj.get_hwp((cpu,)))
                except Error as exc:
                    # Failed to provide additional help, just raise the original exception.
                    raise type(err)(str(err)) from exc

                if hwp:
                    raise ErrorNotSupported(f"'intel_pstate' driver does not support \"off\" mode "
                                            f"when hardware power management (HWP) is enabled:\n"
                                            f"{err.indent(2)}") from err
                raise

    def get_turbo(self, cpus: AbsNumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the turbo on/off status for specified CPUs.

        Args:
            cpus: CPU numbers to get the turbo status for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is either "on" or "off"
            indicating the turbo status.

        Raises:
            ErrorNotSupported: If turbo status cannot be determined for a CPU.
        """

        what = "turbo on/off status"
        path_intel_pstate = self._sysfs_base / "intel_pstate" / "no_turbo"
        path_acpi_cpufreq = self._sysfs_base / "cpufreq" / "boost"

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        for cpu, driver in self.get_driver(cpus):
            if driver == "intel_pstate":
                try:
                    disabled = self._sysfs_io.read_int(path_intel_pstate, what=what)
                except Error as err:
                    try:
                        _, mode = next(self.get_intel_pstate_mode((cpu,)))
                    except (StopIteration, Error) as exc:
                        raise Error(str(err)) from exc

                    if mode != "off":
                        raise

                    raise ErrorNotSupported(f"Turbo is not supported when the 'intel_pstate' "
                                            f"driver is in 'off' mode:\n{err.indent(2)}") from err
                val = "off" if disabled else "on"
            elif driver == "acpi-cpufreq":
                enabled = self._sysfs_io.read_int(path_acpi_cpufreq, what=what)
                val = "on" if enabled else "off"
            else:
                raise ErrorNotSupported(f"Can't check if turbo is enabled for CPU {cpu}"
                                        f"{self._pman.hostmsg}: unsupported CPU frequency driver "
                                        f"'{driver}'")

            # The driver and turbo status are global, so it is enough to read only once.
            break

        for cpu in cpus:
            yield cpu, val

    def set_turbo(self, enable: bool, cpus: AbsNumsType):
        """
        Enable or disable turbo mode for specified CPUs.

        Args:
            enable: if True, enable turbo mode; if False, disable it.
            cpus: CPU numbers to set the turbo mode for.

        Raises:
            ErrorNotSupported: If the CPU frequency driver does not support turbo control or if
                               turbo is not supported in the current driver mode.
        """

        what = "turbo on/off status"
        path_intel_pstate = self._sysfs_base / "intel_pstate" / "no_turbo"
        path_acpi_cpufreq = self._sysfs_base / "cpufreq" / "boost"

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. So get the driver
        # name first.
        for cpu, driver in self.get_driver(cpus):
            if driver == "intel_pstate":
                sysfs_val = str(int(not enable))
                try:
                    self._sysfs_io.write(path_intel_pstate, sysfs_val, what=what)
                except Error as err:
                    try:
                        _, mode = next(self.get_intel_pstate_mode((cpu,)))
                    except (StopIteration, Error) as exc:
                        raise Error(str(err)) from exc

                    if mode != "off":
                        raise

                    raise ErrorNotSupported(f"Turbo is not supported when the 'intel_pstate' "
                                            f"driver is in 'off' mode:\n{err.indent(2)}") from err
            elif driver == "acpi-cpufreq":
                sysfs_val = str(int(enable))
                self._sysfs_io.write(path_acpi_cpufreq, sysfs_val, what=what)
            else:
                status = "on" if enable else "off"
                raise ErrorNotSupported(f"Failed to switch turbo {status} for CPU {cpu}"
                                        f"{self._pman.hostmsg}: Unsupported CPU frequency driver "
                                        f"'{driver}'")

            # The driver and turbo status are global, so it is enough to write only once.
            break

    def get_governor(self, cpus: AbsNumsType) -> Generator[tuple[int, str], None, None]:
        """
        Retrieve and yield the Linux CPU frequency governor name for specified CPUs.

        Args:
            cpus: CPU numbers to get the governor name for.

        Yields:
            Tuple (cpu, governor), where 'cpu' is the CPU number and 'governor' is the current
            governor name for that CPU.

        Raises:
            ErrorNotSupported: If the governor information cannot be determined.
        """

        what = "CPU frequency governor"

        for cpu in cpus:
            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            name = self._sysfs_io.read(path, what=what)
            yield cpu, name

    def get_available_governors(self, cpus: AbsNumsType) -> \
                                            Generator[tuple[int, list[str]], None, None]:
        """
        Retrieve and yield available Linux CPU frequency governor names for specified CPUs.

        Args:
            cpus: CPU numbers to get the list of available governors for.

        Yields:
            Tuple (cpu, governors), where 'cpu' is the CPU number and 'governors' is a list of
            available governor names for that CPU.

        Raises:
            ErrorNotSupported: If the governors sysfs file is not present.
        """

        what = "available CPU frequency governors"

        for cpu in cpus:
            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_available_governors"
            names = self._sysfs_io.read(path, what=what)
            yield cpu, Trivial.split_csv_line(names, sep=" ")

    def set_governor(self, governor: str, cpus: AbsNumsType):
        """
        Set the CPU frequency governor for the specified CPUs.

        Args:
            governor: Name of the governor to set.
            cpus: CPU numbers to set the governor for.
        """

        what = "CPU frequency governor"

        for cpu, governors in self.get_available_governors(cpus):
            if governor not in governors:
                governors_str = ", ".join(governors)
                raise Error(f"Bad governor name '{governor}' for CPU {cpu}{self._pman.hostmsg}, "
                            f"use one of: {governors_str}")

            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            self._sysfs_io.write(path, governor, what=what)
