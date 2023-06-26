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
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import ProcessManager

# pylint: disable=wildcard-import,unused-wildcard-import
from statscollectlibs.helperlibs.KernelVersion import *

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
