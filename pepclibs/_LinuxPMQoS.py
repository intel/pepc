# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of reading and changing Linux PM QoS latency limits.
"""

from pathlib import Path
from pepclibs import _SysfsIO
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers
from pepclibs.helperlibs.Exceptions import ErrorVerifyFailed, ErrorNotFound, ErrorNotSupported

_CPU_BYTEORDER = "little"

class LinuxPMQoS(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of reading and changing Linux PM QoS latency limits.

    Note, class methods do not validate the 'cpus' arguments. The caller is assumed to have done the
    validation. The input CPU numbers should exist and should be online.
    """

    def _get_latency_limit_sysfs_path(self, cpu):
        """Construct and return Linux PM QoS latency limit sysfs path for CPU 'cpu'."""

        return self._sysfs_base / f"cpu{cpu}" / "power" / "pm_qos_resume_latency_us"

    def get_latency_limit(self, cpus):
        """
        For every CPU in 'cpus', yield a '(cpu, val)' tuple, where 'val' is the Linux PM QoS
        latency limit read via the per-CPU sysfs interface, seconds. The arguments are as follows.
          * cpus - a collection of integer CPU numbers to get the latency limit for.

        Raise 'ErrorNotSupported' if the CPU PM QoS latency limit sysfs file does not exist.
        """

        for cpu in cpus:
            path = self._get_latency_limit_sysfs_path(cpu)
            what = "CPU{cpu} PM QoS latency limit"

            val = self._sysfs_io.read_int(path, what=what)
            # Convert microseconds to seconds.
            yield cpu, val / 1000000

    def get_global_latency_limit(self):
        """
        Read and return the global Linux PM QoS latency limit read from the character device node
        (in seconds).

        Raise 'ErrorNotSupported' if the PM QoS global latency limit character device node does not
        exist.
        """

        try:
            with self._pman.open(self._cdev_path, "rb") as fobj:
                limit = fobj.read(4)
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"failed to read '{self._cdev_path}'{self._pman.hostmsg}\n"
                                    f"{err.indent(2)}") from err

        limit = int.from_bytes(limit, byteorder=_CPU_BYTEORDER)
        # Convert from microseconds to seconds.
        return limit / 1000000

    def set_latency_limit(self, latency_limit, cpus):
        """
        For every CPU in 'cpus', set the latency limit via Linux PM QoS sysfs interfaces. The
        arguments are as follows.
          * latency_limit - the latency limit value to set, seconds.
          * cpus - a collection of CPU numbers to set the latency limit for.
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

    def __init__(self, pman=None, sysfs_io=None, enable_cache=True, verify=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to get/set the PM QoS limits on.
          * sysfs_io - an '_SysfsIO.SysfsIO()' object which should be used for accessing sysfs
                       files.
          * enable_cache - this argument can be used to disable caching.
          * verify - enable verification of written values, by default verification is enabled.
        """

        self._pman = pman
        self._sysfs_io = sysfs_io
        self._verify = verify

        self._close_pman = pman is None
        self._close_sysfs_io = sysfs_io is None

        self._sysfs_base = Path("/sys/devices/system/cpu")
        self._cdev_path = Path("/dev/cpu_dma_latency")

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        if not self._sysfs_io:
            self._sysfs_io = _SysfsIO.SysfsIO(pman=pman, enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_sysfs_io", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
