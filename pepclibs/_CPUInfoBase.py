# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide the base class for the 'CPUInfo.CPUInfo' class.
"""

import re
import logging
import contextlib
from pepclibs import _UncoreFreq, CPUModels
from pepclibs.msr import MSR, PMLogicalId
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial, KernelVersion, ArgParse
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = logging.getLogger()

class CPUInfoBase(ClassHelpers.SimpleCloseContext):
    """
    Base class for the 'CPUInfo.CPUInfo' class. Implements low-level "plumbing", while the 'CPUInfo'
    class implements the API methods.
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            # Disable caching to exclude usage of the 'cpuinfo' object by the 'MSR' module, which
            # happens when 'MSR' module uses 'PerCPUCache'.
            self._msr = MSR.MSR(self, pman=self._pman, enable_cache=False)

        return self._msr

    def _get_pliobj(self):
        """Returns a 'PMLogicalId.PMLogicalID()' object."""

        if not self._pliobj:
            if not self._pli_msr_supported:
                return None

            msr = self._get_msr()

            try:
                self._pliobj = PMLogicalId.PMLogicalId(pman=self._pman, cpuinfo=self, msr=msr)
            except ErrorNotSupported:
                self._pli_msr_supported = False

        return self._pliobj

    def _get_uncfreq_obj(self):
        """Return an '_UncoreFreq' object."""

        if not self._uncfreq_supported:
            return None

        if not self._uncfreq_obj:
            try:
                self._uncfreq_obj = _UncoreFreq.UncoreFreq(self, pman=self._pman)
            except ErrorNotSupported:
                self._uncfreq_supported = False

        return self._uncfreq_obj

    def _read_range(self, path, must_exist=True):
        """
        Read a file that is expected to contain a comma separated list of integer numbers or
        integer number rangees. Parse the contents of the file and return it as a list of integers.
        """

        str_of_ranges = self._pman.read(path, must_exist=must_exist).strip()
        return ArgParse.parse_int_list(str_of_ranges, ints=True)

    def _read_online_cpus(self):
        """Read and return online CPU numbers from sysfs."""

        if not self._cpus:
            self._cpus = set(self._read_range("/sys/devices/system/cpu/online"))
        return self._cpus

    def _get_cpu_info(self):
        """Get general CPU information (model, architecture, etc)."""

        self.info = cpuinfo = {}
        lscpu, _ = self._pman.run_verify("lscpu", join=False)

        # Parse misc. information about the CPU.
        patterns = ((r"^Architecture:\s*(.*)$", "arch"),
                    (r"^Byte Order:\s*(.*)$", "byteorder"),
                    (r"^Vendor ID:\s*(.*)$", "vendor"),
                    (r"^Socket\(s\):\s*(.*)$", "packages"),
                    (r"^CPU family:\s*(.*)$", "family"),
                    (r"^Model:\s*(.*)$", "model"),
                    (r"^Model name:\s*(.*)$", "modelname"),
                    (r"^Model name:.*@\s*(.*)GHz$", "basefreq"),
                    (r"^Stepping:\s*(.*)$", "stepping"),
                    (r"^Flags:\s*(.*)$", "flags"))

        for line in lscpu:
            for pattern, key in patterns:
                match = re.match(pattern, line.strip())
                if not match:
                    continue

                val = match.group(1)
                if Trivial.is_int(val):
                    cpuinfo[key] = int(val)
                else:
                    cpuinfo[key] = val

        if cpuinfo.get("flags"):
            cpuflags = set(cpuinfo["flags"].split())
            cpuinfo["flags"] = {}
            # In current implementation we assume all CPUs have the same flags. But ideally, we
            # should read the flags for each CPU from '/proc/cpuinfo', instead of using 'lscpu'.
            for cpu in self._read_online_cpus():
                cpuinfo["flags"][cpu] = cpuflags

        if self._pman.exists("/sys/devices/cpu_atom/cpus"):
            cpuinfo["hybrid"] = True
        else:
            cpuinfo["hybrid"] = False
            with contextlib.suppress(Error):
                kver = KernelVersion.get_kver(pman=self._pman)
                if KernelVersion.kver_lt(kver, "5.13"):
                    _LOG.debug("kernel v%s does not support hybrid CPU topology. The minimum "
                               "required kernel version is v5.13.", kver)

        return cpuinfo

    def _get_cpu_description(self):
        """Build and return a string identifying and describing the processor."""

        if "Genuine Intel" in self.info["modelname"]:
            # Pre-release firmware on Intel CPU describes them as "Genuine Intel", which is not very
            # helpful.
            cpudescr = f"Intel processor model {self.info['model']:#x}"

            for info in CPUModels.MODELS.values():
                if info["model"] == self.info["model"]:
                    cpudescr += f" (codename: {info['codename']})"
                    break
        else:
            cpudescr = self.info["modelname"]

        return cpudescr

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
        """

        # A dictionary including the general CPU information.
        self.info = None
        # A short CPU description string.
        self.cpudescr = None

        self._pman = pman
        self._close_pman = pman is None

        self._msr = None
        self._pliobj = None
        self._uncfreq_obj = None

        # 'True' if 'MSR_PM_LOGICAL_ID' is supported by the target host, otherwise 'False'. When
        # this MSR is supported, it provides the die IDs enumeration.
        self._pli_msr_supported = True
        # 'True' if the target host supports uncore frequency scaling.
        self._uncfreq_supported = True

        # Online CPU numbers.
        self._cpus = set()

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        self.info = self._get_cpu_info()
        self.cpudescr = self._get_cpu_description()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_uncfreq_obj", "_pliobj", "_msr", "_pman"))
