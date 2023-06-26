# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains helper functions for dealing with Linux kernel version numbers.
"""

import re
from collections import namedtuple
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ProcessManager

# The resource owner information namedtuple "type".
SplitKver = namedtuple("SplitKver", ["major", "minor", "stable", "rc", "localver"])

def split_kver(kver, numerical=False):
    """
    Split the kernel version string on the components: major, minor, stable, rc, localver. For
    example, '4.18.1-build0' would be ('4', '18', '1', None, '-build0'), and '5.0-rc2' would be
    ('5', '0', 0, '2', ''). By default the numeric parts of the version are returned as strings, but
    if the 'numerical' argument is 'True', they are returned as integers.
    """

    def _fetch_rc(localver):
        """Fetch the release candidate version number from the local version."""

        matchobj = re.match(r"-rc(\d+)(.*)", localver)
        if matchobj:
            return matchobj.group(1, 2)
        return (None, localver)

    matchobj = re.match(r"^(\d+)\.(\d+)(?:(?:\.(\d+)){0,1}(.*)){0,1}", kver)
    if not matchobj:
        raise Error(f"failed to parse kernel version string '{kver}'")

    major, minor, stable, localver = matchobj.group(1, 2, 3, 4)
    if stable is None:
        stable = 0
    rc, localver = _fetch_rc(localver)
    if numerical:
        major = int(major)
        minor = int(minor)
        stable = int(stable)
        if rc is not None:
            rc = int(rc)

    return SplitKver(major, minor, stable, rc, localver)

def kver_lt(kver1, kver2):
    """
    Return 'True' if kernel version string 'kver1' is smaller than kernel version string 'kver2'
    (kernel version 'kver1' is older than kernel version 'kver2').
    """

    def _lt(a, b):
        if a is None:
            return False
        if b is None:
            return True
        return a < b

    major1, minor1, stable1, rc1, localver1 = split_kver(kver1, numerical=True)
    major2, minor2, stable2, rc2, localver2 = split_kver(kver2, numerical=True)

    if major1 != major2:
        return major1 < major2
    if minor1 != minor2:
        return minor1 < minor2
    if stable1 != stable2:
        return stable1 < stable2
    if rc1 != rc2:
        return _lt(rc1, rc2)
    return localver1 < localver2

def kver_ge(kver1, kver2):
    """
    Return 'True' if kernel version string 'kver1' is greater or equal to kernel version string
    'kver2' (kernel version 'kver1' is newer or equal to kernel version 'kver2').
    """

    return not kver_lt(kver1, kver2)

def get_kver(split=False, pman=None):
    """
    Return version of the kernel running on the host associated with the 'pman' object (local host
    by default).

    By default this function returns the kernel version string (e.g., "4.18.1-build0"), but if
    'split' is 'True', this function returns the split kernel version (refer to 'split_kver()' for
    the details).
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        kver = wpman.run_verify("uname -r")[0].strip()
        if split:
            return split_kver(kver)
        return kver

def get_kver_ktree(ktree, split=False, pman=None, makecmd=None):
    """
    Get version of the kernel in the kernel sources directory 'ktree'. The 'ktree' directory must
    contain an already configured kernel or it should be path to the kernel build directory if the
    kernel was compiled out of tree (make O=<ktree>).

    By default this function runs the 'make -C <ktree> --quiet -- kernelrelease' command to get the
    kernel version. However, you can use the 'makecmd' argument to override the 'make -C <ktree>'
    part of it.

    The 'split' and 'pman' arguments are the same as in 'get_kver()'.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        if not makecmd:
            makecmd = f"make -C '{ktree}'"
        cmd = makecmd + " --quiet -- kernelrelease"

        try:
            kver = wpman.run_verify(cmd)[0].strip()
        except Error as err:
            raise Error(f"cannot detect kernel version in '{ktree}':\n{err}\nMake sure kernel "
                        f"sources are configured.") from err

    if split:
        return split_kver(kver)
    return kver

def get_kver_bin(path, split=False, pman=None):
    """
    Get version of a kernel binary at 'path'. The 'split' and 'pman' arguments are the same as in
    'get_kver()'.
    """

    cmd = f"file -- {path}"

    with ProcessManager.pman_or_local(pman) as wpman:
        stdout = wpman.run_verify(cmd)[0].strip()

        msg = f"ran this command: {cmd}, got output:\n{stdout}"

        matchobj = re.match(r".* Linux kernel.* executable .*", stdout)
        if not matchobj:
            raise Error(f"file at '{path}'{wpman.hostmsg} is not a Linux kernel binary file\n{msg}")

    matchobj = re.match(r".* version ([^ ]+) .*", stdout)
    if not matchobj:
        raise Error(f"{msg}\nFailed to find kernel version in the output.")

    kver = matchobj.group(1)
    if split:
        return split_kver(kver)
    return kver
