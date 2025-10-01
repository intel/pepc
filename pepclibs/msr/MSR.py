# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide a capability to read and write CPU Model Specific Registers, including write-through caching
and transactions support.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import pprint
from pathlib import Path
from pepclibs import _PerCPUCache
from pepclibs.helperlibs import EmulProcessManager, Logging
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed
from pepclibs.msr import _SimpleMSR
from pepclibs.msr._SimpleMSR import _CPU_BYTEORDER

if typing.TYPE_CHECKING:
    from typing import Generator, TypedDict, Literal, Sequence
    from pepclibs import CPUInfo
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import ScopeNameType

    class _TransactionBufferItemTypedDict(TypedDict, total=False):
        """
        The typed dictionary for a transaction buffer item.

        Attributes:
            regval: The MSR value to write.
            verify: Whether to verify the written value.
            iosname: The I/O scope name of the MSR (e.g. "package", "core").
        """

        regval: int
        verify: bool
        iosname: ScopeNameType

    class _TransactionVerifyItemTypedDict(TypedDict, total=False):
        """
        The typed dictionary for a transaction verification item.

        Attributes:
            cpus: CPU numbers to verify the MSR on.
            iosname: The I/O scope name of the MSR (e.g. "package", "core").
        """

        cpus: list[int]
        iosname: ScopeNameType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class MSR(_SimpleMSR.SimpleMSR):
    """
    Provide a capability to read and write CPU Model Specific Registers, including write-through
    caching and transactions support.

    Public methods overview.

    1. Multi-CPU I/O.
        - 'read()' - read an MSR.
        - 'read_bits()'  - read an MSR bits range.
        - 'write()' - write to the an MSR.
        - 'write_bits()'  - write MSR bits range.
    2. Single-CPU I/O.
        - 'read_cpu()' - read an MSR.
        - 'read_cpu_bits()'  - read an MSR bits range.
        - 'write_cpu()' - write to the an MSR.
        - 'write_cpu_bits()'  - write MSR bits range.
    3. Transactions support.
        - 'start_transaction()' - start a transaction.
        - 'flush_transaction()' - flush the transaction buffer.
        - 'commit_transaction()' - commit the transaction.
    4. Miscellaneous.
        - 'get_bits()' - get bits range from a user-provided MSR value.
        - 'set_bits()' - set bits range from a user-provided MSR value.

    Note:
        Current implementation is not thread-safe. Can only be used by single-threaded applications
        (add locking to improve this).
    """

    def __init__(self,
                 cpuinfo: CPUInfo.CPUInfo,
                 pman: ProcessManagerType | None = None,
                 enable_cache: bool = True):
        """
        Initialize a class instance.

        Args:
            cpuinfo: The CPU information object.
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager will be used.
            enable_cache: If True, enable caching of MSR values. The first read fetches from
                          hardware, subsequent reads return the cached value. Writes update the
                          cache and and propagate to hardware immediately (write-through policy). If
                          False, caching is disabled, and every read/write operation accesses the
                          hardware directly.
        """

        super().__init__(pman=pman)

        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache
        self._enable_scope = True

        if isinstance(pman, EmulProcessManager.EmulProcessManager):
            # The emulation layer does not support MSR scope, so disable the scope optimization, and
            # make sure writes go to all CPUs, not just one CPU in the scope.
            self._enable_scope = False

        self._cache = _PerCPUCache.PerCPUCache(cpuinfo, enable_cache=self._enable_cache,
                                               enable_scope=self._enable_scope)
        self._cache._cpuinfo = cpuinfo

        # The write-through per-CPU MSR values cache.
        self._cache = _PerCPUCache.PerCPUCache(cpuinfo, enable_cache=self._enable_cache)
        # The transaction buffer. This is a dictionary of dictionaries, where the first key is the
        # CPU number, and the second key is the MSR address. The value is a dictionary with
        # transaction value and additional information.
        self._transaction_buffer: dict[int, dict[int, _TransactionBufferItemTypedDict]] = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_cache",)
        unref_attrs = ("_cpuinfo",)
        ClassHelpers.close(self, close_attrs=close_attrs, unref_attrs=unref_attrs)

        super().close()

    def _add_for_transation(self,
                            regaddr: int,
                            regval: int,
                            cpu: int,
                            verify: bool,
                            iosname: ScopeNameType):
        """
        Add the specified MSR address and value to the transaction buffer for the given
        CPU.

        Args:
            regaddr: The address of the MSR to add.
            regval: The value to write to the MSR.
            cpu: CPU number for which the transaction is being added.
            verify: Whether to verify the MSR value after writing.
            iosname: The I/O scope name associated with the MSR.
        """

        if not self._enable_cache:
            raise Error("Transactions support requires caching to be enabled")

        if cpu not in self._transaction_buffer:
            self._transaction_buffer[cpu] = {}

        if regaddr in self._transaction_buffer[cpu]:
            tinfo = self._transaction_buffer[cpu][regaddr]

            if "iosname" in tinfo and tinfo["iosname"] != iosname:
                raise Error(f"BUG: Inconsistent I/O scope name for MSR {regaddr:#x}:\n"
                            f"  old: {tinfo['iosname']}, new: {iosname}")
            if "verify" in tinfo and tinfo["verify"] != verify:
                raise Error(f"BUG: Inconsistent verification flag value for MSR {regaddr:#x}:\n"
                            f"  old: {tinfo['iosname']}, new: {iosname}")
        else:
            tinfo = self._transaction_buffer[cpu][regaddr] = {}

        tinfo["regval"] = regval
        tinfo["verify"] = verify
        tinfo["iosname"] = iosname

    def start_transaction(self):
        """
        Begin a transaction to cache MSR writes and merge multiple writes to the same MSR.

        When a transaction is active, all writes to MSRs are buffered and only written to hardware
        upon calling 'commit_transaction()' or 'flush_transaction()'. Writes to the same MSR are
        merged into a single operation to minimize I/O overhead. Transactions do not provide
        atomicity or rollback; they are intended solely for optimizing I/O by batching and merging
        writes.
        """

        if not self._enable_cache:
            _LOG.debug("Transactions support requires caching to be enabled")
            return

        if self._in_transaction:
            raise Error("Cannot start a new transaction: A transaction is already in progress")

        self._in_transaction = True

    def _verify(self, regaddr: int, regval: int, cpus: list[int], iosname: ScopeNameType):
        """
        Read an MSR and verify that the read value matches the expected value.

        Args:
            regaddr: The MSR address to read and verify.
            regval: The expected value to verify against.
            cpus: CPU numbers to verify the MSR on.
            iosname: The I/O scope name of the MSR.

        Raises:
            ErrorVerifyFailed: If the value read from the MSR does not match the expected value for
                               any CPU. The 'cpu' attribute of the exception will contain
                               the CPU number where the verification failed, and 'expected' and
                               'actual' attributes will contain the expected and actual values,
                               respectively.
        """

        for cpu in cpus:
            self._cache.remove(regaddr, cpu, sname=iosname)

        for cpu, new_val in self._read(regaddr, cpus, iosname):
            if new_val != regval:
                raise ErrorVerifyFailed(f"Verification failed for MSR '{regaddr:#x}' on CPU {cpu}"
                                        f"{self._pman.hostmsg}:\n  Wrote '{regval:#x}', read back "
                                        f"'{new_val:#x}'", cpu=cpu, expected=regval, actual=new_val)

    def _transaction_write(self):
        """Write the contents of the transaction buffer to MSRs."""

        for cpu, cpus_info in self._transaction_buffer.items():
            # Write all the dirty data.
            path = Path(f"/dev/cpu/{cpu}/msr")
            with self._pman.open(path, "r+b") as fobj:
                for regaddr, regval_info in cpus_info.items():
                    regval = regval_info["regval"]
                    try:
                        fobj.seek(regaddr)
                        regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                        fobj.write(regval_bytes)
                        fobj.flush()
                        _LOG.debug("CPU%d: Commit MSR 0x%x: Wrote 0x%x%s",
                                   cpu, regaddr, regval, self._pman.hostmsg)
                    except Error as err:
                        raise Error(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                                    f"{cpu}{self._pman.hostmsg} (file '{path}'):\n"
                                    f"{err.indent(2)}") from err

    def _transaction_write_remote(self):
        """
        Write MSR transactions on a remote host.

        Generate a small Python script that performs the MSR writes and executes it on the remote
        host.
        """

        python_path = self._pman.get_python_path()

        printer = pprint.PrettyPrinter(compact=True, sort_dicts=False)
        transaction_buffer_str = printer.pformat(self._transaction_buffer)

        # The code passed to "python -c '<code>'" uses single quotes as delimiters.
        # Replace single quotes in the transaction buffer string with double quotes.
        transaction_buffer_str = transaction_buffer_str.replace("'", "\"")

        cmd = f"""{python_path} -c '
transaction_buffer = {transaction_buffer_str}
for cpu, cpus_info in transaction_buffer.items():
    path = "/dev/cpu/%d/msr" % cpu
    with open(path, "r+b") as fobj:
        for regaddr, regval_info in cpus_info.items():
            regval = regval_info["regval"]
            fobj.seek(regaddr)
            regval_bytes = regval.to_bytes({self.regbytes}, byteorder="{_CPU_BYTEORDER}")
            fobj.write(regval_bytes)
            fobj.flush()
'"""

        self._pman.run_verify(cmd)

    def flush_transaction(self) -> bool:
        """
        Flush the transaction buffer and write all buffered data to the MSRs.

        If multiple writes to the same MSR exist, merge them into a single write operation. The
        transaction does not stop after flushing. If verification is requested for any write, verify
        the written values after flushing. Clear the transaction buffer after writing.

        Returns:
            True if there was data to flush and the operation was performed, False if there was no
            transaction data to flush or if caching or transaction mode is disabled.
        """

        if not self._enable_cache:
            return False
        if not self._in_transaction:
            return False
        if not self._transaction_buffer:
            return False

        _LOG.debug("Flushing the MSR transaction buffer")

        if self._pman.is_remote:
            self._transaction_write_remote()
        else:
            self._transaction_write()

        # Form a temporary dictionary for verifying the contents of the MSRs written to by the
        # transaction.
        verify_info: dict[int, dict[int, _TransactionVerifyItemTypedDict]] = {}

        for cpu, cpus_info in self._transaction_buffer.items():
            for regaddr, regval_info in cpus_info.items():
                verify = regval_info["verify"]
                if not verify:
                    continue
                regval = regval_info["regval"]
                if regval not in verify_info:
                    verify_info[regval] = {}
                if regaddr not in verify_info[regval]:
                    verify_info[regval][regaddr] = {"cpus": []}
                verify_info[regval][regaddr]["iosname"] = regval_info["iosname"]
                verify_info[regval][regaddr]["cpus"].append(cpu)

        self._transaction_buffer.clear()

        for regval, regaddr_info in verify_info.items():
            for regaddr, vinfo in regaddr_info.items():
                self._verify(regaddr, regval, vinfo["cpus"], vinfo["iosname"])

        return True

    def commit_transaction(self):
        """
        Commit the current MSR transaction by flushing all buffered data to the MSRs and closing the
        transaction.

        This method does not provide atomicity guarantees; it is intended as an optimization to
        reduce the number of MSR I/O operations.
        """

        if not self._in_transaction:
            raise Error("Cannot commit transaction: no transaction is currently in progress")

        flushed = self.flush_transaction()
        self._in_transaction = False
        if flushed:
            _LOG.debug("MSR transaction has been committed")
        else:
            _LOG.debug("MSR transaction has been committed, but it was empty")

    def _read_remote(self,
                     regaddr: int,
                     cpus: Sequence[int],
                     iosname: ScopeNameType) -> Generator[tuple[int, int], None, None]:
        """
        Read an MSR from a remote host.

        Generate and execute a small Python script on the remote host to read the specified MSR for
        a set of CPUs.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.
            iosname: The name of the I/O scope, used to determine sibling CPUs.

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        if not self._enable_cache:
            yield from super()._cpus_read_remote(regaddr, cpus)
            return


        # CPU numbers to read the MSR for (subset of 'cpus').
        do_read = []
        # CPU numbers the MSR should not be read for. Instead, the MSR values for these CPU numbres
        # are available from the cache, or will be available from the cache when a sibling CPU from
        # 'do_read' is read.
        dont_read = set()

        for cpu in cpus:
            if cpu in dont_read:
                continue

            if self._cache.is_cached(regaddr, cpu):
                dont_read.add(cpu)
                continue

            if not self._enable_scope:
                do_read.append(cpu)
                continue

            # Read the MSR only for 'iosname' sibling CPU, because MSR value should be the same
            # for the siblings.
            for sibling in self._cpuinfo.get_cpu_siblings(cpu, iosname):
                if sibling == cpu:
                    do_read.append(sibling)
                else:
                    dont_read.add(sibling)

        if not do_read:
            for cpu in cpus:
                yield cpu, self._cache.get(regaddr, cpu)
            return

        for cpu, regval in super()._cpus_read_remote(regaddr, do_read):
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        for cpu in cpus:
            regval = self._cache.get(regaddr, cpu)
            yield cpu, regval

    def _read(self,
              regaddr: int,
              cpus: list[int],
              iosname: ScopeNameType) -> Generator[tuple[int, int], None, None]:
        """
        Read the specified MSR from specified CPUs and yield the result. Same as 'read()', but does
        not validate/normalize the 'cpus' argument.
        """

        if self._pman.is_remote:
            yield from self._read_remote(regaddr, cpus, iosname)
            return

        for cpu in cpus:
            if self._cache.is_cached(regaddr, cpu):
                regval = self._cache.get(regaddr, cpu)
            else:
                regval = super().cpu_read(regaddr, cpu)
                self._cache.add(regaddr, cpu, regval, sname=iosname)
            yield cpu, regval

    def read(self,
             regaddr: int,
             cpus: Sequence[int] | Literal["all"] = "all",
             iosname: ScopeNameType = "CPU") -> Generator[tuple[int, int], None, None]:
        """
        Read the specified MSR from specified CPUs and yield the result.

        Args:
            regaddr: Address of the MSR to read.
            cpus: CPU numbers to read the MSR from. Special value 'all' means "all CPUs".
            iosname: Scope name for the MSR (e.g. "package", "core"). This is used for
                     optimizing the read operation by skipping unnecessary reads of sibling CPUs.

        Yields:
            Tuple of (cpu, regval):
                cpu: CPU number from which the MSR was read.
                regval: Value read from the MSR.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        yield from self._read(regaddr, cpus, iosname)

    def read_cpu(self, regaddr, cpu, iosname="CPU"):
        """
        Read an MSR value from a specific CPU.

        Args:
            regaddr: Address of the MSR to read.
            cpu: The CPU number to read the MSR from.
            iosname: Scope name for the MSR (e.g. "package", "core").

        Returns:
            The value read from the specified MSR on the given CPU.
        """

        regval = None
        for _, regval in self.read(regaddr, cpus=(cpu,), iosname=iosname):
            pass

        return regval

    def read_bits(self,
                  regaddr: int,
                  bits: tuple[int, int] | list[int],
                  cpus: Sequence[int] | Literal["all"] = "all",
                  iosname: ScopeNameType = "CPU") -> Generator[tuple[int, int], None, None]:
        """
        Read specific bits from an MSR for specified CPUs and yield results.

        Args:
            regaddr: Address of the MSR to read bits from.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to extract
                  from the MSR; msb is the most significant bit and lsb is the least significant
                  bit.
            cpus: CPU numbers to read the MSR from. Special value 'all' means "all CPUs".
            iosname: Scope name for the MSR (e.g. "package", "core"). This is used for
                     optimizing the read operation by skipping unnecessary reads of sibling CPUs.

        Yields:
            tuple: A tuple (cpu, val), where:
                cpu: The CPU number the MSR was read from.
                val: The value of the specified bits from the MSR.
        """

        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            _LOG.debug("CPU%d: MSR 0x%x: Bits %s: Read 0x%x%s", cpu, regaddr,
                       ":".join([str(bit) for bit in bits]), self.get_bits(regval, bits),
                       self._pman.hostmsg)
            yield (cpu, self.get_bits(regval, bits))

    def read_cpu_bits(self,
                      regaddr: int,
                      bits: tuple[int, int] | list[int],
                      cpu: int,
                      iosname: ScopeNameType = "CPU") -> int:
        """
        Read specific bits from an MSR for a specific CPU.

        Args:
            regaddr: Address of the MSR to read from.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to extract
                  from the MSR; msb is the most significant bit and lsb is the least significant
                  bit.
            cpu: CPU number to read the MSR from.
            iosname: Scope name for the MSR (e.g. "package", "core").

        Returns:
            Value of the requested bits from the MSR.
        """

        regval = self.read_cpu(regaddr, cpu, iosname=iosname)
        return self.get_bits(regval, bits)

    def _write_remote(self,
                      regaddr: int,
                      regval: int,
                      cpus: list[int],
                      iosname: ScopeNameType = "CPU",
                      verify: bool = False):
        """
        Write a value to an MSR on specified CPUs on a remote host.

        Generate and execute a small Python script on the remote host to write the specified MSR for
        a set of CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on.
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailed: If verification is enabled and the read-back value does not match the
                               written value. The 'cpu' attribute of the exception will contain the
                               CPU number where the verification failed, and 'expected' and 'actual'
                               attributes will contain the expected and actual values, respectively.
        """

        if not self._enable_cache:
            super()._cpus_write_remote(regaddr, regval, cpus)
            return

        # CPU numbers to write the MSR on (subset of 'cpus').
        do_write = []
        # CPU numbers to skip writing the MSR on.
        dont_write = set()

        for cpu in cpus:
            if cpu in dont_write:
                continue

            if self._cache.is_cached(regaddr, cpu):
                _regval = self._cache.get(regaddr, cpu)
                if _regval == regval:
                    dont_write.add(cpu)
                    continue

            if not self._enable_scope:
                do_write.append(cpu)
                continue

            # Write the MSR only on 'iosname' sibling CPU, because MSR value should be the same
            # for the siblings.
            for sibling in self._cpuinfo.get_cpu_siblings(cpu, iosname):
                if sibling == cpu:
                    do_write.append(sibling)
                else:
                    dont_write.add(sibling)

        if not do_write:
            return

        super()._cpus_write_remote(regaddr, regval, do_write)

        for cpu in do_write:
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if verify and not self._in_transaction:
            self._verify(regaddr, regval, cpus, iosname)

    def _write(self,
               regaddr: int,
               regval: int,
               cpus: list[int],
               iosname: ScopeNameType = "CPU",
               verify: bool = False):
        """
        Write a value to an MSR on specified CPUs. Same as 'write()', but does not
        validate/normalize the 'cpus' argument.
        """

        if self._pman.is_remote and not self._in_transaction:
            self._write_remote(regaddr, regval, cpus, iosname=iosname, verify=verify)
            return

        for cpu in cpus:
            self._cache.remove(regaddr, cpu, sname=iosname)

        # Removing 'cpus' from the cache will make sure the following '_cache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_cache.add()'
        # method.
        for cpu in cpus:
            if self._cache.is_cached(regaddr, cpu):
                continue

            if not self._in_transaction:
                super().cpu_write(regaddr, regval, cpu)
            else:
                self._add_for_transation(regaddr, regval, cpu, verify, iosname)

            # Note, below 'add()' call is scope-aware. It will cache 'regval' not only for CPU
            # number 'cpu', but also for all the 'iosname' siblings. For example, if 'iosname' is
            # "package", 'regval' will be cached for all CPUs in the package that contains CPU
            # number 'cpu'.
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if verify and not self._in_transaction:
            self._verify(regaddr, regval, cpus, iosname)

    def write(self,
              regaddr: int,
              regval: int,
              cpus: Sequence[int] | Literal["all"] = "all",
              iosname: ScopeNameType = "CPU",
              verify: bool = False):
        """
        Write a value to an MSR on specified CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on. Special value 'all' means "all CPUs".
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailed: If verification is enabled and the read-back value does not match the
                               written value. The 'cpu' attribute of the exception will contain the
                               CPU number where the verification failed, and 'expected' and 'actual'
                               attributes will contain the expected and actual values, respectively.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        self._write(regaddr, regval, cpus, iosname=iosname, verify=verify)

    def write_cpu(self,
                  regaddr: int,
                  regval: int,
                  cpu: int,
                  iosname: ScopeNameType = "CPU",
                  verify: bool = False):
        """
        Write a value to an MSR on a specific CPU.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpu: CPU number to write the MSR on.
            iosname: The I/O scope name of the MSR.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailed: If verification is enabled and the read-back value does not match the
                               written value.
        """

        self.write(regaddr, regval, cpus=(cpu,), iosname=iosname, verify=verify)

    def write_bits(self,
                   regaddr: int,
                   bits: tuple[int, int] | list[int],
                   val: int,
                   cpus: Sequence[int] | Literal["all"] = "all",
                   iosname: ScopeNameType = "CPU",
                   verify: bool = False):
        """
        Write a value to specific bits of an MSR on one or more CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to to write
                  to; msb is the most significant bit and lsb is the least significant bit.
            val: The value to write to the specified bits range.
            cpus: CPU numbers to write the MSR on. Special value 'all' means "all CPUs".
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailed: If verification is enabled and the read-back value does not match the
                               written value. The 'cpu' attribute of the exception will contain the
                               CPU number where the verification failed, and 'expected' and 'actual'
                               attributes will contain the expected and actual values, respectively.
        """

        regvals: dict[int, list[int]] = {}

        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            new_regval = self.set_bits(regval, bits, val)
            _LOG.debug("CPU %d: MSR 0x%x: Set bits %s to 0x%x: Current MSR value: 0x%x%s, "
                       "new value: 0x%x", cpu, regaddr, ":".join([str(bit) for bit in bits]),
                       val, regval, self._pman.hostmsg, new_regval)
            if regval == new_regval:
                _LOG.debug("CPU %d: MSR 0x%x: No change, skipping writing", cpu, regaddr)
                continue

            if new_regval not in regvals:
                regvals[new_regval] = []
            regvals[new_regval].append(cpu)

        for regval, regval_cpus in regvals.items():
            try:
                self._write(regaddr, regval, regval_cpus, iosname=iosname, verify=verify)
            except Error as err:
                errmsg = err.indent(2)
                cpus_str = ",".join([str(cpu) for cpu in regval_cpus])
                bits_str = ":".join([str(bit) for bit in bits])
                raise type(err)(f"Failed to set bits {bits_str} of MSR 0x{regaddr:x} to value "
                                f"0x{val:x} on CPUs {cpus_str}{self._pman.hostmsg}:\n"
                                f"{errmsg}") from err

    def write_cpu_bits(self,
                       regaddr: int,
                       bits: tuple[int, int] | list[int],
                       val: int,
                       cpu: int,
                       iosname: ScopeNameType = "CPU",
                       verify: bool = False):
        """
        Write a value to specific bits of an MSR on a specific CPU.

        Args:
            regaddr: The address of the MSR to write to.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to to write
                  to; msb is the most significant bit and lsb is the least significant bit.
            val: The value to write to the specified bits range.
            cpu: CPU number to write the MSR on.
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailed: If verification is enabled and the read-back value does not match the
                               written value.
        """

        self.write_bits(regaddr, bits, val, cpus=(cpu,), iosname=iosname, verify=verify)
