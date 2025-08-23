# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Adam Hawley <adam.james.hawley@intel.com>

"""Provide the factory function to create emulated file objects."""

from typing import Any
from pathlib import Path
from pepclibs.helperlibs.emul import _EmulFileBase, _ROFile, _RWFile, _EmulDevMSR

def get_emul_file(path: str,
                  basepath: Path,
                  data: Any = None,
                  datapath: Path | None = None,
                  readonly: bool = False,
                  module: str = ""):
    """
    Create and return an emulated file object representing the file described by the file
    information dictionary 'finfo'. Arguments are as follows:
     * finfo - file information dictionary which describes the file to be emulated.
     * basepath - The basepath is a
                      path to the directory where emulated files should be created.
     * datapath - path to the directory containing data which is used for emulation.
     * module - the name of the module which the file is a part of.
    """

    if datapath is None and data is None:
        return _EmulFileBase.EmulFileBase(Path(path), basepath)

    if datapath is not None:
        data_path = datapath / module / path.lstrip("/")
        with open(data_path, "r", encoding="utf-8") as fobj:
            data = fobj.read()

    if readonly:
        if path.endswith("cpu/online"):
            return _ROFile.ROSysfsFile(Path(path), basepath, data)
        return _ROFile.ROFile(Path(path), basepath, data)

    if path.startswith("/sys/"):
        return _RWFile.RWSysinfoFile(Path(path), basepath, data)
    if path.endswith("/msr"):
        return _EmulDevMSR.EmulDevMSR(Path(path), basepath, data)
    return _RWFile.RWFile(Path(path), basepath, data)
