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
    from typing import Generator, Literal, Sequence
    from pepclibs import _HWPMSR
    from pepclibs.msr import MSR
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    # A CPU frequency sysfs file type. Possible values:
    #   - "min": a minimum CPU frequency file
    #   - "max": a maximum CPU frequency file
    #   - "current": a current CPU frequency file
    _SysfsFileType = Literal["min", "max", "current"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    Provide API for reading and modifying CPU frequency settings via Linux "cpufreq" sysfs.

    Public methods overview.

    1. Frequency control.
        - 'get_min_freq()' - get minimum CPU frequency.
        - 'set_min_freq()' - set minimum CPU frequency.
        - 'get_max_freq()' - get maximum CPU frequency.
        - 'set_max_freq()' - set maximum CPU frequency.
        - 'get_cur_freq()' - get current CPU frequency.
    2. Frequency limits.
        - 'get_min_freq_limit()' - get minimum CPU frequency limit.
        - 'get_max_freq_limit()' - get maximum CPU frequency limit.
        - 'get_available_frequencies()' - get available CPU frequencies.
        - 'get_base_freq()' - get base CPU frequency.
    3. Driver and turbo control.
        - 'get_driver()' - get CPU frequency driver name.
        - 'get_intel_pstate_mode()' - get 'intel_pstate' driver mode.
        - 'set_intel_pstate_mode()' - set 'intel_pstate' driver mode.
        - 'get_turbo()' - get turbo mode status.
        - 'set_turbo()' - enable or disable turbo mode.
    4. Governor control.
        - 'get_governor()' - get CPU frequency governor.
        - 'get_available_governors()' - get available governors.
        - 'set_governor()' - set CPU frequency governor.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers.
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
            verify: Enable verification of values written to sysfs files. The file contents are
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

        self._hwp_msr_obj: _HWPMSR.HWPMSR | None = None

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

        close_attrs = ("_sysfs_io", "_msr", "_hwp_msr_obj", "_cpuinfo", "_pman")
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
        if not self._cpuinfo.is_hybrid():
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
                     self._pman.hostmsg, self._kver)

    def _get_msr(self) -> MSR.MSR:
        """
        Get an 'MSR' object.

        Returns:
            An instance of 'MSR.MSR'.
        """

        if not self._msr:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

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
                        cpus: Sequence[int],
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

        paths_iter = (self._get_cpu_freq_sysfs_path(ftype, cpu, limit=limit) for cpu in cpus)

        for path, freq in self._sysfs_io.read_paths_int(paths_iter, what=f"{ftype} frequency"):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

            # The frequency value is in kHz in sysfs, convert to Hz.
            yield cpu, freq * 1000

    def get_min_freq(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

    def get_max_freq(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

    def get_cur_freq(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

    def get_min_freq_limit(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

    def get_max_freq_limit(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

    def _validate_freq(self, freq: int, ftype: _SysfsFileType, cpus: Sequence[int]):
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

        # Generate paths for all required reads.
        min_paths_iter = (self._get_cpu_freq_sysfs_path("min", cpu, limit=True) for cpu in cpus)
        max_paths_iter = (self._get_cpu_freq_sysfs_path("max", cpu, limit=True) for cpu in cpus)

        if ftype == "min":
            cur_paths_iter = (self._get_cpu_freq_sysfs_path("max", cpu) for cpu in cpus)
            cur_what = "max frequency"
        else:
            cur_paths_iter = (self._get_cpu_freq_sysfs_path("min", cpu) for cpu in cpus)
            cur_what = "min frequency"

        min_limits_iter = self._sysfs_io.read_paths_int(min_paths_iter, what="min frequency limit")
        max_limits_iter = self._sysfs_io.read_paths_int(max_paths_iter, what="max frequency limit")
        cur_freqs_iter = self._sysfs_io.read_paths_int(cur_paths_iter, what=cur_what)
        zipped_iter = zip(cpus, min_limits_iter, max_limits_iter, cur_freqs_iter)

        for cpu, (_, min_limit), (_, max_limit), (_, cur_freq) in zipped_iter:
            # Convert from kHz to Hz.
            min_freq_limit = min_limit * 1000
            max_freq_limit = max_limit * 1000
            current_freq = cur_freq * 1000

            if freq < min_freq_limit or freq > max_freq_limit:
                name = f"{ftype} CPU {cpu} frequency"
                freq_str = Human.num2si(freq, unit="Hz", decp=4)
                min_limit_str = Human.num2si(min_freq_limit, unit="Hz", decp=4)
                max_limit_str = Human.num2si(max_freq_limit, unit="Hz", decp=4)
                raise ErrorOutOfRange(f"{name} value of '{freq_str}' is out of range, must be "
                                      f"within [{min_limit_str},{max_limit_str}]")

            if ftype == "min":
                if freq > current_freq:
                    name = f"{ftype} CPU {cpu} frequency"
                    freq_str = Human.num2si(freq, unit="Hz", decp=4)
                    max_freq_str = Human.num2si(current_freq, unit="Hz", decp=4)
                    raise ErrorBadOrder(f"{name} value of '{freq_str}' is greater than the "
                                        f"currently configured maximum frequency of {max_freq_str}")
            else:
                if freq < current_freq:
                    name = f"{ftype} CPU {cpu} frequency"
                    freq_str = Human.num2si(freq, unit="Hz", decp=4)
                    min_freq_str = Human.num2si(current_freq, unit="Hz", decp=4)
                    raise ErrorBadOrder(f"{name} value of '{freq_str}' is less than the "
                                        f"currently configured minimum frequency of {min_freq_str}")

    def _set_freq_sysfs(self, freq: int, ftype: _SysfsFileType, cpus: Sequence[int]):
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
        retries = 2
        sleep = 0.1

        self._validate_freq(freq, ftype, cpus)

        paths_iter = (self._get_cpu_freq_sysfs_path(ftype, cpu) for cpu in cpus)

        try:
            if not self._verify:
                self._sysfs_io.write_paths_int(paths_iter, freq // 1000, what=what)
            else:
                self._sysfs_io.write_paths_verify_int(paths_iter, freq // 1000, what=what,
                                                       retries=retries, sleep=sleep)
        except ErrorVerifyFailed as err:
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            if not hasattr(err, "path"):
                raise

            path: Path = getattr(err, "path")
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))
            setattr(err, "cpu", cpu)
            raise err

    def set_min_freq(self, freq: int, cpus: Sequence[int]):
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

    def set_max_freq(self, freq: int, cpus: Sequence[int]):
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
                                  cpus: Sequence[int]) -> Generator[tuple[int, list[int]],
                                                                    None, None]:
        """
        Yield available CPU frequencies for specified CPUs. Frequencies are read from the
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

        fname = "scaling_available_frequencies"
        paths_iter = (self._get_policy_sysfs_path(cpu, fname) for cpu in cpus)

        for path, val in self._sysfs_io.read_paths(paths_iter, what="available CPU frequencies"):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

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
                                    cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs using the 'intel_pstate' driver.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.
        """

        paths_iter = (self._get_policy_sysfs_path(cpu, "base_frequency") for cpu in cpus)

        for path, freq in self._sysfs_io.read_paths_int(paths_iter, what="base frequency"):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

            # The frequency value is in kHz in sysfs, convert to Hz.
            yield cpu, freq * 1000

    def _get_base_freq_bios_limit(self,
                                  cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Retrieve and yield the base frequency for specified CPUs using the 'bios_limit' sysfs file.

        Args:
            cpus: CPU numbers to get the base frequency for.

        Yields:
            Tuple of (cpu, frequency), where 'cpu' is the CPU number and 'frequency' is the base
            frequency in Hz.
        """

        paths_iter = (self._sysfs_base / f"cpu{cpu}/cpufreq/bios_limit" for cpu in cpus)

        for path, freq in self._sysfs_io.read_paths_int(paths_iter, what="base frequency"):
            # Extract CPU number from path (e.g., /sys/.../cpu42/cpufreq/bios_limit -> 42).
            cpu_dir = path.parent.parent.name  # e.g., "cpu42"
            cpu = int(cpu_dir.replace("cpu", ""))

            # On Intel systems that support turbo, the 'bios_limit' file includes the turbo
            # activation frequency, which is base frequency + 1MHz. So we need to subtract 1MHz from
            # the value read from the 'bios_limit' file to get the actual base frequency.
            if freq % 10000:
                freq -= 1000

            # The frequency value is in kHz in sysfs, convert to Hz.
            yield cpu, freq * 1000

    def get_base_freq(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
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

        # Try intel_pstate method first, fall back to bios_limit if not supported.
        yielded_cpus = set()
        err1 = None

        try:
            for cpu, val in self._get_base_freq_intel_pstate(cpus):
                yielded_cpus.add(cpu)
                yield cpu, val
        except ErrorNotSupported as exc:
            err1 = exc

        # If some CPUs weren't handled by intel_pstate, try bios_limit for the rest.
        if err1 is not None:
            left_cpus = [cpu for cpu in cpus if cpu not in yielded_cpus]
            if left_cpus:
                yield from self._get_base_freq_bios_limit(left_cpus)
            elif not yielded_cpus:
                # No CPUs were handled successfully, re-raise the original error.
                raise ErrorNotSupported(str(err1))

    def get_driver(self, cpus: Sequence[int]) -> Generator[tuple[int, str], None, None]:
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

        intel_pstate_exists: bool | None = None

        fname = "scaling_driver"
        paths_iter = (self._get_policy_sysfs_path(cpu, fname) for cpu in cpus)

        for path, name in self._sysfs_io.read_paths(paths_iter, what=what, val_if_not_found=""):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

            if not name:
                # The 'intel_pstate' driver may be in 'off' mode, in which case the
                # 'scaling_driver' sysfs file does not exist. Check if the 'intel_pstate'
                # sysfs directory exists to confirm the driver is present.
                if intel_pstate_exists is None:
                    intel_pstate_exists = self._pman.exists(self._sysfs_base / "intel_pstate")

                if intel_pstate_exists:
                    name = "intel_pstate"
                else:
                    raise ErrorNotSupported(f"Failed to read {what} from '{path}'"
                                            f"{self._pman.hostmsg}: File does not exist")
            elif name == "intel_cpufreq":
                # The 'intel_pstate' driver reports itself as 'intel_pstate' in active mode
                # and 'intel_cpufreq' in passive mode. We always return 'intel_pstate' to
                # avoid user confusion.
                name = "intel_pstate"

            yield cpu, name

    def get_intel_pstate_mode(self,
                              cpus: Sequence[int]) -> Generator[tuple[int, str], None, None]:
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

        # Mode is global, read it once when needed.
        mode: str | None = None

        for cpu, driver in self.get_driver(cpus):
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"Failed to get 'intel_pstate' driver mode for CPU "
                                        f"{cpu}{self._pman.hostmsg}: Current driver is '{driver}'")
            if mode is None:
                mode = self._sysfs_io.read(path, what=what)

            yield cpu, mode

    def set_intel_pstate_mode(self, mode: str, cpus: Sequence[int]):
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
            raise Error(f"Bad 'intel_pstate' mode '{mode}', use one of: {modes_str}")

        what = "'intel_pstate' driver mode"
        path = self._sysfs_base / "intel_pstate" / "status"
        cpus_to_check = []

        for cpu, curmode in self.get_intel_pstate_mode(cpus):
            if mode != curmode:
                cpus_to_check.append(cpu)

        if not cpus_to_check:
            return

        # If switching to "off", check HWP for all CPUs needing change (batch operation).
        if mode == "off":
            hwp_msr_obj = self._get_hwp_msr_obj()
            for cpu, hwp in hwp_msr_obj.get_hwp(cpus_to_check):
                if hwp:
                    raise ErrorNotSupported("'intel_pstate' driver does not support \"off\" mode "
                                            "when hardware power management (HWP) is enabled")

        try:
            self._sysfs_io.write(path, mode, what=what)
        except Error as err:
            raise Error(f"Failed to set 'intel_pstate' driver mode to '{mode}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def get_turbo(self, cpus: Sequence[int]) -> Generator[tuple[int, str], None, None]:
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

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. Get the driver
        # name for the first CPU only, since turbo status is global.
        cpu = -1
        for cpu in cpus:
            break
        if cpu == -1:
            raise Error("Failed to determine turbo status: No CPUs were provided")

        driver = ""
        for _, driver in self.get_driver((cpu,)):
            break
        if not driver:
            raise Error(f"Failed to get driver for CPU {cpu}")

        if driver == "intel_pstate":
            try:
                disabled = self._sysfs_io.read_int(path_intel_pstate, what=what)
            except Error as err:
                try:
                    mode = ""
                    for _, mode in self.get_intel_pstate_mode((cpu,)):
                        break
                except Error as exc:
                    raise Error(str(err)) from exc

                if mode == "":
                    raise Error("BUG: Failed to get 'intel_pstate' driver mode") from err

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
                                    f"{self._pman.hostmsg}: Unsupported CPU frequency driver "
                                    f"'{driver}'")

        for cpu in cpus:
            yield cpu, val

    def set_turbo(self, enable: bool, cpus: Sequence[int]):
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

        # Location of the turbo knob in sysfs depends on the CPU frequency driver. Get the driver
        # name for the first CPU only, since turbo status is global.
        cpu = -1
        for cpu in cpus:
            break
        if cpu == -1:
            raise Error("Failed to set turbo: No CPUs were provided")

        driver = ""
        for _, driver in self.get_driver((cpu,)):
            break
        if not driver:
            raise Error(f"Failed to get driver for CPU {cpu}")

        if driver == "intel_pstate":
            sysfs_val = str(int(not enable))
            try:
                self._sysfs_io.write(path_intel_pstate, sysfs_val, what=what)
            except Error as err:
                try:
                    mode = ""
                    for _, mode in self.get_intel_pstate_mode((cpu,)):
                        break
                except Error as exc:
                    raise Error(str(err)) from exc

                if mode == "":
                    raise Error("BUG: Failed to get 'intel_pstate' driver mode") from err

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

        # Flush any pending sysfs writes to ensure that the turbo setting takes effect. This is
        # important because the turbo setting may affect the max. frequency limit.
        self._sysfs_io.flush_transaction()

        for cpu in cpus:
            # The max. frequency limit may change when turbo is enabled or disabled. Clear the
            # frequency paths cache to force re-reading the sysfs paths.
            path = self._get_cpu_freq_sysfs_path("max", cpu, limit=True)
            self._sysfs_io.cache_remove(path)

    def get_governor(self, cpus: Sequence[int]) -> Generator[tuple[int, str], None, None]:
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

        fname = "scaling_governor"
        paths_iter = (self._get_policy_sysfs_path(cpu, fname) for cpu in cpus)

        for path, name in self._sysfs_io.read_paths(paths_iter, what=what):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

            yield cpu, name

    def get_available_governors(self, cpus: Sequence[int]) -> \
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

        fname = "scaling_available_governors"
        paths_iter = (self._get_policy_sysfs_path(cpu, fname) for cpu in cpus)

        for path, names in self._sysfs_io.read_paths(paths_iter, what=what):
            # Extract CPU number from path (e.g., /sys/.../policy42/... -> 42).
            policy_dir = path.parent.name  # e.g., "policy42"
            cpu = int(policy_dir.replace("policy", ""))

            yield cpu, Trivial.split_csv_line(names, sep=" ")

    def set_governor(self, governor: str, cpus: Sequence[int]):
        """
        Set the CPU frequency governor for the specified CPUs.

        Args:
            governor: Name of the governor to set.
            cpus: CPU numbers to set the governor for.

        Raises:
            ErrorNotSupported: If the CPU governors sysfs files do not exist.
        """

        what = "CPU frequency governor"
        paths_to_write = []

        # Validate governor for all CPUs and collect paths.
        for cpu, governors in self.get_available_governors(cpus):
            if governor not in governors:
                governors_str = ", ".join(governors)
                raise Error(f"Bad governor name '{governor}' for CPU {cpu}{self._pman.hostmsg}, "
                            f"use one of: {governors_str}")

            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            paths_to_write.append(path)

        # Write to all governor files in one batch operation.
        if paths_to_write:
            self._sysfs_io.write_paths(paths_to_write, governor, what=what)
