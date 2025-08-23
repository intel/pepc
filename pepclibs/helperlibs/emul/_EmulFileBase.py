# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide base class for emulated file classes.
"""

from typing import IO
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorNotFound

class EmulFileBase:
    """
    Base class for emulated file classes.
    """

    def open(self, mode: str) -> IO:
        """
        Open the emulated file. The file resides in the temporary directory the base directory.

        Args:
            mode: The mode in which to open the file, similar to 'mode' argument the built-in Python
                  'open()' function.
        """

        encoding: str | None

        # Allow for disabling buffering only in binary mode.
        if "b" in mode:
            buffering = 0
            encoding = None
        else:
            buffering = -1
            encoding = "utf-8"

        errmsg_prefix = f"Cannot open file '{self.fullpath}' with mode '{mode}': "
        try:
            # pylint: disable-next=consider-using-with
            fobj = open(self.fullpath, mode, buffering=buffering, encoding=encoding)
        except PermissionError as err:
            errmsg = Error(str(err)).indent(2)
            raise ErrorPermissionDenied(f"{errmsg_prefix}\n{errmsg}") from None
        except FileNotFoundError as err:
            errmsg = Error(str(err)).indent(2)
            raise ErrorNotFound(f"{errmsg_prefix}\n{errmsg}") from None
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"{errmsg_prefix}\n{errmsg}") from None

        return fobj

    def __init__(self, path: Path, basepath: Path):
        """
        Initialize a class instance.

        Args:
            path: Path to the file to emulate.
            basepath: Path to the base directory (where the emulated files are stored).
        """

        # TODO: remove.
        assert isinstance(path, Path)
        assert isinstance(basepath, Path)

        self.path = path
        self.basepath = basepath

        # Note about lstrip(): 'self.path' is usually an absolute path starting with '/', and
        # joining it directly with 'self.basepath' would ignore the base path. For example,
        # Path("/tmp") / "/sys" results in "/sys" instead of "/tmp/sys". Removing the leading '/'
        # ensures the file is placed under the base path.
        self.fullpath = self.basepath / str(self.path).lstrip("/")
