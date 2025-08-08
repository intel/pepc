# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Tests for the 'Human' module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

from typing import TypedDict
from pepclibs.helperlibs import Human

class _BytesizeTestDataType(TypedDict, total=False):
    """Type for the '_BYTESIZE_TEST_DATA' list."""
    size: int | float
    decp: int
    sep: str | None
    strip_zeroes: bool
    result: str

_BYTESIZE_TEST_DATA: list[_BytesizeTestDataType] = [
    {"size": 0, "decp": 0, "sep": None, "strip_zeroes": True, "result": "0 bytes"},
    {"size": 0, "decp": 1, "sep": None, "strip_zeroes": True, "result": "0 bytes"},
    {"size": 0, "decp": 1, "sep": None, "strip_zeroes": False, "result": "0 bytes"},
    {"size": 0.0, "decp": 0, "sep": None, "strip_zeroes": True, "result": "0 bytes"},
    {"size": 0.0, "decp": 0, "sep": None, "strip_zeroes": False, "result": "0 bytes"},
    {"size": 0.0, "decp": 1, "sep": None, "strip_zeroes": True, "result": "0 bytes"},
    {"size": 0, "decp": 0, "sep": "", "strip_zeroes": True, "result": "0bytes"},
    {"size": 0, "decp": 0, "sep": "", "strip_zeroes": False, "result": "0bytes"},
    {"size": 1, "decp": 0, "sep": None, "strip_zeroes": True, "result": "1 byte"},
    {"size": 1, "decp": 1, "sep": None, "strip_zeroes": True, "result": "1 byte"},
    {"size": -1, "decp": 1, "sep": None, "strip_zeroes": True, "result": "-1 byte"},
    {"size": 9, "decp": 0, "sep": None, "strip_zeroes": True, "result": "9 bytes"},
    {"size": 9, "decp": 5, "sep": None, "strip_zeroes": True, "result": "9 bytes"},
    {"size": 10, "decp": 0, "sep": None, "strip_zeroes": True, "result": "10 bytes"},
    {"size": 10, "decp": 0, "sep": None, "strip_zeroes": False, "result": "10 bytes"},
    {"size": 10, "decp": 5, "sep": None, "strip_zeroes": True, "result": "10 bytes"},
    {"size": 10.22, "decp": 5, "sep": None, "strip_zeroes": True, "result": "10 bytes"},
    {"size": -10.22, "decp": 5, "sep": None, "strip_zeroes": True, "result": "-10 bytes"},
    {"size": 511, "decp": 0, "sep": None, "strip_zeroes": True, "result": "511 bytes"},
    {"size": 511, "decp": 3, "sep": "", "strip_zeroes": True, "result": "511bytes"},
    {"size": 512, "decp": 0, "sep": None, "strip_zeroes": True, "result": "512 bytes"},
    {"size": 1023, "decp": 0, "sep": None, "strip_zeroes": True, "result": "1023 bytes"},
    {"size": 1023, "decp": 2, "sep": "-", "strip_zeroes": True, "result": "1023-bytes"},
    {"size": -1023, "decp": 2, "sep": "-", "strip_zeroes": True, "result": "-1023-bytes"},
    {"size": 1024, "decp": 0, "sep": None, "strip_zeroes": True, "result": "1 KiB"},
    {"size": 1025, "decp": 0, "sep": None, "strip_zeroes": True, "result": "1 KiB"},
    {"size": 1025, "decp": 1, "sep": None, "strip_zeroes": True, "result": "1 KiB"},
    {"size": 1025, "decp": 1, "sep": None, "strip_zeroes": False, "result": "1.0 KiB"},
    {"size": 1025, "decp": 2, "sep": None, "strip_zeroes": False, "result": "1.00 KiB"},
    {"size": 1025, "decp": 2, "sep": None, "strip_zeroes": True, "result": "1 KiB"},
    {"size": 1025, "decp": 3, "sep": None, "strip_zeroes": False, "result": "1.001 KiB"},
    {"size": 1025, "decp": 3, "sep": None, "strip_zeroes": True, "result": "1.001 KiB"},
    {"size": 2040, "decp": 0, "sep": None, "strip_zeroes": True, "result": "2 KiB"},
    {"size": 2040, "decp": 1, "sep": None, "strip_zeroes": False, "result": "2.0 KiB"},
    {"size": 2040, "decp": 2, "sep": None, "strip_zeroes": True, "result": "1.99 KiB"},
    {"size": -2040, "decp": 2, "sep": None, "strip_zeroes": True, "result": "-1.99 KiB"},
    {"size": 2040, "decp": 3, "sep": None, "strip_zeroes": True, "result": "1.992 KiB"},
    {"size": 2048, "decp": 0, "sep": None, "strip_zeroes": True, "result": "2 KiB"},
    {"size": 7 * 1024 + 10, "decp": 0, "sep": None, "strip_zeroes": False, "result": "7 KiB"},
    {"size": 7 * 1024 + 10, "decp": 1, "sep": None, "strip_zeroes": False, "result": "7.0 KiB"},
    {"size": 7 * 1024 + 10, "decp": 1, "sep": None, "strip_zeroes": True, "result": "7 KiB"},
    {"size": 7 * 1024 + 10, "decp": 2, "sep": None, "strip_zeroes": True, "result": "7.01 KiB"},
    {"size": 2 * 1024 * 1024 - 1, "decp": 0, "sep": None, "strip_zeroes": True, "result": "2 MiB"},
    {"size": 2 * 1024 * 1024 - 1, "decp": 6, "sep": None, "result": "1.999999 MiB",
     "strip_zeroes": True},
    {"size": 5 * 1024 * 1024 * 1024, "decp": 0, "sep": None, "result": "5 GiB",
     "strip_zeroes": True},
    {"size": 5 * 1024 * 1024 * 1024 + 800 * 1024 * 1024,
     "decp": 0, "sep": None, "strip_zeroes": True, "result": "6 GiB"},
    {"size": 5 * 1024 * 1024 * 1024 + 800 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": True, "result": "5.8 GiB"},
    {"size": 5 * 1024 * 1024 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": False, "result": "5.0 TiB"},
    {"size": 5 * 1024 * 1024 * 1024 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": False, "result": "5.0 PiB"},
    {"size": 5 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": True, "result": "5 EiB"},
    {"size": -5 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": True, "result": "-5 EiB"},
    {"size": 5 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
     "decp": 1, "sep": None, "strip_zeroes": False, "result": "5.0 EiB"},
    {"size": 5 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1000,
     "decp": 0, "sep": None, "strip_zeroes": True, "result": "5000 EiB"},
]

def test_bytesize():
    """Test the 'bytesize()' function."""

    for entry in _BYTESIZE_TEST_DATA:
        size = entry["size"]
        decp = entry["decp"]
        sep = entry["sep"]
        strip_zeroes = entry["strip_zeroes"]
        expected = entry["result"]

        result = Human.bytesize(size, decp=decp, sep=sep, strip_zeroes=strip_zeroes)

        assert result == expected, \
               f"Bad result of bytesize({size}, decp={decp}, sep='{sep}', " \
               f"strip_zeroes={strip_zeroes}):\n" \
               f"expected '{expected}', got '{result}'"

class _SeparateSiPrefixTestDataType(TypedDict, total=False):
    """Type for the '_SEPARATE_SI_PREFIX_TEST_DATA' list."""
    unit: str
    result: tuple[str | None, str]

_SEPARATE_SI_PREFIX_TEST_DATA: list[_SeparateSiPrefixTestDataType] = [
    {"unit": "B", "result": (None, "B")},
    {"unit": "kB", "result": ("k", "B")},
    {"unit": "MB", "result": ("M", "B")},
    {"unit": "GB", "result": ("G", "B")},
    {"unit": "TB", "result": ("T", "B")},
    {"unit": "PB", "result": ("P", "B")},
    {"unit": "EB", "result": ("E", "B")},
    {"unit": "byte", "result": (None, "byte")},
]

def test_separate_si_prefix():
    """Test the 'separate_si_prefix()' function."""

    for entry in _SEPARATE_SI_PREFIX_TEST_DATA:
        unit = entry["unit"]
        expected = entry["result"]

        result = Human.separate_si_prefix(unit)

        assert result == expected, \
               f"Bad result of separate_si_prefix('{unit}'):\n" \
               f"expected '{expected}', got '{result}'"

class _Num2SiTestDataType(TypedDict, total=False):
    """Type for the '_NUM2SI_TEST_DATA' list."""
    value: float
    unit: str
    decp: int
    sep: str | None
    strip_zeroes: bool
    result: str

_NUM2SI_TEST_DATA: list[_Num2SiTestDataType] = [
    {"value": 0.00009999001,
     "unit": "uW", "decp": 5, "sep": " ", "strip_zeroes": False, "result": "0.09999 nW"},
    {"value": 0.00009999001,
     "unit": "W", "decp": 4, "sep": " ", "strip_zeroes": True, "result": "99.99 uW"},
    {"value": 0.00009999001,
     "unit": "W", "decp": 4, "sep": " ", "strip_zeroes": False, "result": "99.9900 uW"},
    {"value": 0.00009999001,
     "unit": "W", "decp": 5, "sep": " ", "strip_zeroes": False, "result": "99.99001 uW"},
    {"value": 0.04,
     "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "40.00 mW"},
    {"value": 0.04,
     "unit": "mW", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "40.00 uW"},
    {"value": 0.1, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": True, "result": "100 mW"},
    {"value": 0.1, "unit": "W", "decp": 0, "sep": None, "strip_zeroes": False, "result": "100mW"},
    {"value": 0.1, "unit": "W", "decp": 1, "sep": None, "strip_zeroes": False, "result": "100.0mW"},
    {"value": 0.0, "unit": "W", "decp": 0, "sep": None, "strip_zeroes": True, "result": "0W"},
    {"value": 0, "unit": "W", "decp": 0, "sep": None, "strip_zeroes": True, "result": "0W"},
    {"value": 0, "unit": "W", "decp": 0, "sep": " ", "strip_zeroes": True, "result": "0 W"},
    {"value": 0, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": True, "result": "0 W"},
    {"value": 0, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": False, "result": "0.0 W"},
    {"value": -0, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": True, "result": "0 W"},
    {"value": 0.0, "unit": "W", "decp": 0, "sep": " ", "strip_zeroes": True, "result": "0 W"},
    {"value": 1, "unit": "W", "decp": 0, "sep": " ", "strip_zeroes": True, "result": "1 W"},
    {"value": 1, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "1.00 W"},
    {"value": -1, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "-1.00 W"},
    {"value": -1.5, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "-1.50 W"},
    {"value": 999, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": True, "result": "999 W"},
    {"value": 1000, "unit": "W", "decp": 2, "sep": None, "strip_zeroes": False, "result": "1.00kW"},
    {"value": 1000.0, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": True, "result": "1 kW"},
    {"value": 1999.1, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": True, "result": "2 kW"},
    {"value": 1999, "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": False, "result": "2.0 kW"},
    {"value": 1999, "unit": "uW", "decp": 1, "sep": " ", "strip_zeroes": False, "result": "2.0 mW"},
    {"value": 1999,
     "unit": "uW", "decp": 3, "sep": " ", "strip_zeroes": False, "result": "1.999 mW"},
    {"value": 1999, "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "2.00 kW"},
    {"value": 1999, "unit": "W", "decp": 3, "sep": "", "strip_zeroes": False, "result": "1.999kW"},
    {"value": 1999 * 1000.0,
     "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": False, "result": "2.0 MW"},
    {"value": 1999 * 1000 * 1000,
     "unit": "W", "decp": 1, "sep": " ", "strip_zeroes": True, "result": "2 GW"},
    {"value": 1999 * 1000 * 1000 * 1000,
     "unit": "W", "decp": 1, "sep": "", "strip_zeroes": False, "result": "2.0TW"},
    {"value": 1999 * 1000 * 1000 * 1000 * 1000,
     "unit": "W", "decp": 2, "sep": " ", "strip_zeroes": False, "result": "2.00 PW"},
    {"value": 1999 * 1000 * 1000 * 1000 * 1000 * 1000,
     "unit": "W", "decp": 0, "sep": " ", "strip_zeroes": False, "result": "2 EW"},
    {"value": 1999 * 1000 * 1000 * 1000 * 1000 * 1000,
     "unit": "MW", "decp": 0, "sep": " ", "strip_zeroes": False, "result": "1999000 EW"},
]

def test_num2si():
    """Test the 'num2si()' function."""

    for entry in _NUM2SI_TEST_DATA:
        value = entry["value"]
        unit = entry["unit"]
        sep = entry["sep"]
        decp = entry["decp"]
        strip_zeroes = entry["strip_zeroes"]
        expected = entry["result"]

        result = Human.num2si(value, unit=unit, decp=decp, sep=sep, strip_zeroes=strip_zeroes)

        assert result == expected, \
               f"Bad result of num2si({value}, '{unit}', decp={decp}, sep='{sep}'" \
               f"strip_zeroes={strip_zeroes}):\n" \
               f"expected '{expected}', got '{result}'"


class _ScaleSiValTestDataType(TypedDict, total=False):
    """Type for the '_SCALE_SI_VAL_TEST_DATA' list."""

    value: float
    unit: str
    result: float

_SCALE_SI_VAL_TEST_DATA: list[_ScaleSiValTestDataType] = [
    {"value": 0, "unit": "kW", "result": 0},
    {"value": -5, "unit": "kW", "result": -5000},
    {"value": 1000000, "unit": "uHz", "result": 1},
    {"value": 5, "unit": "kHz", "result": 5000},
]

def test_scale_si_val():
    """Test the 'scale_si_val()' function."""

    for entry in _SCALE_SI_VAL_TEST_DATA:
        value = entry["value"]
        unit = entry["unit"]
        expected = entry["result"]

        result = Human.scale_si_val(value, unit)

        assert result == expected, \
               f"Bad result of scale_si_val({value}, '{unit}'):\n" \
               f"expected '{expected}', got '{result}'"

class _DurationTestDataType(TypedDict, total=False):
    """Type for the '_DURATION_TEST_DATA' list."""

    seconds: float
    s: bool
    result: str

_DURATION_TEST_DATA: list[_DurationTestDataType] = [
    {"seconds": 0.001, "s": True, "result": "1ms"},
    {"seconds": 0, "s": True, "result": "0s"},
    {"seconds": -0, "s": True, "result": "0s"},
    {"seconds": 1, "s": True, "result": "1s"},
    {"seconds": -1, "s": True, "result": "-1s"},
    {"seconds": 3661, "s": False, "result": "1h 1m"},
    {"seconds": 3661001.9, "s": True, "result": "42 days 8h 56m 42s"},
    {"seconds": 3661001.9, "s": False, "result": "42 days 8h 56m"},
]

def test_duration():
    """Test the 'duration()' function."""

    for entry in _DURATION_TEST_DATA:
        value = entry["seconds"]
        s = entry["s"]
        expected = entry["result"]

        result = Human.duration(value, s=s) # type: ignore

        assert result == expected, \
               f"Bad result of duration({value}, s={s}):\nexpected '{expected}', got '{result}'"

class _ParseHumanTestDataType(TypedDict, total=False):
    """Type for the '_PARSE_HUMAN_DATA' list."""

    hval: str | int | float
    unit: str
    target_unit: str | None
    integer: bool
    result: int | float

_PARSE_HUMAN_DATA: list[_ParseHumanTestDataType] = [
    {"hval": "0", "unit": "s", "target_unit": "s", "integer": True, "result": 0},
    {"hval": 0, "unit": "s", "target_unit": "s", "integer": True, "result": 0},
    {"hval": 0.0, "unit": "s", "target_unit": "s", "integer": True, "result": 0},
    {"hval": "-0", "unit": "s", "target_unit": "s", "integer": True, "result": 0},
    {"hval": "1.1", "unit": "s", "target_unit": "s", "integer": True, "result": 1},
    {"hval": "1.5", "unit": "s", "target_unit": "s", "integer": True, "result": 2},
    {"hval": "1.1", "unit": "s", "target_unit": "s", "integer": False, "result": 1.1},
    {"hval": "1.1", "unit": "s", "target_unit": "ms", "integer": False, "result": 1100.0},
    {"hval": "1200", "unit": "ms", "target_unit": "s", "integer": True, "result": 1},
    {"hval": "1200", "unit": "us", "target_unit": "s", "integer": False, "result": 0.0012},
    {"hval": 1200, "unit": "us", "target_unit": "s", "integer": False, "result": 0.0012},
    {"hval": "-1200us", "unit": "us", "target_unit": "s", "integer": False, "result": -0.0012},
    {"hval": "10%", "unit": "%", "target_unit": "%", "integer": True, "result": 10},
    {"hval": "10%", "unit": "%", "target_unit": None, "integer": True, "result": 10},
    {"hval": "1m", "unit": "s", "target_unit": "s", "integer": True, "result": 60},
    {"hval": "100s", "unit": "s", "target_unit": "ns", "integer": True, "result": 100000000000},
    {"hval": "1us", "unit": "s", "target_unit": "ns", "integer": True, "result": 1000},
    {"hval": "1h 10m 5s", "unit": "s", "target_unit": "s", "integer": True, "result": 4205},
    {"hval": "1h 10m 5s", "unit": "s", "target_unit": "us", "integer": True, "result": 4205000000},
    {"hval": "101ns", "unit": "s", "target_unit": "ns", "integer": True, "result": 101},
    {"hval": "101ns", "unit": "s", "target_unit": "us", "integer": False, "result": 0.101},
]

def test_parse_human():
    """Test the 'parse_human()' function."""

    for entry in _PARSE_HUMAN_DATA:
        hval = entry["hval"]
        unit = entry["unit"]
        target_unit = entry["target_unit"]
        integer = entry["integer"]
        expected = entry["result"]

        result = Human.parse_human(hval, unit, target_unit, integer) # type: ignore

        assert result == expected, \
               f"Bad result of parse_human('{hval}', '{unit}', target_unit='{target_unit}', " \
               f"integer={integer}):\nexpected '{expected}', got '{result}'"

_PARSE_HUMAN_RANGE = [
    {"hval": "1,2", "unit": "s", "target_unit": "s", "integer": True, "sep": ",",
     "result": (1, 2)},
    {"hval": "-1,2", "unit": "s", "target_unit": "s", "integer": True, "sep": ",",
     "result": (-1, 2)},
    {"hval": "500us - 1ms", "unit": "s", "target_unit": "ms", "integer": False, "sep": "-",
     "result": (0.5, 1)},
]

def test_parse_human_range():
    """Test the 'parse_human_range()' function."""

    for entry in _PARSE_HUMAN_RANGE:
        hval = entry["hval"]
        unit = entry["unit"]
        target_unit = entry["target_unit"]
        integer = entry["integer"]
        sep = entry["sep"]
        expected = entry["result"]

        result = Human.parse_human_range(hval, unit, target_unit, integer, sep) # type: ignore

        assert result == expected, \
               f"Bad result of parse_human_range('{hval}', '{unit}', " \
               f"target_unit='{target_unit}', integer={integer}, sep='{sep}):\n" \
               f"expected '{expected}', got '{result}'"

_CAPITALIZE_TEST_DATA = [
    {"sentence": "hello, world!", "result": "Hello, world!"},
    {"sentence": "DMA latency", "result": "DMA latency"},
    {"sentence": "c-state latency", "result": "C-state latency"},
]

def test_capitalize():
    """Test the 'capitalize()' function."""

    for entry in _CAPITALIZE_TEST_DATA:
        sentence = entry["sentence"]
        expected = entry["result"]

        result = Human.capitalize(sentence)

        assert result == expected, \
               f"Bad result of capitalize('{sentence}'):\n" \
               f"expected '{expected}', got '{result}'"

_UNCAPITALIZE_TEST_DATA = [
    {"sentence": "Hello, world!", "result": "hello, world!"},
    {"sentence": "DMA latency", "result": "DMA latency"},
    {"sentence": "C-state latency", "result": "C-state latency"},
]

def test_uncapitalize():
    """Test the 'uncapitalize()' function."""

    for entry in _UNCAPITALIZE_TEST_DATA:
        sentence = entry["sentence"]
        expected = entry["result"]

        result = Human.uncapitalize(sentence)

        assert result == expected, \
               f"Bad result of uncapitalize('{sentence}'):\n" \
               f"expected '{expected}', got '{result}'"
