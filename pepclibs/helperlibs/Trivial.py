# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Common trivial helpers.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import grp
import pwd
import typing
from itertools import groupby
from pepclibs.helperlibs.Exceptions import Error, ErrorBadFormat

if typing.TYPE_CHECKING:
    from typing import Iterable

def is_root() -> bool:
    """
    Check if the current process has superuser (root) privileges.

    Returns:
        bool: True if the current process has superuser privileges, False otherwise.
    """

    try:
        return os.getuid() == 0 or os.geteuid() == 0
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get process UID:\n{errmsg}") from None

def get_pid() -> int:
    """
    Return the current process ID.

    Returns:
        int: The current process ID.
    """

    try:
        return os.getpid()
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get own PID:\n{errmsg}") from None

def get_pgid(pid: int) -> int:
    """
    Return the group ID of a process with the given PID.

    Args:
        pid: The process ID to return the process group ID for.

    Returns:
        int: The group ID of the specified process.
    """

    try:
        return os.getpgid(pid)
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get process group ID for PID {pid}:\n{errmsg}") from None

def get_username(uid: int | None = None) -> str:
    """
    Return the username of the current process or by UID.

    Args:
        uid: The user ID to return the username for. Defaults to the UID of the current process.

    Returns:
        str: The username of the specified UID.
    """

    try:
        if uid is None:
            uid = os.getuid()
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to detect username of current process:\n{errmsg}") from None

    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get username for UID {uid}:\n{errmsg}") from None

def get_groupname(gid: int | None = None) -> str:
    """
    Return the group name for a given group ID (GID) or for the current process.

    Args:
        gid: The group ID to get the group name for. If None, the GID of the current process is
             used.

    Returns:
        str: The name of the group associated with the specified GID or the current process's GID.
    """

    try:
        if gid is None:
            gid = os.getgid()
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get group name of the current process:\n{errmsg}") from None

    try:
        return grp.getgrgid(gid).gr_name
    except KeyError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get group name for GID {gid}:\n{errmsg}") from None

def get_uid(username: str = "") -> int:
    """
    Return the user ID for the specified username or the current process.

    Args:
        username: The username to get the user ID for. If empty, the current process's user ID is
                  returned.

    Returns:
        int: The UID associated with the specified username or the current process.
    """

    if not username:
        username = get_username()

    try:
        return pwd.getpwnam(username).pw_uid
    except KeyError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get UID for user '{username}:\n{errmsg}") from None

def get_gid(groupname: str = ""):
    """
    Return the group ID or a specified group name or for the current process's group.

    Args:
        groupname: The name of the group to return the GID for. If empty, the current process's
                   group is used.

    Returns:
        int: The GID corresponding to the specified or current group.
    """

    if not groupname:
        groupname = get_groupname()

    try:
        return grp.getgrnam(groupname).gr_gid
    except KeyError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to get GID for group '{groupname}':\n{errmsg}") from None

def str_to_int(snum: str | int, base: int = 0, what: str = "") -> int:
    """
    Convert a string to an integer value.

    Args:
        snum: The value to convert to 'int'.
        base: Base of 'snum'. Defaults to auto-detect based on the prefix.
        what: A string describing the value to convert, for the possible error message.

    Returns:
        int: The converted integer value.

    Raises:
        ErrorBadFormat: If 'snum' cannot be converted to an integer.
    """

    try:
        num = int(str(snum), base)
    except (ValueError, TypeError):
        if not what:
            what = "value"
        try:
            str_to_int(base)
        except (ValueError, TypeError) as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"BUG: Bad base value {base} when converting bad {what} '{snum}':\n"
                        f"{errmsg}") from err

        if base != 0 and base < 2:
            raise Error(f"BUG: Bad base value {base} when converting bad {what} '{snum}': must be "
                        f"greater than 2 or 0") from None

        if base:
            errmsg = f"a base {base} integer"
        else:
            errmsg = "an integer"
        raise ErrorBadFormat(f"Bad {what} '{snum}': should be {errmsg}") from None

    return num

def str_to_float(snum: str | float, what: str = "") -> float:
    """
    Convert a string to a floating point number.

    Args:
        snum: The value to convert to 'float'.
        what: A string describing the value to convert, for the possible error message.

    Returns:
        float: The converted floating point value.

    Raises:
        ErrorBadFormat: If 'snum' cannot be converted to a floating point value.
    """

    try:
        return float(str(snum))
    except (ValueError, TypeError):
        if not what:
            what = "value"
        pfx = f"Bad {what} '{snum}'"
        raise ErrorBadFormat(f"{pfx}: should be a floating point number") from None

def str_to_num(snum: str | int, what: str = "") -> int | float:
    """
    Convert a string to a numeric value, either 'int' or 'float'.

    Args:
        snum: The value to convert to 'int' or 'float'.
        what: A string describing the value to convert, for the possible error message.

    Returns:
        int or float: The converted numeric value.

    Raises:
        ErrorBadFormat: If 'snum' cannot be converted to a numeric value.
    """

    try:
        return int(str(snum), 0)
    except (ValueError, TypeError):
        try:
            return float(str(snum))
        except (ValueError, TypeError):
            if not what:
                what = "value"
            pfx = f"Bad {what} '{snum}'"
            raise ErrorBadFormat(f"{pfx}: should be an integer or floating point number") from None

def is_int(value: str | int | float, base: int = 0) -> bool:
    """
    Check if 'value' can be converted to 'int' type'.

    Args:
        value: The value to check.
        base: Base of the value. Defaults to auto-detect based on the prefix.

    Returns:
        bool: True if 'value' can be converted to 'int' type, False otherwise.
    """

    try:
        int(str(value), base)
    except (ValueError, TypeError):
        try:
            int(value)
        except (ValueError, TypeError):
            return False
    return True

def is_float(value: str | float) -> bool:
    """
    Check if 'value' can be converted to 'float' type'.

    Args:
        value: The value to check.

    Returns:
        bool: True if 'value' can be converted to 'float' type, False otherwise.
    """

    try:
        float(str(value))
    except (ValueError, TypeError):
        return False
    return True

def is_num(value: str | int | float) -> bool:
    """
    Check if 'value' can be converted to 'int' or 'float' types.

    Args:
        value: The value to check.

    Returns:
        bool: True if 'value' can be converted to 'int' or 'float' types, False otherwise.
    """

    try:
        int(str(value))
    except (ValueError, TypeError):
        try:
            float(str(value))
        except (ValueError, TypeError):
            return False

    return True

def validate_value_in_range(value: int | float, minval: int | float,
                            maxval: int | float, what: str = ""):
    """
    Validate that 'value' is in the ['minval', 'maxval'] range.

    Args:
        value: The value to validate.
        minval: The minimum allowed value for 'value'.
        maxval: The maximum allowed value for 'value'.
        what: A string describing the value that is being validated, for the possible error message.
    """

    if value < minval or value > maxval:
        if not what:
            what = "value"
        raise Error(f"{what.capitalize()} '{value}' is out of range, should be within "
                    f"[{minval},{maxval}]")

def validate_range(minval: int | float, maxval: int | float, min_limit: int | float | None = None,
                   max_limit: int | float | None = None, what: str = ""):
    """
    Validate correctness of range ['minval', 'maxval'].

    Args:
        minval: The minimum value (first number in the range).
        maxval: The maximum value (second number in the range).
        min_limit: The minimum allowed value for 'minval'.
        max_limit: The maximum allowed value for 'maxval'.
        what: A string describing the range that is being validated, for the possible error
              messages.
    """

    if not what:
        what = "range"
    pfx = f"Bad {what} '[{minval},{maxval}]'"

    if minval > maxval:
        raise Error(f"{pfx}: Min. value '{minval}' should not be greater than max. value "
                    f"'{maxval}'")

    if min_limit is not None:
        if max_limit is not None:
            assert max_limit >= min_limit
        if minval < min_limit:
            raise Error(f"{pfx}: Should be within '[{min_limit},{max_limit}]'")

    if max_limit is not None:
        if maxval > max_limit:
            raise Error(f"{pfx}: Should be within '[{min_limit},{max_limit}]'")

def is_iterable(value: str | Iterable) -> bool:
    """
    Check if 'value' is an iterable collection. The 'str' type is not considered to be an iterable
    collection.

    Args:
        value: The value to check.

    Returns:
        bool: True if 'value' is an iterable collection, False otherwise.
    """

    try:
        iter(value)
    except TypeError:
        return False
    return not isinstance(value, str)

def list_dedup(elts: Iterable) -> list:
    """
    Return a list of unique elements in 'elts'.

    Args:
        elts: The list of elements.

    Returns:
        list: A list of unique elements.
    """

    return list(dict.fromkeys(elts))

def split_csv_line(csv_line: str, sep: str = ",", dedup: bool = False,
                   keep_empty: bool = False) -> list[str]:
    """
    Split a comma-separated values line and return the list of values.

    Args:
        csv_line: The comma-separated line to split.
        sep: The separator character. Defaults to comma.
        dedup: If True, remove duplicated elements from the returned list.
        keep_empty: If True, keep empty values.

    Returns:
        list: A list of values.
    """

    result = []
    if not keep_empty:
        csv_line = csv_line.strip(sep)

    for val in csv_line.split(sep):
        if not val and not keep_empty:
            continue
        result.append(val.strip())

    if dedup:
        return list_dedup(result)
    return result

def split_csv_line_int(csv_line: str, sep: str = ",", dedup: bool = False, base: int = 0,
                       what: str = "") -> list[int]:
    """
    Split a comma-separated values line consisting of integers return the list of integer values.

    Args:
        csv_line: The comma-separated line to split.
        sep: The separator character. Defaults to comma.
        dedup: If True, remove duplicated elements from the returned list.
        base: Base of the values in 'csv_line'. Defaults to auto-detect based on the prefix.
        what: A string describing the values in 'csv_line', for the possible error message.

    Returns:
        list: A list of integer values.

    Raises:
        ErrorBadFormat: If 'csv_line' cannot be converted to a list of integers.

    Example:
        Input: csv_line = "0,1-3,7"
        Output: [0, 1, 2, 3, 7].
    """

    vals = split_csv_line(csv_line=csv_line, sep=sep, dedup=dedup)
    if not what:
        what = "value"

    result = []
    for val in vals:
        if "-" not in val:
            result.append(str_to_int(val, base=base, what=what))
            continue

        range_vals = [range_val for range_val in val.split("-") if range_val]
        if len(range_vals) != 2:
            raise ErrorBadFormat(f"Bad {what} '{csv_line}': error in '{val}': should be two "
                                 f"integers separated by '-'")

        rvals = [str_to_int(rval, base=base, what=what) for rval in range_vals]
        if rvals[0] > rvals[1]:
            raise ErrorBadFormat(f"Bad {what} '{csv_line}': error in range '{val}': the first "
                                 f"number should be smaller than the second")

        result += range(rvals[0], rvals[1] + 1)

    return result

def parse_int_list(nums: str | int | Iterable[str | int], sep: str = ",",
                   dedup: bool = False, base: int = 0, what: str = "") -> list[int]:
    """
    Same as 'split_csv_line_int()', but also accepts non-strings on input.

    Args:
        nums: The numbers to parse.
        sep: The possible separator character. Defaults to comma.
        dedup: If True, remove duplicated elements from the returned list.
        base: Base of the values in 'nums'. Defaults to auto-detect based on the prefix.
        what: A string describing the values in 'nums', for the possible error message.

    Returns:
        list: A list of integer values.

    Examples:
        Input: nums = "0,1-3,7"
        Output: [0, 1, 2, 3, 7].
        Input: nums = ["1", "4-7"]
        Output: [1, 4, 5, 6, 7].
    """

    if isinstance(nums, (int, str)):
        nums = [nums]

    nums = sep.join([str(num) for num in nums])

    return split_csv_line_int(nums, sep=sep, dedup=dedup, base=base, what=what)

def rangify(numbers: Iterable[int | str]) -> str:
    """
    Convert a list of numbers into a comma-separated string of ranges. Consecutive numbers are
    represented as ranges (e.g., "0-2"), while non-consecutive numbers are listed individually.

    Args:
        numbers: List of numbers to convert, as integers or strings.

    Returns:
        A string representing the input numbers as comma-separated ranges.
    """

    try:
        numbers_int = [int(number) for number in numbers]
    except (ValueError, TypeError) as err:
        raise Error(f"failed to translate numbers to ranges, expected list of numbers, got "
                    f"'{numbers}'") from err

    range_strs = []
    numbers_int = sorted(numbers_int)
    for _, pairs in groupby(enumerate(numbers_int), lambda x:x[0]-x[1]):
        # The 'pairs' is an iterable of tuples (enumerate value, number). E.g. 'numbers_int'
        # [5,6,7,8,10,11,13] would result in three iterable groups:
        # ((0, 5), (1, 6), (2, 7), (3, 8)) , ((4, 10), (5, 11)) and  (6, 13)

        nums = [val for _, val in pairs]
        if len(nums) > 2:
            range_strs.append(f"{nums[0]}-{nums[-1]}")
        else:
            for num in nums:
                range_strs.append(str(num))

    return ",".join(range_strs)
