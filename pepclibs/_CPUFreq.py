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
Provide a capability for reading and modifying CPU frequency settings.
"""

# TODO: Split this file on 3 files, one per class. This file is too large.
from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import Generator, cast
import contextlib
from pathlib import Path
from pepclibs import CPUInfo, CPUModels, _SysfsIO
from pepclibs._PropsClassBaseTypes import AbsNumsType
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial, KernelVersion
from pepclibs.helperlibs.Exceptions import Error, ErrorBadFormat, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

if typing.TYPE_CHECKING:
    from pepclibs.msr import MSR, FSBFreq, PMEnable, HWPRequest, HWPRequestPkg, PlatformInfo
    from pepclibs.msr import TurboRatioLimit, HWPCapabilities
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and modify CPU frequency settings via the Linux "cpufreq" sysfs
    interface.

    Public Methods:
        - get_min_freq: Retrieve the minimum CPU frequency for specified CPUs.
        - get_max_freq: Retrieve the maximum CPU frequency for specified CPUs.
        - set_min_freq: Set the minimum CPU frequency for specified CPUs.
        - set_max_freq: Set the maximum CPU frequency for specified CPUs.
        - get_cur_freq: Retrieve the current CPU frequency for specified CPUs.
        - get_min_freq_limit: Retrieve the minimum CPU frequency limit for specified CPUs.
        - get_max_freq_limit: Retrieve the maximum CPU frequency limit for specified CPUs.
        - get_available_frequencies: Retrieve the list of available CPU frequencies for specified
                                     CPUs.
        - get_base_freq: Retrieve the base frequency for specified CPUs.
        - get_driver: Retrieve the CPU frequency driver name for specified CPUs.
        - get_intel_pstate_mode: Retrieve the 'intel_pstate' driver mode for specified CPUs.
        - set_intel_pstate_mode: Set the 'intel_pstate' driver mode for specified CPUs.
        - get_turbo: Retrieve the turbo mode status for specified CPUs.
        - set_turbo: Enable or disable turbo mode for specified CPUs.
        - get_governor: Retrieve the CPU frequency governor for specified CPUs.
        - get_available_governors: Retrieve the list of available governors for specified CPUs.
        - set_governor: Set the CPU frequency governor for specified CPUs.

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

        self._cpufreq_msr_obj: CPUFreqMSR | None = None

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
            self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)
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

    def _get_cpufreq_msr_obj(self) -> CPUFreqMSR:
        """Return an instance of 'CPUFreqMSR' class."""

        if not self._cpufreq_msr_obj:
            msr = self._get_msr()
            self._cpufreq_msr_obj = CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman, msr=msr,
                                               enable_cache=self._enable_cache)
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

    def _get_cpu_freq_sysfs_path(self, key: str, cpu: int, limit: bool = False) -> Path:
        """
        Return the sysfs file path for a CPU frequency read or write operation. Use paths cache to
        avoid recomputing the paths.

        Args:
            key: The frequency key (e.g., "min", "max").
            cpu: CPU number for which to get the path.
            limit: Whether to use the "limit" file or the "scaling" file.

        Returns:
            The sysfs file path for the specified CPU and other parameters.
        """

        if key not in self._path_cache:
            self._path_cache[key] = {}
        if cpu not in self._path_cache[key]:
            self._path_cache[key][cpu] = {}

        if limit in self._path_cache[key][cpu]:
            return self._path_cache[key][cpu][limit]

        fname = "scaling_" + key + "_freq"
        prefix = "cpuinfo_" if limit else "scaling_"
        fname = prefix + key + "_freq"

        path = self._get_policy_sysfs_path(cpu, fname)
        self._path_cache[key][cpu][limit] = path
        return path

    def _get_freq_sysfs(self,
                        key: str,
                        cpus: AbsNumsType,
                        limit: bool = False) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield CPU frequencies from the Linux "cpufreq" sysfs files for specified CPUs.

        Args:
            key: The frequency key (e.g., "min", "max").
            cpus: CPU numbers to get the frequency for.
            limit: Whether to use the "limit" file or the "scaling" sysfs file for reading the
                   frequency.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            frequency in Hz.
        """

        self._warn_no_ecores_bug()

        for cpu in cpus:
            path = self._get_cpu_freq_sysfs_path(key, cpu, limit=limit)
            freq = self._sysfs_io.read_int(path, what=f"{key}. frequency for CPU {cpu}")
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

        yield from self._get_freq_sysfs("cur", cpus)

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

    def _set_freq_sysfs(self, freq: int, key: str, cpus: AbsNumsType):
        """
        Set the CPU frequency for the specified CPUs using the Linux "cpufreq" sysfs interface.

        Args:
            freq: Target CPU frequency in Hz.
            key: The frequency key (e.g., "min", "max").
            cpus: CPU numbers to set the frequency for.
        """

        self._warn_no_ecores_bug()

        what = f"{key}. CPU frequency"
        retries = 0
        sleep = 0.0

        for cpu in cpus:
            if self._verify:
                cpu_info = self._cpuinfo.info
                if cpu_info["vendor"] == "GenuineIntel" and "hwp" in cpu_info["flags"][cpu]:
                    # On some Intel platforms with HWP enabled the change does not happen
                    # immediately. Retry few times.
                    retries = 2
                    sleep = 0.1

            path = self._get_cpu_freq_sysfs_path(key, cpu)

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
            ErrorVerifyFailed: If the frequency could not be set or verified after retries. The
                               exception object will have an additional 'cpu' attribute indicating
                               the CPU number that failed, the 'expected' attribute will contain the
                               expected value, and the 'actual' attribute will contain the actual
                               value read from sysfs.
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
            ErrorVerifyFailed: If the frequency could not be set or verified after retries. The
                               exception object will have an additional 'cpu' attribute indicating
                               the CPU number that failed, the 'expected' attribute will contain the
                               expected value, and the 'actual' attribute will contain the actual
                               value read from sysfs.
        """

        self._set_freq_sysfs(freq, "max", cpus)

    def get_available_frequencies(self, cpus: AbsNumsType) -> \
                                            Generator[tuple[int, list[int]], None, None]:
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

    def _get_base_freq_intel_pstate(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
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

    def _get_base_freq_bios_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
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

class CPUFreqCPPC(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read CPU frequency and performance information from ACPI CPPC via Linux
    sysfs.

    Public Methods:
        - get_min_freq_limit: Yield minimum frequency limits for CPUs from ACPI CPPC.
        - get_max_freq_limit: Yield maximum frequency limits for CPUs from ACPI CPPC.
        - get_min_perf_limit: Yield minimum performance limits for CPUs from ACPI CPPC.
        - get_max_perf_limit: Yield maximum performance limits for CPUs from ACPI CPPC.
        - get_base_freq: Yield base frequency for CPUs from ACPI CPPC.
        - get_base_perf: Yield base performance for CPUs from ACPI CPPC.

    Notes:
        Methods do not validate the 'cpus' argument. Ensure that provided CPU numbers are valid and
        online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access, used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
        """

        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo
        self._sysfs_io: _SysfsIO.SysfsIO

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

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

        close_attrs = ("_sysfs_io", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_sysfs_path(self, cpu: int, fname: str) -> Path:
        """
        Construct and return full sysfs path for a given CPU and file name under the 'acpi_cppc'
        sysfs sub-directory.

        Args:
            cpu: CPU number for which to construct the path.
            fname: Name of the sysfs file under the 'acpi_cppc' sysfs sub-directory.

        Returns:
            The full path to the requested sysfs file.
        """

        return self._sysfs_base / f"cpu{cpu}/acpi_cppc" / fname

    def _read_cppc_sysfs_file(self, cpu: int, fname: str, what: str) -> int:
        """
        Read the specified ACPI CPPC sysfs file for a given CPU and gracefully handle errors. Cache
        the value read from the sysfs file to avoid repeated reads.

        Args:
            cpu: CPU number for which to read the sysfs file.
            fname: Name of the sysfs file under the 'acpi_cppc' sysfs sub-directory to read.
            what: Description of the value being read, used for logging and error messages.

        Returns:
            The value read from the sysfs file, after adding it to the cache.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        path = self._get_sysfs_path(cpu, fname)

        val = None

        try:
            val = self._sysfs_io.read_int(path, what=what)
        except ErrorBadFormat:
            raise
        except ErrorNotSupported:
            raise
        except Error as err:
            # On some platforms reading CPPC sysfs files always fails. So treat these errors as if
            # the sysfs file was not even available and raise 'ErrorNotSupported'.
            _LOG.debug("ACPI CPPC sysfs file '%s' is not readable%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(str(err)) from err

        if val == 0:
            _LOG.debug("ACPI CPPC sysfs file '%s' contains 0%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(f"Read '0' for {what} from '{path}'")

        return self._sysfs_io.cache_add(path, val)

    def get_min_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the minimum frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum frequency limit for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the minimum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "lowest_freq", f"max. CPU {cpu} frequency limit")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_max_freq_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the maximum frequency limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum frequency limit for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the maximum
            frequency limit in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "highest_freq", f"max. CPU {cpu} frequency limit")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_min_perf_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the the minimum performance level limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the minimum performance level limit for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its minimum performance
            level limit.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"min. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "lowest_perf", what)
            yield cpu, val

    def get_max_perf_limit(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the the maximum performance level limit for specified CPUs.

        Args:
            cpus: CPU numbers to get the maximum performance level limit for.

        Yields:
            Tuple of (cpu, val), where 'cpu' is the CPU number and 'val' is its maximum performance
            level limit.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"max. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "highest_perf", what)
            yield cpu, val

    def get_base_freq(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.

        Raises:
            ErrorNotSupported: If the ACPI CPPC CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "nominal_freq", f"base CPU {cpu} frequency")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_base_perf(self, cpus: AbsNumsType) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base performance level value for specified CPUs.

        Args:
            cpus: CPU numbers to get the base performance level value for.

        Yields:
            Tuple (cpu, value), where 'cpu' is the CPU number and 'value' is the base performance
            level.

        Raises:
            ErrorNotSupported: If the ACPI CPPC sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "nominal_perf", f"base CPU {cpu} performance")
            yield cpu, val

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

    def _get_freq_msr(self, key, cpus):
        """
        Retrieve and yield the minimum or maximum CPU frequency for specified CPUs.

        Args:
            key: The frequency key (e.g., "min", "max").
            cpus: CPU numbers to get the frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the
            corresponding minimum or maximum frequency in Hz.

        Raises:
            ErrorNotSupported: If the 'MSR_HWP_REQUEST' model specific register is not supported.
        """

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{key}_perf"

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

    def _set_freq_msr(self, freq: int, key: str, cpus: AbsNumsType):
        """
        Set the CPU frequency for specified CPUs using the 'MSR_HWP_REQUEST' model specific
        register.

        Args:
            freq: The frequency value to set, in Hz.
            key: The frequency key (e.g., "min", "max").
            cpus: CPU numbers to set the frequency for.

        Raises:
            ErrorNotSupported: If disabling package control via 'MSR_HWP_REQUEST' is not supported.
        """

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{key}_perf"

        hwpreq = self._get_hwpreq()

        # Disable package control.
        pkg_control_cpus = []
        with contextlib.suppress(ErrorNotSupported):
            for cpu, enabled in hwpreq.is_feature_enabled("pkg_control"):
                if enabled:
                    pkg_control_cpus.append(cpu)
            hwpreq.write_feature(f"{feature_name}_valid", "on", cpus=pkg_control_cpus)

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
