# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability to read and write CPU Model Specific Registers.
"""

import pprint
from pathlib import Path
from pepclibs.helperlibs import Logging, LocalProcessManager, FSHelpers, KernelModule, Trivial
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorVerifyFailed, ErrorNotFound
from pepclibs import _PerCPUCache

_CPU_BYTEORDER = "little"

# A special value which can be used to specify that all bits have to be set to "1" in methods like
# 'write_bits()'.
ALL_BITS_1 = object()

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class MSR(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and write CPU Model Specific Registers.

    Public methods overview.

    1. Multi-CPU I/O.
        * 'read()' - read an MSR.
        * 'read_bits()'  - read an MSR bits range.
        * 'write()' - write to the an MSR.
        * 'write_bits()'  - write MSR bits range.
    2. Single-CPU I/O.
        * 'read_cpu()' - read an MSR.
        * 'read_cpu_bits()'  - read an MSR bits range.
        * 'write_cpu()' - write to the an MSR.
        * 'write_cpu_bits()'  - write MSR bits range.
    3. Transactions support.
        * 'start_transaction()' - start a transaction.
        * 'flush_transaction()' - flush the transaction buffer.
        * 'commit_transaction()' - commit the transaction.
    4. Miscellaneous.
        * 'get_bits()' - get bits range from a user-provided MSR value.
        * 'set_bits()' - set bits range from a user-provided MSR value.
    """

    def _add_for_transation(self, regaddr, regval, cpu, verify, iosname):
        """Add CPU 'cpu' MSR at 'regaddr' with its value 'regval' to the transaction buffer."""

        if not self._enable_cache:
            raise Error("transactions support requires caching to be enabled, see 'enable_cache' "
                        "argument of the 'MSR.MSR()' constructor")

        if cpu not in self._transaction_buffer:
            self._transaction_buffer[cpu] = {}

        if regaddr not in self._transaction_buffer[cpu]:
            self._transaction_buffer[cpu][regaddr] = {}

        tinfo = self._transaction_buffer[cpu][regaddr] = {}

        if "iosname" in tinfo and tinfo["iosname"] != iosname:
            raise Error(f"BUG: inconsistent I/O scope name for MSR {regaddr:#x}:\n"
                        f"  old: {tinfo['iosname']}, new: {iosname}.")
        if "verify" in tinfo and tinfo["verify"] != verify:
            raise Error(f"BUG: inconsistent verification flag value for MSR {regaddr:#x}:\n"
                        f"  old: {tinfo['iosname']}, new: {iosname}.")

        tinfo["regval"] = regval
        tinfo["verify"] = verify
        tinfo["iosname"] = iosname

    def start_transaction(self):
        """
        Start transaction. All writes to MSRs will be cached, and will only be written to the actual
        hardware on 'commit_transaction()' or 'flush_transaction(). Writes to the same MSRs will be
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

    def _verify(self, regaddr, regval, cpus, iosname):
        """Read MSR 'regaddr' for CPUs in 'cpus' and verify that it's value is 'regval'."""

        for cpu in cpus:
            self._cache.remove(regaddr, cpu, sname=iosname)

        for cpu, new_val in self._read(regaddr, cpus, iosname):
            if new_val != regval:
                raise ErrorVerifyFailed(f"verification failed for MSR '{regaddr:#x}' on CPU {cpu}"
                                        f"{self._pman.hostmsg}:\n  wrote '{regval:#x}', read back "
                                        f"'{new_val:#x}'", cpu=cpu, expected=regval, actual=new_val)

    def _transaction_write(self):
        """Write the contents of the transaction buffer to the MSRs."""

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
                        _LOG.debug("CPU%d: commit MSR 0x%x: wrote 0x%x%s",
                                   cpu, regaddr, regval, self._pman.hostmsg)
                    except Error as err:
                        raise Error(f"failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                                    f"{cpu}{self._pman.hostmsg} (file '{path}'):\n"
                                    f"{err.indent(2)}") from err

    def _transaction_write_remote_optimized(self):
        """
        An optmimized implementation of transaction '_transaction_write()' for a remote host.

        Observation: opening and writing to multiple remote '/dev/msr/{cpu}' files from the local
        system is significantly slower than running a script on the remote system and having the
        script open/write to the files.

        Optimized solution: generate a small python script that writes to the MSRs and run it on the
        remote host.
        """

        python_path = self._pman.get_python_path()

        printer = pprint.PrettyPrinter(compact=True, sort_dicts=False)
        transaction_buffer_str = printer.pformat(self._transaction_buffer)

        # Single quotes are used for the as the code delimiters in "python -c '<code>'". Replace
        # them with double quotes.
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

    def flush_transaction(self):
        """
        Flush the transaction buffer. Write all the buffered data to the MSRs. If there are multiple
        writes to the same MSR, they will be merged into a single write operation. The transaction
        does not stop after flushing. Return 'True' if there was something to flush, return 'False'
        if there was not taransaction data to flush.
        """

        if not self._enable_cache:
            return False
        if not self._in_transaction:
            return False
        if not self._transaction_buffer:
            return False

        _LOG.debug("flushing MSR transaction buffer")

        if self._pman.is_remote and len(self._transaction_buffer) > 1:
            self._transaction_write_remote_optimized()
        else:
            self._transaction_write()

        # Form a temporary dictionary for verifying the contents of the MSRs written to by the
        # transaction.
        verify_info = {}
        for cpu, cpus_info in self._transaction_buffer.items():
            for regaddr, regval_info in cpus_info.items():
                verify = regval_info["verify"]
                if not verify:
                    continue
                regval = regval_info["regval"]
                if regval not in verify_info:
                    verify_info[regval] = {}
                if regaddr not in verify_info[regval]:
                    verify_info[regval][regaddr] = {"iosname": None, "cpus": []}
                verify_info[regval][regaddr]["iosname"] = regval_info["iosname"]
                verify_info[regval][regaddr]["cpus"].append(cpu)

        self._transaction_buffer.clear()

        for regval, regaddr_info in verify_info.items():
            for regaddr, cpus_info in regaddr_info.items():
                self._verify(regaddr, regval, cpus_info["cpus"], cpus_info["iosname"])

        return True

    def commit_transaction(self):
        """
        Commit the transaction. Write all the buffered data to MSRs and close the transaction. Note,
        there is no atomicity guarantee, this is not like a database transaction, this is just an
        optimization to reduce the amount of MSR I/O.
        """

        if not self._in_transaction:
            raise Error("cannot commit a transaction, it did not start")

        flushed = self.flush_transaction()
        self._in_transaction = False
        if flushed:
            _LOG.debug("MSR transaction has been committed")
        else:
            _LOG.debug("MSR transaction has been committed, but it was empty")

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

    def _read_cpu_nocache(self, regaddr, cpu):
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

    def _read_remote_optimized(self, regaddr, cpus, iosname):
        """
        An optimized implementation of 'read()' method for a remote host.

        Observation: opening and reading multiple remote '/dev/msr/{cpu}' files from the local
        system is significantly slower than running a script on the remote system and having the
        script open/read the files.

        Optimized solution: generate a small python script that reads the 'regaddr' MSR on 'cpus'
        and prints the values, run the script on the remote host, parse script output.
        """

        # CPU numbers to read the MSR for (subset of 'cpus').
        do_read = []
        # CPU numbers the MSR should not be read for. Instead, the MSR values for these CPU numbres
        # are available from the cache, or will be available from the cache when a sibling CPU from
        # 'do_read' is read.
        dont_read = set()

        for cpu in cpus:
            if cpu in dont_read:
                continue

            try:
                self._cache.get(regaddr, cpu)
                continue
            except ErrorNotFound:
                if self._enable_cache:
                    # The cache is enabled, but MSR value is not available from there. Read the MSR
                    # only for 'ioscope' sibling CPU, because MSR value should be the same for the
                    # siblings.
                    for sibling in self._cpuinfo.get_cpu_siblings(cpu, iosname):
                        if sibling == cpu:
                            do_read.append(sibling)
                        else:
                            dont_read.add(sibling)
                else:
                    # The cache is disabled. Technically, it is not necessary to do anything
                    # differently in this case. But emulate the 'read()' method behavior for
                    # consistency: ignore the 'ioscope' and just read the MSR for all CPUs in
                    # 'cpus'.
                    do_read.append(cpu)

        if not do_read:
            for cpu in cpus:
                yield cpu, self._cache.get(regaddr, cpu)
            return

        python_path = self._pman.get_python_path()
        cpus_str = ",".join([str(cpu) for cpu in do_read])
        cmd = f"""{python_path} -c '
cpus = [{cpus_str}]
for cpu in cpus:
    path = "/dev/cpu/%d/msr" % cpu
    with open(path, "rb") as fobj:
        fobj.seek({regaddr})
        regval = fobj.read({self.regbytes})
        regval = int.from_bytes(regval, byteorder="{_CPU_BYTEORDER}")
        print("%d,%d" % (cpu, regval))
'"""

        stdout, _ = self._pman.run_verify(cmd)
        regvals = {}

        for line in stdout.splitlines():
            split = Trivial.split_csv_line(line.strip())
            if len(split) != 2:
                raise Error("BUG: bad MSR read script line '{line}'")

            cpu = Trivial.str_to_int(split[0], what="CPU number")
            regval = Trivial.str_to_int(split[1], what=f"MSR {regaddr:#x} value on CPU {cpu}")

            regvals[cpu] = regval
            self._cache.add(regaddr, cpu, regval, sname=iosname)

        for cpu in cpus:
            regval = regvals.get(cpu)
            if regval is None:
                regval = self._cache.get(regaddr, cpu)
            yield cpu, regval

    def _read(self, regaddr, cpus, iosname):
        """Implement 'read()'."""

        if self._pman.is_remote and len(cpus) > 1:
            yield from self._read_remote_optimized(regaddr, cpus, iosname)
            return

        for cpu in cpus:
            # Return the cached value if possible.
            try:
                regval = self._cache.get(regaddr, cpu)
            except ErrorNotFound:
                # Not in the cache, read from the HW.
                regval = self._read_cpu_nocache(regaddr, cpu)
                self._cache.add(regaddr, cpu, regval, sname=iosname)

            yield cpu, regval

    def read(self, regaddr, cpus="all", iosname="CPU"):
        """
        Read an MSR on CPUs 'cpus' and yield the result. The arguments are as follows.
          * regaddr - address of the MSR to read.
          * cpus - collection of integer CPU numbers. Special value 'all' means "all CPUs".
          * iosname - the 'regaddr' MSR I/O scope name (e.g. "package", "core").

        Yields tuples of '(cpu, regval)'.
          * cpu - the CPU number the MSR was read from.
          * regval - the read MSR value.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        yield from self._read(regaddr, cpus, iosname)

    def read_cpu(self, regaddr, cpu, iosname="CPU"):
        """
        Read an MSR at 'regaddr' on CPU 'cpu' and return read result. The arguments are as follows.
          * regaddr - address of the MSR to read.
          * cpu - the CPU to read the MSR at. Can be an integer or a string with an integer number.
          * iosname - same as in 'read()'.
        """

        regval = None
        for _, regval in self.read(regaddr, cpus=(cpu,), iosname=iosname):
            pass

        return regval

    def read_bits(self, regaddr, bits, cpus="all", iosname="CPU"):
        """
        Read bits 'bits' from an MSR at 'regaddr' from CPUs in 'cpus' and yield the results. The
        arguments are as follows.
          * regaddr - address of the MSR to read the bits from.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * cpus - the CPUs to read from (similar to the 'cpus' argument in 'read()').
          * iosname - same as in 'read()'.

        Yields tuples of '(cpu, regval)'.
          * cpu - the CPU number the MSR was read from.
          * val - the value in MSR bits 'bits'.
        """

        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            yield (cpu, self.get_bits(regval, bits))

    def read_cpu_bits(self, regaddr, bits, cpu, iosname="CPU"):
        """
        Read bits 'bits' from an MSR at 'regaddr' on CPU 'cpu'. The arguments are as follows.
          * regaddr - address of the MSR to read the bits from.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * cpu - the CPU to read the MSR at. Can be an integer or a string with an integer number.
          * iosname - same as in 'read()'.
        """

        regval = self.read_cpu(regaddr, cpu, iosname=iosname)
        return self.get_bits(regval, bits)

    def set_bits(self, regval, bits, val):
        """
        Set bits 'bits' to value 'val' in an MSR value 'regval', and return the result. The
        arguments are as follows.
          * regval - an MSR value to set the bits in.
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

    def _write_cpu_nocache(self, regaddr, regval, cpu, regval_bytes=None, verify=False):
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

    def write(self, regaddr, regval, cpus="all", iosname="CPU", verify=False):
        """
        Write 'regval' to an MSR at 'regaddr' on CPUs in 'cpus'. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - the value to write to the MSR.
          * cpus - the CPUs to write to (similar to the 'cpus' argument in 'read()').
          * iosname - the 'regaddr' MSR I/O scope name (e.g. "package", "core").
          * verify - read-back and verify the written value, raises 'ErrorVerifyFailed' if it
                     differs.
        """

        cpus = self._cpuinfo.normalize_cpus(cpus)
        regval_bytes = None

        for cpu in cpus:
            self._cache.remove(regaddr, cpu, sname=iosname)

        # Removing 'cpus' from the cache will make sure the following '_cache.is_cached()' returns
        # 'False' for every CPU number that was not yet modified by the scope-aware '_cache.add()'
        # method.
        for cpu in cpus:
            if self._cache.is_cached(regaddr, cpu):
                continue

            if not self._in_transaction:
                if regval_bytes is None:
                    regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)
                self._write_cpu_nocache(regaddr, regval, cpu, regval_bytes=regval_bytes)
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

    def write_cpu(self, regaddr, regval, cpu, iosname="CPU", verify=False):
        """
        Write 'regval' to an MSR at 'regaddr' on CPU 'cpu'. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - the value to write to the MSR.
          * cpu - the CPU to write the MSR on. Can be an integer or a string with an integer number.
          * iosname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        self.write(regaddr, regval, cpus=(cpu,), iosname=iosname, verify=verify)

    def write_bits(self, regaddr, bits, val, cpus="all", iosname="CPU", verify=False):
        """
        Write value 'val' to bits 'bits' of an MSR at 'regaddr' on CPUs in 'cpus'. The arguments are
        as follows.
          * regaddr - address of the MSR to write the bits to.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * val - the integer value to write to MSR bits 'bits'. Use 'MSR.ALL_BITS_1' to set all
                  bits to '1'.
          * cpus - the CPUs to write to (similar to the 'cpus' argument in 'read()').
          * iosname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        regvals = {}
        for cpu, regval in self.read(regaddr, cpus, iosname=iosname):
            new_regval = self.set_bits(regval, bits, val)
            if regval == new_regval:
                continue

            if new_regval not in regvals:
                regvals[new_regval] = []
            regvals[new_regval].append(cpu)

        for regval, regval_cpus in regvals.items():
            self.write(regaddr, regval, regval_cpus, iosname=iosname, verify=verify)

    def write_cpu_bits(self, regaddr, bits, val, cpu, iosname="CPU", verify=False):
        """
        Write value 'val' to bits 'bits' of an MSR at 'regaddr' on CPU 'cpu'. The arguments are
        as follows.
          * regaddr - address of the MSR to write the bits to.
          * bits - the MSR bits range (similar to the 'bits' argument in 'get_bits()').
          * val - the integer value to write to MSR bits 'bits'. Use 'MSR.ALL_BITS_1' to set all
                  bits to '1'.
          * cpu - the CPU to write the MSR on. Can be an integer or a string with an integer number.
          * iosname - same as in 'write()'.
          * verify - same as in 'write()'.
        """

        self.write_bits(regaddr, bits, val, cpus=(cpu,), iosname=iosname, verify=verify)

    def _ensure_dev_msr(self):
        """
        Make sure that device nodes for accessing MSRs are available. Try to load the MSR driver if
        necessary.
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

    def __init__(self, cpuinfo, pman=None, enable_cache=True):
        """
        The class constructor. The arguments are as follows.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * pman - the process manager object that defines the host to run the measurements on.
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

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        # MSR size in bits and bytes.
        self.regbits = 64
        self.regbytes = self.regbits // 8

        self._msr_drv = None
        self._unload_msr_drv = False

        # The write-through per-CPU MSR values cache.
        self._cache = _PerCPUCache.PerCPUCache(self._cpuinfo, enable_cache=self._enable_cache)
        # Stores new MSR values to be written when 'commit_transaction()' is called.
        self._transaction_buffer = {}
        # Whether there is an ongoing transaction.
        self._in_transaction = False

        self._ensure_dev_msr()

    def close(self):
        """Uninitialize the class object."""

        if self._unload_msr_drv:
            self._msr_drv.unload()

        close_attrs = ("_pman", "_msr_drv", "_cache")
        unref_attrs = ("_cpuinfo",)
        ClassHelpers.close(self, close_attrs=close_attrs, unref_attrs=unref_attrs)
