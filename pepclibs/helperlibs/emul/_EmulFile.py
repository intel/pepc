# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Adam Hawley <adam.james.hawley@intel.com>

"""Provide the factory function to create emulated file objects."""

from pathlib import Path
from pepclibs.helperlibs.emul import _ROFile, _RWFile

def get_emul_file(finfo, datapath, basepath, module=None):
    """
    Create and return an emulated file object representing the file described by the file
    information dictionary 'finfo'. Arguments are as follows:
     * finfo - file information dictionary which describes the file to be emulated.
     * datapath - path to the directory containing data which is used for emulation.
     * basepath - The basepath is a
                      path to the directory where emulated files should be created.
     * module - the name of the module which the file is a part of.
    """

    path = Path(finfo["path"])
    if "data" in finfo:
        data = finfo["data"]
    else:
        src = datapath / module / finfo["path"].lstrip("/")
        with open(src, "r", encoding="utf-8") as fobj:
            data = fobj.read()

    if finfo.get("readonly", False):
        if finfo["path"].endswith("cpu/online"):
            return _ROFile.ROSysfsFile(path, basepath, data)
        else:
            return _ROFile.ROFile(path, basepath, data)
    else:
        if finfo["path"].startswith("/sys/"):
            return _RWFile.RWSysinfoFile(path, basepath, data)
        else:
            return _RWFile.RWFile(path, basepath, data)
