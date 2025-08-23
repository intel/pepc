# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Adam Hawley <adam.james.hawley@intel.com>

"""Provide the factory function to create emulated file objects."""

from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.emul import _ROFile, _RWFile

def get_emul_file(finfo, datapath, get_basepath, module=None):
    """
    Create and return an emulated file object representing the file described by the file
    information dictionary 'finfo'. Arguments are as follows:
     * finfo - file information dictionary which describes the file to be emulated.
     * datapath - path to the directory containing data which is used for emulation.
     * get_basepath - a function which can be called to access the basepath. The basepath is a
                      path to the directory where emulated files should be created.
     * module - the name of the module which the file is a part of.
    """

    basepath = get_basepath()

    emul = None
    if finfo.get("readonly", False):
        if finfo["path"].endswith("cpu/online"):
            emul = _ROFile.ROSysfsFile(finfo, datapath, basepath, module)
        else:
            emul = _ROFile.ROFile(finfo, datapath, basepath, module)
    else:
        if finfo["path"].startswith("/sys/"):
            emul = _RWFile.RWSysinfoFile(finfo, datapath, basepath, module)
        else:
            emul = _RWFile.RWFile(finfo, datapath, basepath, module)

    if emul is None:
        raise Error(f"BUG: emulation of file '{finfo['path']}' is not supported")

    return emul
