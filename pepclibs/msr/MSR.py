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
from pepclibs.helperlibs import Procs, Logging, FSHelpers, KernelModule, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepclibs import CPUInfo

_CPU_BYTEORDER = "little"

# A special value which can be used to specify that all bits have to be set to "1" in methods like
# 'set_bits()'.
ALL_BITS_1 = object()

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

def fetch_bits(bits, val):
    """
    Fetch bits 'bits' from an integer 'val'. The 'bits' argument is the bits range: a tuple of a
    list of 2 intergers: (msb, lsb), where 'msb' is the more significant bit, and 'lsb' is a less
    significant bit. For example, (3,1) would mean bits 3-1 of the MSR. In a 64-bit number, the
    least significant bit number would be 0, and the most significan bit number would be 63.
    """

    bits_cnt = (bits[0] - bits[1]) + 1
    mask = (1 << bits_cnt) - 1
    return (val >> bits[1]) & mask

class MSR:
    """This class provides helpers to read and write CPU Model Specific Registers."""

    def _cache_add(self, regaddr, regval, cpu, dirty=False):
        """Add CPU 'cpu' MSR at 'regaddr' with its value 'regval' to the cache."""

        if not self._enable_cache:
            return

        if cpu not in self._cache:
            self._cache[cpu] = {}
        if regaddr not in self._cache[cpu]:
            self._cache[cpu][regaddr] = {}

        self._cache[cpu][regaddr] = { "regval" : regval, "dirty" : dirty }

    def _cache_get(self, regaddr, cpu):
        """
        If MSR register at 'regaddr' is in the cache, return the cached value, otherwise return
        'None'.
        """

        if not self._enable_cache:
            return None
        if cpu not in self._cache:
            return None
        if regaddr not in self._cache[cpu]:
            return None

        return self._cache[cpu][regaddr]["regval"]

    def start_transaction(self):
        """
        Start transaction. All writes to MSR registers will be cahched, and will only be written
        to the actual hardware on 'commit_transaction()'.
        """

        if self._in_transaction:
            raise Error("cannot start a transaction, it has already started")

        if not self._enable_cache:
            raise Error("transactions support requires caching to be enabled (see 'enable_cache' "
                        "argument of the 'MSR.MSR()' constructor.")

        self._in_transaction = True

    def commit_transaction(self):
        """
        Commit the transaction. Write all the MSR registers that have been modified after
        'start_transaction()'.
        """

        if not self._in_transaction:
            raise Error("cannot commit a transaction, it did not start")

        for cpu, cdata in self._cache.items():
            # Pick all the dirty data from the cache.
            to_write = []
            for regaddr in cdata:
                if cdata[regaddr]["dirty"]:
                    to_write.append((regaddr, cdata[regaddr]["regval"]))
                    cdata[regaddr]["dirty"] = False

            if not to_write:
                continue

            # Write all the dirty data.
            path = Path(f"/dev/cpu/{cpu}/msr")
            with self._proc.open(path, "wb") as fobj:
                for regaddr, regval in to_write:
                    fobj.seek(regaddr)
                    regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                    fobj.write(regval_bytes)
                    _LOG.debug("CPU%d: commit MSR 0x%x: wrote 0x%x", cpu, regaddr, regval)

        self._in_transaction = False

    def _read(self, regaddr, cpu):
        """Read MSR at address 'regaddr' on CPU 'cpu'."""

        path = Path(f"/dev/cpu/{cpu}/msr")
        try:
            with self._proc.open(path, "rb") as fobj:
                fobj.seek(regaddr)
                regval = fobj.read(self.regbytes)
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
                self._cache_add(regaddr, regval, cpu, dirty=False)

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
            regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)

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
        regval_bytes = None

        for cpu in cpus:
            if not self._in_transaction:
                if regval_bytes is not None:
                    regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                self._write(regaddr, regval, cpu, regval_bytes=regval_bytes)
                dirty = False
            else:
                dirty = True

            self._cache_add(regaddr, regval, cpu, dirty=dirty)

    def _normalize_bits(self, bits):
        """Validate and notmalize bits range 'bits'."""

        orig_bits = bits
        try:
            if not Trivial.is_int(orig_bits[0]) or not Trivial.is_int(orig_bits[1]):
                raise Error("bad bits range '{bits}', must be a list or tuple of 2 integers")

            bits = (int(orig_bits[0]), int(orig_bits[1]))

            if bits[0] < bits[1]:
                raise Error(f"bad bits range ({bits[0]}, {bits[1]}), the first number must be "
                            f"greater or equal to the second number")

            bits_cnt = (bits[0] - bits[1]) + 1
            if bits_cnt > self.regbits:
                raise Error(f"too many bits in ({bits[0]}, {bits[1]}), MSRs only have "
                            f"{self.regbits} bits")
        except TypeError:
            raise Error("bad bits range '{bits}', must be a list or tuple of 2 integers") from None

        return bits

    def fetch_bits(self, bits, val):
        """
        Fetch bits 'bits' from an MSR. The arguments are as follows:
          * val - an MSR value to fetch the bits from.
          * bits - same as in 'set_bits()'.
        """

        bits = self._normalize_bits(bits)
        return fetch_bits(bits, val)

    def read_bits(self, regaddr, bits, cpu=0):
        """
        Read bits 'bits' from an MSR. The arguments are as follows:
          * regaddr - same as in 'write()'.
          * bits - same as in 'set_bits()'.
          * cpu - CPU number to get the bits from.
        """

        bits = self._normalize_bits(bits)
        regval = self.read(regaddr, cpu=cpu)
        return fetch_bits(bits, regval)

    def set_bits(self, regaddr, bits, val, cpus="all"):
        """
        Set bits 'bits' in MSR to value 'val'. The arguments are as follows.
          * regaddr - same as in 'write()'.
          * bits - the MSR bits range. A tuple of a list of 2 intergers: (msb, lsb), where 'msb' is
                   the more significant bit, and 'lsb' is a less significant bit. For example, (3,1)
                   would mean bits 3-1 of the MSR. In a 64-bit number, the least significant bit
                   number would be 0, and the most significan bit number would be 64.
          * val - integer value to put to MSR bits 'bits'. Use 'MSR.ALL_BITS_1' to set all bets to
                  '1'.
          * cpus - same as in 'write()'.
        """

        bits = self._normalize_bits(bits)

        bits_cnt = (bits[0] - bits[1]) + 1
        max_val = (1 << bits_cnt) - 1

        if val is ALL_BITS_1:
            val = max_val
        else:
            if not Trivial.is_int(val):
                raise Error(f"bad value {val}, please provide a positive integer")
            val = int(val)

        if val > max_val:
            raise Error(f"too large value {val} for bits range ({bits[0]}, {bits[1]})")

        clear_mask = max_val << bits[1]
        set_mask = val << bits[1]
        for cpunum, regval in self.read_iter(regaddr, cpus):
            new_regval = (regval & ~clear_mask) | set_mask
            if regval != new_regval:
                self.write(regaddr, new_regval, cpunum)

    def set_mask(self, regaddr, mask, cpus="all"):
        """
        Set 'mask' bits in MSR (<MSR value> | mask). The 'regaddr' and 'cpus' arguments are the same
        as in 'write()'.
        """

        for cpunum, regval in self.read_iter(regaddr, cpus):
            new_regval = regval | mask
            if regval != new_regval:
                self.write(regaddr, new_regval, cpunum)

    def clear_mask(self, regaddr, mask, cpus="all"):
        """
        Clear 'mask' bits in MSR (<MSR value> & mask). The 'regaddr' and 'cpus' arguments are the
        same as in 'write()'.
        """

        for cpunum, regval in self.read_iter(regaddr, cpus):
            new_regval = regval & ~mask
            if regval != new_regval:
                self.write(regaddr, new_regval, cpunum)

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

        Important: current implementation is not thread-safe. Can only be used by single-threaded
        applications (add locking to improve this).
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

        # MSR registers' size in bits and bytes.
        self.regbits = 64
        self.regbytes = self.regbits // 8

        self._msr_drv = None
        self._unload_msr_drv = False

        # The MSR I/O cache. Indexed by CPU number and MSR address. Contains MSR values.
        self._cache = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

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
