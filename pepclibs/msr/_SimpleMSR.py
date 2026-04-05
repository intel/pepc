# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability to read and write CPU Model Specific Registers.

MSR I/O Performance Note:
    Using Python's built-in 'open()' followed by 'seek()' and 'read()'/'write()' is ~130 times
    slower than using 'os.open()' with 'os.pread()'/'os.pwrite()' for MSR operations. The exact
    reason is not fully understood, but is likely related to how the MSR kernel driver handles
    these operations. This module uses 'os.pread()'/'os.pwrite()' for optimal performance.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import typing
from pathlib import Path
from pepclibs.helperlibs import ClassHelpers, FSHelpers, Trivial, Logging, KernelModule
from pepclibs.helperlibs import LocalProcessManager
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorPerCPUPath

if typing.TYPE_CHECKING:
    from typing import Literal, Generator, Final, Iterable
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

_CPU_BYTEORDER: Final[Literal["little", "big"]] = "little"

# A debug option to disable I/O optimizations.
DISABLE_IO_OPTIMIZATIONS: bool = False

class SimpleMSR(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability to read and write CPU Model Specific Registers.
    """

    @staticmethod
    def format_msr_device_path(cpu: int) -> Path:
        """
        Format the MSR device path for a given CPU.

        Args:
            cpu: CPU number.

        Returns:
            Path to the MSR device file for the specified CPU.
        """

        return Path(f"/dev/cpu/{cpu}/msr")

    def __init__(self, pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager will be used.

        Raises:
            ErrorPermissionDenied: No permissions to access MSRs.
            ErrorNotSupported: MSR is not supported.
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

        try:
            self._ensure_dev_msr()
        except ErrorPermissionDenied as err:
            raise type(err)(f"No permissions to access MSRs{self._pman.hostmsg}:\n"
                            f"{err.indent(2)}") from err
        except Error as err:
            raise ErrorNotSupported(f"MSR access is not supported{self._pman.hostmsg}:\n"
                                    f"{err.indent(2)}") from err

        # Use sudo for privileged MSR I/O when not running as superuser but passwordless sudo is
        # available. Applies to both local and remote hosts. Not applicable to emulated hosts.
        if not self._pman.is_emulated:
            use_sudo = not self._pman.is_superuser() and self._pman.has_passwdless_sudo()
        else:
            use_sudo = False
        self._use_sudo = use_sudo

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

        dev_path = self.format_msr_device_path(0)
        if self._pman.exists(dev_path):
            return

        drvname = "msr"
        msg = f"File '{dev_path}' is not available{self._pman.hostmsg}\nMake sure your kernel" \
              f"has the '{drvname}' driver enabled (CONFIG_X86_MSR)."
        try:
            self._msr_drv = KernelModule.KernelModule(drvname, pman=self._pman)
        except Error as err:
            raise type(err)(f"{msg}\n{err.indent(2)}") from err

        try:
            loaded = self._msr_drv.is_loaded()
        except Error as err:
            self._msr_drv.close()
            self._msr_drv = None
            raise type(err)(f"{msg}\n{err.indent(2)}") from err

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
            raise type(err)(f"{msg}\n{err.indent(2)}") from err

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

    def _cpus_read_local(self,
                         regaddr: int,
                         cpus: Iterable[int]) -> Generator[tuple[int, int], None, None]:
        """
        Read an MSR from specified CPUs on a local host.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        for cpu in cpus:
            path = self.format_msr_device_path(cpu)
            _LOG.debug("Local: Read: CPU%d: MSR 0x%x from '%s'%s",
                       cpu, regaddr, path, self._pman.hostmsg)
            try:
                with open(path, "rb") as fobj:
                    regval_bytes = os.pread(fobj.fileno(), self.regbytes, regaddr)
            except PermissionError as err:
                errmsg = Error(str(err)).indent(2)
                raise ErrorPermissionDenied(f"No permissions to read MSR '{regaddr:#x}' from "
                                            f"file '{path}'{self._pman.hostmsg}:\n"
                                            f"{errmsg}") from err
            except OSError as err:
                raise ErrorPerCPUPath(f"Failed to read MSR '{regaddr:#x}' from file '{path}'"
                                      f"{self._pman.hostmsg}: {err}", cpu=cpu, path=path) from err
            regval = int.from_bytes(regval_bytes, byteorder=_CPU_BYTEORDER)
            yield cpu, regval

    def _cpus_read_optimized(self,
                             regaddr: int,
                             cpus: Iterable[int],
                             su: bool = False) -> Generator[tuple[int, int], None, None]:
        """
        Read an MSR from specified CPUs using optimized I/O.

        Execute a small Python script in a single operation to read the specified MSR for a set of
        CPUs, instead of opening each MSR device file individually.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.
            su: If 'True', run the script as superuser (root).

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        python_path = self._pman.get_python_path()
        cpus_list = list(cpus)
        cpus_str = ",".join([str(cpu) for cpu in cpus_list])

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            cpus_range = Trivial.rangify(cpus_list)
            _LOG.debug("Optimized: Read: MSR 0x%x from CPUs %s%s",
                       regaddr, cpus_range, self._pman.hostmsg)

        cmd = f"""{python_path} -c '
import os
cpus = [{cpus_str}]
for cpu in cpus:
    path = "/dev/cpu/%d/msr" % cpu
    try:
        with open(path, "rb") as fobj:
            regval = os.pread(fobj.fileno(), {self.regbytes}, {regaddr:#x})
            regval = int.from_bytes(regval, byteorder="{_CPU_BYTEORDER}")
            print("%d,%d" % (cpu, regval))
    except PermissionError as err:
        print("ERROR: Permission: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
    except Exception as err:
        print("ERROR: Read: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
'"""

        try:
            stdout, stderr = self._pman.run_verify_join(cmd, su=su)
        except Error as err:
            raise type(err)(f"Failed to read MSR '{regaddr:#x}' on CPUs {cpus_str}"
                            f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        if stderr:
            # Nothing is expected on stderr, if there is any output, treat it as an error.
            raise Error(f"Failed to read MSR '{regaddr:#x}' on CPUs {cpus_str}"
                        f"{self._pman.hostmsg}:\nUnexpected output on stderr:\n{stderr}")

        regex = re.compile(r"ERROR: (Permission|Read): CPU: (\d+): Path: ([^:]+): Error: (.+)")

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            # Check for error message from the remote script.
            if line.startswith("ERROR: "):
                generic_errmsg = (f"Failed to read MSR '{regaddr:#x}' on CPUs {cpus_str}"
                                  f"{self._pman.hostmsg}:\n{line}")

                # Try to parse the error message to extract CPU, path, and error.
                mobj = regex.match(line)
                if not mobj:
                    raise Error(generic_errmsg)

                errtype = mobj.group(1)
                cpu = Trivial.str_to_int(mobj.group(2), what="CPU number")
                path = Path(mobj.group(3))
                errmsg = mobj.group(4)

                if errtype == "Permission":
                    raise ErrorPermissionDenied(f"No permissions to read MSR '{regaddr:#x}' from "
                                                f"CPU {cpu}{self._pman.hostmsg} (file '{path}'):\n"
                                                f"{Error(errmsg).indent(2)}")
                raise ErrorPerCPUPath(f"Failed to read MSR '{regaddr:#x}' from CPU {cpu}"
                                      f"{self._pman.hostmsg} (file '{path}'):\n"
                                      f"{Error(errmsg).indent(2)}", cpu=cpu, path=path)

            # Normal output: CPU,value
            split = Trivial.split_csv_line(line)
            if len(split) != 2:
                raise Error(f"BUG: bad MSR read script line '{line}'")

            cpu = Trivial.str_to_int(split[0], what="CPU number")
            regval = Trivial.str_to_int(split[1], what=f"MSR {regaddr:#x} value on CPU {cpu}")
            yield cpu, regval

    def _cpus_read_pman(self,
                        regaddr: int,
                        cpus: Iterable[int]) -> Generator[tuple[int, int], None, None]:
        """
        Read an MSR from specified CPUs using the process manager object.

        Args:
            regaddr: The address of the MSR to read.
            cpus: CPU numbers to read the MSR from.

        Yields:
            Tuples of (cpu, regval), where 'cpu' is the CPU number and 'regval' is the value read
            from the MSR.
        """

        for cpu in cpus:
            path = self.format_msr_device_path(cpu)
            _LOG.debug("Emulation: Read: CPU%d: MSR 0x%x from '%s'%s",
                       cpu, regaddr, path, self._pman.hostmsg)
            try:
                with self._pman.openb(path, "rb") as fobj:
                    fobj.seek(regaddr)
                    regval_bytes = fobj.read(self.regbytes)
            except ErrorPermissionDenied as err:
                raise type(err)(f"No permissions to read MSR '{regaddr:#x}' from "
                                f"file '{path}'{self._pman.hostmsg}:\n"
                                f"{err.indent(2)}") from err
            except Error as err:
                raise type(err)(f"Failed to read MSR '{regaddr:#x}' from file '{path}'"
                                f"{self._pman.hostmsg}:\n{err.indent(2)}") from err
            regval = int.from_bytes(regval_bytes, byteorder=_CPU_BYTEORDER)
            yield cpu, regval

    def cpus_read(self,
                  regaddr: int,
                  cpus: Iterable[int]) -> Generator[tuple[int, int], None, None]:
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

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        if DISABLE_IO_OPTIMIZATIONS or self._pman.is_emulated:
            yield from self._cpus_read_pman(regaddr, cpus)
        elif self._pman.is_remote or self._use_sudo:
            yield from self._cpus_read_optimized(regaddr, cpus, su=self._use_sudo)
        else:
            yield from self._cpus_read_local(regaddr, cpus)

    def cpu_read(self, regaddr: int, cpu: int) -> int:
        """
        Read an MSR at the specified address for a given CPU.

        Args:
            regaddr: The address of the MSR to read.
            cpu: CPU number to read the MSR from. The number has to be validated and normalized
                 by the caller.

        Returns:
            The value of the MSR as an integer.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while reading the MSR (includes CPU and path
                             information).
        """

        for _, regval in self.cpus_read(regaddr, (cpu,)):
            return regval

        path = self.format_msr_device_path(cpu)
        raise ErrorPerCPUPath(f"Failed to read MSR '{regaddr:#x}' from CPU {cpu}"
                              f"{self._pman.hostmsg}", cpu=cpu, path=path)

    def set_bits(self, regval: int, bits: tuple[int, int] | list[int], val: int) -> int:
        """
        Set a range of bits in an MSR value to a specified value and return the modified result.

        Args:
            regval: The MSR value in which to set the bits.
            bits: A tuple or list of two integers (msb, lsb) specifying the bit range to set;
                  msb is the most significant bit and lsb is the least significant bit.
            val: The value to set in the bits range to.

        Returns:
            The modified MSR value with the specified bits set.
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

    def _cpus_write_local(self,
                          regaddr: int,
                          regval: int,
                          cpus: Iterable[int]):
        """
        Write a value to an MSR on specified CPUs on a local host.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on.
        """

        regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)

        for cpu in cpus:
            path = self.format_msr_device_path(cpu)
            _LOG.debug("Local: Write: CPU%d: MSR 0x%x: 0x%x to '%s'%s",
                       cpu, regaddr, regval, path, self._pman.hostmsg)
            try:
                with open(path, "r+b") as fobj:
                    os.pwrite(fobj.fileno(), regval_bytes, regaddr)
            except PermissionError as err:
                errmsg = Error(str(err)).indent(2)
                raise ErrorPermissionDenied(f"No permissions to write '{regval:#x}' to MSR "
                                            f"'{regaddr:#x}' of CPU {cpu}{self._pman.hostmsg} "
                                            f"(file '{path}'):\n{errmsg}") from err
            except OSError as err:
                raise ErrorPerCPUPath(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                                      f"{cpu}{self._pman.hostmsg} (file '{path}'): {err}",
                                      cpu=cpu, path=path) from err

    def _cpus_write_optimized(self,
                              regaddr: int,
                              regval: int,
                              cpus: Iterable[int],
                              su: bool = False):
        """
        Write a value to an MSR on specified CPUs using optimized I/O.

        Execute a small Python script in a single operation to write the specified MSR for a set of
        CPUs, instead of opening each MSR device file individually.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on.
            su: If 'True', run the script as superuser (root).
        """

        python_path = self._pman.get_python_path()
        cpus_list = list(cpus)
        cpus_str = ",".join([str(cpu) for cpu in cpus_list])

        cmd = f"""{python_path} -c '
import os
cpus = [{cpus_str}]
regval = {regval:#x}
regval_bytes = regval.to_bytes({self.regbytes}, byteorder="{_CPU_BYTEORDER}")
for cpu in cpus:
    path = "/dev/cpu/%d/msr" % cpu
    try:
        with open(path, "r+b") as fobj:
            os.pwrite(fobj.fileno(), regval_bytes, {regaddr:#x})
    except PermissionError as err:
        print("ERROR: Permission: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
    except Exception as err:
        print("ERROR: Write: CPU: %d: Path: %s: Error: %s" % (cpu, path, err))
        raise SystemExit(0)
'"""

        _LOG.debug("Optimized: Write: MSR 0x%x: 0x%x%s",
                   regaddr, regval, self._pman.hostmsg)

        try:
            stdout, stderr = self._pman.run_verify_join(cmd, su=su)
        except Error as err:
            errmsg = err.indent(2)
            raise type(err)(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' on CPUs "
                            f"{cpus_str}{self._pman.hostmsg}:\n{errmsg}") from err

        if stderr:
            # Nothing is expected on stderr, if there is any output, treat it as an error.
            raise Error(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' on CPUs {cpus_str}"
                        f"{self._pman.hostmsg}:\nUnexpected output on stderr:\n{stderr}")

        if not stdout:
            # All writes succeeded.
            return

        stdout = stdout.strip()
        generic_errmsg = (f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' on CPUs "
                          f"{cpus_str}{self._pman.hostmsg}:\n{stdout}")

        if not stdout.startswith("ERROR: "):
            raise Error(generic_errmsg)

        # Try to parse the error message to extract CPU, path, and error.
        # Regex for parsing error lines printed by remote MSR read/write scripts.
        regex = re.compile(r"ERROR: (Permission|Write): CPU: (\d+): Path: ([^:]+): Error: (.+)")

        mobj = regex.match(stdout)
        if not mobj:
            raise Error(generic_errmsg)

        errtype = mobj.group(1)
        cpu = Trivial.str_to_int(mobj.group(2), what="CPU number")
        path = Path(mobj.group(3))
        errmsg = mobj.group(4)

        if errtype == "Permission":
            raise ErrorPermissionDenied(f"No permissions to write '{regval:#x}' to MSR "
                                        f"'{regaddr:#x}' of CPU {cpu}{self._pman.hostmsg} "
                                        f"(file '{path}'):\n{Error(errmsg).indent(2)}")
        raise ErrorPerCPUPath(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU {cpu}"
                              f"{self._pman.hostmsg} (file '{path}'):\n"
                              f"{Error(errmsg).indent(2)}", cpu=cpu, path=path)

    def _cpus_write_pman(self, regaddr: int, regval: int, cpus: Iterable[int]):
        """
        Write a value to an MSR on specified CPUs using the process manager object.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on.
        """

        regval_bytes = regval.to_bytes(self.regbytes, byteorder=_CPU_BYTEORDER)

        for cpu in cpus:
            path = self.format_msr_device_path(cpu)
            _LOG.debug("Emulation: Write: CPU%d: MSR 0x%x: 0x%x to '%s'%s",
                       cpu, regaddr, regval, path, self._pman.hostmsg)
            with self._pman.openb(path, "r+") as fobj:
                try:
                    fobj.seek(regaddr)
                    fobj.write(regval_bytes)
                    fobj.flush()
                except ErrorPermissionDenied as err:
                    errmsg = err.indent(2)
                    raise type(err)(f"No permissions to write '{regval:#x}' to MSR "
                                    f"'{regaddr:#x}' of CPU {cpu}"
                                    f"{self._pman.hostmsg} (file '{path}'):\n"
                                    f"{errmsg}") from err
                except Error as err:
                    raise type(err)(f"Failed to write '{regval:#x}' to MSR '{regaddr:#x}' of CPU "
                                    f"{cpu}{self._pman.hostmsg} (file '{path}'):\n"
                                    f"{err.indent(2)}") from err

    def cpus_write(self, regaddr: int, regval: int, cpus: Iterable[int]):
        """
        Write a value to an MSR on specified CPUs.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpus: CPU numbers to write the MSR on. The numbers have to be validated and normalized
                  by the caller.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while writing to the MSR (includes CPU and path
                             information).
        """

        if DISABLE_IO_OPTIMIZATIONS or self._pman.is_emulated:
            self._cpus_write_pman(regaddr, regval, cpus)
        elif self._pman.is_remote or self._use_sudo:
            self._cpus_write_optimized(regaddr, regval, cpus, su=self._use_sudo)
        else:
            self._cpus_write_local(regaddr, regval, cpus)

    def cpu_write(self, regaddr: int, regval: int, cpu: int):
        """
        Write a value to an MSR for a specific CPU.

        Args:
            regaddr: The address of the MSR to write to.
            regval: The value to write to the MSR.
            cpu: CPU number to write the MSR on.

        Raises:
            ErrorPermissionDenied: No permissions to access the MSR device file.
            ErrorPerCPUPath: An I/O error occurred while writing to the MSR (includes CPU and path
                             information).
        """

        self.cpus_write(regaddr, regval, (cpu,))
