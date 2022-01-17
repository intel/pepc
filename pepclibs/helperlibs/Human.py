# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains misc. helper functions with the common theme of representing something in a
human-readable format, or turning human-oriented data into a machine format.
"""

from itertools import groupby
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error

_SIZE_UNITS = ["KiB", "MiB", "GiB", "TiB", "EiB"]
_LARGENUM_UNITS = ["K", "M", "G", "T", "E"]

# pylint: disable=undefined-loop-variable
def bytesize(size, precision=1):
    """
	Transform size in bytes into a human-readable form. The 'precision' argument can be use to
    specify the amount of fractional digits to print.
	"""

    if size == 1:
        return "1 byte"

    if size < 512:
        return "%d bytes" % size

    for unit in _SIZE_UNITS:
        size /= 1024.0
        if size < 1024:
            break

    if precision <= 0:
        return "%d %s" % (int(size), unit)

    pattern = "%%.%df %%s" % int(precision)
    return pattern % (size, unit)
# pylint: enable=undefined-loop-variable

def parse_bytesize(size):
    """
    This function does the opposite to what the 'bytesize()' function does - turns a
    human-readable string describing a size in bytes into an integer amount of bytes.
    """

    size = str(size).strip()
    orig_size = size
    multiplier = 1

    for idx, unit in enumerate(_SIZE_UNITS):
        if size.lower().endswith(unit.lower()):
            multiplier = pow(1024, idx + 1)
            size = size[:-3]
            break

    try:
        return int(float(size) * multiplier)
    except ValueError:
        raise Error("cannot interpret bytes count '%s', please provide a number and "
                    "possibly the unit: %s" % (orig_size, ", ".join(_SIZE_UNITS))) from None

def largenum(value):
    """
    Transform a supposedly large integer into a human-readable form using suffixes like "K" (Kilo),
    "M" (Mega), etc.
    """

    unit = None
    if value >= 500:
        for unit in _LARGENUM_UNITS:
            value /= 1000.0
            if value < 1000:
                break

    result = "%.1f" % value
    result = result.rstrip("0").rstrip(".")
    if unit:
        result += unit
    return result

def duration(seconds, s=True, ms=False):
    """
    Transform duration in seconds to the human-readable format. The 's' and 'ms' arguments control
    whether seconds/milliseconds should be printed or not.
    """

    if not isinstance(seconds, int):
        msecs = int((float(seconds) - int(seconds)) * 1000)
    else:
        msecs = 0

    (mins, secs) = divmod(int(seconds), 60)
    (hours, mins) = divmod(mins, 60)
    (days, hours) = divmod(hours, 24)

    result = ""
    if days:
        result += "%d days " % days
    if hours:
        result += "%dh " % hours
    if mins:
        result += "%dm " % mins
    if s or seconds < 60:
        if ms or seconds < 1 or (msecs and seconds < 10):
            result += "%f" % (secs + float(msecs) / 1000)
            result = result.rstrip("0").rstrip(".")
            result += "s"
        else:
            result += "%ds " % secs

    return result.strip()

def _tokenize(htime, specs, default_unit, name):
    """Split human time and return the dictionary of tokens."""

    if name:
        name = f" for {name}"
    else:
        name = ""

    if default_unit not in specs:
        specs_descr = ", ".join([f"{spec} - {key}" for spec, key in specs.items()])
        raise Error(f"bad unit '{default_unit}{name}', supported units are: {specs_descr}")

    htime = htime.strip()
    if htime.isdigit():
        htime += default_unit

    tokens = {}
    rest = htime.lower()
    for spec in specs:
        split = rest.split(spec, 1)
        if len(split) > 1:
            tokens[spec] = split[0]
            rest = split[1]
        else:
            rest = split[0]

    if rest.strip():
        raise Error(f"failed to parse duration '{htime}'{name}")

    for spec, val in tokens.items():
        if not Trivial.is_int(val):
            raise Error(f"failed to parse duration '{htime}'{name}: non-integer amount of "
                        f"{specs[spec]}")

    return tokens

# The specifiers that 'parse_duration()' accepts.
DURATION_SPECS = {"d" : "days", "h" : "hours", "m" : "minutes", "s" : "seconds"}

def parse_duration(htime, default_unit="s", name=None):
    """
    This function does the opposite to what 'duration()' does - parses the human time string and
    returns integer number of seconds. This function supports the following specifiers:
      * d - days
      * h - hours
      * m - minutes
      * s - seconds.

    If 'htime' is just a number without a specifier, it is assumed to be in seconds. But the
    'default_unit' argument can be used to specify a different default unit. The optional 'what'
    argument can be used to pass a name that will be used in error message.
    """

    tokens = _tokenize(htime, DURATION_SPECS, default_unit, name)

    days = int(tokens.get("d", 0))
    hours = int(tokens.get("h", 0))
    mins = int(tokens.get("m", 0))
    secs = int(tokens.get("s", 0))
    return days * 24 * 60 * 60 + hours * 60 * 60 + mins * 60 + secs

# The specifiers that 'parse_duration_ns()' accepts.
DURATION_NS_SPECS = {"ms" : "milliseconds", "us" : "microseconds", "ns" : "nanoseconds"}

def parse_duration_ns(htime, default_unit="ns", name=None):
    """
    Similar to 'parse_duration()', but supports different specifiers and returns integer amount of
    nanoseconds. The supported specifiers are:
      * ms - milliseconds
      * us - microseconds
      * ns - nanoseconds
    """

    tokens = _tokenize(htime, DURATION_NS_SPECS, default_unit, name)

    ms = int(tokens.get("ms", 0))
    us = int(tokens.get("us", 0))
    ns = int(tokens.get("ns", 0))
    return ms * 1000 * 1000 + us * 1000 + ns

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
