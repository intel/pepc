# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""Emulate read-write sysfs, procfs, and debugfs files."""

import types
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound
from pepclibs.helperlibs.emul import _EmulFileBase

def _get_err_prefix(fobj, method):
    """Return the error message prefix."""
    return f"method '{method}()' failed for {fobj.name}"

def populate_rw_file(path, data):
    """Create text file 'path' and write 'data' into it."""

    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    with open(path, "w", encoding="utf-8") as fobj:
        try:
            fobj.write(data)
        except OSError as err:
            msg = Error(err).indent(2)
            raise Error(f"failed to write into file '{path}':\n{msg}") from err

def open_rw(path, mode, basepath):
    """
    Create a file in the temporary directory and return the file object. Arguments are as
    follows:
     * path - non-emulated path.
     * mode - mode with which to open the file.
     * basepath - base path of the temporary directory containing emulated files.
    """

    tmppath = basepath / str(path).strip("/")

    # Disabling buffering is only allowed in binary mode.
    if "b" in mode:
        buffering = 0
        encoding = None
    else:
        buffering = -1
        encoding = "utf-8"

    errmsg = f"cannot open file '{path}' with mode '{mode}': "
    try:
        # pylint: disable=consider-using-with
        fobj = open(tmppath, mode, buffering=buffering, encoding=encoding)
    except PermissionError as err:
        msg = Error(err).indent(2)
        raise ErrorPermissionDenied(f"{errmsg}\n{msg}") from None
    except FileNotFoundError as err:
        msg = Error(err).indent(2)
        raise ErrorNotFound(f"{errmsg}\n{msg}") from None
    except OSError as err:
        msg = Error(err).indent(2)
        raise Error(f"{errmsg}\n{msg}") from None

    # Make sure methods of 'fobj' always raise the 'Error' exceptions.
    return ClassHelpers.WrapExceptions(fobj, get_err_prefix=_get_err_prefix)

class RWFile(_EmulFileBase.EmulFileBase):
    """Emulate read-write sysfs, procfs, and debugfs files."""

    def _set_write_method(self, fobj, path, mode):
        """
        Some files needs special handling when written to. Replace the 'write()' method of 'fobj'
        with a custom method in order to properly emulate the behavior of the file in 'path'.
        """

        def _epb_write(self, data):
            """
            Mimic the sysfs 'energy_perf_bias' file behavior. In addition to supporting numbers, it
            also supports policies.
            """

            policies = {"performance": 0, "balance-performance": 4, "normal": 6,
                        "balance-power": 8, "power": 15}

            key = data.strip()
            if key in policies:
                data = f"{policies[key]}\n"
            self.truncate(len(data))
            self.seek(0)
            self._orig_write(data)

        def _aspm_write(self, data):
            """
            Mimic the sysfs ASPM policy file behavior.

            For example, writing "powersave" to the file results in the following file contents:
            "default performance [powersave] powersupersave".
            """

            line = fobj._policies.replace(data, f"[{data}]") # pylint: disable=protected-access
            self.truncate(len(data))
            self.seek(0)
            self._orig_write(line)

        def _truncate_write(self, data):
            """
            Mimic behavior of most sysfs files: writing does not continue from the current file
            offset, but instead, starts from file offset 0. For example, writing "performance" to
            the 'scaling_governor' results in the file containing only "performance", regardless of
            what the file contained before the write operation.
            """

            self.truncate(len(data))
            self.seek(0)
            self._orig_write(data)

        if path.startswith("/sys/"):
            if "w" in mode:
                raise Error("BUG: use 'r+' mode when opening sysfs virtual files")

            if mode != "r+":
                return

            # pylint: disable=pepc-unused-variable,protected-access
            fobj._orig_write = fobj.write

            if path.endswith("pcie_aspm/parameters/policy"):
                policies = fobj.read().strip()
                fobj._policies = policies.replace("[", "").replace("]", "")
                fobj.write = types.MethodType(_aspm_write, fobj)
            elif path.endswith("/energy_perf_bias"):
                fobj.write = types.MethodType(_epb_write, fobj)
            else:
                fobj.write = types.MethodType(_truncate_write, fobj)
            # pylint: enable=pepc-unused-variable,protected-access

    def open(self, mode):
        """Create a file in the temporary directory and return the file object with 'mode'."""

        fobj = open_rw(self.path, mode, self._get_basepath())
        self._set_write_method(fobj, self.path, mode)

        return fobj

    def __init__(self, finfo, datapath, get_basepath, module=None):
        """
        Class constructor. Arguments are as follows:
         * finfo - file info dictionary.
         * datapath - path to the directory containing data which is used for emulation.
         * get_basepath - a function which can be called to access the basepath. The basepath is a
                          path to the directory where emulated files should be created.
         * module - the name of the module which the file is a part of.
        """

        self._get_basepath = get_basepath
        self.ro = False

        if "data" in finfo:
            data = finfo["data"]
        else:
            src = datapath / module / finfo["path"].lstrip("/")
            with open(src, "r", encoding="utf-8") as fobj:
                data = fobj.read()

        # Create file in temporary directory. Here is an example.
        #   * Emulated path: "/sys/devices/system/cpu/cpu0".
        #   * Real path: "/tmp/emulprocs_861089_0s3hy8ye/sys/devices/system/cpu/cpu0".
        path = self._get_basepath() / finfo["path"].lstrip("/")
        populate_rw_file(path, data)

        super().__init__(str(finfo["path"]))
