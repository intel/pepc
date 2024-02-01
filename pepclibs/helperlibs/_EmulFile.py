# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""This module provides the API to interact with emulated files."""

# pylint: disable=protected-access

import io
import types
from pepclibs.helperlibs import Trivial, ClassHelpers, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorNotFound

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

def open_ro(data, mode): # pylint: disable=unused-argument
    """
    Return an emulated read-only file object using a 'StringIO' object, containing 'data' and
    opened with 'mode'.
    """

    def _ro_write(data):
        """Write 'data' to emulated RO file."""
        raise Error("not writable")

    fobj = io.StringIO(data)
    fobj.write = types.MethodType(_ro_write, fobj)
    return fobj

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

class EmulFile:
    """This class provides an API to interact with emulated files."""

    def _set_read_method(self, fobj, path):
        """
        Contents of some read-only sysfs files can change depending on other files. Replace the
        'read()' method of 'fobj' with a custom method in order to properly emulate the behavior of
        a read-only file in 'path'.
        """

        def _online_read(self):
            """
            Mimic the '/sys/devices/system/cpu/online' file. It's contents depends on the per-CPU
            online files. For example if the per-cpu files contain the following:

            '/sys/devices/system/cpu/cpu0/online' : "1"
            '/sys/devices/system/cpu/cpu1/online' : "1"
            '/sys/devices/system/cpu/cpu2/online' : "0"
            '/sys/devices/system/cpu/cpu3/online' : "1"

            The global file contains the following:
            '/sys/devices/system/cpu/online' : "0-1,3"
            """

            online = []
            for dirname in self._base_path.iterdir():
                if not dirname.name.startswith("cpu"):
                    continue

                cpunum = dirname.name[3:]
                if not Trivial.is_int(cpunum):
                    continue

                try:
                    with open(dirname / "online", "r", encoding="utf-8") as fobj:
                        data = fobj.read().strip()
                except FileNotFoundError:
                    # CPU 0 does not have a "online" file, but it is online. So, we assume the same
                    # for any other CPU that has a folder but no "online" file.
                    online.append(cpunum)
                    continue

                if data == "1":
                    online.append(cpunum)

            return Human.rangify(online)

        if path.endswith("cpu/online"):
            fobj._base_path = self._get_basepath() / "sys" / "devices" / "system" / "cpu"
            fobj._orig_read = fobj.read
            fobj.read = types.MethodType(_online_read, fobj)

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

            line = fobj._policies.replace(data, f"[{data}]")
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

            fobj._orig_write = fobj.write

            if path.endswith("pcie_aspm/parameters/policy"):
                policies = fobj.read().strip()
                fobj._policies = policies.replace("[", "").replace("]", "")
                fobj.write = types.MethodType(_aspm_write, fobj)
            elif path.endswith("/energy_perf_bias"):
                fobj.write = types.MethodType(_epb_write, fobj)
            else:
                fobj.write = types.MethodType(_truncate_write, fobj)

    def open(self, mode):
        """Create a file in the temporary directory and return the file object with 'mode'."""

        if self.ro:
            fobj = open_ro(self.ro_data, mode)
            self._set_read_method(fobj, self.path)
        else:
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

        if "data" in finfo:
            data = finfo["data"]
        else:
            src = datapath / module / finfo["path"].lstrip("/")
            with open(src, "r", encoding="utf-8") as fobj:
                data = fobj.read()

        if finfo.get("readonly"):
            self.ro = True
            self.ro_data = data
        else:
            # Create file in temporary directory. Here is an example.
            #   * Emulated path: "/sys/devices/system/cpu/cpu0".
            #   * Real path: "/tmp/emulprocs_861089_0s3hy8ye/sys/devices/system/cpu/cpu0".
            self.ro = False
            path = self._get_basepath() / finfo["path"].lstrip("/")
            populate_rw_file(path, data)

        self.path = str(finfo["path"])
