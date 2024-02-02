# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""This module provides the API to emulate 'msr' driver device nodes."""

import types
from pepclibs.helperlibs import _EmulFile
from pepclibs.helperlibs.Exceptions import Error

def _populate_sparse_file(path, data):
    """Create sparse file 'path' and write sparse data 'data' into it."""

    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    try:
        with open(path, "wb") as fobj:
            for offset, value in data.items():
                fobj.seek(offset)
                fobj.write(value)
    except OSError as err:
        msg = Error(err).indent(2)
        raise Error(f"failed to prepare sparse file '{path}':\n{msg}") from err

class EmulDevMSR:
    """This class provides the API to emulate 'msr' driver device nodes."""

    def _set_seek_method(self, fobj, path):
        """
        Some files needs special 'seek()' handling. Replace the 'seek()' method of 'fobj' with a
        custom method in order to properly emulate the behavior of the file in 'path'.
        """

        def _seek_offset(self, offset, whence=0):
            """
            Mimic '/dev/msr/*' files' 'seek()' behavior. MSR register address are offset by 8 bytes,
            meaning register address 10 is 80 bytes from start of file.
            """
            self._orig_seek(offset * 8, whence)

        if path.endswith("/msr"):
            fobj._orig_seek = fobj.seek # pylint: disable=protected-access,pepc-unused-variable
            fobj.seek = types.MethodType(_seek_offset, fobj)

    def open(self, mode):
        """
        Create a file in the temporary directory and return the file object, opened with 'mode'.
        """

        fobj = _EmulFile.open_rw(self.path, mode, self._basepath)
        self._set_seek_method(fobj, self.path)
        return fobj

    def __init__(self, msrinfo, basepath):
        """
        Class constructor. Arguments are as follows:
         * msrinfo - MSR information dictionary.
         * basepath - path to the temporary directory containing emulated files.
        """

        self._basepath = basepath
        self.ro = msrinfo.get("readonly", False)

        self.path = str(msrinfo["path"])
        real_path = basepath / msrinfo["path"].lstrip("/")
        _populate_sparse_file(real_path, msrinfo["data"])
