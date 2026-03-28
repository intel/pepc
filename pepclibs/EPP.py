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
Provide a capability of reading and changing EPP (Energy Performance Preference).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs import CPUModels
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorPath, ErrorPerCPUPath
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailedPath, ErrorVerifyFailedPerCPUPath
from pepclibs.helperlibs import Trivial, ClassHelpers, KernelVersion, Logging
from pepclibs import _EPBase

if typing.TYPE_CHECKING:
    from typing import Final, Union, Generator, Sequence
    from pepclibs import CPUInfo, _SysfsIO
    from pepclibs.msr import MSR, HWPRequest, HWPRequestPkg
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The minimum and maximum EPP values.
_EPP_MIN: Final[int] = 0
_EPP_MAX: Final[int] = 0xFF

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class EPP(_EPBase.EPBase):
    """
    Provide API for reading and changing EPP (Energy Performance Preference).

    Public methods overview.

    1. Multi-CPU I/O.
        - 'get_vals()' - read EPP values.
        - 'set_vals()' - set EPP values.
    2. Single-CPU I/O.
        - 'get_cpu_val()' - read EPP value for a single CPU.
        - 'set_cpu_val()' - set EPP value for a single CPU.
    3. Miscellaneous.
        - 'close()' - uninitialize the class instance.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object, used only in some error cases to provide additional details in
                 error messages. Will be created on demand if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created on demand if not
                      provided.
            enable_cache: Whether to enable caching.
        """

        super().__init__("EPP", pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._hwpreq: HWPRequest.HWPRequest | None = None
        self._hwpreq_pkg: HWPRequestPkg.HWPRequestPkg | None = None

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        # List of available EPP policies according to sysfs.
        self._epp_policies: list[str] = []

        # Kernel version on the target host.
        self._kver: str = ""

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, close_attrs=("_hwpreq", "_hwpreq_pkg"))
        super().close()

    def _extract_cpu_from_path(self, path: Path) -> int:
        """
        Extract the CPU number from EPP sysfs path.

        Args:
            path: The EPP sysfs path.

        Returns:
            The CPU number.
        """

        # Path format: /sys/devices/system/cpu/cpufreq/policy<N>/energy_performance_preference
        # Extract "policy<N>" from the path
        dir_name = path.parent.name
        cpu_str = dir_name.replace("policy", "")
        return Trivial.str_to_int(cpu_str, what=f"CPU number from path '{path}'")

    def _get_hwpreq(self) -> HWPRequest.HWPRequest:
        """
        Return an 'HWPRequest.HWPRequest' object.

        Returns:
            An instance of 'HWPRequest.HWPRequest'.
        """

        if not self._hwpreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequest

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self) -> HWPRequestPkg.HWPRequestPkg:
        """
        Return an 'HWPRequestPkg.HWPRequestPkg' object.

        Returns:
            An instance of 'HWPRequestPkg.HWPRequestPkg'.
        """

        if not self._hwpreq_pkg:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequestPkg

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_available_policies(self, cpu: int) -> list[str]:
        """
        Return list of available EPP policies read from sysfs.

        Args:
            cpu: CPU number.

        Returns:
            List of available EPP policy names.
        """

        if not self._epp_policies:
            try:
                with self._pman.open(self._sysfs_epp_policies_path % cpu, "r") as fobj:
                    line: str = fobj.read()
                    line = line.strip()

                self._epp_policies = Trivial.split_csv_line(line, sep=" ")
            except Error:
                self._epp_policies = []

        return self._epp_policies

    def _validate_value(self, val: str | int, policy_ok: bool = False):
        """Refer to '_EPBase._validate_value()'."""

        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPP_MIN, _EPP_MAX, what="EPP value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPP value must be an integer within [{_EPP_MIN},{_EPP_MAX}]")
        else:
            policies = self._get_available_policies(0)
            if not policies:
                raise ErrorNotSupported(f"No EPP policies supported{self._pman.hostmsg}, please "
                                        f"use instead an integer within [{_EPP_MIN},{_EPP_MAX}]")

            if val not in policies:
                policies_str = ", ".join(policies)
                raise ErrorNotSupported(f"EPP value must be one of the following EPP policies: "
                                        f"{policies_str}, or integer within "
                                        f"[{_EPP_MIN},{_EPP_MAX}]")

    def _fetch_from_msr_remote(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Implement '_fetch_from_msr()' for a remote host, where it is more optimal to read MSRs in
        bulk, rather than one by one. Refer to '_EPBase._fetch_from_msr()' for details.
        """

        hwpreq = self._get_hwpreq()

        # Separate CPUs into package-controlled and per-CPU controlled.
        cpus_list: list[int] = []
        pkg_controlled_cpus: list[int] = []
        percpu_controlled_cpus: list[int] = []

        for cpu, pkg_controlled in hwpreq.is_feature_pkg_controlled("epp", cpus=cpus):
            cpus_list.append(cpu)
            if pkg_controlled:
                pkg_controlled_cpus.append(cpu)
            else:
                percpu_controlled_cpus.append(cpu)

        # Read EPP from per-CPU MSR for CPUs not controlled by package MSR.
        epp_vals: dict[int, int] = {}
        if percpu_controlled_cpus:
            for cpu, vals in hwpreq.read_features(["epp"], cpus=percpu_controlled_cpus):
                epp_vals[cpu] = int(vals["epp"])

        # Read EPP from package MSR for CPUs controlled by package MSR.
        if pkg_controlled_cpus:
            hwpreq_pkg = self._get_hwpreq_pkg()
            for cpu, vals in hwpreq_pkg.read_features(["epp"], cpus=pkg_controlled_cpus):
                epp_vals[cpu] = int(vals["epp"])

        # Yield in the order of input cpus.
        for cpu in cpus_list:
            yield cpu, epp_vals[cpu]

    def _read_cpu_msr(self, cpu: int) -> int:
        """
        Read EPP for a specific CPU from MSR.

        Args:
            cpu: CPU number to read EPP for (already normalized).

        Returns:
            EPP value for the specified CPU.
        """

        # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
        hwpreq_union: Union[HWPRequest.HWPRequest, HWPRequestPkg.HWPRequestPkg]
        hwpreq_union = hwpreq = self._get_hwpreq()

        if hwpreq.is_cpu_feature_pkg_controlled("epp", cpu):
            hwpreq_union = self._get_hwpreq_pkg()

        return hwpreq_union.read_cpu_feature_int("epp", cpu)

    def _fetch_from_msr(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """Refer to '_EPBase._fetch_from_msr()'."""

        # The remote host implementation is not so optimal for a local host, because it has to read
        # multiple MSRs, collect results for all CPUs and then yield them in the order of input
        # CPUs, while the local host implementation reads MSRs one by one, yielding results
        # immediately, which is more efficient for a local host

        if self._pman.is_remote:
            yield from self._fetch_from_msr_remote(cpus)
        else:
            for cpu in cpus:
                yield cpu, self._read_cpu_msr(cpu)

    def _write_to_msr_remote(self, val: str | int, cpus: Sequence[int]):
        """
        Implement '_write_to_msr()' for a remote host, where it is more optimal to write MSRs in
        bulk, rather than one by one. Refer to '_EPBase._write_to_msr()' for details.
        """

        hwpreq = self._get_hwpreq()

        if not Trivial.is_int(val):
            raise Error(f"Cannot set EPP to '{val}' using MSR mechanism, because it is not an "
                        f"integer value")

        # Disable package control for all CPUs.
        hwpreq.disable_feature_pkg_control("epp", cpus=cpus)

        try:
            hwpreq.write_feature("epp", val, cpus=cpus)
        except Error as err:
            raise type(err)(f"Failed to set EPP{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _write_cpu_msr(self, val: str | int, cpu: int):
        """
        Write EPP for a specific CPU to MSR.

        Args:
            val: EPP value to write.
            cpu: CPU number to write EPP for (already normalized).
        """

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control("epp", cpu)

        if not Trivial.is_int(val):
            raise Error(f"Cannot set EPP to '{val}' using MSR mechanism, because it is not an "
                        f"integer value")

        try:
            hwpreq.write_cpu_feature("epp", val, cpu)
        except Error as err:
            raise type(err)(f"Failed to set EPP{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _write_to_msr(self, val: str | int, cpus: Sequence[int]):
        """Refer to '_EPBase._write_to_msr()'."""

        # There are 2 separate implementations for local and remote hosts, for the same reasons as
        # describe in '_fetch_from_msr()'.
        if self._pman.is_remote:
            self._write_to_msr_remote(val, cpus)
        else:
            for cpu in cpus:
                self._write_cpu_msr(val, cpu)

    def __fetch_from_sysfs(self,
                           cpus: Sequence[int]) -> Generator[tuple[int, str | int], None, None]:
        """Implement '_fetch_from_sysfs()'. Arguments are the same."""

        sysfs_io = self._get_sysfs_io()
        paths_iter = (Path(self._sysfs_epp_path % cpu) for cpu in cpus)

        for cpu, (_, val) in zip(cpus, sysfs_io.read_paths(paths_iter, what="EPP")):
            _val: str | int = val
            if Trivial.is_int(val):
                _val = int(val)
            yield cpu, _val

    def _fetch_from_sysfs(self,
                          cpus: Sequence[int]) -> Generator[tuple[int, str | int], None, None]:
        """
        Refer to '_EPBase._fetch_from_sysfs()'.

        Raises:
            ErrorPerCPUPath: If reading the sysfs file fails with path-related error.
        """

        try:
            yield from self.__fetch_from_sysfs(cpus)
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err

    def _has_write_bug(self) -> bool:
        """
        Check if the target system has the EPP sysfs write bug. The bug is that write fails if the
        new value is the same as the current value. It was fixed in v6.5 in this commit:
            03f44ffb3d5be (cpufreq: intel_pstate: Fix energy_performance_preference for passive)

        Returns:
            True if the bug is present, False otherwise.
        """

        if self._pman.is_emulated:
            # The bug is not present in the emulator, so skip the check.
            return False

        if not self._kver:
            self._kver = KernelVersion.get_kver(self._pman)

        if KernelVersion.kver_ge(self._kver, "6.5.0"):
            return False
        return True

    def __write_to_sysfs(self, val: str | int, cpus: Sequence[int]):
        """Implement '_write_to_sysfs()'. Arguments are the same."""

        val_str = str(val).strip()

        # AMD CPUs support only policy names, not numeric EPP values. Check upfront.
        proc_cpuinfo = self._cpuinfo.get_proc_cpuinfo()
        if proc_cpuinfo["vendor"] == CPUModels.VENDOR_AMD and Trivial.is_int(val_str):
            policies = self._get_available_policies(cpus[0])
            policies_str = ", ".join(policies) if policies else "(unknown)"
            raise ErrorNotSupported(f"Numeric EPP values are not supported "
                                    f"'{self._cpuinfo.get_cpudescr()}'\n"
                                    f"Use one of the following EPP policies: {policies_str}")

        # Check if workaround for write bug is needed. The bug causes writes to fail when the new
        # value matches the current value. If the bug is present, filter out CPUs that already
        # have the target value.
        cpus_to_write: Sequence[int] = cpus
        if self._has_write_bug():
            _LOG.debug("Kernel version %s detected, applying EPP write bug workaround", self._kver)
            current_vals: dict[int, str] = {}
            for cpu, cur_val in self._fetch_from_sysfs(cpus):
                current_vals[cpu] = str(cur_val).strip()

            cpus_to_write = [cpu for cpu in cpus if current_vals.get(cpu) != val_str]

        if cpus_to_write:
            sysfs_io = self._get_sysfs_io()
            paths_iter = (Path(self._sysfs_epp_path % cpu) for cpu in cpus_to_write)
            sysfs_io.write_paths(paths_iter, val_str, what="EPP")

    def _write_to_sysfs(self, val: str | int, cpus: Sequence[int]):
        """
        Refer to '_EPBase._write_to_sysfs()'.

        Raises:
            ErrorPerCPUPath: If writing the sysfs file fails with path-related error.
            ErrorVerifyFailedPerCPUPath: If the written value doesn't match the expected value.
        """

        try:
            self.__write_to_sysfs(val, cpus)
        except ErrorVerifyFailedPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorVerifyFailedPerCPUPath(str(err), cpu=cpu, path=err.path,
                                              expected=err.expected, actual=err.actual) from err
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err
