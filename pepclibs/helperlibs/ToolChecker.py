# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a capability of checking if a tool is installed on a Linux host and providing a
meaningful OS package installation suggestion if it is not installed.
"""

import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from pepclibs.helperlibs import ClassHelpers

_LOG = logging.getLogger()

#
# Tools information dictionary. Maps tool names to OS package names.
#

# Common for CentOS, Fedora, Debian, and Ubuntu.
_COMMON_PKGINFO = {
    "cat"       : "coreutils",
    "cc"        : "gcc",
    "clang"     : "clang",
    "find"      : "findutils",
    "depmod"    : "kmod",
    "dmesg"     : "util-linux",
    "gcc"       : "gcc",
    "libelf"    : "elfutils-libelf-devel",
    "lscpu"     : "util-linux",
    "lspci"     : "pciutils",
    "make"      : "make",
    "modprobe"  : "kmod",
    "phc2sys"   : "linuxptp",
    "rmmod"     : "kmod",
    "rsync"     : "rsync",
    "sync"      : "coreutils",
    "systemctl" : "systemd",
    "xargs"     : "findutils",
}

# CentOS and Fedora
_FEDORA_PKGINFO = {
    "tc"         : "iproute-tc",
    "bpftool"    : "bpftool",
    "libbpf"     : "libbpf-devel",
    "sch_etf.ko" : "kernel-modules-extra",
}

# Ubuntu
_UBUNTU_PKGINFO = {
    "tc"         : "iproute2",
    "bpftool"    : "linux-tools-common",
    "libbpf"     : "libbpf-dev",
    "sch_etf.ko" : "linux-modules",
}

# Debian.
_DEBIAN_PKGINFO = {
    "tc"         : "iproute2",
    "bpftool"    : "bpftool",
    "libbpf"     : "libbpf-dev",
    "sch_etf.ko" : "linux-modules",
}

_FEDORA_PKGINFO.update(_COMMON_PKGINFO)
_UBUNTU_PKGINFO.update(_COMMON_PKGINFO)
_DEBIAN_PKGINFO.update(_COMMON_PKGINFO)

_PKGINFO = {
    "Fedora Linux"     : _FEDORA_PKGINFO,
    "CentOS Linux"     : _FEDORA_PKGINFO,
    "CentOS Stream"    : _FEDORA_PKGINFO,
    "Ubuntu"           : _UBUNTU_PKGINFO,
    "Debian GNU/Linux" : _DEBIAN_PKGINFO,
}

class ToolChecker(ClassHelpers.SimpleCloseContext):
    """
    This class provides a capability of checking if a tool is installed on a Linux host and
    providing a meaningful suggestion if it is not installed.
    """

    def _read_os_release(self, sysroot="/"):
        """
        Read and parse the '/etc/os-release' file, and return its contents as a dictionary.
        """

        paths = ("/usr/lib/os-release", "/etc/os-release")
        paths = [Path(sysroot) / path.lstrip("/") for path in paths]
        osinfo = {}

        for path in paths:
            with contextlib.suppress(self._pman.Error):
                with self._pman.open(path, "r") as fobj:
                    for line in fobj:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("#"):
                            continue

                        split_line = line.split("=")
                        if len(split_line) != 2:
                            _LOG.warning("unexpected line in '%s'%s:\n%s\nExpected lines have have "
                                         "'key=value' format.", path, self._pman.hostmsg, line)
                            continue

                        osinfo[split_line[0]] = split_line[1].strip('"')
            if osinfo:
                break

        if not osinfo:
            files = "\n".join([str(path) for path in paths])
            raise Error(f"cannot discover OS version{self._pman.hostmsg}, these files were "
                        f"checked:\n{files}")

        return osinfo

    def get_osname(self):
        """Returns the OS name of the SUT."""

        if self._osname:
            return self._osname

        osinfo = self._read_os_release()
        osname = osinfo.get("NAME")

        if osname == "Fedora":
            # Prior to Fedora 35, the OS name was "Fedora". In Fedora 35, it changed to "Fedora
            # Linux".
            osname = "Fedora Linux"

        return osname

    def tool_to_pkg(self, tool, osname=None):
        """
        Get OS package name by tool name. The arguments are as follows.
          * tool - name of the tool to get OS package name for.
          * osname - optional OS name (will be automatically discovered by default)

        Returns the OS package name providing 'tool'. Returns 'None' if package name is was not
        found.
        """

        if not osname:
            osname = self.get_osname()

        if osname not in _PKGINFO:
            return None

        return _PKGINFO[osname].get(tool)

    def check_tool(self, tool):
        """
        Check if tool 'tool' is available on the SUT. Returns tool path if it is available, raises
        an 'ErrorNotFound' exception otherwise.
        """

        if tool is self._cache:
            return self._cache[tool]

        path = self._pman.which(tool, must_find=False)
        if path:
            self._cache[tool] = path
            return path

        msg = f"failed to find tool '{tool}'{self._pman.hostmsg}"

        osname = self.get_osname()

        pkgname = self.tool_to_pkg(Path(tool).name, osname=osname)
        if pkgname:
            msg += f".\nTry to install {osname} package '{pkgname}'{self._pman.hostmsg}."

        raise ErrorNotFound(msg)

    def __init__(self, pman):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to check for the tools on.
        """

        self._pman = pman
        self._osname = None
        # Tools name to tool path cache.
        self._cache = {}

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_pman",))
