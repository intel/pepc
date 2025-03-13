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

def bytesize(size: int | float,
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

def scale_si_val(val: int | float, unit: str) -> float:
    """
    Scale a value based on a SI unit prefix.

    Args:
        val: The numerical value to be scaled.
        unit: The unit of the value, which may include a SI prefix (e.g., "kHz", "ms").

    Returns:
        float: The scaled value with the SI prefix removed from the unit.

    Examples:
        >>> scale_si_val(5, unit="kHz")
        5000
        >>> scale_si_val(10, unit="ms")
        0.01
        >>> scale_si_val(10, unit="s")
        10
    """

    prefix, _ = separate_si_prefix(unit)

    if not prefix:
        return val

    scale_factor = _SIPFX_SCALERS[prefix]
    return val * scale_factor

def duration(seconds: int | float, s: bool = True) -> str:
    """
    Convert a duration in seconds to a human-readable format. If the amount of seconds is less than
    1, return the result of 'num2si()' with the unit "s".

    Args:
        second: The duration in seconds.
        s: Whether to include seconds in the output for durations greater than 1 minute.

    Returns:
        str: The human-readable duration string.

    Examples:
        >>> duration(3661)
        "1h 1m 1s"
        >>> duration(3661, s=False)
        "1h 1m"
        >>> duration(0.001, s=True)
        "1ms"
    """

    if abs(seconds) < 1:
        return num2si(seconds, unit="s", decp=1, strip_zeroes=True)

    if seconds < 0:
        sign = "-"
        seconds = -seconds
    else:
        sign = ""

    (mins, secs) = divmod(round(seconds), 60)
    (hours, mins) = divmod(mins, 60)
    (days, hours) = divmod(hours, 24)

    result = ""
    if days:
        result += f"{days} days "
    if hours:
        result += f"{hours}h "
    if mins:
        result += f"{mins}m "
    if s or abs(seconds) < 60:
        if abs(seconds) < 1:
            result += f"{secs}".rstrip("0").rstrip(".")
            result += "s"
        elif secs:
            result += f"{secs}s "

    return sign + result.strip()

def _tokenize(hval: str,
              specs: dict[str, str],
              what: str | None = None,
              multiple: bool = True) -> dict[str, int | float]:
    """
    Split a human-provided value string into tokens based on unit names specified in the 'specs'
    dictionary.

    Args:
        hval: The human-provided value string to be tokenized.
        specs: The specifiers dictionary, where keys are unit symbols and values are their
               corresponding names.
        what: A description of what is being parsed, used in error messages.
        multiple: If True, allow multiple unit-value pairs in 'hval' (e.g., "1d 5h"). If False,
                  restricts to a single unit-value pair.

    Returns:
        A dictionary where keys are unit symbols and values are the corresponding numeric values.

    Example:
        >>> hval = "1d 4m 1s"
        >>> specs = {"d": "days", "m": "minutes", "s": "seconds"}
        >>> _tokenize(hval, specs)
        {'d': 1, 'm': 4, 's': 1}
    """

    if what:
        what = f" {what}"
    else:
        what = ""

    tokens_str: dict[str, str] = {}
    tokens: dict[str, int | float] = {}
    rest = hval

    for spec in specs:
        split = rest.split(spec, 1)
        if len(split) > 1:
            tokens_str[spec] = split[0]
            rest = split[1]
        else:
            rest = split[0]

    if rest.strip():
        raise Error(f"Failed to parse{what} value '{hval}'")

    if not multiple and len(tokens_str) > 1:
        raise Error(f"Failed to parse{what} value '{hval}': should be one value")

    for idx, (spec, val) in enumerate(tokens_str.items()):
        if idx < len(tokens_str) - 1:
            # This is not the last element, it must be an integer.
            try:
                tokens[spec] = int(val)
            except ValueError:
                raise Error(f"Failed to parse{what} value '{hval}': non-integer amount of "
                            f"{specs[spec]}") from None
        else:
            # This is the last element. It can be a floating point or integer.
            try:
                tokens[spec] = float(val)
            except ValueError:
                raise Error(f"Failed to parse{what} value '{hval}': non-numeric amount of "
                            f"{specs[spec]}") from None

            if Trivial.is_int(val):
                tokens[spec] = int(val)

    return tokens

def _tokenize_prepare(unit: str) -> tuple[dict[str, str], dict[str, int | float], bool]:
    """
    Prepare for tokenizing a human-oriented value which has unit 'unit'.

    Args:
        unit: The unit of measurement to prepare for tokenizing.

    Returns:
        A tuple containing:
            specs: The specifiers dictionary, suitable for passing to the '_tokenize()' function.
            scalers: The scalers dictionary, with keys being the specifiers from 'specs' and values
                     being the corresponding scaling factors.
            multiple: Whether multiple specifiers can be used, such as in "1d 5h" for time.
    """

    specs: dict[str, str] = {}
    scalers: dict[str, int | float] = {}
    multiple = False

    fullname = SUPPORTED_UNITS.get(unit, unit)

    # Create the specifiers dictionary.
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

def parse_human(hval: str | float | int,
                unit: str,
                target_unit: str | None = None,
                integer: bool = True,
                what: str | None = None):
    """
    Convert a user-provided value 'hval' into an integer or float amount of 'unit' units (hertz,
    seconds, etc).

    Args:
        hval: The value to convert. Can be of type string, int, or float. If it is a string, it may
              include the unit.
        unit: The unit of 'hval', including any SI prefixes.
        target_unit: The unit of the result, including any SI prefixes. Defaults to the same 'unit'
                     without a SI prefix.
        integer: If True, round the result to the nearest integer and return an 'int' type,
                 otherwise return the result as a floating point number.
        what: An optional name associated with the value, used only in case of an error for
              formatting a nicer message.

    Returns:
        int or float: The converted value in the target unit.

    Examples:
        >>> parse_human("1m", unit="s", target_unit="s", integer=True)
        60
        >>> parse_human("100s", unit="s", target_unit="ns", integer=True)
        100000000000
        >>> parse_human("1us", unit="s", target_unit="ns", integer=True)
        1000
        >>> parse_human("1h 10m 5s", unit="s", target_unit="s", integer=True)
        4205
        >>> parse_human("1h 10m 5s", unit="s", target_unit="us", integer=True)
        4205000000
        >>> parse_human("101ns", unit="s", target_unit="ns", integer=True)
        101
        >>> parse_human("101ns", unit="s", target_unit="us", integer=False)
        0.101
    """

    sipfx, base_unit = separate_si_prefix(unit)
    target_sipfx, target_base_unit = None, base_unit

    if target_unit:
        target_sipfx, target_base_unit = separate_si_prefix(target_unit)
        if target_base_unit != base_unit:
            raise Error(f"the target base unit has to be '{base_unit}', not '{target_base_unit}")

    hval = str(hval)
    if Trivial.is_num(hval):
        if sipfx:
            hval = f"{hval}{sipfx}"
        hval = f"{hval}{base_unit}"

    specs, scalers, multiple = _tokenize_prepare(base_unit)
    tokens = _tokenize(hval, specs, what, multiple=multiple)

    result = 0.0
    for base_unit, val in tokens.items():
        result += val * scalers[base_unit]

    if target_sipfx:
        result /= _SIPFX_SCALERS[target_sipfx]

    if integer:
        result = round(result)

    return result

def parse_human_range(rng: str,
                      unit: str,
                      target_unit: str | None = None,
                      integer: bool = True,
                      sep: str = ",",
                      what: str | None = None) -> tuple[int | float, int | float]:
    """
    Convert a user-provided range  'rng' into a pair of an integer or float numbers, taking into
    account the unit. The range is expected to be in the form of two numbers separated by 'sep'.
    Each number is parsed with 'human_range()'.

    Args:
        rng: The range string to parse, expected to contain two numbers separated by 'sep'.
        unit: The unit of the 2 numbers in 'rng'.
        target_unit: The unit of the numbers, including any SI prefixes. Defaults to the same 'unit'
                     without a SI prefix.
        integer: Whether to round the parsed values to integers.
        sep: The separator used in the range string.
        what: An optional name associated with the values in 'rng', used only in case of an error
        for formatting a nicer message.

    Returns:
        A tuple containing the parsed range.

    Example.
      * parse_human_range("1m, 2m", unit="s", target_unit="s", integer=True)
        (60, 120)
      * parse_human_range("500us - 1ms", unit="s", target_unit="ms", sep="-", integer=True)
        (0.5, 1)
    """

    split_rng = Trivial.split_csv_line(rng, sep=sep)

    if len(split_rng) != 2:
        raise Error(f"Bad {what} range '{rng}', it should include 2 numbers separated with '{sep}'")

    vals = [0, 0]

    for idx, val in enumerate(split_rng):
        vals[idx] = parse_human(val, unit=unit, target_unit=target_unit, integer=integer, what=what)

    if len(vals) == 2:
        if vals[1] - vals[0] < 0:
            raise Error(f"Bad {what} range '{rng}', first number cannot be greater than the second "
                        f"number")
        if vals[0] == vals[1]:
            raise Error(f"Bad {what} range '{rng}', first number cannot be the same as the second "
                        f"number")

    if integer:
        return round(vals[0]), round(vals[1])
    return vals[0], vals[1]

def uncapitalize(sentence: str) -> str:
    """
    Convert the first letter of the first word in the sentence from uppercase to lowercase, with
    some heuristics to avoid un-capitalizing certain words.

    The following kind of words will not be un-capitalized:
    - Include a hyphen, where the first part is a single character (e.g., "C-state").
    - Have the first character already in lowercase.
    - Have both the first and second characters in uppercase (e.g., abbreviations like "DNA").
    - Contain any digits.

    Args:
        sentence: The input sentence to be modified.

    Returns:
        The modified sentence with the first letter of the first word in lowercase, if applicable.
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
