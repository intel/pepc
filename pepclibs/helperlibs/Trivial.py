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
        raise Error(f"failed to detect user name of current process:\n{err}") from None

    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError as err:
        raise Error(f"failed to get user name for UID {uid}:\n{err}") from None

def str_to_num(snum):
    """
    Convert a string to a numeric value, either 'int' or 'float'. The arguments are as follows.
      * snum - the value to convert to 'int' or 'float'. Should be a string or a numeric value.
    """

    try:
        num = int(str(snum))
    except (ValueError, TypeError):
        try:
            num = float(str(snum))
        except (ValueError, TypeError):
            raise Error(f"failed to convert '{str(snum)}' to a number") from None

    return num

def is_int(value, base=10):
    """
    Return 'True' if 'value' can be converted to an integer using 'int()' and 'False' otherwise.
    """

    try:
        int(str(value), base)
    except (ValueError, TypeError):
        try:
            int(value)
        except (ValueError, TypeError):
            return False
    return True

def is_float(value):
    """
    Return 'True' if 'value' can be converted to a float using 'float()' and 'False' otherwise.
    """

    try:
        float(str(value))
    except (ValueError, TypeError):
        return False
    return True

def is_num(value):
    """
    Return 'True' if 'value' can be converted to an integer using 'int()' or to a float using
    'float()'. Returns 'False' otherwise.
    """

    try:
        int(str(value))
    except (ValueError, TypeError):
        try:
            float(str(value))
        except (ValueError, TypeError):
            return False

    return True

def validate_value_in_range(value, minval, maxval, what="value"):
    """
    Validate that value 'value' is in the ['minval', 'maxval'] range. The arguments are as follows.
      * value - the value to validate.
      * minval - the minimum allowed value for 'value'.
      * maxval - the maximum allowed value for 'value'.
      * what - a string describing the value that is being validated, for the possible error
               message.
    """

    if value < minval or value > maxval:
        raise Error(f"{what} '{value}' is out of range, should be within [{minval},{maxval}]")

def validate_range(minval, maxval, min_limit=None, max_limit=None, what="range"):
    """
    Validate correctness of range ['minval', 'maxval']. The arguments are as follows.
      * minval - the minimum value (first number in the range).
      * maxval - the maximum value (second number in the range).
      * min_limit - the minimum allowed value for 'minval'.
      * max_limit - the maximum allowed value for 'maxval'.
      * what - a string describing the range that is being validated, for the possible error
               messages.
    """

    pfx = f"bad {what} '[{minval},{maxval}]'"

    if minval > maxval:
        raise Error(f"{pfx}: min. value '{minval}' should not be greater than max. value "
                    f"'{maxval}'")

    if min_limit is not None:
        if max_limit is not None:
            assert max_limit >= min_limit
        if minval < min_limit:
            raise Error(f"{pfx}: should be within '[{min_limit},{max_limit}]'")

    if max_limit is not None:
        if maxval > max_limit:
            raise Error(f"{pfx}: should be within '[{min_limit},{max_limit}]'")

def is_iterable(value):
    """Return 'True' if 'value' is iterable collection (not string) and 'False' otherwise."""
    try:
        iter(value)
    except TypeError:
        return False
    return not isinstance(value, str)

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
