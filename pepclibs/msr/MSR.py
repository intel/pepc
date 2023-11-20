# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a capability for reading and writing to read and write CPU Model Specific
Registers. This module has been designed and implemented for Intel CPUs.

Terminology.
  * MSR scope. MSR scope is defined by the observability of MSR writes, not by their functional
    impact. For example, if modifying an MSR register from CPU X makes the modification visible on
    all core siblings, the MSR has core scope. If the modification is visible on all package
    siblings, the MSR has package scope. Some MSRs may have, for example, core scope, but impact the
    entire package from the functional point of view.
  * MSR feature scope, defines the scope for specific bit/bits inside a MSR. Some MSR can be hybrid
    for example, on Knights Mill MSR_MISC_FEATURE_CONTROL bit 0 has core scope and bit 1 has module
    scope.
"""

import logging
from pathlib import Path
from pepclibs.helperlibs import LocalProcessManager, FSHelpers, KernelModule, Trivial, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed, ErrorNotFound
from pepclibs import CPUInfo, _PerCPUCache

_CPU_BYTEORDER = "little"

# A special value which can be used to specify that all bits have to be set to "1" in methods like
# 'write_bits()'.
ALL_BITS_1 = object()

# Feature control MSR.
MSR_MISC_FEATURE_CONTROL = 0x1A4
MLC_STREAMER = 0
MLC_SPACIAL = 1
DCU_STREAMER = 2
DCU_IP = 3

_LOG = logging.getLogger()

class MSR(ClassHelpers.SimpleCloseContext):
    """
    This class provides helpers to read and write CPU Model Specific Registers.

    Public methods overview.

    1. Multi-CPU I/O.
        * Read/write entire MSR: 'read()', 'write()'.
        * Read/write MSR bits range: 'read_bits()', 'write_bits()'.
    2. Single-CPU I/O.
        * Read/write entire MSR: 'read_cpu()', 'write_cpu()'.
        * Read/write MSR bits range: 'read_cpu_bits()', 'write_cpu_bits()'.
    3. Transactions support.
        * Start a transaction: start_transaction().
        * Flush the transaction buffer: flush_transaction().
        * Commit the transaction: commit_transaction().
    4. Miscellaneous helpers.
        * Get/set bits from/in a user-provided MSR value: 'get_bits()', 'set_bits()'.
    """

    def _add_for_transation(self, regaddr, regval, cpu):
        """Add CPU 'cpu' MSR at 'regaddr' with its value 'regval' to the transaction buffer."""

        if not self._enable_cache:
            raise Error("transactions support requires caching to be enabled, see 'enable_cache' "
                        "argument of the 'MSR.MSR()' constructor")

        if cpu not in self._transaction_buffer:
            self._transaction_buffer[cpu] = {}

        self._transaction_buffer[cpu][regaddr] = regval

    def start_transaction(self):
        """
        Start transaction. All writes to MSR registers will be cached, and will only be written
        to the actual hardware on 'commit_transaction()'. Writes to the same MSR registers will be
        merged.

        The purpose of a transaction is to reduce the amount of I/O. There is no atomicity and
        roll-back functionality, it is only about buffering the I/O and merging multiple writes to
        the same register into a single write operation.
        """

        if not self._enable_cache:
            _LOG.debug("transactions support requires caching to be enabled")
            return

        if self._in_transaction:
            raise Error("cannot start a transaction, it has already started")

        self._in_transaction = True

    def flush_transaction(self):
        """
        Flush the transaction buffer. Write all the buffered data to the MSR registers. If there are
        multiple writes to the same MSR register, they will be merged into a single write operation.
        The transaction does not stop after flushing.
        """

        if not self._enable_cache:
            return

        if not self._in_transaction:
            raise Error("cannot commit a transaction, it did not start")

        if self._transaction_buffer:
            _LOG.debug("flushing MSR transaction buffer")

        for cpu, to_write in self._transaction_buffer.items():
            # Write all the dirty data.
            path = Path(f"/dev/cpu/{cpu}/msr")
            with self._pman.open(path, "r+b") as fobj:
                for regaddr, regval in to_write.items():
                    try:
                        fobj.seek(regaddr)
                        regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                        fobj.write(regval_bytes)
                        fobj.flush()
                        _LOG.debug("CPU%d: commit MSR 0x%x: wrote 0x%x%s",
                                   cpu, regaddr, regval, self._pman.hostmsg)
                    except Error as err:
                        raise Error(f"failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                                    f"{cpu}{self._pman.hostmsg} (file '{path}'):\n"
                                    f"{err.indent(2)}") from err

        self._transaction_buffer.clear()

    def commit_transaction(self):
        """
        Commit the transaction. Write all the buffered data to the MSR registers and close the
        transaction. Note, there is no atomicity guarantee, this is not like a database transaction,
        this is just an optimization to reduce the amount of MSR I/O.
        """

        self.flush_transaction()
        self._in_transaction = False
        _LOG.debug("MSR transaction has been committed")

    def _normalize_bits(self, bits):
        """Validate and normalize bits range 'bits'."""

        orig_bits = bits
        try:
            if not Trivial.is_int(orig_bits[0]) or not Trivial.is_int(orig_bits[1]):
                raise Error(f"bad bits range '{bits}', must be a list or tuple of 2 integers")

            bits = (int(orig_bits[0]), int(orig_bits[1]))

            if bits[0] < bits[1]:
                raise Error(f"bad bits range ({bits[0]}, {bits[1]}), the first number must be "
                            f"greater or equal to the second number")

            bits_cnt = (bits[0] - bits[1]) + 1
            if bits_cnt > self.regbits:
                raise Error(f"too many bits in ({bits[0]}, {bits[1]}), MSRs only have "
                            f"{self.regbits} bits")
        except TypeError:
            raise Error(f"bad bits range '{bits}', must be a list or tuple of 2 integers") from None

        return bits

    def get_bits(self, regval, bits):
        """
        Fetch bits 'bits' from an MSR value 'regval'. The arguments are as follows.
          * regval - an MSR value to fetch the bits from.
          * bits - the MSR bits range. A tuple or a list of 2 integers: (msb, lsb), where 'msb' is
                   the more significant bit, and 'lsb' is a less significant bit. For example, (3,1)
                   would mean bits 3-1 of the MSR. In a 64-bit number, the least significant bit
                   number would be 0, and the most significant bit number would be 63.
        """

        bits = self._normalize_bits(bits)
        bits_cnt = (bits[0] - bits[1]) + 1
        mask = (1 << bits_cnt) - 1
        return (regval >> bits[1]) & mask

    def _read_cpu(self, regaddr, cpu):
        """Read an MSR at address 'regaddr' on CPU 'cpu'."""

        path = Path(f"/dev/cpu/{cpu}/msr")
        try:
            with self._pman.open(path, "rb") as fobj:
                fobj.seek(regaddr)
                regval = fobj.read(self.regbytes)
        except Error as err:
            raise Error(f"failed to read MSR '{regaddr:#x}' from file '{path}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        regval = int.from_bytes(regval, byteorder=_CPU_BYTEORDER)
        _LOG.debug("CPU%d: MSR 0x%x: read 0x%x%s", cpu, regaddr, regval, self._pman.hostmsg)

        return regval

    def read(self, regaddr, cpus="all", sname="CPU"):
        """
        Read an MSR on CPUs 'cpus' and yield the result. The arguments are as follows.
          * regaddr - address of the MSR to read.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * sname - the 'regaddr' MSR scope name (e.g. "package", "core").

        Yields tuples of '(cpu, regval)'.
          * cpu - the CPU number the MSR was read from.
          * regval - the read MSR value.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)

        for cpu in cpus:
            # Return the cached value if possible.
            try:
                regval = self._pcache.get(regaddr, cpu)
            except ErrorNotFound:
                # Not in the cache, read from the HW.
                regval = self._read_cpu(regaddr, cpu)
                self._pcache.add(regaddr, cpu, regval, sname=sname)

            yield (cpu, regval)

    def read_cpu(self, regaddr, cpu, sname="CPU"):
        """
        Read an MSR at 'regaddr' on CPU 'cpu' and return read result. The arguments are as follows.
          * regaddr - address of the MSR to read.
          * cpu - the CPU to read the MSR at. Can be an integer or a string with an integer number.
          * sname - same as in 'read()'.
        """

        regval = None
        for _, regval in self.read(regaddr, cpus=(cpu,), sname=sname):
            pass

        return regval

    def read_bits(self, regaddr, bits, cpus="all", sname="CPU"):
        """
        Read bits 'bits' from an MSR at 'regaddr' from CPUs in 'cpus' and yield the results. The
        arguments are as follows.
          * regaddr - address of the MSR to read the bits from.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * cpus - the CPUs to read from (similar to the 'cpus' argument in 'read()').
          * sname - same as in 'read()'.

        Yields tuples of '(cpu, regval)'.
          * cpu - the CPU number the MSR was read from.
          * val - the value in MSR bits 'bits'.
        """

        for cpu, regval in self.read(regaddr, cpus, sname=sname):
            yield (cpu, self.get_bits(regval, bits))

    def read_cpu_bits(self, regaddr, bits, cpu, sname="CPU"):
        """
        Read bits 'bits' from an MSR at 'regaddr' on CPU 'cpu'. The arguments are as follows.
          * regaddr - address of the MSR to read the bits from.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * cpu - the CPU to read the MSR at. Can be an integer or a string with an integer number.
          * sname - same as in 'read()'.
        """

        regval = self.read_cpu(regaddr, cpu, sname=sname)
        return self.get_bits(regval, bits)

    def set_bits(self, regval, bits, val):
        """
        Set bits 'bits' to value 'val' in an MSR value 'regval', and return the result. The
        arguments are as follows.
          * regval - an MSR register value to set the bits in.
          * bits - the bits range to set (similar to the 'bits' argument in 'get_bits()').
          * val - the value to set the bits to.
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
        return (regval & ~clear_mask) | set_mask

    def _write_cpu(self, regaddr, regval, cpu, regval_bytes=None):
        """Write value 'regval' to MSR at 'regaddr' on CPU 'cpu."""

        if regval_bytes is None:
            regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)

        path = Path(f"/dev/cpu/{cpu}/msr")
        with self._pman.open(path, "r+b") as fobj:
            try:
                fobj.seek(regaddr)
                fobj.write(regval_bytes)
                fobj.flush()
                _LOG.debug("CPU%d: MSR 0x%x: wrote 0x%x", cpu, regaddr, regval)
            except Error as err:
                raise Error(f"failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                            f"{cpu}{self._pman.hostmsg} (file '{path}'):\n{err.indent(2)}") from err

    def write(self, regaddr, regval, cpus="all", sname="CPU", verify=False):
        """
        Write 'regval' to an MSR at 'regaddr' on CPUs in 'cpus'. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - the value to write to the MSR.
          * cpus - the CPUs to write to (similar to the 'cpus' argument in 'read()').
          * sname - the 'regaddr' MSR scope name (e.g. "package", "core").
          * verify - read-back and verify the written value, raises 'ErrorVerifyFailed' if it
                     differs. Setting this flag to 'True' also flushed any pending transaction
                     buffers, but lets the transaction continue afterwards.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        regval_bytes = None

        for cpu in cpus:
            self._pcache.remove(regaddr, cpu, sname=sname)

        # Removing 'cpus' from the cache will make sure the following '_pcache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_pcache.add()'
        # method.
        for cpu in cpus:
            if self._pcache.is_cached(regaddr, cpu):
                continue

            if not self._in_transaction:
                if regval_bytes is None:
                    regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                self._write_cpu(regaddr, regval, cpu, regval_bytes=regval_bytes)
            else:
                self._add_for_transation(regaddr, regval, cpu)

            # Note, below 'add()' call is scope-aware. It will cache 'regval' not only for CPU
            # number 'cpu', but also for all the 'sname' siblings. For example, if 'sname' is
            # "package", 'regval' will be cached for all CPUs in the package that contains CPU
            # number 'cpu'.
            self._pcache.add(regaddr, cpu, regval, sname=sname)

        if verify:
            if self._in_transaction:
                self.flush_transaction()

            for cpu in cpus:
                self._pcache.remove(regaddr, cpu, sname=sname)

            for cpu in cpus:
                if self._pcache.is_cached(regaddr, cpu):
                    continue

                new_val = self.read_cpu(regaddr, cpu, sname=sname)
                if new_val != regval:
                    err_msg = f"verification failed for MSR '{regaddr:#x}' on CPU {cpu}" \
                              f"{self._pman.hostmsg}:\n  wrote '{regval:#x}', read back " \
                              f"'{new_val:#x}'"
                    raise ErrorVerifyFailed(err_msg, cpu=cpu, expected=regval, actual=new_val)

    def write_cpu(self, regaddr, regval, cpu, sname="CPU", verify=False):
        """
        Write 'regval' to an MSR at 'regaddr' on CPU 'cpu'. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - the value to write to the MSR.
          * cpu - the CPU to write the MSR on. Can be an integer or a string with an integer number.
          * sname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        self.write(regaddr, regval, cpus=(cpu,), sname=sname, verify=verify)

    def write_bits(self, regaddr, bits, val, cpus="all", sname="CPU", verify=False):
        """
        Write value 'val' to bits 'bits' of an MSR at 'regaddr' on CPUs in 'cpus'. The arguments are
        as follows.
          * regaddr - address of the MSR to write the bits to.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * val - the integer value to write to MSR bits 'bits'. Use 'MSR.ALL_BITS_1' to set all
                  bits to '1'.
          * cpus - the CPUs to write to (similar to the 'cpus' argument in 'read()').
          * sname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        regvals = {}
        for cpu, regval in self.read(regaddr, cpus, sname=sname):
            new_regval = self.set_bits(regval, bits, val)
            if regval == new_regval:
                continue

            if new_regval not in regvals:
                regvals[new_regval] = []
            regvals[new_regval].append(cpu)

        for regval, regval_cpus in regvals.items():
            self.write(regaddr, regval, regval_cpus, sname=sname, verify=verify)

    def write_cpu_bits(self, regaddr, bits, val, cpu, sname="CPU", verify=False):
        """
        Write value 'val' to bits 'bits' of an MSR at 'regaddr' on CPU 'cpu'. The arguments are
        as follows.
          * regaddr - address of the MSR to write the bits to.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * val - the integer value to write to MSR bits 'bits'. Use 'MSR.ALL_BITS_1' to set all
                  bits to '1'.
          * cpu - the CPU to write the MSR on. Can be an integer or a string with an integer number.
          * sname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        self.write_bits(regaddr, bits, val, cpus=(cpu,), sname=sname, verify=verify)

    def _ensure_dev_msr(self):
        """
        Make sure that device nodes for accessing MSR registers are available. Try to load the MSR
        driver if necessary.
        """

        cpus = self._cpuinfo.get_cpus()
        dev_path = Path(f"/dev/cpu/{cpus[0]}/msr")
        if self._pman.exists(dev_path):
            return

        drvname = "msr"
        msg = f"file '{dev_path}' is not available{self._pman.hostmsg}\nMake sure your kernel" \
              f"has the '{drvname}' driver enabled (CONFIG_X86_MSR)."
        try:
            self._msr_drv = KernelModule.KernelModule(drvname, pman=self._pman)
            loaded = self._msr_drv.is_loaded()
        except Error as err:
            raise Error(f"{msg}\n{err.indent(2)}") from err

        if loaded:
            raise Error(msg)

        try:
            self._msr_drv.load()
            self._unload_msr_drv = True
            FSHelpers.wait_for_a_file(dev_path, timeout=1, pman=self._pman)
        except Error as err:
            raise Error(f"{msg}\n{err.indent(2)}") from err

    def __init__(self, pman=None, cpuinfo=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - by default, this class caches values read from MSRs. This means that
                           the first time an MSR is read, it will be read from the hardware, but the
                           subsequent reads will return the cached value. The writes are not cached
                           (write-through cache policy). This option can be used to disable
                           caching.

        Important: current implementation is not thread-safe. Can only be used by single-threaded
        applications (add locking to improve this).
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # MSR registers' size in bits and bytes.
        self.regbits = 64
        self.regbytes = self.regbits // 8

        self._msr_drv = None
        self._unload_msr_drv = False

        # The write-through per-CPU MSR values cache.
        self._pcache = _PerCPUCache.PerCPUCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                                enable_cache=self._enable_cache)
        # Stores new MSR values to be written when 'commit_transaction()' is called.
        self._transaction_buffer = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

        self._ensure_dev_msr()

    def close(self):
        """Uninitialize the class object."""

        if self._unload_msr_drv:
            self._msr_drv.unload()

        ClassHelpers.close(self, close_attrs=("_cpuinfo", "_pman", "_msr_drv", "_pcache",))
