# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Adam Hawley <adam.james.hawley@intel.com>

"""Provide the factory function to create emulated file objects."""

from typing import Any, Union
from pathlib import Path
from pepclibs.helperlibs.emul import _EmulFileBase, _CPUOnlineEmulFIle, _RWFile, _EmulDevMSR

EmulFileType = Union[_EmulFileBase.EmulFileBase, _CPUOnlineEmulFIle.CPUOnlineEmulFile,
                     _EmulDevMSR.EmulDevMSR]

def get_emul_file(path: str,
                  basepath: Path,
                  data: Any = None,
                  readonly: bool = False) -> EmulFileType:
    """
    Create and return an emulated file object for the specified path.

    Args:
        path: Path to the file to emulate.
        basepath: Directory where emulated files should be created.
        data: Optional data to populate the emulated file with. Create an empty file if "", do not
              create the file in None.
        readonly: Whether the emulated file should be read-only.

    Returns:
        An emulated file object representing the specified file.

    Raises:
        ValueError: If the file type is not supported for emulation.
    """

    # TODO: remove.
    assert isinstance(path, str)
    assert isinstance(basepath, Path)

    if data is None:
        # A pre-created file in the base directory.
        return _EmulFileBase.EmulFileBase(Path(path), basepath, readonly=readonly, data=data)

    if path.endswith("/sys/devices/system/cpu/online"):
        # The global CPU online sysfs file.
        return _CPUOnlineEmulFIle.CPUOnlineEmulFile(Path(path), basepath, data)

    if path.startswith("/sys/"):
        return _RWFile.RWSysinfoFile(Path(path), basepath, data)

    if path.endswith("/msr"):
        return _EmulDevMSR.EmulDevMSR(Path(path), basepath, data)

    return _EmulFileBase.EmulFileBase(Path(path), basepath, readonly=readonly, data=data)
