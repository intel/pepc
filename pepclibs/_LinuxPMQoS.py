# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of reading and changing Linux PM QoS latency limits.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs import _SysfsIO
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorPath, ErrorPerCPUPath
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailedPath, ErrorVerifyFailedPerCPUPath

if typing.TYPE_CHECKING:
    from typing import Generator, Final, Literal, Sequence
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_CPU_BYTEORDER: Final[Literal["little", "big"]] = "little"

class LinuxPMQoS(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and changing Linux PM QoS latency limits.

    Public methods overview.

    1. Per-CPU latency limits.
        - 'get_latency_limit()' - read per-CPU latency limits.
        - 'set_latency_limit()' - set per-CPU latency limits.
    2. Global latency limit.
        - 'get_global_latency_limit()' - read global latency limit.
    3. Miscellaneous.
        - 'close()' - uninitialize the class object.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers and
          ensure they exist and are online.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True,
                 verify: bool = True):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the host to get/set the PM QoS limits on.
                  If not provided, a local process manager will be used.
            sysfs_io: An '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                      files. Will be created if not provided.
            enable_cache: Enable or disable caching for sysfs access. Used only when 'sysfs_io' is
                          not provided. If 'sysfs_io' is provided, this argument is ignored.
            verify: Enable verification of written values, by default verification is enabled.
        """

        self._pman: ProcessManagerType
        self._sysfs_io: _SysfsIO.SysfsIO
        self._verify = verify

        self._close_pman = pman is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self._cdev_path = Path("/dev/cpu_dma_latency")

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=self._pman, enable_cache=enable_cache)
        else:
            self._sysfs_io = sysfs_io

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _get_latency_limit_sysfs_path(self, cpu: int) -> Path:
        """
        Construct and return Linux PM QoS latency limit sysfs path for CPU 'cpu'.

        Args:
            cpu: The CPU number.

        Returns:
            Path to the sysfs file.
        """

        return self._sysfs_base / f"cpu{cpu}" / "power" / "pm_qos_resume_latency_us"

    def _extract_cpu_from_path(self, path: Path) -> int:
        """
        Extract the CPU number from PM QoS sysfs path.

        Args:
            path: The PM QoS sysfs path.

        Returns:
            The CPU number.
        """

        # Path format: /sys/devices/system/cpu/cpu<N>/power/pm_qos_resume_latency_us
        # Extract "cpu<N>" from the path
        dir_name = path.parent.parent.name
        cpu_str = dir_name.replace("cpu", "")
        return Trivial.str_to_int(cpu_str, what=f"CPU number from path '{path}'")

    def __get_latency_limit(self, cpus: Sequence[int]) -> Generator[tuple[int, float], None, None]:
        """Implement 'get_latency_limit()'. Arguments are the same."""

        for cpu in cpus:
            path = self._get_latency_limit_sysfs_path(cpu)
            what = f"CPU{cpu} PM QoS latency limit"

            val = self._sysfs_io.read_int(path, what=what)
            # Convert microseconds to seconds.
            yield cpu, val / 1000000

    def get_latency_limit(self, cpus: Sequence[int]) -> Generator[tuple[int, float], None, None]:
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the Linux PM QoS
        latency limit read via the per-CPU sysfs interface, in seconds.

        Args:
            cpus: CPU numbers to get the latency limit for (the caller must validate CPU numbers).

        Yields:
            Tuples of (cpu, latency_limit) where latency_limit is in seconds.

        Raises:
            ErrorNotSupported: The CPU PM QoS latency limit sysfs file does not exist.
            ErrorPerCPUPath: Reading the sysfs file fails with path-related error.
        """

        try:
            yield from self.__get_latency_limit(cpus)
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err

    def get_global_latency_limit(self) -> float:
        """
        Read and return the global Linux PM QoS latency limit read from the character device node
        (in seconds).

        Returns:
            The global latency limit in seconds.

        Raises:
            ErrorNotSupported: The PM QoS global latency limit character device node does not
                               exist.
        """

        try:
            with self._pman.openb(self._cdev_path, "rb") as fobj:
                limit_bytes = fobj.read(4)
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"failed to read '{self._cdev_path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}") from err

        limit_us = int.from_bytes(limit_bytes, byteorder=_CPU_BYTEORDER)
        # Convert from microseconds to seconds.
        return limit_us / 1000000

    def __set_latency_limit(self, latency_limit: float, cpus: Sequence[int]):
        """Implement 'set_latency_limit()'. Arguments are the same."""

        # Convert seconds to microseconds.
        limit_us = round(latency_limit * 1000000)

        for cpu in cpus:
            what = f"CPU{cpu} PM QoS latency limit"
            path = self._get_latency_limit_sysfs_path(cpu)

            if not self._verify:
                self._sysfs_io.write_int(path, limit_us, what=what, su=True)
            else:
                self._sysfs_io.write_verify_int(path, limit_us, what=what, su=True)

    def set_latency_limit(self, latency_limit: float, cpus: Sequence[int]):
        """
        For every CPU in 'cpus', set the latency limit via Linux PM QoS sysfs interfaces.

        Args:
            latency_limit: The latency limit value to set, in seconds.
            cpus: CPU numbers to set the latency limit for (the caller must validate CPU numbers).

        Raises:
            ErrorPermissionDenied: No permissions to set the CPU PM QoS latency limit.
            ErrorPerCPUPath: Writing the sysfs file fails with path-related error.
            ErrorVerifyFailedPerCPUPath: The written value doesn't match the expected value.
        """

        try:
            self.__set_latency_limit(latency_limit, cpus)
        except ErrorVerifyFailedPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorVerifyFailedPerCPUPath(str(err), cpu=cpu, path=err.path,
                                              expected=err.expected, actual=err.actual) from err
        except ErrorPath as err:
            cpu = self._extract_cpu_from_path(err.path)
            raise ErrorPerCPUPath(str(err), cpu=cpu, path=err.path) from err
