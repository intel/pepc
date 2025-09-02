# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability to read and write CPU Model Specific Registers.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path
from pepclibs.helperlibs import ClassHelpers, Trivial
from pepclibs.helperlibs import Logging, LocalProcessManager, KernelModule, FSHelpers
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Literal, Generator, Sequence
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

_CPU_BYTEORDER: Literal["little", "big"] = "little"

class SimpleMSR(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and write CPU Model Specific Registers.
    """

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager will be used.
        """

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        self._close_pman = pman is None

        # MSR size in bits and bytes.
        self.regbits = 64
        self.regbytes = self.regbits // 8

        self._msr_drv: KernelModule.KernelModule | None = None

        self._ensure_dev_msr()

    def close(self):
        """Uninitialize the class object."""

        if self._msr_drv:
            try:
                self._msr_drv.unload()
            except Error as err:
                _LOG.warning("Failed to unload the previously loaded MSR driver: %s", err.indent(2))

        close_attrs = ("_pman", "_msr_drv")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _ensure_dev_msr(self):
        """
        Ensure that device nodes for accessing Model-Specific Registers (MSRs) are available.
        Attempt to load the 'msr' kernel driver if the required device node does not exist.
        """

        dev_path = Path("/dev/cpu/0/msr")
        if self._pman.exists(dev_path):
            return

        drvname = "msr"
        msg = f"File '{dev_path}' is not available{self._pman.hostmsg}\nMake sure your kernel" \
              f"has the '{drvname}' driver enabled (CONFIG_X86_MSR)."
        try:
            self._msr_drv = KernelModule.KernelModule(drvname, pman=self._pman)
        except Error as err:
            raise Error(f"{msg}\n{err.indent(2)}") from err

        try:
            loaded = self._msr_drv.is_loaded()
        except Error as err:
            self._msr_drv.close()
            self._msr_drv = None
            raise Error(f"{msg}\n{err.indent(2)}") from err

        if loaded:
            self._msr_drv.close()
            self._msr_drv = None
            raise Error(msg)

        try:
            self._msr_drv.load()
            FSHelpers.wait_for_a_file(dev_path, timeout=1, pman=self._pman)
        except Error as err:
            self._msr_drv.close()
            self._msr_drv = None
            raise Error(f"{msg}\n{err.indent(2)}") from err

    def _normalize_bits(self, bits: tuple[int, int] | list[int]) -> tuple[int, int]:
        """
        Validate and normalize a bits range.

        Args:
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to extract;
                  msb is the most significant bit and lsb is the least significant bit.

        Returns:
            A tuple of two integers representing the normalized bit range.
        """

        orig_bits = bits
        try:
            if not Trivial.is_int(orig_bits[0]) or not Trivial.is_int(orig_bits[1]):
                raise Error(f"Bad bits range '{bits}', must be a list or tuple of 2 integers")

            bits = (int(orig_bits[0]), int(orig_bits[1]))

            if bits[0] < bits[1]:
                raise Error(f"Bad bits range ({bits[0]}, {bits[1]}), the first number must be "
                            f"greater or equal to the second number")

            bits_cnt = (bits[0] - bits[1]) + 1
            if bits_cnt > self.regbits:
                raise Error(f"Too many bits in ({bits[0]}, {bits[1]}), MSRs only have "
                            f"{self.regbits} bits")
        except TypeError:
            raise Error(f"Bad bits range '{bits}', must be a list or tuple of 2 integers") from None

        return bits

    def get_bits(self, regval: int, bits: tuple[int, int] | list[int]) -> int:
        """
        Extract a range of bits from an MSR value.

        Args:
            regval: The MSR value to extract bits from.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to extract;
                  msb is the most significant bit and lsb is the least significant bit.

        Returns:
            The integer value represented by the specified bit range, right-aligned to bit 0.
        """

        bits = self._normalize_bits(bits)
        bits_cnt = (bits[0] - bits[1]) + 1
        mask = (1 << bits_cnt) - 1
        return (regval >> bits[1]) & mask

    def _cpus_read_remote(self,
                          regaddr: int,
                          cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Optimized method for reading MSR values from a remote host.

        Improve performance by generating and executing a small Python script on the remote host to
        read the specified MSR for a set of CPUs. This approach is faster than opening and reading
        multiple remote '/dev/msr/{cpu}' files from the local system.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        python_path = self._pman.get_python_path()
        cpus_str = ",".join([str(cpu) for cpu in cpus])
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

        stdout, _ = self._pman.run_verify(cmd, join=False)

        for line in stdout:
            split = Trivial.split_csv_line(line.strip())
            if len(split) != 2:
                raise Error("BUG: bad MSR read script line '{line}'")

            cpu = Trivial.str_to_int(split[0], what="CPU number")
            regval = Trivial.str_to_int(split[1], what=f"MSR {regaddr:#x} value on CPU {cpu}")

            yield cpu, regval

    def cpus_read(self,
                  regaddr: int,
                  cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Read the specified MSR from specified CPUs and yield the result.

        Args:
            regaddr: Address of the MSR to read.
            cpus: CPU numbers to read the MSR from. The numbers have to be validated and normalized
                  by the caller.

        Yields:
            Tuple of (cpu, regval):
                cpu: CPU number from which the MSR was read.
                regval: Value read from the MSR.
        """

        if self._pman.is_remote:
            yield from self._cpus_read_remote(regaddr, cpus)
        else:
            for cpu in cpus:
                regval = self.cpu_read(regaddr, cpu)
                yield cpu, regval

    def cpu_read(self, regaddr: int, cpu: int) -> int:
        """
        Read an MSR at the specified address for a given CPU

        Args:
            regaddr: The address of the MSR to read.
            cpu: CPU number to read the MSR from. The number has to be validated and normalized
                 by the caller.

        Returns:
            The value of the MSR as an integer.
        """

        path = Path(f"/dev/cpu/{cpu}/msr")
        try:
            with self._pman.open(path, "rb") as fobj:
                fobj.seek(regaddr)
                regval = fobj.read(self.regbytes)
        except Error as err:
            raise Error(f"Failed to read MSR '{regaddr:#x}' from file '{path}'"
                        f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        regval = int.from_bytes(regval, byteorder=_CPU_BYTEORDER)
        _LOG.debug("CPU%d: MSR 0x%x: read 0x%x%s", cpu, regaddr, regval, self._pman.hostmsg)

        return regval

    def set_bits(self, regval: int, bits: tuple[int, int] | list[int], val: int) -> int:
        """
        Set a range of bits in an MSR value to a specified value and return the modified result.

        Args:
            regval: The MSR value in which to set the bits.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to set;
                  msb is the most significant bit and lsb is the least significant bit.
            val: The value to set in the bits range to.
        """

        bits = self._normalize_bits(bits)
        bits_cnt = (bits[0] - bits[1]) + 1
        max_val = (1 << bits_cnt) - 1

        if not Trivial.is_int(val):
            raise Error(f"Bad value {val}, please provide a positive integer")
        val = int(val)

        if val > max_val:
            raise Error(f"Too large value {val} for bits range ({bits[0]}, {bits[1]})")

        clear_mask = max_val << bits[1]
        set_mask = val << bits[1]
        return (regval & ~clear_mask) | set_mask

    def cpu_write(self, regaddr: int, regval: int, cpu: int, regval_bytes: bytes | None = None):
        """
        Write a value to an MSR for a specific CPU.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpu: CPU number to write the MSR on.
            regval_bytes: The value to write as a bytes object. If not provided, regval is converted
                          to bytes. If provided, regval is ignored and regval_bytes is written to
                          the MSR. In other words, this is an optimization saving the "to_bytes()"
                          conversion step.
        """

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
                raise Error(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                            f"{cpu}{self._pman.hostmsg} (file '{path}'):\n{err.indent(2)}") from err
