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
import pwd
from itertools import groupby
from pepclibs.helperlibs.Exceptions import Error, ErrorBadFormat

def is_root() -> bool:
    """
    Check if the current process has superuser (root) privileges.

    Returns:
        bool: True if the current process has superuser privileges, False otherwise.
    """

    try:
        return os.getuid() == 0 or os.geteuid() == 0
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to get process UID:\n{msg}") from None

def get_pid() -> int:
    """
    Return the current process ID.

    Returns:
        int: The current process ID.
    """

    try:
        return os.getpid()
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to get own PID:\n{msg}") from None

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
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to get process group ID for PID {pid}:\n{msg}") from None

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
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to detect username of current process:\n{msg}") from None

    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to get username for UID {uid}:\n{msg}") from None

def str_to_int(snum: str | int, base: int = 0, what: str | None = None) -> int:
    """
    Convert a string to an integer numeric value.

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
        if what is None:
            what = "value"
        try:
            str_to_int(base)
        except (ValueError, TypeError) as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"BUG: Bad base value {base} when converting bad {what} '{snum}':\n"
                        f"{msg}") from err

        if base != 0 and base < 2:
            raise Error(f"BUG: Bad base value {base} when converting bad {what} '{snum}': must be "
                        f"greater than 2 or 0") from None

        if base:
            msg = f"a base {base} integer"
        else:
            msg = "an integer"
        raise ErrorBadFormat(f"Bad {what} '{snum}': should be {msg}") from None

    return num

def str_to_num(snum: str | int, what: str | None = None) -> int | float:
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
            if what is None:
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
                            maxval: int | float, what: str | None = None):
    """
    Validate that 'value' is in the ['minval', 'maxval'] range.

    Args:
        value: The value to validate.
        minval: The minimum allowed value for 'value'.
        maxval: The maximum allowed value for 'value'.
        what: A string describing the value that is being validated, for the possible error message.
    """

    if value < minval or value > maxval:
        if what is None:
            what = "value"
        raise Error(f"{what.capitalize()} '{value}' is out of range, should be within "
                    f"[{minval},{maxval}]")

def validate_range(minval: int | float, maxval: int | float, min_limit: int | float | None = None,
                   max_limit: int | float | None = None, what: str | None = None):
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

    if what is None:
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

def is_iterable(value: str | list | tuple | set | dict) -> bool:
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

def list_dedup(elts: list) -> list:
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
                       what: str | None = None) -> list[int]:
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
    if what is None:
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

def parse_int_list(nums: str | int | list[str | int] | tuple[str | int], sep: str = ",",
                   dedup: bool = False, base: int = 0, what: str | None = None) -> list[int]:
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

def rangify(numbers):
    """
    Turn list of numbers in 'numbers' to a string of comma-separated ranges. Numbers can be integers
    or strings. E.g. list of numbers [0,1,2,4] is translated to "0-2,4".
    """

    try:
        numbers = [int(number) for number in numbers]
    except (ValueError, TypeError) as err:
        raise Error(f"failed to translate numbers to ranges, expected list of numbers, got "
                    f"'{numbers}'") from err

    range_strs = []
    numbers = sorted(numbers)
    for _, pairs in groupby(enumerate(numbers), lambda x:x[0]-x[1]):
        # The 'pairs' is an iterable of tuples (enumerate value, number). E.g. 'numbers'
        # [5,6,7,8,10,11,13] would result in three iterable groups:
        # ((0, 5), (1, 6), (2, 7), (3, 8)) , ((4, 10), (5, 11)) and  (6, 13)

        nums = [val for _, val in pairs]
        if len(nums) > 2:
            range_strs.append(f"{nums[0]}-{nums[-1]}")
        else:
            for num in nums:
                range_strs.append(str(num))

    return ",".join(range_strs)
