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

    def _handle_arguments(self, regsize, cpus):
        """Validate arguments, and convert 'cpus' to valid list of CPU numbers if needed."""

        regsizes = (4, 8)
        if regsize not in regsizes:
            regsizes_str = ",".join([str(regsz) for regsz in regsizes])
            raise Error(f"invalid register size value '{regsize}', use one of: {regsizes_str}")

        cpus = self._cpuinfo.normalize_cpus(cpus)

        return (regsize, cpus)

    def read_iter(self, regaddr, regsize=8, cpus="all"):
        """
        Read an MSR register on one or multiple CPUs and yield tuple with CPU number and the read
        result.
          * regaddr - address of the MSR to read.
          * regsize - size of MSR register in bytes.
          * cpus - list of CPU numbers value should be read from. It is the same as the 'cpus'
                   argument of the 'CPUIdle.get_cstates_info()' function - please, refer to the
                   'CPUIdle' module for the exact format description.
        """

        regsize, cpus = self._handle_arguments(regsize, cpus)

        for cpu in cpus:
            path = Path(f"/dev/cpu/{cpu}/msr")
            try:
                with self._proc.open(path, "rb") as fobj:
                    fobj.seek(regaddr)
                    regval = fobj.read(regsize)
            except Error as err:
                raise Error(f"failed to read MSR '{hex(regaddr)}' from file '{path}'"
                            f"{self._proc.hostmsg}:\n{err}") from err

            regval = int.from_bytes(regval, byteorder=_CPU_BYTEORDER)
            _LOG.debug("CPU%d: MSR 0x%x: read 0x%x", cpu, regaddr, regval)

            yield (cpu, regval)

    def read(self, regaddr, regsize=8, cpu=0):
        """
        Read an MSR on single CPU and return read result. Arguments are same as in read_iter().
        """

        _, msr = next(self.read_iter(regaddr, regsize, cpu))
        return msr

    def write(self, regaddr, regval, regsize=8, cpus="all"):
        """
        Write to MSR register. The arguments are as follows.
          * regaddr - address of the MSR to write to.
          * regval - integer value to write to MSR.
          * regsize - size of MSR register in bytes.
          * cpus - list of CPU numbers write should be done at. It is the same as the 'cpus'
                   argument of the 'CPUIdle.get_cstates_info()' function - please, refer to the
                   'CPUIdle' module for the exact format description.
        """

        regsize, cpus = self._handle_arguments(regsize, cpus)

        regval_bytes = regval.to_bytes(regsize, byteorder=_CPU_BYTEORDER)
        for cpu in cpus:
            path = Path(f"/dev/cpu/{cpu}/msr")
            try:
                with self._proc.open(path, "wb") as fobj:
                    fobj.seek(regaddr)
                    fobj.write(regval_bytes)
                    _LOG.debug("CPU%d: MSR 0x%x: wrote 0x%x", cpu, regaddr, regval)
            except Error as err:
                raise Error(f"failed to write MSR '{hex(regaddr)}' to file '{path}'"
                            f"{self._proc.hostmsg}:\n{err}") from err

    def set(self, regaddr, mask, regsize=8, cpus="all"):
        """Set 'mask' bits in MSR. Arguments are the same as in 'write()'."""

        regsize, cpus = self._handle_arguments(regsize, cpus)

        for cpunum, regval in self.read_iter(regaddr, regsize, cpus):
            new_regval = regval | mask
            if regval != new_regval:
                self.write(regaddr, new_regval, regsize, cpunum)

    def clear(self, regaddr, mask, regsize=8, cpus="all"):
        """Clear 'mask' bits in MSR. Arguments are the same as in 'write()'."""

        regsize, cpus = self._handle_arguments(regsize, cpus)

        for cpunum, regval in self.read_iter(regaddr, regsize, cpus):
            new_regval = regval & ~mask
            if regval != new_regval:
                self.write(regaddr, new_regval, regsize, cpunum)

    def toggle_bit(self, regaddr, bitnr, bitval, regsize=8, cpus="all"):
        """
        Toggle bit number 'bitnr', in MSR 'regaddr' to value 'bitval'. Other arguments are the same
        as in 'write()'.
        """

        regsize, cpus = self._handle_arguments(regsize, cpus)
        bitval = int(bool(bitval))

        if bitval:
            self.set(regaddr, bit_mask(bitnr), regsize=regsize, cpus=cpus)
        else:
            self.clear(regaddr, bit_mask(bitnr), regsize=regsize, cpus=cpus)

    def _ensure_dev_msr(self):
        """
        Make sure that device nodes for accessing MSR registers are available. Try to load the MSR
        driver if necessary.
        """

        cpus = self._cpuinfo.get_cpus()
        dev_path = Path(f"/dev/cpu/{cpus[0]}/msr")
        if FSHelpers.exists(dev_path, self._proc):
            return

        msg = f"file '{dev_path}' is not available{self._proc.hostmsg}\nIf you are running a " \
              f"custom kernel, ensure your kernel has the module-specific register support " \
              f"(CONFIG_X86_MSR) enabled."
        try:
            self._msr_drv = KernelModule.KernelModule(self._proc, "msr")
            loaded = self._msr_drv.is_loaded()
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

        if loaded:
            raise Error(msg)

        try:
            self._msr_drv.load()
            self._loaded_by_us = True
            FSHelpers.wait_for_a_file(dev_path, timeout=1, proc=self._proc)
        except Error as err:
            raise Error(f"{msg}\n{err}") from err

    def __init__(self, proc=None, cpuinfo=None):
        """
        The class constructor. The arguments are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
        """

        if not proc:
            proc = Procs.Proc()
        self._proc = proc
        self._cpuinfo = cpuinfo
        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(proc=self._proc)

        self._msr_drv = None
        self._loaded_by_us = False

        self._ensure_dev_msr()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_msr_drv", None) and self._loaded_by_us:
            self._msr_drv.unload()
            self._msr_drv = None
        if getattr(self, "_proc", None):
            self._proc = None
        if getattr(self, "_cpuinfo", None):
            self._cpuinfo.close()
            self._cpuinfo = None

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
