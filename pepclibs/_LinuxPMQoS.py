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
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed, ErrorNotFound, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Generator, Final, Literal
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_CPU_BYTEORDER: Final[Literal["little", "big"]] = "little"

class LinuxPMQoS(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and changing Linux PM QoS latency limits.

    Note, class methods do not validate the 'cpus' arguments. The caller is assumed to have done the
    validation. The input CPU numbers should exist and should be online.
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

    def get_latency_limit(self, cpus: list[int]) -> Generator[tuple[int, float], None, None]:
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the Linux PM QoS
        latency limit read via the per-CPU sysfs interface, in seconds.

        Args:
            cpus: A collection of integer CPU numbers to get the latency limit for.

        Yields:
            Tuples of (cpu, latency_limit) where latency_limit is in seconds.

        Raises:
            ErrorNotSupported: If the CPU PM QoS latency limit sysfs file does not exist.
        """

        for cpu in cpus:
            path = self._get_latency_limit_sysfs_path(cpu)
            what = "CPU{cpu} PM QoS latency limit"

            val = self._sysfs_io.read_int(path, what=what)
            # Convert microseconds to seconds.
            yield cpu, val / 1000000

    def get_global_latency_limit(self) -> float:
        """
        Read and return the global Linux PM QoS latency limit read from the character device node
        (in seconds).

        Returns:
            The global latency limit in seconds.

        Raises:
            ErrorNotSupported: If the PM QoS global latency limit character device node does not
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

    def set_latency_limit(self, latency_limit: float, cpus: list[int]):
        """
        For every CPU in 'cpus', set the latency limit via Linux PM QoS sysfs interfaces.

        Args:
            latency_limit: The latency limit value to set, in seconds.
            cpus: A collection of CPU numbers to set the latency limit for.
        """

        # Convert seconds to microseconds.
        limit_us = round(latency_limit * 1000000)

        for cpu in cpus:
            what = "CPU{cpu} PM QoS latency limit"
            path = self._get_latency_limit_sysfs_path(cpu)

            try:
                if not self._verify:
                    self._sysfs_io.write_int(path, limit_us, what=what)
                else:
                    self._sysfs_io.write_verify_int(path, limit_us, what=what)
            except ErrorVerifyFailed as err:
                setattr(err, "cpu", cpu)
                raise err
