# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides the base class for 'PState' and 'CState' classes.
"""

import logging
from pepclibs.helperlibs import Trivial
from pepclibs import _PropsClassBase
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

_LOG = logging.getLogger()

class PCStatesBase(_PropsClassBase.PropsClassBase):
    """
    This is a base class for the 'PState' and 'CState' classes.
    """

    def _validate_governor_name(self, name):
        """Validate P-state or C-state governor name 'name'."""

        # Get the list of governors to validate 'name' against. Note, the list of governors is the
        # same for all CPUs (global scope).
        governors = self._get_cpu_prop("governors", 0)
        if name not in governors:
            governors = ", ".join(governors)
            raise Error(f"bad governor name '{name}', use one of: {governors}")

    def _read_prop_from_sysfs(self, pname, path):
        """Read property 'pname' from sysfs, and return its value."""

        try:
            val = self._pman.read(path).strip()
        except ErrorNotFound as err:
            _LOG.debug(err)
            return None

        prop = self._props[pname]

        if prop["type"] == "int":
            if not Trivial.is_int(val):
                raise Error(f"read an unexpected non-integer value from '{path}'"
                            f"{self._pman.hostmsg}")

            val = int(val)
            if prop.get("unit") == "Hz":
                # Sysfs files have the numbers in kHz, convert to Hz.
                val *= 1000

        if prop["type"] == "list[str]":
            val = val.split()

        return val

    def _write_prop_to_sysfs(self, pname, path, val):
        """Write property value 'val' to a sysfs file at path 'path'."""

        prop = self._props[pname]
        if prop["type"] == "int":
            if not Trivial.is_int(val):
                raise Error(f"received an unexpected non-integer value from '{pname}'"
                            f"{self._pman.hostmsg}")

            val = int(val)
            if prop.get("unit") == "Hz":
                # Sysfs files have the numbers in kHz, convert to Hz.
                val //= 1000

        if prop["type"] == "list[str]":
            val = ' '.join(val)

        try:
            with self._pman.open(path, "r+") as fobj:
                fobj.write(str(val))
        except Error as err:
            raise type(err)(f"failed to set '{pname}'{self._pman.hostmsg}:\n{err.indent(2)}") \
                            from err
