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

from pepclibs.helperlibs import Human

_BYTESIZE_TEST_DATA = [
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

_SEPARATE_SI_PREFIX_TEST_DATA = [
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

_NUM2SI_TEST_DATA = [
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


_SCALE_SI_VAL_TEST_DATA = [
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
