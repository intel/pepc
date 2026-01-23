# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

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
        Type for the '/proc/cpuinfo' information dictionary.

        Attributes:
            vendor_name: The CPU vendor name (e.g., "GenuineIntel").
            vendor: The CPU vendor ID.
            family: The CPU family number.
            model: The CPU model number.
            modelname: The full name of the CPU model.
            flags: A dictionary mapping CPU numbers to their flags.
            vfm: The vendor-family-model identifier for the CPU.
            topology: A dictionary representing the CPU topology ({package: {core: [CPUs]}).
        """

        vendor_name: str
        vendor: int
        family: int
        model: int
        modelname: str
        flags: dict[int, set[str]]
        vfm: int
        topology: dict[int, dict[int, list[int]]]

def _parse_cpuinfo_block(block: str, info: ProcCpuinfoTypedDict):
    """
    Parse a single CPU information block from '/proc/cpuinfo' and update the provided information
    dictionary.

    Args:
        block: The CPU information block to parse.
        info: The dictionary to update with parsed CPU information.
    """

    cpu = core = package = -1
    flags = set()

    # General CPU information is the same for all CPUs, parse it only once.
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

    if package not in info["topology"]:
        info["topology"][package] = {}
    if core not in info["topology"][package]:
        info["topology"][package][core] = []
    info["topology"][package][core].append(cpu)

    info["flags"][cpu] = flags

def get_proc_cpuinfo(pman: ProcessManagerType | None = None) -> ProcCpuinfoTypedDict:
    """
    Collect and return CPU information from '/proc/cpuinfo'.

    Args:
        pman: The process manager object for the target host. If not provided, a local process
              manager is created.

    Returns:
        ProcCpuinfoTypedDict: The '/proc/cpuinfo' information dictionary.
    """

    proc_cpuinfo: ProcCpuinfoTypedDict = {"topology": {}, "flags": {}}

    with ProcessManager.pman_or_local(pman) as wpman:
        for block in wpman.read_file("/proc/cpuinfo").strip().split("\n\n"):
            _parse_cpuinfo_block(block, proc_cpuinfo)

    proc_cpuinfo["vfm"] = CPUModels.make_vfm(proc_cpuinfo["vendor"], proc_cpuinfo["family"],
                                             proc_cpuinfo["model"])

    return proc_cpuinfo
