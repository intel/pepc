# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides a capability of reading and changing CPU frequency.
"""

import logging
import contextlib
from pathlib import Path
from pepclibs import CPUInfo, _SysfsIO
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed

_LOG = logging.getLogger()

class CPUFreqSysfs(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency via Linux "cpufreq"
    subsystem sysfs interfaces.

    Public methods overview.

    1. Get/set CPU frequency via Linux "cpufreq" sysfs interfaces.
       * Multiple CPUs.
           - 'get_min_freq()'
           - 'get_max_freq()'
           - 'set_min_freq()'
           - 'set_max_freq()'
       * Single CPU.
           - 'get_cpu_min_freq()'
           - 'get_cpu_max_freq()'
           - 'set_cpu_min_freq()'
           - 'set_cpu_max_freq()'
    2. Get CPU frequency limits via Linux "cpufreq" sysfs interfaces.
       * Multiple CPUs.
           - 'get_min_freq_limit()'
           - 'get_max_freq_limit()'
       * Single CPU.
           - 'get_cpu_min_freq_limit()'
           - 'get_cpu_max_freq_limit()'
    3. Get avalilable CPU frequencies list.
       * Multiple CPUs.
           - 'get_available_frequencies()'
       * Single CPU.
           - 'get_cpu_available_frequencies()'
    4. Get CPU base frequency.
       * Multiple CPUs.
           - 'get_base_freq()'
       * Single CPU.
           - 'get_cpu_base_freq()'
    5. Get CPU frequency driver name.
       * 'get_driver()'
    6. Get/set 'intel_pstate' driver mode.
       * 'get_intel_pstate_mode()'
       * 'set_intel_pstate_mode()'
    7. Get/set turbo on/off status.
       * 'get_turbo()'
       * 'set_turbo()'
    8. Get/set Linux CPU frequency governor.
       * 'get_governor()'
       * 'get_available_governors()'
       * 'set_governor()'

    Note, class methods do not validate the 'cpu' and 'cpus' arguments. The caller is assumed to
    have done the validation. The input CPU number(s) should exist and should be online.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

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

        fname = "scaling_" + key + "_freq"
        prefix = "cpuinfo_" if limit else "scaling_"
        fname = prefix + key + "_freq"
        return self._get_policy_sysfs_path(cpu, fname)

    def _get_freq_sysfs(self, key, cpus, limit=False):
        """Yield CPU frequency from the Linux "cpufreq" sysfs file."""

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

    def get_cpu_min_freq(self, cpu):
        """
        Get minimum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the minimum frequency for.

        Return the minimum CPU frequency in Hz. Raise 'ErrorNotSupported' if the CPU frequency sysfs
        file does not exist.
        """

        _, val = next(self._get_freq_sysfs("min", (cpu,)))
        return val

    def get_max_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum frequency for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus)

    def get_cpu_max_freq(self, cpu):
        """
        Get maximum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the maximum frequency for.

        Return the maximum CPU frequency in Hz. Raise 'ErrorNotSupported' if the CPU frequency sysfs
        file does not exist.
        """

        _, val = next(self._get_freq_sysfs("max", (cpu,)))
        return val

    def get_min_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum CPU
        frequency limit for CPU 'cpu', read via Linux "cpufreq" sysfs interfaces. The arguments are
        as follows.
          * cpus - a collection of integer CPU numbers to get the frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("min", cpus, limit=True)

    def get_cpu_min_freq_limit(self, cpu):
        """
        Get minimum CPU frequency limit via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the frequency limit for.

        Return the minimum CPU frequency limit in Hz. Raise 'ErrorNotSupported' if the CPU frequency
        sysfs file does not exist.
        """

        _, val = next(self._get_freq_sysfs("min", (cpu,), limit=True))
        return val

    def get_max_freq_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency limit for CPU 'cpu', read via Linux "cpufreq" sysfs interfaces. The arguments are
        as follows.
          * cpus - a collection of integer CPU numbers to get the frequency limit for.

        Raise 'ErrorNotSupported' if the CPU frequency sysfs file does not exist.
        """

        yield from self._get_freq_sysfs("max", cpus, limit=True)

    def get_cpu_max_freq_limit(self, cpu):
        """
        Get maximum CPU frequency limit via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the frequency limit for.

        Return the maximum CPU frequency limit in Hz. Raise 'ErrorNotSupported' if the CPU frequency
        sysfs file does not exist.
        """

        _, val = next(self._get_freq_sysfs("max", (cpu,), limit=True))
        return val

    def _set_freq_sysfs(self, freq, key, cpus):
        """
        For every CPU in 'cpus', set CPU frequency by writing to the Linux "cpufreq" sysfs file.
        """

        what = f"{key}. CPU frequency"

        for cpu in cpus:
            cpu_info = self._cpuinfo.info
            if cpu_info["vendor"] == "GenuineIntel" and "hwp" in cpu_info["flags"][cpu]:
                # On some Intel platforms with HWP enabled the change does not happen immediately.
                # Retry few times.
                retries = 2
                sleep = 0.1
            else:
                retries = sleep = 0

            path = self._get_cpu_freq_sysfs_path(key, cpu)

            try:
                self._sysfs_io.write_verify(path, str(freq // 1000), what=what, retries=retries,
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

    def set_cpu_min_freq(self, freq, cpu):
        """
        Set minimum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * freq - the minimum frequency value to set, hertz.
          * cpu - CPU number to set the frequency for.
        """

        self._set_freq_sysfs(freq, "min", (cpu,))

    def set_max_freq(self, freq, cpus):
        """
        For every CPU in 'cpus', set maximum CPU frequency via Linux "cpufreq" sysfs interfaces. The
        arguments are as follows.
          * freq - the maximum frequency value to set, hertz.
          * cpus - a collection of CPU numbers to set the frequency for.
        """

        self._set_freq_sysfs(freq, "max", cpus)

    def set_cpu_max_freq(self, freq, cpu):
        """
        Set maximum CPU frequency via Linux "cpufreq" sysfs interfaces. The arguments are as
        follows.
          * freq - the maximum frequency value to set, hertz.
          * cpu - CPU number to set the frequency for.
        """

        self._set_freq_sysfs(freq, "max", (cpu,))

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

    def get_cpu_available_frequencies(self, cpu):
        """
        Get the list of available CPU frequency values. The arguments are as follows.
          * cpu - CPU number to get the list of available frequencies for.

        Return the list of available frequencies Hz. Raise 'ErrorNotSupported' if the frequencies
        sysfs file does not exist. The sysfs file is provided by the 'acpi-cpufreq' driver, but not
        the 'intel_idle' driver.
        """

        _, val = next(self.get_available_frequencies((cpu,)))
        return val

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

    def get_cpu_base_freq(self, cpu):
        """
        Get CPU base frequency via Linux "cpufreq" sysfs interfaces. The arguments are as follows.
          * cpu - CPU number to get base frequency for.

        Return the base frequency vaule in Hz. Raise 'ErrorNotSupported' if the base frequency sysfs
        files do not exist.
        """

        _, val = next(self.get_base_freq((cpu,)))
        return val

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
                    # When 'intel_pstate' driver is 'off', writing 'off' again errors out. Ignore the
                    # error.
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
            print(cpu, governors)
            if governor not in governors:
                governors = ", ".join(governors)
                raise Error(f"bad governor name '{governor}' for CPU {cpu}{self._pman.hostmsg}, "
                            f"use one of: {governors}")

            path = self._sysfs_base / "cpufreq" / f"policy{cpu}" / "scaling_governor"
            self._sysfs_io.write(path, governor, what=what)

    def __init__(self, pman=None, msr=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to get/set CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for the rare cases this class accessing
                  MSR registers.
          * enable_cache - this argument can be used to disable caching.

        This class is focused on 'sysfs' interface, but in some cases it may access MSR registers
        via the 'CPUFreqMSR' class.
        """

        self._pman = pman
        self._msr = msr
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_msr = msr is None
        self._close_cpuinfo = cpuinfo is None

        self._cpufreq_msr_obj = None

        self._sysfs_io = None
        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_cpufreq_msr_obj", "_msr", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

class CPUFreqCPPC(ClassHelpers.SimpleCloseContext):
    """
    This class provides a cpability of reading CPU frequency information from ACPI CPPC via Linux
    sysfs interfaces.

    Public methods overview.

    1. Get CPU frequency limits from ACPI CPPC.
       * Multiple CPUs.
           - 'get_min_freq_limit()'
           - 'get_max_freq_limit()'
       * Single CPU.
           - 'get_cpu_min_freq_limit()'
           - 'get_cpu_max_freq_limit()'
    1. Get CPU performance limits from ACPI CPPC.
       * Multiple CPUs.
           - 'get_min_perf_limit()'
           - 'get_max_perf_limit()'
       * Single CPU.
           - 'get_cpu_min_perf_limit()'
           - 'get_cpu_max_perf_limit()'
    4. Get CPU base frequency and performance from ACPI CPPC.
       * Multiple CPUs.
           - 'get_base_freq()'
           - 'get_base_perf()'
       * Single CPU.
           - 'get_cpu_base_freq()'
           - 'get_cpu_base_perf()'

    Note, class methods do not validate the 'cpu' and 'cpus' arguments. The caller is assumed to
    have done the validation. The input CPU number(s) should exist and should be online.
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

    def get_cpu_min_freq_limit(self, cpu):
        """
        Get minimum CPU frequency limit from ACPI CPPC via Linux sysfs interfaces. The arguments are
        as follows.
          * cpu - CPU number to get the frequency limit for.

        Return the minimum CPU frequency limit in Hz. Raise 'ErrorNotSupported' if the CPU frequency
        sysfs file does not exist.
        """

        _, val = next(self.get_min_freq_limit((cpu,)))
        return val

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

    def get_cpu_max_freq_limit(self, cpu):
        """
        Get maximum CPU frequency limit from ACPI CPPC via Linux sysfs interfaces. The arguments are
        as follows.
          * cpu - CPU number to get the frequency limit for.

        Return the maximum CPU frequency limit in Hz. Raise 'ErrorNotSupported' if the CPU frequency
        sysfs file does not exist.
        """

        _, val = next(self.get_max_freq_limit((cpu,)))
        return val

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

    def get_cpu_min_perf_limit(self, cpu):
        """
        Get minimum CPU performance limit from ACPI CPPC via Linux sysfs interfaces. The arguments
        are as follows.
          * cpu - CPU number to get the frequency limit for.

        Return the minimum CPU limit. Raise 'ErrorNotSupported' if the CPU frequency sysfs file does
        not exist.
        """

        _, val = next(self.get_min_perf_limit((cpu,)))
        return val

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

    def get_cpu_max_perf_limit(self, cpu):
        """
        Get maximum CPU performance limit from ACPI CPPC via Linux sysfs interfaces. The arguments
        are as follows.
          * cpu - CPU number to get the frequency limit for.

        Return the maximum CPU limit. Raise 'ErrorNotSupported' if the CPU frequency sysfs file does
        not exist.
        """

        _, val = next(self.get_max_perf_limit((cpu,)))
        return val

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

    def get_cpu_base_freq(self, cpu):
        """
        Get base CPU frequency from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the base frequency for.

        Return the base CPU frequency in Hz. Raise 'ErrorNotSupported' if the CPU frequency sysfs
        file does not exist.
        """

        _, val = next(self.get_base_freq((cpu,)))
        return val

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

    def get_cpu_base_perf(self, cpu):
        """
        Get base CPU performance from ACPI CPPC via Linux sysfs interfaces. The arguments are as
        follows.
          * cpu - CPU number to get the base performance for.

        Return the base CPU performance in Hz. Raise 'ErrorNotSupported' if the CPU performance
        sysfs file does not exist.
        """

        _, val = next(self.get_base_perf((cpu,)))
        return val

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to get/set CPU frequency on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        self._sysfs_io = None
        self._sysfs_base = Path("/sys/devices/system/cpu")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

class CPUFreqMSR(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of reading and changing CPU frequency for Intel platforms
    supporting thie 'MSR_HWP_REQUEST' model-specific register (MSR).

    Public methods overview.

    1. Get/set CPU frequency via an MSR (Intel CPUs only).
       * Multiple CPUs.
           - 'get_min_freq()'
           - 'get_max_freq()'
           - 'set_min_freq()'
           - 'set_max_freq()'
       * Single CPU.
            - 'get_cpu_min_freq()'
            - 'get_cpu_max_freq()'
            - 'set_cpu_min_freq()'
            - 'set_cpu_max_freq()'
    3. Get base frequency via an MSR (Intel CPUs only).
       * Multiple CPUs.
            - 'get_base_freq()'
       * Single CPU.
            - 'get_cpu_base_freq()'
    4. Get the minimum CPU operating frequency via an MSR (Intel CPUs only).
       * Multiple CPUs.
            - 'get_min_oper_freq()'
       * Single CPU.
            - 'get_cpu_min_oper_freq()'
    5. Get the maximum CPU efficiency frequency via an MSR (Intel CPUs only).
       * Multiple CPUs.
            - 'get_max_eff_freq()'
       * Single CPU.
            - 'get_cpu_max_eff_freq()'
    6. Get the maximum CPU turbo frequency via an MSR (Intel CPUs only).
       * Multiple CPUs.
            - 'get_max_turbo_freq()'
       * Single CPU.
            - 'get_cpu_max_turbo_freq()'
    7. Get hardware power management (HWP) on/off status.
       * 'get_hwp()'

    Note, class methods do not validate the 'cpu' and 'cpus' arguments. The caller is assumed to
    have done the validation. The input CPU number(s) should exist and should be online.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            from pepclibs.msr import MSR # pylint: disable=import-outside-toplevel

            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)

        return self._msr

    def _get_fsbfreq(self):
        """Discover bus clock speed."""

        if not self._fsbfreq:
            from pepclibs.msr import FSBFreq # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._fsbfreq = FSBFreq.FSBFreq(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._fsbfreq

    def _get_pmenable(self):
        """Returns an 'PMEnable.PMEnable()' object."""

        if not self._pmenable:
            from pepclibs.msr import PMEnable # pylint: disable=import-outside-toplevel

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
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            from pepclibs.msr import HWPRequest # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            from pepclibs.msr import HWPRequestPkg # pylint: disable=import-outside-toplevel

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

        if self._cpuinfo.info["hybrid"]:
            pcore_cpus = set(self._cpuinfo.get_hybrid_cpu_topology()["pcore"])
            # In HWP mode, the Linux 'intel_pstate' driver changes CPU frequency by programming
            # 'MSR_HWP_REQUEST'.
            # On many Intel platforms,the MSR is programmed in terms of frequency ratio (frequency
            # divided by 100MHz). But on hybrid Intel platform (e.g., Alder Lake), the MSR works in
            # terms of platform-dependent abstract performance units on P-cores. Convert the
            # performance units to CPU frequency in Hz.
            if cpu in pcore_cpus:
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

    def get_cpu_min_freq(self, cpu):
        """
        Get minimum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * cpu - CPU number to get the frequency for.

        Return the minimum CPU frequency in Hz. Raise 'ErrorNotSupported' if 'MSR_HWP_REQUEST' is
        not supported.
        """

        _, val = next(self._get_freq_msr("min", (cpu,)))
        return val

    def get_max_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum CPU
        frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get max. frequency for.

        Raise 'ErrorNotSupported' if 'MSR_HWP_REQUEST' is not supported.
        """

        yield from self._get_freq_msr("max", cpus)

    def get_cpu_max_freq(self, cpu):
        """
        Get maximum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * cpu - CPU number to get the frequency for.

        Return the maximum CPU frequency in Hz. Raise 'ErrorNotSupported' if 'MSR_HWP_REQUEST' is
        not supported.
        """

        _, val = next(self._get_freq_msr("max", (cpu,)))
        return val

    def _set_freq_msr(self, freq, key, cpus):
        """For every CPU in 'cpus', set CPU frequency by writing to 'MSR_HWP_REQUEST'."""

        # The corresponding 'MSR_HWP_REQUEST' feature name.
        feature_name = f"{key}_perf"

        hwpreq = self._get_hwpreq()

        # Disable package control.
        with contextlib.suppress(ErrorNotSupported):
            hwpreq.write_feature(f"{feature_name}_valid", "on", cpus=cpus)

        if self._cpuinfo.info["hybrid"]:
            pcore_cpus = set(self._cpuinfo.get_hybrid_cpu_topology()["pcore"])
        else:
            pcore_cpus = set()

        # Prepare the values dictionary, which maps each value to the list of CPUs to write this
        # value to.
        vals = {}
        for cpu, bclk in self._get_bclks(cpus):
            if cpu in pcore_cpus:
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

    def set_cpu_min_freq(self, freq, cpu):
        """
        Set minimum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * freq - the minimum frequency value to set, hertz.
          * cpu - CPU number to set minimum frequency for.
        """

        self._set_freq_msr(freq, "min", (cpu,))

    def set_max_freq(self, freq, cpus):
        """
        Set maximum frequency for CPUs in 'cpus' via the 'MSR_HWP_REQUEST' model specific register.
        The arguments are as follows.
          * freq - the maximum frequency value to set, hertz.
          * cpus - a collection CPU numbers to set maximum frequency for.
        """

        self._set_freq_msr(freq, "max", cpus)

    def set_cpu_max_freq(self, freq, cpu):
        """
        Set maximum CPU frequency via the 'MSR_HWP_REQUEST' model specific register. The arguments
        are as follows.
          * freq - the maximum frequency value to set, hertz.
          * cpu - CPU number to set maximum frequency for.
        """

        self._set_freq_msr(freq, "max", (cpu,))

    def _get_platinfo(self):
        """Returns an 'PlatformInfo.PlatformInfo()' object."""

        if not self._platinfo:
            from pepclibs.msr import PlatformInfo # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._platinfo = PlatformInfo.PlatformInfo(pman=self._pman, cpuinfo=self._cpuinfo,
                                                       msr=msr)
        return self._platinfo

    def _get_trl(self):
        """Returns an 'TurboRatioLimit.TurboRatioLimit()' object."""

        if not self._trl:
            from pepclibs.msr import TurboRatioLimit # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._trl = TurboRatioLimit.TurboRatioLimit(pman=self._pman, cpuinfo=self._cpuinfo,
                                                        msr=msr)
        return self._trl

    def get_base_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the base frequency for
        CPU 'cpu', read from the 'MSR_PLATFORM_INFO' model-specific register. The arguments are as
        follows.
          * cpus - a collection of integer CPU numbers to get the turbo frequency for.

        Raise 'ErrorNotSupported' if 'MSR_PLATFORM_INFO' is not supported.
        """

        platinfo = self._get_platinfo()
        bclks_iter = self._get_bclks(cpus)
        platinfo_iter = platinfo.read_feature("max_non_turbo_ratio", cpus=cpus)
        for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, platinfo_iter):
            assert cpu1 == cpu2
            yield cpu1, ratio * bclk

    def get_cpu_base_freq(self, cpu):
        """
        Get base CPU frequency from the 'MSR_PLATFORM_INFO' model-specific register. The arguments
        are as follows.
          * cpu - CPU number to get base frequency for.

        Return base CPU frequency in Hz. Raise 'ErrorNotSupported' if 'MSR_PLATFORM_INFO' is not
        supported.
        """

        _, val = next(self.get_base_freq((cpu,)))
        return val

    def get_min_oper_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the minimum operating
        frequency for CPU 'cpu', read from the 'MSR_PLATFORM_INFO' model-specific register. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the minimum operating frequency for.

        Return the minium opeating CPU frequency in Hz. Raise 'ErrorNotSupported' if
        'MSR_PLATFORM_INFO' is not supported.
        """

        platinfo = self._get_platinfo()
        bclks_iter = self._get_bclks(cpus)
        platinfo_iter = platinfo.read_feature("min_oper_ratio", cpus=cpus)
        for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, platinfo_iter):
            assert cpu1 == cpu2
            yield cpu1, ratio * bclk

    def get_cpu_min_oper_freq(self, cpu):
        """
        Get the minimum CPU operating frequency from the 'MSR_PLATFORM_INFO' model-specific
        register. The arguments are as follows.
          * cpu - CPU number to get the minimum operating frequency for.

        Return the minium opeating CPU frequency in Hz. Raise 'ErrorNotSupported' if
        'MSR_PLATFORM_INFO' is not supported.
        """

        _, val = next(self.get_min_oper_freq((cpu,)))
        return val

    def get_max_eff_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum efficiency
        frequency for CPU 'cpu', read from the 'MSR_PLATFORM_INFO' model-specific register. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum efficiency frequency for.

        Maximum efficiency frequency is the frequency with best CPU performance per watt ratio.
        Raise 'ErrorNotSupported' if 'MSR_PLATFORM_INFO' is not supported.
        """

        platinfo = self._get_platinfo()
        bclks_iter = self._get_bclks(cpus)
        platinfo_iter = platinfo.read_feature("max_eff_ratio", cpus=cpus)
        for (cpu1, bclk), (cpu2, ratio) in zip(bclks_iter, platinfo_iter):
            assert cpu1 == cpu2
            yield cpu1, ratio * bclk

    def get_cpu_max_eff_freq(self, cpu):
        """
        Get the maximum CPU efficiency frequency from the 'MSR_PLATFORM_INFO' model-specific
        register. The arguments are as follows.
          * cpu - CPU number to get the maximum efficiency frequency for.

        Return the maximum CPU efficiency frequency in Hz. Maximum efficiency frequency is the
        frequency with best CPU performance per watt ratio. Raise 'ErrorNotSupported' if
        'MSR_PLATFORM_INFO' is not supported.
        """

        _, val = next(self.get_max_eff_freq((cpu,)))
        return val

    def get_max_turbo_freq(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the maximum 1-core turbo
        frequency for CPU 'cpu', read from the 'MSR_TURBO_RATIO_LIMIT' model-specific register. The
        arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the maximum 1-core turbo frequency
                   for.

        Raise 'ErrorNotSupported' if 'MSR_TURBO_RATIO_LIMIT' is not supported.
        """

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

    def get_cpu_max_turbo_freq(self, cpu):
        """
        Get the maximum 1-core turbo frequency from the 'MSR_TURBO_RATIO_LIMIT' model-specific
        register. The arguments are as follows.
          * cpu - CPU number to get the maximum turbo frequency for.

        Return the maximum 1-core turbo frequency in Hz. Raise 'ErrorNotSupported' if
        'MSR_TURBO_RATIO_LIMIT' is not supported.
        """

        _, val = next(self.get_max_turbo_freq((cpu,)))
        return val

    def get_hwp(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' the hardware power
        management on/off status for CPU 'cpu'.
        """

        pmenable = self._get_pmenable()
        yield from pmenable.is_feature_enabled("hwp", cpus=cpus)

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
        self._platinfo = None
        self._trl = None

        # Performance to frequency factor.
        self._perf_to_freq_factor = 78740157

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_trl", "_platinfo", "_fsbfreq", "_pmenable", "_hwpreq", "_hwpreq_pkg",
                       "_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
