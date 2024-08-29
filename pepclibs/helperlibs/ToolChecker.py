# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of checking if a tool is installed on a Linux host, and generate a meaningful
suggestion if the OS package is not installed.
"""

import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs.Exceptions import ErrorNotFound
from pepclibs.helperlibs import ClassHelpers

_LOG = logging.getLogger()

#
# The tools information dictionary. Map tool names to OS package names.
#

# Common for CentOS, Fedora, RHEL, Debian, and Ubuntu.
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

# CentOS, Fedora, RHEL.
_FEDORA_PKGINFO = {
    "tc"         : "iproute-tc",
    "bpftool"    : "bpftool",
    "libbpf"     : "libbpf-devel",
    "sch_etf.ko" : "kernel-modules-extra",
}

# Ubuntu.
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
    "fedora"  : _FEDORA_PKGINFO,
    "centos"  : _FEDORA_PKGINFO,
    "rhel"    : _FEDORA_PKGINFO,
    "ubuntu"  : _UBUNTU_PKGINFO,
    "debian"  : _DEBIAN_PKGINFO,
}

class ToolChecker(ClassHelpers.SimpleCloseContext):
    """
    Provide a capability of checking if a tool is installed on a Linux host, and generate a
    meaningful suggestion if the OS package is not installed.
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

                        osinfo[split_line[0]] = split_line[1].strip("\"")
            if osinfo:
                break

        if not osinfo:
            files = "\n".join([str(path) for path in paths])
            raise ErrorNotFound(f"cannot discover OS information{self._pman.hostmsg}, these files "
                                f"were checked:\n{files}")

        return osinfo

    def _get_osinfo(self):
        """Return the OS information dictionary."""

        if not self._osinfo:
            self._osinfo = self._read_os_release()
        return self._osinfo

    def get_osname(self):
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

    def get_osid(self):
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

    def tool_to_pkg(self, tool, osid=None):
        """
        Get OS package name by tool name. The arguments are as follows.
          * tool - name of the tool to get OS package name for.
          * osid - optional OS ID (will be automatically discovered by default).

        Return name of the OS package that provids 'tool'. Return 'None' if package name is was not
        found.
        """

        if not osid:
            osid = self.get_osid()

        if osid not in _PKGINFO:
            return None

        return _PKGINFO[osid].get(tool)

    def check_tool(self, tool):
        """
        Check if tool 'tool' is available on the target system. Return tool path if it is available,
        raise an 'ErrorNotFound' exception otherwise.
        """

        if tool is self._cache:
            return self._cache[tool]

        path = self._pman.which(tool, must_find=False)
        if path:
            self._cache[tool] = path
            return path

        msg = f"failed to find tool '{tool}'{self._pman.hostmsg}"

        osid = self.get_osid()

        pkgname = self.tool_to_pkg(Path(tool).name, osid=osid)
        if pkgname:
            osname = self.get_osname()
            msg += f".\nTry to install {osname} OS package '{pkgname}'{self._pman.hostmsg}."

        raise ErrorNotFound(msg)

    def __init__(self, pman):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to check for the tools on.
        """

        self._pman = pman
        self._osinfo = None
        # Tools name to tool path cache.
        self._cache = {}

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_pman",))
