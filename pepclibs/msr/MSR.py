# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>

"""
Provide a capability to read and write CPU Model Specific Registers, including write-through caching
and transactions support.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import typing
import pprint
from pathlib import Path
from pepclibs import _PerCPUCache
from pepclibs.helperlibs import ClassHelpers, Trivial, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorPerCPUPath, ErrorVerifyFailedPerCPUPath
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied
from pepclibs.msr import _SimpleMSR
from pepclibs.msr._SimpleMSR import _CPU_BYTEORDER

if typing.TYPE_CHECKING:
    from typing import cast, Generator, TypedDict, Sequence
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
    Provide API for reading and writing CPU Model Specific Registers with caching and transactions.

    Public methods overview.

    1. Multi-CPU I/O.
        - 'read()' - read an MSR.
        - 'read_bits()' - read an MSR bits range.
        - 'write()' - write to an MSR.
        - 'write_bits()' - write MSR bits range.
    2. Single-CPU I/O.
        - 'read_cpu()' - read an MSR.
        - 'read_cpu_bits()' - read an MSR bits range.
        - 'write_cpu()' - write to an MSR.
        - 'write_cpu_bits()' - write MSR bits range.
    3. Transactions support.
        - 'start_transaction()' - start a transaction.
        - 'flush_transaction()' - flush the transaction buffer.
        - 'commit_transaction()' - commit the transaction.
    4. Miscellaneous.
        - 'get_bits()' - get bits range from a user-provided MSR value.
        - 'set_bits()' - set bits range from a user-provided MSR value.
        - 'close()' - uninitialize the class object.

    Notes:
        - Methods do not validate the 'cpus' argument. The caller must validate CPU numbers.
        - Implementation is not thread-safe, intended for single-threaded applications.
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
                          cache and propagate to hardware immediately (write-through policy). If
                          False, caching is disabled, and every read/write operation accesses the
                          hardware directly.

        Raises:
            ErrorPermissionDenied: No permissions to access MSRs.
            ErrorNotSupported: MSR access is not supported.
        """

        super().__init__(pman=pman)

        self._cpuinfo = cpuinfo
        self._enable_cache = enable_cache
        self._enable_scope = True

        if typing.TYPE_CHECKING:
            # Suppress "self._pman may not be initialized" type checker warning for the following
            # code - it is initialized by the parent class constructor.
            assert pman is not None

        if pman.is_emulated:
            # The emulation layer does not support MSR scope, so disable the scope optimization, and
            # make sure writes go to all CPUs, not just one CPU in the scope.
            self._enable_scope = False

        # The write-through per-CPU MSR values cache.
        self._cache = _PerCPUCache.PerCPUCache(cpuinfo, enable_cache=self._enable_cache,
                                               enable_scope=self._enable_scope)

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

    def _add_for_transaction(self,
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

        if cpu not in self._transaction_buffer:
            self._transaction_buffer[cpu] = {}

        if regaddr in self._transaction_buffer[cpu]:
            tinfo = self._transaction_buffer[cpu][regaddr]

            if "iosname" in tinfo and tinfo["iosname"] != iosname:
                raise Error(f"BUG: Inconsistent I/O scope name for MSR {regaddr:#x}:\n"
                            f"  old: {tinfo['iosname']}, new: {iosname}")
            if "verify" in tinfo and tinfo["verify"] != verify:
                raise Error(f"BUG: Inconsistent verification flag value for MSR {regaddr:#x}:\n"
                            f"  old: {tinfo['verify']}, new: {verify}")
        else:
            if typing.TYPE_CHECKING:
                _empty_dict = cast(_TransactionBufferItemTypedDict, {})
            else:
                _empty_dict = {}
            tinfo = self._transaction_buffer[cpu][regaddr] = _empty_dict

        tinfo["regval"] = regval
        tinfo["verify"] = verify
        tinfo["iosname"] = iosname

    def start_transaction(self):
        """
        Begin a transaction to cache MSR writes and merge multiple writes to the same MSR.

        When a transaction is active, all writes to MSRs are buffered and only written to hardware
        upon calling 'commit_transaction()' or 'flush_transaction()'. Writes to the same MSR are
        merged into a single operation to minimize I/O overhead. Transactions do not provide
        atomicity or rollback. They are intended solely for optimizing I/O by batching and merging
        writes.
        """

        if not self._enable_cache:
            _LOG.debug("Transactions support requires caching to be enabled")
            return

        if self._in_transaction:
            raise Error("Cannot start a new transaction: A transaction is already in progress")

        self._in_transaction = True

    def _verify(self, regaddr: int, regval: int, cpus: Sequence[int], iosname: ScopeNameType):
        """
        Read an MSR and verify that the read value matches the expected value.

        Args:
            regaddr: The MSR address to read and verify.
            regval: The expected value to verify against.
            cpus: CPU numbers to verify the MSR on.
            iosname: The I/O scope name of the MSR.

        Raises:
            ErrorVerifyFailedPerCPUPath: The value read from the MSR does not match the expected
                                         value for any CPU. The exception contains the CPU
                                         number, expected and actual values, and the MSR device
                                         path.
        """

        for cpu in cpus:
            self._cache.remove(regaddr, cpu, sname=iosname)

        for cpu, new_val in self.read(regaddr, cpus, iosname=iosname):
            if new_val != regval:
                path = self.format_msr_device_path(cpu)
                raise ErrorVerifyFailedPerCPUPath(f"Verification failed for MSR '{regaddr:#x}' on "
                                                  f"CPU {cpu}{self._pman.hostmsg}:\n  "
                                                  f"Wrote '{regval:#x}', read back '{new_val:#x}'",
                                                  cpu=cpu, expected=regval, actual=new_val,
                                                  path=path)

    def _transaction_write_local(self):
        """Write MSR transactions on a local host."""

        for cpu, cpus_info in self._transaction_buffer.items():
            path = self.format_msr_device_path(cpu)
            try:
                with open(path, "r+b") as fobj:
                    for regaddr, regval_info in cpus_info.items():
                        regval = regval_info["regval"]
                        _LOG.debug("Transaction: Local: Write: CPU%d: MSR 0x%x: 0x%x to '%s'%s",
                                   cpu, regaddr, regval, path, self._pman.hostmsg)
                        try:
                            regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                            os.pwrite(fobj.fileno(), regval_bytes, regaddr)
                        except PermissionError as err:
                            errmsg = Error(str(err)).indent(2)
                            raise ErrorPermissionDenied(f"No permissions to write '{regval:#x}' to "
                                                        f"MSR '{regaddr:#x}' of CPU {cpu}"
                                                        f"{self._pman.hostmsg} (file '{path}'):\n"
                                                        f"{errmsg}") from err
                        except OSError as err:
                            errmsg = Error(str(err)).indent(2)
                            raise ErrorPerCPUPath(f"Failed to write '{regval:#x}' to MSR "
                                                  f"'{regaddr:#x}' of CPU {cpu}"
                                                  f"{self._pman.hostmsg} (file '{path}'):\n"
                                                  f"{errmsg}", cpu=cpu, path=path) from err
            except PermissionError as err:
                errmsg = Error(str(err)).indent(2)
                raise ErrorPermissionDenied(f"No permissions to write to MSR of CPU {cpu}"
                                            f"{self._pman.hostmsg} (file '{path}'):\n"
                                            f"{errmsg}") from err

    def _transaction_write_optimized(self, su: bool = False):
        """
        Write MSR transactions using optimized I/O.

        Generate a small Python script that performs the MSR writes in a single operation, instead
        of opening each MSR device file individually.

        Args:
            su: If 'True', run the script as superuser (root).
        """

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            for cpu, cpus_info in self._transaction_buffer.items():
                for regaddr, regval_info in cpus_info.items():
                    regval = regval_info["regval"]
                    _LOG.debug("Transaction: Optimized: Write: CPU%d: MSR 0x%x: 0x%x%s",
                               cpu, regaddr, regval, self._pman.hostmsg)

        python_path = self._pman.get_python_path()

        printer = pprint.PrettyPrinter(compact=True, sort_dicts=False)
        transaction_buffer_str = printer.pformat(self._transaction_buffer)

        # The code passed to "python -c '<code>'" uses single quotes as delimiters.
        # Replace single quotes in the transaction buffer string with double quotes.
        transaction_buffer_str = transaction_buffer_str.replace("'", "\"")

        cmd = f"""{python_path} -c '
import os
transaction_buffer = {transaction_buffer_str}
for cpu, cpus_info in transaction_buffer.items():
    path = "/dev/cpu/%d/msr" % cpu
    try:
        with open(path, "r+b") as fobj:
            for regaddr, regval_info in cpus_info.items():
                regval = regval_info["regval"]
                regval_bytes = regval.to_bytes({self.regbytes}, byteorder="{_CPU_BYTEORDER}")
                os.pwrite(fobj.fileno(), regval_bytes, regaddr)
    except PermissionError as err:
        print("ERROR: Permission: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
    except Exception as err:
        print("ERROR: Write: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
'"""

        _LOG.debug("Transaction: Optimized: Write: Executing command%s", self._pman.hostmsg)

        regex = re.compile(r"ERROR: (Permission|Write): CPU: (\d+): Path: (.+): Error: (.+)")

        stdout, _ = self._pman.run_verify_join(cmd, su=su)
        for line in stdout.splitlines():
            if not line.startswith("ERROR: "):
                continue

            mobj = regex.match(line)
            if not mobj:
                raise Error(f"Failed to parse MSR transaction write error:\n{line}")

            errtype = mobj.group(1)
            cpu = Trivial.str_to_int(mobj.group(2), what="CPU number")
            path = Path(mobj.group(3))
            errmsg = Error(mobj.group(4)).indent(2)

            if errtype == "Permission":
                raise ErrorPermissionDenied(f"No permissions to write to MSR of CPU {cpu}"
                                            f"{self._pman.hostmsg} (file '{path}'):\n{errmsg}")
            raise ErrorPerCPUPath(f"MSR transaction write failed for CPU {cpu} "
                                  f"{self._pman.hostmsg} (file '{path}'):\n{errmsg}",
                                  cpu=cpu, path=path)

    def _transaction_write_emulation(self):
        """Write MSR transactions on an emulated host."""

        for cpu, cpus_info in self._transaction_buffer.items():
            path = self.format_msr_device_path(cpu)
            with self._pman.openb(path, "r+") as fobj:
                for regaddr, regval_info in cpus_info.items():
                    regval = regval_info["regval"]
                    _LOG.debug("Transaction: Emulation: Write: CPU%d: MSR 0x%x: 0x%x to '%s'%s",
                               cpu, regaddr, regval, path, self._pman.hostmsg)
                    try:
                        fobj.seek(regaddr)
                        regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                        fobj.write(regval_bytes)
                        fobj.flush()
                    except ErrorPermissionDenied as err:
                        raise type(err)(f"No permissions to write '{regval:#x}' to "
                                        f"MSR '{regaddr:#x}' of CPU {cpu}"
                                        f"{self._pman.hostmsg} (file '{path}'):\n"
                                        f"{err.indent(2)}") from err
                    except Error as err:
                        raise ErrorPerCPUPath(f"Failed to write '{regval:#x}' to MSR "
                                              f"'{regaddr:#x}' of CPU {cpu}{self._pman.hostmsg} "
                                              f"(file '{path}'):\n{err.indent(2)}",
                                              cpu=cpu, path=path) from err

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

        if self._pman.is_remote or self._use_sudo:
            self._transaction_write_optimized(su=self._use_sudo)
        elif self._pman.is_emulated:
            self._transaction_write_emulation()
        else:
            self._transaction_write_local()

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

        This method does not provide atomicity guarantees. It is intended as an optimization to
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

    def _read_optimized(self,
                        regaddr: int,
                        cpus: Sequence[int],
                        iosname: ScopeNameType) -> Generator[tuple[int, int], None, None]:
        """
        Read an MSR using optimized I/O.

        Execute a Python script in a single operation to read the specified MSR for a set of CPUs,
        instead of opening each MSR device file individually. Also implements scope-aware caching
        to skip unnecessary reads of sibling CPUs.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.
            iosname: The name of the I/O scope, used to determine sibling CPUs.

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        if not self._enable_cache:
            yield from super()._cpus_read_optimized(regaddr, cpus, su=self._use_sudo)
            return

        # CPU numbers to read the MSR for (subset of 'cpus').
        do_read = []
        # CPU numbers the MSR should not be read for. Instead, the MSR values for these CPU numbers
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

            # Read only one CPU per 'iosname' scope, because sibling CPUs share the same MSR value.
            for sibling in self._cpuinfo.get_cpu_siblings(cpu, iosname):
                if sibling == cpu:
                    do_read.append(sibling)
                else:
                    dont_read.add(sibling)

        if not do_read:
            for cpu in cpus:
                _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)
                regval = self._cache.get(regaddr, cpu)
                yield cpu, regval
            return

        for cpu, regval in super()._cpus_read_optimized(regaddr, do_read, su=self._use_sudo):
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        for cpu in cpus:
            regval = self._cache.get(regaddr, cpu)
            if cpu in dont_read:
                _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)
            yield cpu, regval

    def read(self,
             regaddr: int,
             cpus: Sequence[int],
             iosname: ScopeNameType = "CPU") -> Generator[tuple[int, int], None, None]:
        """
        Read the specified MSR from specified CPUs and yield the result.

        Args:
            regaddr: Address of the MSR to read.
            cpus: CPU numbers to read the MSR from (the caller must validate CPU numbers).
            iosname: Scope name for the MSR (e.g. "package", "core"). This is used for optimizing
                     the read operation by skipping unnecessary reads of sibling CPUs.

        Yields:
            Tuple of (cpu, regval):
                cpu: CPU number from which the MSR was read.
                regval: Value read from the MSR.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        if self._pman.is_remote or self._use_sudo:
            yield from self._read_optimized(regaddr, cpus, iosname)
            return

        for cpu in cpus:
            if self._cache.is_cached(regaddr, cpu):
                _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)
                regval = self._cache.get(regaddr, cpu)
            else:
                regval = super().cpu_read(regaddr, cpu)
                self._cache.add(regaddr, cpu, regval, sname=iosname)
            yield cpu, regval

    def read_cpu(self, regaddr: int, cpu: int, iosname: ScopeNameType = "CPU") -> int:
        """
        Read an MSR value from a specific CPU.

        Args:
            regaddr: Address of the MSR to read.
            cpu: The CPU number to read the MSR from (the caller must validate CPU number).
            iosname: Scope name for the MSR (e.g. "package", "core").

        Returns:
            The value read from the specified MSR on the given CPU.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        for _, regval in self.read(regaddr, (cpu,), iosname=iosname):
            return regval

        path = self.format_msr_device_path(cpu)
        raise ErrorPerCPUPath(f"Failed to read MSR 0x{regaddr:x} from CPU {cpu}"
                              f"{self._pman.hostmsg}", cpu=cpu, path=path)

    def read_bits(self,
                  regaddr: int,
                  bits: tuple[int, int] | list[int],
                  cpus: Sequence[int],
                  iosname: ScopeNameType = "CPU") -> Generator[tuple[int, int], None, None]:
        """
        Read specific bits from an MSR for specified CPUs and yield results.

        Args:
            regaddr: Address of the MSR to read bits from.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to extract
                  from the MSR, where msb is the most significant bit and lsb is the least
                  significant bit.
            cpus: CPU numbers to read the MSR from (the caller must validate CPU numbers).
            iosname: Scope name for the MSR (e.g. "package", "core"). This is used for optimizing
                     the read operation by skipping unnecessary reads of sibling CPUs.

        Yields:
            tuple: A tuple (cpu, val), where:
                cpu: The CPU number the MSR was read from.
                val: The value of the specified bits from the MSR.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            val = self.get_bits(regval, bits)
            _LOG.debug("CPU%d: MSR 0x%x: Bits %s: Read 0x%x%s",
                       cpu, regaddr, ":".join([str(bit) for bit in bits]), val,
                       self._pman.hostmsg)
            yield cpu, val

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
                  from the MSR, where msb is the most significant bit and lsb is the least
                  significant bit.
            cpu: CPU number to read the MSR from (the caller must validate CPU number).
            iosname: Scope name for the MSR (e.g. "package", "core").

        Returns:
            Value of the requested bits from the MSR.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        regval = self.read_cpu(regaddr, cpu, iosname=iosname)
        return self.get_bits(regval, bits)

    def _write_optimized(self,
                         regaddr: int,
                         regval: int,
                         cpus: Sequence[int],
                         iosname: ScopeNameType = "CPU",
                         verify: bool = False):
        """
        Write a value to an MSR using optimized I/O.

        Execute a Python script in a single operation to write the specified MSR for a set of CPUs,
        instead of opening each MSR device file individually. Also implements scope-aware caching
        to skip unnecessary writes to sibling CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on.
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorVerifyFailedPerCPUPath: Verification is enabled and the read-back value does not
                                         match the written value. The 'cpu' attribute of the
                                         exception will contain the CPU number where the
                                         verification failed, and 'expected' and 'actual'
                                         attributes will contain the expected and actual values,
                                         respectively.
        """

        if not self._enable_cache:
            super()._cpus_write_optimized(regaddr, regval, cpus, su=self._use_sudo)
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

            # Write only one CPU per 'iosname' scope, because sibling CPUs share the same MSR value.
            for sibling in self._cpuinfo.get_cpu_siblings(cpu, iosname):
                if sibling == cpu:
                    do_write.append(sibling)
                else:
                    dont_write.add(sibling)

        if not do_write:
            return

        super()._cpus_write_optimized(regaddr, regval, do_write, su=self._use_sudo)

        for cpu in do_write:
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        for cpu in cpus:
            if cpu in dont_write:
                _LOG.debug("Cached: Write skipped: CPU%d: MSR 0x%x: 0x%x (value matches)%s",
                           cpu, regaddr, regval, self._pman.hostmsg)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if verify and not self._in_transaction:
            self._verify(regaddr, regval, cpus, iosname)

    def write(self,
              regaddr: int,
              regval: int,
              cpus: Sequence[int],
              iosname: ScopeNameType = "CPU",
              verify: bool = False):
        """
        Write a value to an MSR on specified CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on (the caller must validate CPU numbers).
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while writing to the MSR (includes CPU and path
                             information).
            ErrorVerifyFailedPerCPUPath: Verification is enabled and the read-back value does not
                                         match the written value. The 'cpu' attribute of the
                                         exception will contain the CPU number where the
                                         verification failed, and 'expected' and 'actual'
                                         attributes will contain the expected and actual values,
                                         respectively.
        """

        if (self._pman.is_remote or self._use_sudo) and not self._in_transaction:
            self._write_optimized(regaddr, regval, cpus, iosname=iosname, verify=verify)
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
                self._add_for_transaction(regaddr, regval, cpu, verify, iosname)
                _LOG.debug("Transaction: Buffered: CPU%d: MSR 0x%x: 0x%x%s",
                           cpu, regaddr, regval, self._pman.hostmsg)

            # The '_cache.add()' call below is scope-aware: it caches 'regval' not only for CPU
            # 'cpu', but also for all its 'iosname' siblings. For example, if 'iosname' is
            # "package", 'regval' is cached for all CPUs in the package containing CPU 'cpu'.
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        # In case of an ongoing transaction, skip the verification, it'll be done at the end of the
        # transaction.
        if verify and not self._in_transaction:
            self._verify(regaddr, regval, cpus, iosname)

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
            cpu: CPU number to write the MSR on (the caller must validate CPU number).
            iosname: The I/O scope name of the MSR.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while writing to the MSR (includes CPU and path
                             information).
            ErrorVerifyFailedPerCPUPath: Verification is enabled and the read-back value does not
                                         match the written value.
        """

        self.write(regaddr, regval, (cpu,), iosname=iosname, verify=verify)

    def write_bits(self,
                   regaddr: int,
                   bits: tuple[int, int] | list[int],
                   val: int,
                   cpus: Sequence[int],
                   iosname: ScopeNameType = "CPU",
                   verify: bool = False):
        """
        Write a value to specific bits of an MSR on one or more CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to write to;
                  msb is the most significant bit and lsb is the least significant bit.
            val: The value to write to the specified bits range.
            cpus: CPU numbers to write the MSR on (the caller must validate CPU numbers).
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading or writing the MSR (includes CPU
                             and path information).
            ErrorVerifyFailedPerCPUPath: Verification is enabled and the read-back value does not
                                         match the written value. The 'cpu' attribute of the
                                         exception will contain the CPU number where the
                                         verification failed, and 'expected' and 'actual'
                                         attributes will contain the expected and actual values,
                                         respectively.
        """

        regvals: dict[int, list[int]] = {}

        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            new_regval = self.set_bits(regval, bits, val)
            _LOG.debug("CPU %d: MSR 0x%x: Set bits %s to 0x%x: Current MSR value: 0x%x%s, "
                       "new value: 0x%x",
                       cpu, regaddr, ":".join([str(bit) for bit in bits]), val, regval,
                       self._pman.hostmsg, new_regval)
            if regval == new_regval:
                _LOG.debug("CPU %d: MSR 0x%x: No change, skipping writing", cpu, regaddr)
                continue

            if new_regval not in regvals:
                regvals[new_regval] = []
            regvals[new_regval].append(cpu)

        for regval, regval_cpus in regvals.items():
            try:
                self.write(regaddr, regval, regval_cpus, iosname=iosname, verify=verify)
            except Error as err:
                cpus_str = ",".join([str(cpu) for cpu in regval_cpus])
                bits_str = ":".join([str(bit) for bit in bits])
                raise type(err)(f"Failed to set bits {bits_str} of MSR 0x{regaddr:x} to value "
                                f"0x{val:x} on CPUs {cpus_str}{self._pman.hostmsg}:\n"
                                f"{err.indent(2)}") from err

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
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to write to;
                  msb is the most significant bit and lsb is the least significant bit.
            val: The value to write to the specified bits range.
            cpu: CPU number to write the MSR on (the caller must validate CPU number).
            iosname: I/O scope name for the MSR address (e.g., "package", "core"). Used for
                     optimizing the write operation by avoiding writing to sibling CPUs.
            verify: If True, read back and verify the written value.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading or writing the MSR (includes CPU
                             and path information).
            ErrorVerifyFailedPerCPUPath: Verification is enabled and the read-back value does not
                                         match the written value.
        """

        self.write_bits(regaddr, bits, val, (cpu,), iosname=iosname, verify=verify)
