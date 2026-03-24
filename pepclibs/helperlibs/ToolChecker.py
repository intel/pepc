# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of checking if a tool is installed on a Linux host, and generate a meaningful
suggestion if the OS package is not installed.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import Logging, ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Final
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# Common for CentOS, Fedora, RHEL, Debian, and Ubuntu.
_COMMON_PKGINFO: Final[dict[str, str]] = {
    "cat":       "coreutils",
    "cc":        "gcc",
    "clang":     "clang",
    "find":      "findutils",
    "depmod":    "kmod",
    "dmesg":     "util-linux",
    "gcc":       "gcc",
    "libelf":    "elfutils-libelf-devel",
    "lscpu":     "util-linux",
    "lspci":     "pciutils",
    "make":      "make",
    "modprobe":  "kmod",
    "phc2sys":   "linuxptp",
    "rmmod":     "kmod",
    "rsync":     "rsync",
    "sync":      "coreutils",
    "systemctl": "systemd",
    "xargs":     "findutils",
}

# CentOS, Fedora, RHEL.
_FEDORA_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute-tc",
    "bpftool":    "bpftool",
    "libbpf":     "libbpf-devel",
    "sch_etf.ko": "kernel-modules-extra",
}

# Ubuntu.
_UBUNTU_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute2",
    "bpftool":    "linux-tools-common",
    "libbpf":     "libbpf-dev",
    "sch_etf.ko": "linux-modules",
}

# Debian.
_DEBIAN_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute2",
    "bpftool":    "bpftool",
    "libbpf":     "libbpf-dev",
    "sch_etf.ko": "linux-modules",
}

#
# The tools information dictionary. Map tool names to OS package names.
#
_PKGINFO: Final[dict[str, dict[str, str]]] = {
    "fedora": _FEDORA_PKGINFO,
    "centos": _FEDORA_PKGINFO,
    "rhel":   _FEDORA_PKGINFO,
    "ubuntu": _UBUNTU_PKGINFO,
    "debian": _DEBIAN_PKGINFO,
}

class ToolChecker(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of checking if a tool is installed on a Linux host, and generate a
    meaningful suggestion if the OS package is not installed.
    """

    def __init__(self, pman: ProcessManagerType):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the host to check for the tools on.
        """

        self._pman = pman
        self._osinfo: dict[str, str] = {}
        # Tools name to tool path cache.
        self._cache: dict[str, Path] = {}

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_pman",))

    def _read_os_release(self, sysroot: str = "/") -> dict[str, str]:
        """
        Read and parse the '/etc/os-release' file, and return its contents as a dictionary.

        Args:
            sysroot: The system root directory to use when locating the os-release file.

        Returns:
            A dictionary containing the OS information from the os-release file.
        """

        path_strs = ("/usr/lib/os-release", "/etc/os-release")
        paths = [Path(sysroot) / path.lstrip("/") for path in path_strs]
        osinfo: dict[str, str] = {}

        for path in paths:
            with contextlib.suppress(Error):
                with self._pman.open(path, "r") as fobj:
                    for line in fobj:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("#"):
                            continue

                        split_line = line.split("=")
                        if len(split_line) != 2:
                            _LOG.warning("Unexpected line in '%s'%s:\n%s\nExpected lines have have "
                                         "'key=value' format.", path, self._pman.hostmsg, line)
                            continue

                        osinfo[split_line[0]] = split_line[1].strip("\"")
            if osinfo:
                break

        if not osinfo:
            files = "\n".join([str(path) for path in paths])
            raise ErrorNotFound(f"Cannot discover OS information{self._pman.hostmsg}, these files "
                                f"were checked:\n{files}")

        return osinfo

    def _get_osinfo(self) -> dict[str, str]:
        """Return the OS information dictionary."""

        if not self._osinfo:
            self._osinfo = self._read_os_release()
        return self._osinfo

    def get_osname(self) -> str:
        """
        Return name of the OS running on the target system. The name is read from the
        '/etc/os-release' file. Return '<unknown_OS_NAME>' if OS name could not be determined.
        """

        try:
            osinfo = self._get_osinfo()
        except ErrorNotFound as err:
            _LOG.debug(err)
            return "<unknown_OS_NAME>"

        if "NAME" in osinfo:
            return osinfo["NAME"]
        if "ID" in osinfo:
            return osinfo["ID"].capitalize()
        return "<unknown_OS_NAME>"

    def get_osid(self) -> str:
        """
        Return ID of the OS running on the target system. The ID is read from the
        '/etc/os-release' file. Return '<unknown_OS_ID>' if OS ID could not be determined.
        """

        try:
            osinfo = self._get_osinfo()
        except ErrorNotFound as err:
            _LOG.debug(err)
            return "<unknown_OS_ID>"

        if "ID" in osinfo:
            return osinfo["ID"]

        return "<unknown_OS_ID>"

    def tool_to_pkg(self, tool: str, osid: str = "") -> str:
        """
        Get OS package name by tool name.

        Args:
            tool: Name of the tool to get OS package name for.
            osid: Optional OS ID (will be automatically discovered by default).

        Returns:
            Name of the OS package that provides 'tool'. Return an empty string if package name was
            not found.
        """

        if not osid:
            osid = self.get_osid()

        if osid not in _PKGINFO:
            return ""

        return _PKGINFO[osid].get(tool, "")

    def check_tool(self, tool: str) -> Path:
        """
        Check if tool 'tool' is available on the target system. Return tool path if it is available,
        raise an 'ErrorNotFound' exception otherwise.

        Args:
            tool: Name of the tool to check for.

        Returns:
            Path to the tool if it is available.
        """

        if tool is self._cache:
            return self._cache[tool]

        path = self._pman.which(tool, must_find=False)
        if path:
            self._cache[tool] = path
            return path

        msg = f"Failed to find tool '{tool}'{self._pman.hostmsg}"

        osid = self.get_osid()

        pkgname = self.tool_to_pkg(Path(tool).name, osid=osid)
        if pkgname:
            osname = self.get_osname()
            msg += f".\nTry to install the '{osname}' OS package '{pkgname}'{self._pman.hostmsg}."

        raise ErrorNotFound(msg)
