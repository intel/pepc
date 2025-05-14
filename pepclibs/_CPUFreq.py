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

from __future__ import annotations # Remove when switching to Python 3.10+.

import contextlib
from pathlib import Path
from pepclibs import CPUInfo, CPUModels, _SysfsIO
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial, KernelVersion
from pepclibs.msr import MSR, FSBFreq, PMEnable, HWPRequest, HWPRequestPkg, PlatformInfo
from pepclibs.msr import TurboRatioLimit, HWPCapabilities
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    Provide functionality for reading and modifying CPU frequency settings via the Linux "cpufreq"
    subsystem sysfs interface.

    Overview of public methods:

    1. Get or set CPU frequency using Linux "cpufreq" sysfs interfaces:
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'
       * 'get_cur_freq()'
    2. Retrieve CPU frequency limits via sysfs:
       * 'get_min_freq_limit()'
       * 'get_max_freq_limit()'
    3. Retrieve the list of available CPU frequencies:
       * 'get_available_frequencies()'
    4. Retrieve the CPU base frequency:
       * 'get_base_freq()'
    5. Retrieve the CPU frequency driver name:
       * 'get_driver()'
    6. Get or set the 'intel_pstate' driver mode:
       * 'get_intel_pstate_mode()'
       * 'set_intel_pstate_mode()'
    7. Get or set turbo mode status:
       * 'get_turbo()'
       * 'set_turbo()'
    8. Get or set the Linux CPU frequency governor:
       * 'get_governor()'
       * 'get_available_governors()'
       * 'set_governor()'

    Note: Methods of this class do not validate the 'cpus' argument. The caller is responsible for
    ensuring that the provided CPU numbers are valid and online.
    """

    def _warn_no_ecores_bug(self):
        """
        Kernels prior to v6.5 had a bug that affected hybrid systems with disabled E-cores. This
        issue was fixed by the following Linux kernel commit:

        0fcfc9e51990 cpufreq: intel_pstate: Fix scaling for hybrid-capable systems with disabled
        E-cores

        Detect if the target system is affected and print a warning.
        """

        if not self._check_no_ecores_bug:
            return
        if not self._cpuinfo.info["hybrid"]:
            return

        ecore_cpus, pcore_cpus = self._cpuinfo.get_hybrid_cpus()
        if ecore_cpus or pcore_cpus:
            return

        if not self._kver:
            try:
                self._kver = KernelVersion.get_kver(pman=self._pman)
            except Error as err:
                _LOG.warning("failed to detect kernel version%s:\n%s",
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
        _LOG.warning("kernel version%s is %s, and the processor is hybrid with no E-cores or all "
                     "E-cores disabled.\nKernel versions prior to 6.5 have a bug: sysfs CPU "
                     "frequency files have incorrect numbers on systems like this.\nThe fix is in "
                     "Linux kernel commit '0fcfc9e51990246a9813475716746ff5eb98c6aa'.",
                     {self._pman.hostmsg}, {self._kver})

    def _get_msr(self):
        """Return an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_cpufreq_msr_obj(self):
        """Return a '_CPUFreqMSR' object."""

        if not self._cpufreq_msr_obj:
            msr = self._get_msr()
            self._cpufreq_msr_obj = CPUFreqMSR(cpuinfo=self._cpuinfo, pman=self._pman, msr=msr,
                                               enable_cache=self._enable_cache)
        return self._cpufreq_msr_obj

    def _get_policy_sysfs_path(self, cpu, fname):
        """Construct and return a Linux "cpufreq" policy sysfs path for file 'fname'."""

        return self._sysfs_base / "cpufreq" / f"policy{cpu}" / fname

    def _get_cpu_freq_sysfs_path(self, key, cpu, limit=False):
        """Get the sysfs file path for a CPU frequency read of write operation."""

        if key not in self._path_cache:
            self._path_cache[key] = {}
        if cpu not in self._path_cache[key]:
            self._path_cache[key][cpu] = {}

        path = self._path_cache[key][cpu].get(limit)
        if path:
            return path

        fname = "scaling_" + key + "_freq"
        prefix = "cpuinfo_" if limit else "scaling_"
        fname = prefix + key + "_freq"

        path = self._get_policy_sysfs_path(cpu, fname)
        self._path_cache[key][cpu][limit] = path
        return path

    def _get_freq_sysfs(self, key, cpus, limit=False):
        """Yield CPU frequency from the Linux "cpufreq" sysfs file."""

        self._warn_no_ecores_bug()

        for cpu in cpus:
            path = self._get_cpu_freq_sysfs_path(key, cpu, limit=limit)
            freq = self._sysfs_io.read_int(path, what=f"{key}. frequency for CPU {cpu}")
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_min_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum CPU
        frequency via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the minimum frequency for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("min", cpus)

    def get_max_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum frequency for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus)

    def get_cur_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the current CPU
        frequency read via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the current frequency for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("cur", cpus)

    def get_min_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum CPU
        frequency limit for CPU 'cpu', read via Linux "cpufreq" sysfs interfaces. The arguments are
        as follows.
          * cpus - a collection of integer CPU numbers to get the frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("min", cpus, limit=True)

    def get_max_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency limit for CPU 'cpu', read via Linux "cpufreq" sysfs interfaces. The arguments are
        as follows.
          * cpus - a collection of integer CPU numbers to get the frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus, limit=True)

    def _set_freq_sysfs(self, freq, key, cpus):
        """
        For every CPU in 'cpus', set CPU frequency by writing to the Linux "cpufreq" sysfs file.
        """

        self._warn_no_ecores_bug()

        what = f"{key}. CPU frequency"

        for cpu in cpus:
            if self._verify:
                cpu_info = self._cpuinfo.info
                if cpu_info["vendor"] == "GenuineIntel" and "hwp" in cpu_info["flags"][cpu]:
                    # On some Intel platforms with HWP enabled the change does not happen
                    # immediately. Retry few times.
                    retries = 2
                    sleep = 0.1
                else:
                    retries = sleep = 0

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

    def set_min_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', set minimum CPU frequency via Linux "cpufreq" sysfs interfaces. The
        arguments are as follows.
          * freq - the minimum frequency value to set, hertz.
          * cpus - a collection of CPU numbers to set the frequency for.
        """

        self._set_freq_sysfs(freq, "min", cpus)

    def set_max_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', set maximum CPU frequency via Linux "cpufreq" sysfs interfaces. The
        arguments are as follows.
          * freq - the maximum frequency value to set, hertz.
          * cpus - a collection of CPU numbers to set the frequency for.
        """

        self._set_freq_sysfs(freq, "max", cpus)

    def get_available_frequencies(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the list of available
        CPU frequencies in Hz for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the list of available frequencies for.

        Raise 'ErrorNotSupported' if the frequencies sysfs file does not exist. The sysfs file
        is provided by the 'acpi-cpufreq' driver, but not by the 'intel_idle' driver.
        """

        for cpu in cpus:
            path = self._get_policy_sysfs_path(cpu, "scaling_available_frequencies")
            val = self._sysfs_io.read(path, what="available CPU frequencies")

            freqs = []
            for freq in val.split():
                try:
                    freq = Trivial.str_to_int(freq, what="CPU frequency value")
                    freqs.append(freq * 1000)
                except Error as err:
                    raise Error(f"bad contents of file '{path}'{self._pman.hostmsg}\n"
                                f"{err.indent(2)}") from err

            yield cpu, sorted(freqs)

    def _get_base_freq_intel_pstate(self, cpus):
        """Yield base frequency from 'intel_pstate' driver's sysfs file."""

        for cpu in cpus:
            path = self._get_policy_sysfs_path(cpu, "base_frequency")
            freq = self._sysfs_io.read_int(path, what=f"base frequency for CPU {cpu}")
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def _get_base_freq_bios_limit(self, cpus):
        """Yield base frequency from the 'bios_limit' sysfs file."""

        for cpu in cpus:
            path = self._sysfs_base / f"cpu{cpu}/cpufreq/bios_limit"
            freq = self._sysfs_io.read_int(path, what=f"base frequency for CPU {cpu}")
            # The frequency value is in kHz in sysfs.
            yield cpu, freq * 1000

    def get_base_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is base frequency of CPU
        'cpu', read via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get base frequency for.

        Raise 'ErrorNotSupported' if the base frequency sysfs files do not exist.
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

    def get_driver(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the Linux CPU frequency
        driver name for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get driver name for.
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

    def get_intel_pstate_mode(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the 'intel_pstate' CPU
        frequency driver mode for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get driver mode for.
        """

        what = "'intel_pstate' driver mode"
        path = self._sysfs_base / "intel_pstate" / "status"

        for cpu, driver in self.get_driver(cpus):
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"failed to get 'intel_pstate' driver mode for CPU "
                                        f"{cpu}{self._pman.hostmsg}: current driver is '{driver}'")
            mode = self._sysfs_io.read(path, what=what)
            yield cpu, mode

    def set_intel_pstate_mode(self, mode, cpus):
        """
        For every CPU in 'cpus', set 'intel_pstate' driver mode to 'mode'. The arguments are as
        follows.
          * mode - 'intel_pstate' driver mode.
          * cpus - a collection of integer CPU numbers to set driver mode for.
        """

        modes = ("active", "passive", "off")
        if mode not in modes:
            modes = ", ".join(modes)
            raise Error(f"bad 'intel_pstate' mode '{mode}', use one of: {modes}")

        what = "'intel_pstate' driver mode"
        path = self._sysfs_base / "intel_pstate" / "status"

        driver_iter = self.get_driver(cpus)
        mode_iter = self.get_intel_pstate_mode(cpus)

        for (cpu, driver), (_, curmode) in zip(driver_iter, mode_iter):
            if driver != "intel_pstate":
                raise ErrorNotSupported(f"failed to set 'intel_pstate' driver mode to '{mode}' for "
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
                    raise type(err)(err) from exc

                if hwp == "on":
                    raise ErrorNotSupported(f"'intel_pstate' driver does not support \"off\" mode "
                                            f"when hardware power management (HWP) is enabled:\n"
                                            f"{err.indent(2)}") from err
                raise

    def get_turbo(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the turbo on/of status
        for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get turbo status for.
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
                        raise Error(err) from exc

                    if mode != "off":
                        raise

                    raise ErrorNotSupported(f"turbo is not supported when the 'intel_pstate' "
                                            f"driver is in 'off' mode:\n{err.indent(2)}") from err
                val = "off" if disabled else "on"
            elif driver == "acpi-cpufreq":
                enabled = self._sysfs_io.read_int(path_acpi_cpufreq, what=what)
                val = "on" if enabled else "off"
            else:
                raise ErrorNotSupported(f"can't check if turbo is enabled for CPU {cpu}"
                                        f"{self._pman.hostmsg}: unsupported CPU frequency driver "
                                        f"'{driver}'")

            yield cpu, val

    def set_turbo(self, enable, cpus):
        """
        Enable or disable turbo for CPUs in 'cpus'. The arguments are as follows.
          * enable - enable turbo if 'True', disable otherwise.
          * cpus - a collection of integer CPU numbers to set turbo for.
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
                        raise Error(err) from exc

                    if mode != "off":
                        raise

                    raise ErrorNotSupported(f"turbo is not supported when the 'intel_pstate' "
                                            f"driver is in 'off' mode:\n{err.indent(2)}") from err
            elif driver == "acpi-cpufreq":
                sysfs_val = str(int(enable))
                self._sysfs_io.write(path_acpi_cpufreq, sysfs_val, what=what)
            else:
                status = "on" if enable else "off"
                raise ErrorNotSupported(f"failed to switch turbo {status} for CPU {cpu}"
                                        f"{self._pman.hostmsg}: unsupported CPU frequency driver "
                                        f"'{driver}'")

    def get_governor(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the Linux CPU frequency
        governor name for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get governor name for.
        """

        what = "CPU frequency governor"

        for cpu in cpus:
            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            name = self._sysfs_io.read(path, what=what)
            yield cpu, name

    def get_available_governors(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the list of available
        Linux CPU frequency governor names for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get available governor names for.
        """

        what = "available CPU frequency governors"

        for cpu in cpus:
            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_available_governors"
            names = self._sysfs_io.read(path, what=what)
            yield cpu, Trivial.split_csv_line(names, sep=" ")

    def set_governor(self, governor, cpus):
        """
        For the Linux CPU frequency governor to 'governor' for CPUs 'cpus'. The arguments are as
        follows.
          * governor - name of the governor to set.
          * cpus - a collection of integer CPU numbers to set the governor for.
        """

        what = "CPU frequency governor"

        for cpu, governors in self.get_available_governors(cpus):
            if governor not in governors:
                governors = ", ".join(governors)
                raise Error(f"bad governor name '{governor}' for CPU {cpu}{self._pman.hostmsg}, "
                            f"use one of: {governors}")

            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            self._sysfs_io.write(path, governor, what=what)

    def __init__(self, pman=None, cpuinfo=None, msr=None, sysfs_io=None, enable_cache=True,
                 verify=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to get/set CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for the rare cases this class accessing
                  MSR registers.
          * sysfs_io - an '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                       files.
          * enable_cache - this argument can be used to disable caching.
          * verify - enable verification of written values, by default verification is enabled.

        This class is focused on 'sysfs' interface, but in some cases it may access MSR registers
        via the 'CPUFreqMSR' class.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._sysfs_io = sysfs_io
        self._enable_cache = enable_cache
        self._verify = verify
        self._path_cache = {}

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_sysfs_io = sysfs_io is None

        self._cpufreq_msr_obj = None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        # Kernel version running on the target system.
        self._kver = None
        # The warning about the disabled E-cores bug was printed.
        self._check_no_ecores_bug = True

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        if not self._sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_msr", "_cpufreq_msr_obj", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

class CPUFreqCPPC(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading CPU frequency information from ACPI CPPC via Linux
    sysfs interfaces.

    Public methods overview.

    1. Get CPU frequency limits from ACPI CPPC.
       * 'get_min_freq_limit()'
       * 'get_max_freq_limit()'
    2. Get CPU performance limits from ACPI CPPC.
       * 'get_min_perf_limit()'
       * 'get_max_perf_limit()'
    3. Get CPU base frequency and performance from ACPI CPPC.
       * 'get_base_freq()'
       * 'get_base_perf()'

    Note, class methods do not validate the 'cpus' arguments. The caller is assumed to have done the
    validation. The input CPU numbers should exist and should be online.
    """

    def _get_sysfs_path(self, cpu, fname):
        """Construct and return CPPC sysfs file path."""

        return self._sysfs_base / f"cpu{cpu}/acpi_cppc" / fname

    def _read_cppc_sysfs_file(self, cpu, fname, what):
        """Read ACPI CPPC sysfs file 'fname' for CPU 'cpu'."""

        path = self._get_sysfs_path(cpu, fname)

        val = None

        try:
            val = self._sysfs_io.read_int(path, what=what)
        except Error as err:
            # On some platforms reading CPPC sysfs files always fails. So treat these errors as if
            # the sysfs file was not even available and raise 'ErrorNotSupported'.
            _LOG.debug("ACPI CPPC sysfs file '%s' is not readable%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(err) from err

        if val == 0:
            _LOG.debug("ACPI CPPC sysfs file '%s' contains 0%s", path, self._pman.hostmsg)
            raise ErrorNotSupported(f"read '0' for {what} from '{path}'")

        return self._sysfs_io.cache_add(path, val)

    def get_min_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum frequency
        limit for CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpus - a collection of integer CPU numbers to get the minimum frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "lowest_freq", f"max. CPU {cpu} frequency limit")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_max_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum frequency
        limit for CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpus - a collection of integer CPU numbers to get the maximum frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "highest_freq", f"max. CPU {cpu} frequency limit")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_min_perf_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum performance
        limit for CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpus - a collection of integer CPU numbers to get the minimum performance limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"min. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "lowest_perf", what)
            yield cpu, val

    def get_max_perf_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum performance
        limit for CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpus - a collection of integer CPU numbers to get the maximum performance limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            what = f"max. CPU {cpu} performance limit"
            val = self._read_cppc_sysfs_file(cpu, "highest_perf", what)
            yield cpu, val

    def get_base_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the base frequency of
        CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the base frequency for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "nominal_freq", f"base CPU {cpu} frequency")
            # CPPC sysfs files use MHz.
            yield cpu, val * 1000 * 1000

    def get_base_perf(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the base performance of
        CPU 'cpu', read from ACPI CPPC via Linux sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum performance limit for.

        Raise 'ErrorNotSupported' if the CPU performance sysfs file does not exist.
        """

        for cpu in cpus:
            val = self._read_cppc_sysfs_file(cpu, "nominal_perf", f"base CPU {cpu} performance")
            yield cpu, val

    def __init__(self, pman=None, cpuinfo=None, sysfs_io=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to get/set CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * sysfs_io - an '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                       files.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._sysfs_io = sysfs_io

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        if not self._sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

class CPUFreqMSR(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency for Intel platforms
    supporting the 'MSR_HWP_REQUEST' model-specific register (MSR).

    Public methods overview.

    1. Get/set CPU frequency via an MSR (Intel CPUs only).
       * 'get_min_freq()'
       * 'get_max_freq()'
       * 'set_min_freq()'
       * 'set_max_freq()'
    3. Get base frequency via an MSR (Intel CPUs only).
       * 'get_base_freq()'
    4. Get the minimum CPU operating frequency via an MSR (Intel CPUs only).
       * 'get_min_oper_freq()'
    5. Get the maximum CPU efficiency frequency via an MSR (Intel CPUs only).
       * 'get_max_eff_freq()'
    6. Get the maximum CPU turbo frequency via an MSR (Intel CPUs only).
       * 'get_max_turbo_freq()'
    7. Get hardware power management (HWP) on/off status.
       * 'get_hwp()'

    Note, class methods do not validate the 'cpus' arguments. The caller is assumed to have done the
    validation. The input CPU numbers should exist and should be online.
    """

    def _get_msr(self):
        """Return an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)

        return self._msr

    def _get_fsbfreq(self):
        """Discover bus clock speed."""

        if not self._fsbfreq:
            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_pmenable(self):
        """Return a 'PMEnable.PMEnable()' object."""

        if not self._pmenable:
            msr = self._get_msr()
            self._pmenable = PMEnable.PMEnable(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._pmenable

    def _get_bclks(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the bus clock speed for
        CPU 'cpu' in Hz.
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
        """Return bus clock speed in Hz."""

        _, val = next(self._get_bclks((cpu,)))
        return val

    def _get_hwpreq(self):
        """Return an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Return an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _perf_to_freq(self, cpu, perf, bclk):
        """
        On many Intel platforms, the MSR registers such as 'MSR_HWP_REQUEST  use frequency ratio
        units - CPU frequency in Hz divided by 100MHz (bus clock). But on hybrid Intel platform
        (e.g., Alder Lake), the MSR works in  terms of platform-dependent abstract performance units
        on P-cores.

        Convert the performance units to CPU frequency in Hz.
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
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the min. or max. CPU
        frequency.
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
            if hwpreq.is_cpu_feature_pkg_controlled(feature_name, cpu1):
                run_again = True
                break
            yielded_cpus.add(cpu1)
            yield cpu1, self._perf_to_freq(cpu1, perf, bclk)

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
            if hwpreq.is_cpu_feature_pkg_controlled(feature_name, cpu1):
                val = perf_pkg
            else:
                val = perf
            yield cpu1, self._perf_to_freq(cpu1, val, bclk)

    def get_min_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum CPU
        frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get min. frequency for.

        Raise 'ErrorNotSupported' if 'MSR_HWP_REQUEST' is not supported.
        """

        yield from self._get_freq_msr("min", cpus)

    def get_max_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get max. frequency for.

        Raise 'ErrorNotSupported' if 'MSR_HWP_REQUEST' is not supported.
        """

        yield from self._get_freq_msr("max", cpus)

    def _set_freq_msr(self, freq, key, cpus):
        """For every CPU in 'cpus', set CPU frequency by writing to 'MSR_HWP_REQUEST'."""

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
        vals = {}
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

    def set_min_freq(self, freq, cpus="all"):
        """
        Set minimum frequency for CPUs in 'cpus' via the 'MSR_HWP_REQUEST' model specific register.
        The arguments are as follows.
          * freq - the minimum frequency value to set, hertz.
          * cpus - a collection CPU numbers to set minimum frequency for.
        """

        self._set_freq_msr(freq, "min", cpus)

    def set_max_freq(self, freq, cpus):
        """
        Set maximum frequency for CPUs in 'cpus' via the 'MSR_HWP_REQUEST' model specific register.
        The arguments are as follows.
          * freq - the maximum frequency value to set, hertz.
          * cpus - a collection CPU numbers to set maximum frequency for.
        """

        self._set_freq_msr(freq, "max", cpus)

    def _get_hwpcap(self):
        """Return an 'HWPCapabilities.HWPCapabilities()' object."""

        if not self._hwpcap:
            msr = self._get_msr()
            self._hwpcap = HWPCapabilities.HWPCapabilities(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)

        return self._hwpcap

    def _get_platinfo(self):
        """Return a 'PlatformInfo.PlatformInfo()' object."""

        if not self._platinfo:
            msr = self._get_msr()
            self._platinfo = PlatformInfo.PlatformInfo(pman=self._pman, cpuinfo=self._cpuinfo,
                                                       msr=msr)
        return self._platinfo

    def _get_trl(self):
        """Return a 'TurboRatioLimit.TurboRatioLimit()' object."""

        if not self._trl:
            msr = self._get_msr()
            self._trl = TurboRatioLimit.TurboRatioLimit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=msr)
        return self._trl

    def _get_patinfo_freq(self, fname, cpus):
        """
        Yield '(cpu, frequency)' pairs for all CPUs in 'cpus', where frequency is read from feature
        'fname' of 'MSR_PLATFORM_INFO'.
        """

        if not cpus:
            return

        platinfo = self._get_platinfo()
        bclks_iter = self._get_bclks(cpus)
        platinfo_iter = platinfo.read_feature(fname, cpus=cpus)

        for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, platinfo_iter):
            assert cpu1 == cpu2
            yield cpu1, ratio * bclk

    def _get_hwpcap_freq(self, fname, cpus):
        """
        Yield '(cpu, frequency)' pairs for all CPUs in 'cpus', where frequency is read from feature
        'fname' of 'MSR_HWP_CAPABILITIES'.
        """

        if not cpus:
            return

        hwpcap = self._get_hwpcap()
        bclks_iter = self._get_bclks(cpus)
        hwpcap_iter = hwpcap.read_feature(fname, cpus=cpus)

        for (cpu1, bclk), (cpu2, perf) in zip(bclks_iter, hwpcap_iter):
            assert cpu1 == cpu2
            yield cpu1, self._perf_to_freq(cpu1, perf, bclk)

    def _get_from_2_iterators(self, cpus, iter1, iter2):
        """
        Yield '(cpu, frequency)' paris for all CPUs in 'cpus'. Get them from 'iter1' or 'iter2'.
        """

        result = {}
        for cpu, freq in iter1:
            result[cpu] = freq
        for cpu, freq in iter2:
            if cpu in result:
                raise Error(f"BUG: CPU {cpu} is covered more than once")
            result[cpu] = freq

        for cpu in cpus:
            yield cpu, result[cpu]

    def _split_cpus(self, cpus):
        """Split CPUs list 'cpus' in two: CPUs not supporting HWP and CPUs supporting HPW."""

        leg_cpus = []
        hwp_cpus = []

        for cpu in cpus:
            if "hwp" in self._cpuinfo.info["flags"][cpu]:
                hwp_cpus.append(cpu)
            else:
                leg_cpus.append(cpu)

        return leg_cpus, hwp_cpus

    def get_base_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the base frequency for
        CPU 'cpu' The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the turbo frequency for.

        For CPU that do not support HWP, read from the 'MSR_PLATFORM_INFO' model-specific register.
        Otherwise read from the 'MSR_HWP_CAPABILITIES' register. Raise 'ErrorNotSupported' if MSRs
        are not supported.
        """

        leg_cpus, hwp_cpus = self._split_cpus(cpus)
        iter1 = self._get_patinfo_freq("max_non_turbo_ratio", leg_cpus)
        iter2 = self._get_hwpcap_freq("base_perf", hwp_cpus)

        yield from self._get_from_2_iterators(cpus, iter1, iter2)

    def get_min_oper_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum operating
        frequency for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the minimum operating frequency for.

        For CPU that do not support HWP, read from the 'MSR_PLATFORM_INFO' model-specific register.
        Otherwise read from the 'MSR_HWP_CAPABILITIES' register. Raise 'ErrorNotSupported' if MSRs
        are not supported.
        """

        leg_cpus, hwp_cpus = self._split_cpus(cpus)
        iter1 = self._get_patinfo_freq("min_oper_ratio", leg_cpus)
        iter2 = self._get_hwpcap_freq("min_perf", hwp_cpus)

        yield from self._get_from_2_iterators(cpus, iter1, iter2)

    def get_max_eff_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum efficiency
        frequency for CPU 'cpu'. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum efficiency frequency for.

        For CPU that do not support HWP, read from the 'MSR_PLATFORM_INFO' model-specific register.
        Otherwise read from the 'MSR_HWP_CAPABILITIES' register. Raise 'ErrorNotSupported' if MSRs
        are not supported.
        """

        leg_cpus, hwp_cpus = self._split_cpus(cpus)
        iter1 = self._get_patinfo_freq("max_eff_ratio", leg_cpus)
        iter2 = self._get_hwpcap_freq("eff_perf", hwp_cpus)

        yield from self._get_from_2_iterators(cpus, iter1, iter2)

    def _get_max_turbo_freq_trl(self, cpus):
        """
        Yield '(cpu, frequency)' tuples by reading from 'MSR_TURBO_RATIO_LIMIT'. Raise
        'ErrorNotSupported' if 'MSR_TURBO_RATIO_LIMIT' is not supported.
        """

        if not cpus:
            return

        trl = self._get_trl()
        trl_iter = trl.read_feature("max_1c_turbo_ratio", cpus=cpus)
        bclks_iter = self._get_bclks(cpus)

        try:
            for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, trl_iter):
                assert cpu1 == cpu2
                yield cpu1, ratio * bclk
        except ErrorNotSupported as err1:
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
                _LOG.warn_once("module 'TurboRatioLimit' doesn't support "
                               "'MSR_TURBO_RATIO_LIMIT' for CPU '%s'%s\nPlease, contact project "
                               "maintainers.", self._cpuinfo.cpudescr, self._pman.hostmsg)
                raise ErrorNotSupported(f"{err1}\n{err2}") from err2

    def get_max_turbo_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum 1-core turbo
        frequency for CPU 'cpu' The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum 1-core turbo frequency
                   for.

        For CPU that do not support HWP, read from the 'MSR_TURBO_RATIO_LIMIT' model-specific
        register. Otherwise read from the 'MSR_HWP_CAPABILITIES' register. Raise 'ErrorNotSupported'
        if MSRs are not supported.
        """

        leg_cpus, hwp_cpus = self._split_cpus(cpus)
        iter1 = self._get_max_turbo_freq_trl(leg_cpus)
        iter2 = self._get_hwpcap_freq("max_perf", hwp_cpus)

        yield from self._get_from_2_iterators(cpus, iter1, iter2)

    def get_hwp(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the hardware power
        management on/off status for CPU 'cpu'.
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

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to control CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._fsbfreq = None
        self._pmenable = None
        self._hwpreq = None
        self._hwpreq_pkg = None
        self._hwpcap = None
        self._platinfo = None
        self._trl = None

        self._pcore_cpus = set()
        # Performance to frequency factor.
        self._perf_to_freq_factor = None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        if self._cpuinfo.info["hybrid"]:
            self._init_scaling_factor()
            _, pcore_cpus = self._cpuinfo.get_hybrid_cpus()
            self._pcore_cpus = set(pcore_cpus)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_trl", "_platinfo", "_fsbfreq", "_pmenable", "_hwpreq", "_hwpreq_pkg",
                       "_hwpcap", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
