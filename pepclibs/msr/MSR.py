# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""
This module provides a capability for reading and writing to read and write CPU Model Specific
Registers. This module has been designed and implemented for Intel CPUs.
"""

import logging
from pathlib import Path
from pepclibs.helperlibs import Procs, Logging, FSHelpers, KernelModule
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

_CPU_BYTEORDER = "little"

# Platform info MSR.
MSR_PLATFORM_INFO = 0xCE

# Scalable bus speed MSR.
MSR_FSB_FREQ = 0xCD

# Feature control MSR.
MSR_MISC_FEATURE_CONTROL = 0x1A4
MLC_STREAMER = 0
MLC_SPACIAL = 1
DCU_STREAMER = 2
DCU_IP = 3

# Turbo ratio limit MSR, informs about turbo frequencies for core croups.
MSR_TURBO_RATIO_LIMIT = 0x1AD

# Energy performance bias MSR.
MSR_ENERGY_PERF_BIAS = 0x1B0

# PM enable MSR.
MSR_PM_ENABLE = 0x770
HWP_ENABLE = 0

# HWP Request MSR. Includes hardware power management control bits.
MSR_HWP_REQUEST = 0x774
PKG_CONTROL = 42
EPP_VALID = 60

OWN_NAME="MSR.py"
_LOG = logging.getLogger()
Logging.setup_logger(prefix=OWN_NAME)

def bit_mask(bitnr):
    """Return bitmask for a bit by its number."""
    return 1 << bitnr

def is_bit_set(bitnr, bitval):
    """
    Return 'True' if bit number 'bitnr' is set in MSR value 'bitval', otherwise returns
    'False'.
    """
    return bit_mask(bitnr) & bitval

class MSR:
    """This class provides helpers to read and write CPU Model Specific Registers."""

    def _cache_add(self, regaddr, regval, cpu):
        """Add CPU 'cpu' MSR at 'regaddr' with its value 'regval' to the cache."""

        if not self._enable_cache:
            return

        if cpu not in self._cache:
            self._cache[cpu] = {}
        if regaddr not in self._cache[cpu]:
            self._cache[cpu][regaddr] = {}

        self._cache[cpu][regaddr] = regval

    def _cache_get(self, regaddr, cpu):
        """
        If MSR register at 'regaddr' is in the cache, return the cached value, otherwise return
        'None'.
        """

        if not self._enable_cache:
            return None
        if cpu not in self._cache:
            return None

        return self._cache[cpu].get(regaddr, None)

    def _read(self, regaddr, cpu):
        """Read MSR at address 'regaddr' on CPU 'cpu'."""

        path = Path(f"/dev/cpu/{cpu}/msr")
        try:
            with self._proc.open(path, "rb") as fobj:
                fobj.seek(regaddr)
                regval = fobj.read(self.regsize)
        except Error as err:
            raise Error(f"failed to read MSR '{hex(regaddr)}' from file '{path}'"
                        f"{self._proc.hostmsg}:\n{err}") from err

        regval = int.from_bytes(regval, byteorder=_CPU_BYTEORDER)
        _LOG.debug("CPU%d: MSR 0x%x: read 0x%x", cpu, regaddr, regval)

        return regval

    def read_iter(self, regaddr, cpus="all"):
        """
        Read an MSR register on one or multiple CPUs and yield tuple with CPU number and the read
        result.
          * regaddr - address of the MSR to read.
          * cpus - list of CPU numbers value should be read from. It is the same as the 'cpus'
                   argument of the 'CPUIdle.get_cstates_info()' function - please, refer to the
                   'CPUIdle' module for the exact format description.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)

        for cpu in cpus:
            # Return the cached value if possible.
            regval = self._cache_get(regaddr, cpu)
            if regval is None:
                # Not in the cache, read from the HW.
                regval = self._read(regaddr, cpu)
                self._cache_add(regaddr, regval, cpu)

            yield (cpu, regval)

    def read(self, regaddr, cpu=0):
        """
        Read an MSR on single CPU and return read result. Arguments are same as in read_iter().
        """

        _, msr = next(self.read_iter(regaddr, cpu))
        return msr

    def _write(self, regaddr, regval, cpu, regval_bytes=None):
        """Write value 'regval' to MSR at 'regaddr' on CPU 'cpu."""

        if regval_bytes is None:
            regval_bytes = regval.to_bytes(self.regsize, byteorder=_CPU_BYTEORDER)

        path = Path(f"/dev/cpu/{cpu}/msr")
        try:
            with self._proc.open(path, "wb") as fobj:
                fobj.seek(regaddr)
                fobj.write(regval_bytes)
                _LOG.debug("CPU%d: MSR 0x%x: wrote 0x%x", cpu, regaddr, regval)
        except Error as err:
            raise Error(f"failed to write MSR '{hex(regaddr)}' to file '{path}'"
                        f"{self._proc.hostmsg}:\n{err}") from err

    def write(self, regaddr, regval, cpus="all"):
        """
        Write to MSR register. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - integer value to write to MSR.
          * cpus - list of CPU numbers write should be done at. It is the same as the 'cpus'
                   argument of the 'CPUIdle.get_cstates_info()' function - please, refer to the
                   'CPUIdle' module for the exact format description.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        regval_bytes = regval.to_bytes(self.regsize, byteorder=_CPU_BYTEORDER)

        for cpu in cpus:
            self._write(regaddr, regval, cpu, regval_bytes=regval_bytes)
            # Save the written value in the cache.
            self._cache_add(regaddr, regval, cpu)

    def set(self, regaddr, mask, cpus="all"):
        """Set 'mask' bits in MSR. Arguments are the same as in 'write()'."""

        cpus = self._cpuinfo.normalize_cpus(cpus)

        for cpunum, regval in self.read_iter(regaddr, cpus):
            new_regval = regval | mask
            if regval != new_regval:
                self.write(regaddr, new_regval, cpunum)

    def clear(self, regaddr, mask, cpus="all"):
        """Clear 'mask' bits in MSR. Arguments are the same as in 'write()'."""

        cpus = self._cpuinfo.normalize_cpus(cpus)

        for cpunum, regval in self.read_iter(regaddr, cpus):
            new_regval = regval & ~mask
            if regval != new_regval:
                self.write(regaddr, new_regval, cpunum)

    def toggle_bit(self, regaddr, bitnr, bitval, cpus="all"):
        """
        Toggle bit number 'bitnr', in MSR 'regaddr' to value 'bitval'. Other arguments are the same
        as in 'write()'.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        bitval = int(bool(bitval))

        if bitval:
            self.set(regaddr, bit_mask(bitnr), cpus=cpus)
        else:
            self.clear(regaddr, bit_mask(bitnr), cpus=cpus)

    def _ensure_dev_msr(self):
        """
        Make sure that device nodes for accessing MSR registers are available. Try to load the MSR
        driver if necessary.
        """

        cpus = self._cpuinfo.get_cpus()
        dev_path = Path(f"/dev/cpu/{cpus[0]}/msr")
        if FSHelpers.exists(dev_path, self._proc):
            return

        drvname = "msr"
        msg = f"file '{dev_path}' is not available{self._proc.hostmsg}\nMake sure your kernel" \
              f"has the '{drvname}' driver enabled (CONFIG_X86_MSR)."
        try:
            self._msr_drv = KernelModule.KernelModule(self._proc, drvname)
            loaded = self._msr_drv.is_loaded()
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

        if loaded:
            raise Error(msg)

        try:
            self._msr_drv.load()
            self._unload_msr_drv = True
            FSHelpers.wait_for_a_file(dev_path, timeout=1, proc=self._proc)
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

    def __init__(self, proc=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - by default, this class caches values read from MSRs. This means that
                           the first time an MSR is read, it will be read from the hardware, but the
                           subsequent reads will return the cached value. The writes are not cached
                           (write-through cache policy). This option can be used to disable
                           caching.
        """

        self._proc = proc
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_proc = proc is None
        self._close_cpuinfo = cpuinfo is None

        if not self._proc:
            self._proc = Procs.Proc()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        # MSR registers' size in bytes.
        self.regsize = 8

        self._msr_drv = None
        self._unload_msr_drv = False

        # The MSR I/O cache. Indexed by CPU number and MSR address. Contains MSR values.
        self._cache = {}

        self._ensure_dev_msr()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_msr_drv", None):
            if self._unload_msr_drv:
                self._msr_drv.unload()
            self._msr_drv = None

        for attr in ("_cpuinfo", "_proc"):
            obj = getattr(self, attr, None)
            if obj:
                if getattr(self, f"_close_{attr}", False):
                    getattr(obj, "close")()
                setattr(self, attr, None)

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
