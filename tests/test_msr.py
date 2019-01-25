#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Antti Laakso <antti.laakso@linux.intel.com>

"""Unittests for the public methods of the 'MSR' module."""

import random
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, ANY
from common import mock_Proc
from pepclibs.msr import MSR

_TEST_DATA_BYTES = random.randbytes(8)
_TEST_DATA = int.from_bytes(_TEST_DATA_BYTES, byteorder="little")

#pylint:disable=no-self-use

@patch("builtins.open", new_callable=mock_open, read_data=_TEST_DATA_BYTES)
@patch("helperlibs.Procs.Proc", new=mock_Proc)
class TestMSR(unittest.TestCase):
    """Unittests for the 'MSR' module."""

    def test_read(self, m_open):
        """Test the 'read()' method, and verify output data."""

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for cpu in (0, 1, 99):
                    for regsize in (4, 8):
                        mask = (1 << 8 * regsize) - 1

                        res = msr.read(addr, regsize=regsize, cpu=cpu)
                        m_open.assert_called_with(Path(f"/dev/cpu/{cpu}/msr"), ANY)
                        m_open().seek.assert_called_with(addr)
                        self.assertEqual(res, _TEST_DATA & mask)

    def test_read_iter(self, m_open):
        """Test the 'read_iter()' method, and verify output."""

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for regsize in (4, 8):
                    mask = (1 << 8 * regsize) - 1
                    cpus = [0, 1, 3, 4]

                    for cpu, res in msr.read_iter(addr, regsize=regsize, cpus=cpus):
                        m_open.assert_called_with(Path(f"/dev/cpu/{cpu}/msr"), ANY)
                        m_open().seek.assert_called_with(addr)
                        self.assertEqual(cpu, cpus.pop(0))
                        self.assertEqual(res, _TEST_DATA & mask)

                    self.assertEqual(m_open().read.call_count, 4)
                    m_open.reset_mock()

    def test_write(self, m_open):
        """Test the 'write()' method, and verify call arguments."""

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for cpu in (0, 1, 99):
                    for regsize in (4, 8):
                        mask = (1 << 8 * regsize) - 1

                        msr.write(addr, _TEST_DATA & mask, regsize=regsize, cpus=cpu)
                        m_open.assert_called_with(Path(f"/dev/cpu/{cpu}/msr"), ANY)
                        m_open().seek.assert_called_with(addr)

                        ref_data = int.to_bytes(_TEST_DATA & mask, regsize, byteorder="little")
                        m_open().write.assert_called_with(ref_data)

    def test_set(self, m_open):
        """
        Test the 'set()' method, and verify that register write is done only if the bits are not
        already set.
        """

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for cpu in (0, 1, 99):
                    for regsize in (4, 8):
                        mask = (1 << 8 * regsize) - 1

                        msr.set(addr, _TEST_DATA & mask, regsize=regsize, cpus=cpu)
                        m_open().write.assert_not_called()

                        new_value = _TEST_DATA + 1
                        msr.set(addr, new_value & mask, regsize=regsize, cpus=cpu)

                        m_open().seek.assert_called_with(addr)
                        m_open().write.assert_called_once()

                        ref_data = int.to_bytes((_TEST_DATA | new_value) & mask, regsize,
                                                byteorder="little")
                        m_open().write.assert_called_with(ref_data)
                        m_open.reset_mock()

    def test_clear(self, m_open):
        """
        Test the 'clear()' method, and verify that register write is done only if the bits are not
        already cleared.
        """

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for cpu in (0, 1, 99):
                    for regsize in (4, 8):
                        mask = (1 << 8 * regsize) - 1

                        msr.clear(addr, 0 & mask, regsize=regsize, cpus=cpu)
                        m_open().write.assert_not_called()

                        msr.clear(addr, _TEST_DATA & mask, regsize=regsize, cpus=cpu)
                        m_open().write.assert_called_once()

                        ref_data = int.to_bytes(0 & mask, regsize, byteorder="little")
                        m_open().write.assert_called_with(ref_data)
                        m_open.reset_mock()

    def test_toggle_bit(self, m_open):
        """
        Test the 'toggle_bit()' method, and verify that register write is done only when the new bit
        value is different to the value in the register.
        """

        with MSR.MSR() as msr:
            for addr in (MSR.MSR_PM_ENABLE, MSR.MSR_MISC_FEATURE_CONTROL, MSR.MSR_HWP_REQUEST):
                for cpu in (0, 1, 99):
                    for regsize in (4, 8):
                        mask = (1 << 8 * regsize) - 1

                        val = int(bool(_TEST_DATA & 1))
                        msr.toggle_bit(addr, 0, val, regsize=regsize, cpus=cpu)
                        m_open().write.assert_not_called()

                        msr.toggle_bit(addr, 0, int(not bool(val)), regsize=regsize, cpus=cpu)
                        m_open().write.assert_called_once()

                        ref_data = int.to_bytes((_TEST_DATA ^ 1) & mask, regsize,
                                                byteorder="little")
                        m_open().write.assert_called_with(ref_data)
                        m_open.reset_mock()

if __name__ == '__main__':
    unittest.main()
