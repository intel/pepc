# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide functions for obtaining, splitting and comparing Linux kernel version numbers.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import re
import typing
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ProcessManager

if typing.TYPE_CHECKING:
    from typing import TypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class SplitKernelVersionTypedDict(TypedDict):
        """
        Split kernel version components.

        Attributes:
            major: Major version number (e.g., 4 in "4.18.1").
            minor: Minor version number (e.g., 18 in "4.18.1").
            stable: Stable version number (e.g., 1 in "4.18.1"). If not present, it is 0.
            rc: Release candidate version number (e.g., 2 in "5.0-rc2"). If not present, it is 0.
            localver: Local version string (e.g., "-build0" in "4.18.1-build0"). An empty string if
                      not present.
        """
        major: int
        minor: int
        stable: int
        rc: int
        localver: str

def _fetch_rc(localver: str) -> tuple[int, str]:
    """
    Extract the release candidate version from local version string.

    Args:
        localver: The local version string to parse (e.g., "-rc2-custom" or "-build0").

    Returns:
        A tuple containing:
            - rc: The RC number (0 if not found).
            - remaining_localver: The localver string with RC pattern removed.

    Examples:
        >>> _fetch_rc("-rc2-custom")
        (2, "-custom")
        >>> _fetch_rc("-build0")
        (0, "-build0")
        >>> _fetch_rc("")
        (0, "")
    """

    matchobj = re.match(r"-rc(\d+)(.*)", localver)
    if matchobj:
        return int(matchobj.group(1)), matchobj.group(2)
    return 0, localver

def split_kver(kver: str) -> SplitKernelVersionTypedDict:
    """
    Split a kernel version string into its components.

    Args:
        kver: The kernel version string to parse (e.g., "5.10.1-rc2-custom").

    Returns:
        The split kernel version components as a SplitKernelVersionTypedDict.

    Examples:
        >>> split_kver("4.18.1-build0")
        {"major": 4, "minor": 18, "stable": 1, "rc": 0, "localver": "-build0"}
        >>> split_kver("5.0-rc2")
        {"major": 5, "minor": 0, "stable": 0, "rc": 2, "localver": ""}
        >>> split_kver("6.1")
        {"major": 6, "minor": 1, "stable": 0, "rc": 0, "localver": ""}
    """

    matchobj = re.match(r"^(\d+)\.(\d+)(?:(?:\.(\d+)){0,1}(.*)){0,1}", kver)
    if not matchobj:
        raise Error(f"Failed to parse kernel version string '{kver}'")

    major, minor, stable, localver = matchobj.group(1, 2, 3, 4)
    if stable is None:
        stable = 0
    rc, localver = _fetch_rc(localver)
    major = int(major)
    minor = int(minor)
    stable = int(stable)

    return {"major": major,
            "minor": minor,
            "stable": stable,
            "rc": rc,
            "localver": localver}


def _lt_rc(rc1: int, rc2: int) -> bool:
    """
    Compares two RC numbers. RC value 0 indicates a final release (no RC), which is considered newer
    than any RC version.

    Args:
        rc1: First RC number (0 for final release, positive integer for RC).
        rc2: Second RC number (0 for final release, positive integer for RC).

    Returns:
        bool: True if 'rc1' is older than 'rc2'.

    Examples:
        >>> _lt_rc(1, 2)
        True
        >>> _lt_rc(1, 0)
        True
    """

    if rc1 == 0 and rc2 == 0:
        # Both are final releases, equal.
        return False
    if rc1 == 0:
        # rc1 is final (newer), rc2 is RC (older).
        return False
    if rc2 == 0:
        # rc1 is RC (older), rc2 is final (newer).
        return True

    return rc1 < rc2

def kver_lt(kver1: str, kver2: str) -> bool:
    """
    Compare two kernel version strings for less-than relationship.

    Args:
        kver1: First kernel version string to compare (e.g., "5.10.1").
        kver2: Second kernel version string to compare (e.g., "5.10.2").

    Returns:
        bool: True if kver1 is older than kver2, False otherwise.

    Examples:
        >>> kver_lt("5.10.1", "5.10.2")
        True
        >>> kver_lt("5.10.2", "5.10.1")
        False
        >>> kver_lt("5.10-rc1", "5.10.0")
        True
        >>> kver_lt("5.10.0", "5.10-rc1")
        False
    """

    kver1_split = split_kver(kver1)
    kver2_split = split_kver(kver2)

    if kver1_split["major"] != kver2_split["major"]:
        return kver1_split["major"] < kver2_split["major"]
    if kver1_split["minor"] != kver2_split["minor"]:
        return kver1_split["minor"] < kver2_split["minor"]
    if kver1_split["stable"] != kver2_split["stable"]:
        return kver1_split["stable"] < kver2_split["stable"]
    if kver1_split["rc"] != kver2_split["rc"]:
        return _lt_rc(kver1_split["rc"], kver2_split["rc"])
    return kver1_split["localver"] < kver2_split["localver"]

def kver_ge(kver1: str, kver2: str) -> bool:
    """
    Compare two kernel version strings for greater-than-or-equal relationship.

    Args:
        kver1: First kernel version string to compare (e.g., "5.10.1").
        kver2: Second kernel version string to compare (e.g., "5.10.2").

    Returns:
        bool: True if kver1 is newer than or equal to kver2, False otherwise.

    Examples:
        >>> kver_ge("5.10.2", "5.10.1")
        True
        >>> kver_ge("5.10.1", "5.10.2")
        False
        >>> kver_ge("5.10.0", "5.10-rc1")
        True
        >>> kver_ge("5.10-rc1", "5.10.0")
        False
        >>> kver_ge("5.10.1", "5.10.1")
        True
    """

    return not kver_lt(kver1, kver2)

def get_kver(pman: ProcessManagerType | None = None) -> str:
    """
    Retrieve the kernel version string from the currently running kernel on the host associated with
    'pman'.

    Args:
        pman: A process manager object for the target host. If not provided, a local process manager
              will be used.

    Returns:
        str: Kernel version string (e.g., "5.10.1-build0", "6.1.0-rc2").

    Examples:
        >>> get_kver()  # Local host
        "5.15.0-76-generic"
        >>> get_kver(remote_pman)  # Remote host
        "6.1.0-rc1"
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        proc_version = Path("/proc/version")

        try:
            with wpman.open(proc_version, "r") as fobj:
                contents = fobj.read()
        except Error as err:
            raise type(err)(f"Failed to read '{proc_version}'{wpman.hostmsg}:\n"
                            f"{err.indent(2)}") from err

        # Format: "Linux version <kver> (...)".
        parts = contents.split()
        if len(parts) < 3 or parts[0] != "Linux" or parts[1] != "version":
            raise Error(f"Failed to parse kernel version from '{proc_version}'{wpman.hostmsg}:\n"
                        f"  {contents.strip()!r}")

        return parts[2]

def get_kver_ktree(ktree: Path,
                   pman: ProcessManagerType | None = None,
                   makecmd: str = "") -> str:
    """
    Retrieve the kernel version from a configured kernel source tree or build directory. The kernel
    sources must be already configured (e.g., '.config' file must exist). Supports both in-tree and
    out-of-tree builds.

    Args:
        ktree: Path to the kernel source directory or build directory (for out-of-tree builds
               created with 'make O=<ktree>').
        pman: A process manager object for the target host. If not provided, a local process manager
              will be used.
        makecmd: Custom make command prefix to use instead of 'make -C <ktree>'.

    Returns:
        str: Kernel version string (e.g., '5.10.1-custom', '6.1.0-rc2').
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        if not makecmd:
            makecmd = f"make -C '{ktree}'"
        cmd = makecmd + " --quiet -- kernelrelease"

        try:
            kver = wpman.run_verify_join(cmd)[0].strip()
        except Error as err:
            raise type(err)(f"Cannot detect kernel version in '{ktree}':\n{err.indent(2)}\n"
                            f"Make sure kernel sources are configured.") from err

    return kver

def get_kver_bin(path: Path, pman: ProcessManagerType | None = None) -> str:
    """
    Extract the kernel version from a compiled kernel binary (e.g., vmlinux, bzImage) by using the
    'file' command and parsing its output. The binary must be a valid Linux kernel executable.

    Args:
        path: Path object pointing to the kernel binary file.
        pman: Process manager for the target host. If None, uses the local host.

    Returns:
        str: Kernel version string extracted from the binary (e.g., '5.10.1', '6.1.0-rc2').
    """

    cmd = f"file -- {path}"

    with ProcessManager.pman_or_local(pman) as wpman:
        stdout = wpman.run_verify_join(cmd)[0].strip()

        msg = f"Ran this command: {cmd}, got output:\n{stdout}"

        matchobj = re.match(r".* Linux kernel.* executable[ ,].*", stdout)
        if not matchobj:
            raise Error(f"File at '{path}'{wpman.hostmsg} is not a Linux kernel binary file\n{msg}")

    matchobj = re.match(r".* version ([^ ]+) .*", stdout)
    if not matchobj:
        raise Error(f"{msg}\nFailed to find kernel version in the output")

    kver = matchobj.group(1)
    return kver
