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
