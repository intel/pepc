# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Miscellaneous helper functions for converting data between human-readable and machine-readable
formats.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

from itertools import groupby
from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# The units this module supports.
SUPPORTED_UNITS = {
    "B"  : "byte",
    "Hz" : "hertz",
    "s"  : "second",
    "W"  : "watt",
}

_BYTESIZE_PREFIXES = ["KiB", "MiB", "GiB", "TiB", "PiB", "EiB"]
_BYTESIZE_FULLNAMES = {
    "Ei": "exbi",
    "Pi": "pebi",
    "Ti": "tebi",
    "Gi": "gibi",
    "Mi": "mebi",
    "Ki": "kibi",
}
_BYTESIZE_SCALERS = {
    "Ei": 1024*1024*1024*1024*1024*1024,
    "Pi": 1024*1024*1024*1024*1024,
    "Ti": 1024*1024*1024*1024,
    "Gi": 1024*1024*1024,
    "Mi": 1024*1024,
    "Ki": 1024,
}

def bytesize(size: int,
             decp: int = 1,
             sep: str | None = None,
             strip_zeroes = False) -> str:
    """
    Convert a size in bytes into a human-friendly string.

    Args:
        size: The size in bytes.
        decp: Maximum number of decimal places the result should include.
        sep: The separator string to use between the number and the unit. Default is " "
             (white-space).
        strip_zeroes: if True, strip trailing zeroes after the decimal point.

    Returns:
        str: The human-readable string representation of the size.

    Examples:
        >>> bytesize(1025, decp=1, sep=None, strip_zeroes=True)
        "1 KiB"
        >>> bytesize(1025, decp=1, sep=None, strip_zeroes=False)
        "1.0 KiB"
        >>> bytesize(1025, decp=2, sep=None, strip_zeroes=False)
        "1.00 KiB"
    """

    if decp < 0:
        raise Error(f"BUG: Bad decimal points count '{decp}'")

    if sep is None:
        sep = " "

    if abs(size) == 1:
        return f"{size}{sep}byte"

    if abs(size) < 1024:
        return f"{int(size)}{sep}bytes"

    sz = float(size)
    for unit in _BYTESIZE_PREFIXES:
        sz /= 1024.0
        if abs(sz) < 1024:
            break

    result = f"{sz:.{decp}f}"
    if strip_zeroes and "." in result:
        result = result.rstrip("0").rstrip(".")

    return f"{result}{sep}{unit}"

_SIPFX_LARGE = ["k", "M", "G", "T", "P", "E"]
_SIPFX_SMALL = ["m", "u", "n"]
_SIPFX_SCALERS = {
    "E": 1000000000000000000,
    "P": 1000000000000000,
    "T": 1000000000000,
    "G": 1000000000,
    "M": 1000000,
    "k": 1000,
    "m": 0.001,
    "u": 0.000001,
    "n": 0.000000001,
}
_SIPFX_FULLNAMES = {
    "E": "exa",
    "P": "peta",
    "T": "tera",
    "G": "giga",
    "M": "mega",
    "k": "kilo",
    "m": "milli",
    "u": "micro",
    "n": "nano",
}

def separate_si_prefix(unit: str) -> tuple[str | None, str]:
    """
    Split a SI-unit prefix from the base unit.

    Args:
        unit: The unit string which may contain a SI-unit prefix.

    Returns:
        A tuple containing the SI-unit prefix and the base unit. If 'unit' does not contain a
        SI-unit prefix, the first element of the tuple is None.

    Examples:
        >>> separate_si_prefix("kHz")
        ("k", "Hz")
        >>> separate_si_prefix("Hz")
        (None, "Hz")
    """

    if len(unit) < 2:
        return None, unit

    sipfx = unit[0]
    base_unit = unit[1:]

    if sipfx not in _SIPFX_SCALERS:
        return None, unit

    if base_unit not in SUPPORTED_UNITS:
        _LOG.warning("Unsupported unit '%s' was split into SI-prefix '%s' and base unit '%s'",
                     unit, sipfx, base_unit)

    return sipfx, base_unit

def num2si(value: int | float,
           unit: str | None = None,
           decp: int = 1,
           sep: str | None = None,
           strip_zeroes: bool = False) -> str:
    """
    Convert a number into a human-readable form using SI suffixes like "k" (Kilo), "M" (Mega), etc.

    Args:
        value: The number to convert.
        unit: The unit used with 'value', including any SI-prefixes.
        decp: Maximum number of decimal places the result should include.
        sep: The separator string to use between the resulting number and its unit.
        strip_zeroes: if True, strip trailing zeroes after the decimal point.

    Returns:
        str: The human-readable string representation of the number with its unit.

    Examples:
        >>> num2si(0.1, unit="W", decp=0)
        "100mW"
        >>> num2si(0.1, unit="W", decp=1)
        "100.0mW"
        >>> num2si(1, unit="W", decp=0, sep=" ", strip_zeroes=True)
        "1 W"
        >>> num2si(1999, unit="uW", decp=1, sep=" ")
        "2.0 mW"
        >>> num2si(1999, unit="uW", decp=3, sep=" ")
        "1.999 mW"
    """

    if not Trivial.is_num(value):
        raise Error("Bad input '{value}: Not a number")

    if unit is None:
        unit = ""

    if decp < 0:
        raise Error("BUG: decimal places number bust be a positive integer")
    if decp > 8:
        raise Error("Specify at max. 8 decimal places")

    if sep is None:
        sep = ""
    if sep and not unit:
        raise Error("Specify the separator only if unit was specified")

    sipfx, base_unit = separate_si_prefix(unit)
    value = float(value)

    if abs(value) >= 1 and abs(value) < 1000:
        result = f"{value:.{decp}f}"
        if strip_zeroes and "." in result:
            result = result.rstrip("0").rstrip(".")
        return f"{result}{sep}{base_unit}"

    if sipfx:
        factor = _SIPFX_SCALERS[sipfx]
        if abs(value) >= 500 or abs(value) < 1:
            value *= factor

    pfx = None
    if abs(value) > 500:
        for pfx in _SIPFX_LARGE:
            value /= 1000.0
            if abs(value) < 1000:
                break
    elif abs(value) < 1:
        for pfx in _SIPFX_SMALL:
            value *= 1000.0
            if abs(value) >= 1:
                break
    else:
        pfx = sipfx

    result = f"{value:.{decp}f}"
    if strip_zeroes and "." in result:
        result = result.rstrip("0").rstrip(".")

    # Avoid things like 0nHz. If the result is 0 after the rounding, do not add the SI prefix.
    if pfx and float(result) != 0:
        result += sep + pfx
        if base_unit:
            result += base_unit
    elif base_unit:
        result += sep + base_unit

    return result

def scale_si_val(val, unit):
    """
    Scale 'val' which has unit 'unit'. The data will be scaled so that the unit representing the
    data does not contain any SI-unit prefix. Example behaviour:
     * 5, "kHz" -> 5000
     * 10, "ms" -> 0.01
     * 10, "s" -> 10
    """

    prefix, _ = separate_si_prefix(unit)

    if not prefix:
        return val

    scale_factor = _SIPFX_SCALERS[prefix]
    return val * scale_factor

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
        elif secs:
            result += "%ds " % secs

    return result.strip()

_NSTIME_UNITS = ["us", "ms", "s"]

def duration_ns(value, sep=""):
    """
    Transform a supposedly large integer amount of nanoseconds into a human-readable form using
    suffixes like "us" (microseconds), etc.
    """

    scaler = None
    if value >= 500:
        for scaler in _NSTIME_UNITS:
            value /= 1000.0
            if value < 1000:
                break

    result = "%f" % value
    result = result.rstrip("0").rstrip(".")
    if not scaler:
        scaler = "ns"
    result += sep + scaler
    return result

def _tokenize(hval, specs, name=None, multiple=True):
    """
    Split human-provided value 'hval' according unit names in the 'specs' dictionary. Returns the
    dictionary of tokens.

    Example.
        * hval = "1d 4m 1s"
        * specs = {"d" : "days", "m" : "minutes", "s" : "seconds"}
        * Result: {'d': '1', 'm': '4', 's': '1'}

    The 'multiple' argument can be used to limit the input value to just a single number and unit.
    In the above example, if 'multiple' is 'False', this function would raise an error.
    """

    if name:
        name = f" {name}"
    else:
        name = ""

    tokens = {}
    rest = hval
    for spec in specs:
        split = rest.split(spec, 1)
        if len(split) > 1:
            tokens[spec] = split[0]
            rest = split[1]
        else:
            rest = split[0]

    if rest.strip():
        raise Error(f"failed to parse{name} value '{hval}'")

    if not multiple and len(tokens) > 1:
        raise Error(f"failed to parse{name} value '{hval}': should be one value")

    for idx, (spec, val) in enumerate(tokens.items()):
        if idx < len(tokens) - 1:
            # This is not the last element, it must be an integer.
            try:
                tokens[spec] = int(val)
            except:
                raise Error(f"failed to parse{name} value '{hval}': non-integer amount of "
                            f"{specs[spec]}") from None
        else:
            # This is the last element. It can be a floating point or integer.
            try:
                tokens[spec] = float(val)
            except:
                raise Error(f"failed to parse{name} value '{hval}': non-numeric amount of "
                            f"{specs[spec]}") from None

            if Trivial.is_int(val):
                tokens[spec] = int(val)

    return tokens

def _tokenize_prepare(unit):
    """
    Prepare for tokenizing a human-oriented value where the expected unit is 'unit'. Returns a tuple
    of the following 3 elements.
      * specs - the specifiers dictionary, suitable for passing to the '_tokenize()' function.
      * scalers - the scalers dictionary, with key being the specifiers from 'specs' and values
                  being the scaling factors.
      * multiple - value of the 'multiple' argument that can be passed to '_tokenize()'.
    """

    # Create the specifiers dictionary.
    specs = {}
    scalers = {}
    multiple = False
    fullname = SUPPORTED_UNITS.get(unit, unit)

    for pfx, pfx_fullname in _SIPFX_FULLNAMES.items():
        spec = f"{pfx}{unit}"
        if fullname != unit:
            specs[spec] = f"{pfx_fullname}{fullname}"
        else:
            specs[spec] = spec
        scalers[spec] = _SIPFX_SCALERS[pfx]

    if unit == "B":
        # For byte size, allow for "KiB" and so on.
        for pfx, pfx_fullname in _BYTESIZE_FULLNAMES.items():
            spec = f"{pfx}{unit}"
            if fullname != unit:
                specs[spec] = f"{pfx_fullname}{fullname}"
            else:
                specs[spec] = spec
            scalers[spec] = _BYTESIZE_SCALERS[pfx]
    elif unit == "s":
        # For time, allow for day/hour/minute specifiers in upper and lower case.
        specs["d"] = specs["D"] = "day"
        specs["h"] = specs["H"] = "hour"
        specs["m"] = specs["M"] = "minute"
        scalers["d"] = scalers["D"] = 24 * 60 * 60
        scalers["h"] = scalers["H"] = 60 * 60
        scalers["m"] = scalers["M"] = 60
        # Allow for multiple specifiers for time, like in "1d 5h".
        multiple = True

    specs[unit] = fullname
    scalers[unit] = 1

    return specs, scalers, multiple

def parse_human(hval, unit, target_unit=None, integer=True, name=None):
    """
    Convert a user-provided value 'hval' into an integer of float amount of 'unit' units (hertz,
    seconds, etc). The arguments are as follows.
      * hval - the value to convert. Can be a of a string, int, float type. If it is a string, may
               include the unit.
      * unit - the unit of 'hval', including any SI prefixes.
      * target_unit - the unit of the result, including any SI prefixes (same 'unit' without a SI
                      prefix by default).
      * integer - if 'True', round the result to the nearest integer and return an 'int' type,
                  otherwise return the result as a floating point number ('float' type).
      * name - an optional name associated with the value, will be used only in case of an error for
               formatting a nicer message.

    Examples.
      * 100,         unit="Hz",                    integer=False  -> 100.0
      * 100,         unit="kHz",                   integer=True   -> 100000
      * "100kHz",    unit="Hz", target_unit="kHz", integer=False  -> 100.0
      * "100MHz",    unit="Hz", target_unit="kHz", integer=False  -> 100000.0
      * "1m",        unit="s",  target_unit="s",   integer=True    -> 60
      * "100s",      unit="s",  target_unit="ns",  integer=True    -> 100000000000
      * "1us",       unit="s",  target_unit="ns",  integer=True    -> 1000
      * "1h 10m 5s", unit="s",  target_unit="s",   integer=True    -> 4205
      * "1h 10m 5s", unit="s",  target_unit="us",  integer=True    -> 4205000000
      * "101ns",     unit="s",  target_unit="ns",  integer=True    -> 101
      * "101ns",     unit="s",  target_unit="us",  integer=False   -> 0.101
    """

    sipfx, base_unit = separate_si_prefix(unit)
    target_sipfx, target_base_unit = None, base_unit

    if target_unit:
        target_sipfx, target_base_unit = separate_si_prefix(target_unit)
        if target_base_unit != base_unit:
            raise Error(f"the target base unit has to be '{base_unit}', not '{target_base_unit}")

    if Trivial.is_num(hval):
        if sipfx:
            hval = f"{hval}{sipfx}"
        hval = f"{hval}{base_unit}"

    specs, scalers, multiple = _tokenize_prepare(base_unit)
    tokens = _tokenize(hval, specs, name, multiple=multiple)

    result = 0.0
    for base_unit, val in tokens.items():
        result += val * scalers[base_unit]

    if target_sipfx:
        result /= _SIPFX_SCALERS[target_sipfx]

    if integer:
        result = round(result)

    return result

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

def uncapitalize(sentence):
    """
    Return 'sentence' but with the first letter in the first word modified from capital to small.
    This function includes some heuristics to avoid un-capitalizing words like "C1" or "C-state".
    """

    # Separate out the first word by splitting the sentence. If the word include a hyphen, separate
    # out the first part. E.g., "C-state residency" will become just "C".
    word = sentence
    for separator in (" ", "-"):
        split = word.split(separator)
        if len(split) < 1:
            return sentence
        word = split[0]
        if len(word) < 2:
            return sentence

    # Do nothing if the first character is lowercase or if both first and second characters are
    # upper case, which would mean this 'word' is an abbreviation, such as "DNA".
    if word[0].islower() or word[1].isupper():
        return sentence

    # Do nothing if there are digits in the word.
    for char in word:
        if char.isdigit():
            return sentence

    return sentence[0].lower() + sentence[1:]
