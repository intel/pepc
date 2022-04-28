# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains common trivial helpers.
"""

import os
import pwd
from pepclibs.helperlibs.Exceptions import Error

def is_root():
    """
    Return 'True' if current process has superuser (root) privileges and 'False' otherwise.
    """

    try:
        return os.getuid() == 0 or os.geteuid() == 0
    except OSError as err:
        raise Error(f"failed to get process UID: {err}") from None

def get_pid():
    """Return current process ID."""

    try:
        return os.getpid()
    except OSError as err:
        raise Error(f"failed to get own PID: {err}") from None

def get_pgid(pid):
    """Return process group ID of a process with PID 'pid'."""

    try:
        return os.getpgid(pid)
    except OSError as err:
        raise Error(f"failed to get group ID of process with PID {pid}: {err}") from None

def get_username(uid=None):
    """Return username of current process."""

    try:
        if uid is None:
            uid = os.getuid()
    except OSError as err:
        raise Error("failed to detect user name of current process:\n%s" % err) from None

    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError as err:
        raise Error("failed to get user name for UID %d:\n%s" % (uid, err)) from None


def str_to_num(snum, must_convert=True):
    """
    Convert a string to a numeric value, either 'int' or 'float'. The arguments are as follows.
      * snum - the value to convert to 'int' or 'float'. Should be a string or a numeric value.
      * must_convert - if 'True', raises an exception if the conversion is impossible, otherwise
                       returns 'None' in that case.
    """

    try:
        num = int(snum)
    except (ValueError, TypeError):
        try:
            num = float(snum)
        except (ValueError, TypeError):
            if must_convert:
                raise Error(f"failed to convert '{str(snum)}' to a number") from None
            return None

    return num

def is_int(value, base=10):
    """
    Return 'True' if 'value' can be converted to integer using 'int()' and 'False' otherwise.
    """

    try:
        int(str(value), base)
    except (ValueError, TypeError):
        try:
            int(value)
        except (ValueError, TypeError):
            return False
    return True

def validate_int_range(value, minval, maxval, what="value"):
    """Validate integer value against range ['minval', 'maxval']."""

    if not is_int(value) or int(value) < minval or int(value) > maxval:
        raise Error(f"{what} '{value}' is not supported, please provide integer number between "
                    f"[{minval},{maxval}]")

def is_iterable(value):
    """Return 'True' if 'value' is iterable collection (not string) and 'False' otherwise."""
    try:
        iter(value)
    except TypeError:
        return False
    return not isinstance(value, str)

def is_float(value):
    """
    Return 'True' if 'value' can be converted to a float using 'float()' and 'False' otherwise.
    """

    try:
        float(value)
    except (ValueError, TypeError):
        return False
    return True

def list_dedup(elts):
    """Return list of unique elements in 'elts'."""

    seen = set()
    new_elts = []
    for elt in elts:
        if elt not in seen:
            new_elts.append(elt)
            seen.add(elt)

    return new_elts

def split_csv_line(csv_line, sep=",", dedup=False):
    """
    Split a comma-separated values line and return the list of the comma separated values. The 'sep'
    argument can be used to change the separator from comma to something else. If 'dedup' is 'True',
    this function removes duplicated elements from the returned list.
    """

    result = [val.strip() for val in csv_line.strip(sep).split(sep) if val]
    if dedup:
        return list_dedup(result)
    return result
