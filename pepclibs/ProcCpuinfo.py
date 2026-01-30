# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Read CPU information from '/proc/cpuinfo'."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUModels
from pepclibs.helperlibs import ProcessManager, Trivial
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class ProcCpuinfoTypedDict(TypedDict, total=False):
        """
        Type for the general '/proc/cpuinfo' information dictionary. Contains CPU
        information that is the same for all CPUs and does not change.

        Attributes:
            vendor_name: The CPU vendor name (e.g., "GenuineIntel").
            vendor: The CPU vendor ID.
            family: The CPU family number.
            model: The CPU model number.
            modelname: The full name of the CPU model.
            vfm: The vendor-family-model identifier for the CPU.
        """

        vendor_name: str
        vendor: int
        family: int
        model: int
        modelname: str
        vfm: int

    class ProcCpuinfoPerCPUTypedDict(TypedDict, total=False):
        """
        Type for the per-CPU '/proc/cpuinfo' topology information dictionary. Contains
        CPU topology and flags that change when CPUs go online or offline.

        Attributes:
            flags: A dictionary mapping CPU numbers to their flags.
            topology: A dictionary representing the CPU topology ({package: {core: [CPUs]}}).
        """

        flags: dict[int, set[str]]
        topology: dict[int, dict[int, list[int]]]

def _parse_cpuinfo_block(block: str,
                         info: ProcCpuinfoTypedDict,
                         percpu_info: ProcCpuinfoPerCPUTypedDict):
    """
    Parse a single CPU information block from '/proc/cpuinfo' and update the provided information
    dictionaries.

    Args:
        block: The CPU information block to parse.
        info: The dictionary to update with general CPU information.
        percpu_info: The dictionary to update with per-CPU information.
    """

    cpu = core = package = -1
    flags = set()

    # General (static) CPU information is the same for all CPUs, parse it only once.
    parse_general = "vendor" not in info

    for line in block.split("\n"):
        key, val = line.split(":")
        key = key.strip()
        val = val.strip()

        what = f"value of '{key}' from '/proc/cpuinfo'"
        if key == "processor":
            cpu = Trivial.str_to_int(val, what=what)
        elif key == "core id":
            core = Trivial.str_to_int(val, what=what)
        elif key == "physical id":
            package = Trivial.str_to_int(val, what=what)
        elif key == "flags":
            # Collect flags for each CPU.
            flags = set(val.split())

        if not parse_general:
            continue

        if key == "vendor_id":
            info["vendor_name"] = val
            info["vendor"] = CPUModels.vendor_name_to_id(val)
        elif key == "cpu family":
            info["family"] = Trivial.str_to_int(val, what=what)
        elif key == "model":
            info["model"] = Trivial.str_to_int(val, what=what)
        elif key == "model name":
            info["modelname"] = val

    if cpu == -1 or core == -1 or package == -1:
        raise Error(f"Incomplete CPU information block in '/proc/cpuinfo': 'processor', 'core id', "
                    f"or 'physical id' is missing:\n{block}")

    if package not in percpu_info["topology"]:
        percpu_info["topology"][package] = {}
    if core not in percpu_info["topology"][package]:
        percpu_info["topology"][package][core] = []
    percpu_info["topology"][package][core].append(cpu)
    percpu_info["flags"][cpu] = flags

def get_proc_cpuinfo(pman: ProcessManagerType | None = None) -> ProcCpuinfoTypedDict:
    """
    Collect and return general CPU information from '/proc/cpuinfo'.

    This function returns CPU information that is the same for all CPUs and does not change, such
    as vendor, family, model, and VFM.

    Args:
        pman: The process manager object for the target host. If not provided, a local process
              manager is created.

    Returns:
        The general '/proc/cpuinfo' information dictionary.
    """

    proc_cpuinfo: ProcCpuinfoTypedDict = {}
    proc_percpuinfo: ProcCpuinfoPerCPUTypedDict = {"flags": {}, "topology": {}}

    with ProcessManager.pman_or_local(pman) as wpman:
        for block in wpman.read_file("/proc/cpuinfo").strip().split("\n\n"):
            _parse_cpuinfo_block(block, proc_cpuinfo, proc_percpuinfo)
            # We only need general CPU information from one block.
            break

    proc_cpuinfo["vfm"] = CPUModels.make_vfm(proc_cpuinfo["vendor"], proc_cpuinfo["family"],
                                             proc_cpuinfo["model"])
    return proc_cpuinfo

def get_proc_percpuinfo(pman: ProcessManagerType | None = None) -> ProcCpuinfoPerCPUTypedDict:
    """
    Collect and return per-CPU information from '/proc/cpuinfo'.

    This function returns CPU topology and flags that change when CPUs are hotplugged (go online
    or offline).

    Args:
        pman: The process manager object for the target host. If not provided, a local process
              manager is created.

    Returns:
        The per-CPU '/proc/cpuinfo' topology information dictionary.
    """

    proc_cpuinfo: ProcCpuinfoTypedDict = {}
    proc_percpuinfo: ProcCpuinfoPerCPUTypedDict = {"flags": {}, "topology": {}}

    with ProcessManager.pman_or_local(pman) as wpman:
        for block in wpman.read_file("/proc/cpuinfo").strip().split("\n\n"):
            _parse_cpuinfo_block(block, proc_cpuinfo, proc_percpuinfo)

    return proc_percpuinfo
