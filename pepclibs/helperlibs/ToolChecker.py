# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>

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
    from typing import Final, Iterable
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
    "git":       "git",
    "id":        "coreutils",
    "libelf":    "elfutils-libelf-devel",
    "lscpu":     "util-linux",
    "lspci":     "pciutils",
    "make":      "make",
    "modprobe":  "kmod",
    "phc2sys":   "linuxptp",
    "pip3":      "python3-pip",
    "rm":        "coreutils",
    "rmmod":     "kmod",
    "rsync":     "rsync",
    "sync":      "coreutils",
    "systemctl": "systemd",
    "uname":     "coreutils",
    "unlink":    "coreutils",
    "xargs":     "findutils",
}

# CentOS, Fedora, RHEL.
_FEDORA_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute-tc",
    "bpftool":    "bpftool",
    "libbpf":     "libbpf-devel",
    "pgrep":      "procps-ng",
    "ps":         "procps-ng",
    "sch_etf.ko": "kernel-modules-extra",
    "virtualenv": "python3-virtualenv",
}

# Ubuntu.
_UBUNTU_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute2",
    "bpftool":    "linux-tools-common",
    "libbpf":     "libbpf-dev",
    "pgrep":      "procps",
    "ps":         "procps",
    "sch_etf.ko": "linux-modules",
    "virtualenv": "python3-venv",
}

# Debian.
_DEBIAN_PKGINFO: Final[dict[str, str]] = {
    **_COMMON_PKGINFO,
    "tc":         "iproute2",
    "bpftool":    "bpftool",
    "libbpf":     "libbpf-dev",
    "pgrep":      "procps",
    "ps":         "procps",
    "sch_etf.ko": "linux-modules",
    "virtualenv": "python3-venv",
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

# Maps OS IDs to the package manager installer command.
_PKG_INSTALLER: Final[dict[str, str]] = {
    "fedora": "dnf",
    "centos": "dnf",
    "rhel":   "dnf",
    "ubuntu": "apt",
    "debian": "apt",
}

# Maps supported OS IDs to human-readable OS names.
SUPPORTED_OSIDS: Final[dict[str, str]] = {
    "fedora": "Fedora",
    "centos": "CentOS",
    "rhel":   "Red Hat Enterprise Linux",
    "ubuntu": "Ubuntu",
    "debian": "Debian",
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

                        split_line = line.split("=", 1)
                        if len(split_line) != 2:
                            _LOG.warning("Unexpected line in '%s'%s:\n%s\nExpected lines have "
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

    def get_os_name(self) -> str:
        """
        Return name of the OS running on the target system. The name is read from the
        '/etc/os-release' file. Examples: 'Fedora Linux', 'Ubuntu', 'Debian GNU/Linux'.

        Raises:
            ErrorNotFound: If the OS name could not be determined.
        """

        osinfo = self._get_osinfo()

        if "NAME" in osinfo:
            return osinfo["NAME"]
        if "ID" in osinfo:
            return osinfo["ID"].capitalize()

        raise ErrorNotFound(f"Cannot determine OS name{self._pman.hostmsg}.")

    def get_osid(self) -> str:
        """
        Return ID of the OS running on the target system. The ID is read from the
        '/etc/os-release' file. Examples: 'fedora', 'ubuntu', 'debian'.

        Raises:
            ErrorNotFound: If the OS ID could not be determined.
        """

        osinfo = self._get_osinfo()

        if "ID" in osinfo:
            return osinfo["ID"]

        raise ErrorNotFound(f"Cannot determine OS ID{self._pman.hostmsg}.")

    def tool_to_pkg(self, tool: str, osid: str = "") -> str:
        """
        Get OS package name by tool name.

        Args:
            tool: Name of the tool to get OS package name for.
            osid: Optional OS ID (will be automatically discovered by default).

        Returns:
            Name of the OS package that provides 'tool'.

        Raises:
            ErrorNotFound: If the package name could not be found, or if 'osid' is not provided
                           and the OS ID could not be determined.
        """

        if not osid:
            osid = self.get_osid()

        if osid not in _PKGINFO:
            raise ErrorNotFound(f"Cannot find OS package for tool '{tool}'{self._pman.hostmsg}: "
                                f"Unsupported OS '{osid}'.")

        pkg = _PKGINFO[osid].get(tool, "")
        if not pkg:
            raise ErrorNotFound(f"Cannot find OS package for tool '{tool}'{self._pman.hostmsg}")

        return pkg

    def check_tool(self, tool: str) -> Path:
        """
        Check if tool 'tool' is available on the target system.

        Args:
            tool: Name of the tool to check for.

        Returns:
            Path to the tool.

        Raises:
            ErrorNotFound: The tool is not found on the target system.
        """

        if tool in self._cache:
            return self._cache[tool]

        path = self._pman.which_or_none(tool)
        if path:
            self._cache[tool] = path
            return path

        msg = f"Failed to find tool '{tool}'{self._pman.hostmsg}."

        with contextlib.suppress(ErrorNotFound):
            osid = self.get_osid()
            pkgname = self.tool_to_pkg(Path(tool).name, osid=osid)
            osname = self.get_os_name()
            cmd = self.get_os_packages_install_cmd([pkgname], osid=osid)
            msg += f"\nTry to install the '{osname}' OS package '{pkgname}' using the " \
                   f"following command{self._pman.hostmsg}:\n{cmd}"

        raise ErrorNotFound(msg)

    def get_os_packages_install_cmd(self, pkgnames: Iterable[str], osid: str = "") -> str:
        """
        Return the OS command for installing the given packages on the target system.

        Args:
            pkgnames: Names of the OS packages to install.
            osid: Optional OS ID (will be automatically discovered by default).

        Returns:
            The install command string, e.g. 'dnf install pkg1 pkg2'. Returns an empty string if
            the OS is not recognized.

        Raises:
            ErrorNotFound: If 'osid' is not provided and the OS ID could not be determined.
        """

        if not osid:
            osid = self.get_osid()

        installer = _PKG_INSTALLER.get(osid, "")
        if not installer:
            return ""

        return f"{installer} install -y {' '.join(pkgnames)}"

    def ensure_tools_available(self, tools: Iterable[str]):
        """
        Ensure that the specified tools are available on the target system.

        Args:
            tools: An iterable of tool names to check for.
        """

        packages: set[str] = set()
        missed_tools: list[str] = []

        for tool in tools:
            try:
                self.check_tool(tool)
            except ErrorNotFound:
                try:
                    packages.add(self.tool_to_pkg(tool))
                except ErrorNotFound:
                    missed_tools.append(tool)

        if missed_tools:
            raise ErrorNotFound(f"Failed to determine OS packages for the following tools"
                                f"{self._pman.hostmsg}:\n{', '.join(missed_tools)}")

        if packages:
            cmd = self.get_os_packages_install_cmd(packages)
            _LOG.info("Installing OS packages by running%s:\n%s", self._pman.hostmsg, cmd)
            try:
                self._pman.run_verify(cmd, su=True)
            except Error as err:
                raise type(err)(f"Failed to install OS packages{self._pman.hostmsg}:\n"
                                f"{err}") from err
