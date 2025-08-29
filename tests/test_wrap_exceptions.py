# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Tests for the 'ClassHelpers.WrapExceptions' class.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from typing import cast
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Any, Final

_TEST_VALUE: Final[int] = 42

class _TestClass:
    """
    A test class for testing the functionality of the 'WrapExceptions' class.
    """

    def __init__(self, raise_iter: bool = False):
        """Initialize the test class."""

        self._raise_iter = raise_iter
        self._max_iter = 2
        self._iter_cnt = 0

    def no_exceptions(self) -> int:
        """No exceptions are raised."""

        return _TEST_VALUE

    def raise_value_error(self):
        """Raise a 'ValueError' exception."""

        raise ValueError("Test 'ValueError' exception")

    def raise_permission_error(self):
        """Raise a 'PermissionError' exception."""

        raise PermissionError("Test 'PermissionError' exception")

    def raise_file_not_found_error(self):
        """Raise a 'FileNotFoundError' exception."""

        raise FileNotFoundError("Test 'FileNotFoundError' exception")

    def __iter__(self) -> _TestClass:
        """Return an iterator for the class instance."""

        self._iter_cnt = 0
        return self

    def __next__(self) -> int:
        """Return the next item in the iteration."""

        if self._iter_cnt < self._max_iter:
            self._iter_cnt += 1
            return _TEST_VALUE

        if self._raise_iter:
            raise OSError("Test 'OSError' exception.")

        raise StopIteration

    def __enter__(self) -> _TestClass:
        """Enter the runtime context."""

        return self

    def __exit__(self, *_: Any) -> None:
        """Exit the runtime context."""

        raise OSError("Test 'OSError' exception.")

def test_base_functionality():
    """Test the 'WrapExceptions' class base functionality."""

    test_obj = _TestClass()
    wrapped_obj = cast(_TestClass, ClassHelpers.WrapExceptions(test_obj))

    assert wrapped_obj.no_exceptions() == _TEST_VALUE, \
           f"Expected no exceptions to be raised and return {_TEST_VALUE}."

    try:
        wrapped_obj.raise_value_error()
    except Error:
        pass
    except Exception as err: # pylint: disable=broad-except
        assert False, f"Expected an 'Error' exception, but got {type(err)}."
    else:
        assert False, "Expected an 'Error' exception, but no exception was raised."

    try:
        wrapped_obj.raise_permission_error()
    except ErrorPermissionDenied:
        pass
    except Exception as err: # pylint: disable=broad-except
        assert False, f"Expected an 'ErrorPermissionDenied' exception, but got {type(err)}."
    else:
        assert False, "Expected an 'ErrorPermissionDenied' exception, but no exception was raised."

    try:
        wrapped_obj.raise_file_not_found_error()
    except ErrorNotFound:
        pass
    except Exception as err: # pylint: disable=broad-except
        assert False, f"Expected an 'ErrorNotFound' exception, but got {type(err)}."
    else:
        assert False, "Expected an 'ErrorNotFound' exception, but no exception was raised."

def test_iterator():
    """Test that 'WrapExceptions' class wraps exceptions from iterables."""

    test_obj = _TestClass()
    wrapped_obj = cast(_TestClass, ClassHelpers.WrapExceptions(test_obj))

    iterable = iter(wrapped_obj)
    for idx, val in enumerate(iterable):
        assert val == _TEST_VALUE, \
               f"Expected the value in iteration #{idx} to be {_TEST_VALUE}, but got {val}."

    # Test that exceptions from the iterable are wrapped correctly.
    test_obj = _TestClass(raise_iter=True)
    wrapped_obj = cast(_TestClass, ClassHelpers.WrapExceptions(test_obj))

    try:
        for idx, val in enumerate(wrapped_obj):
            pass
    except Error:
        pass
    except Exception as err: # pylint: disable=broad-except
        assert False, f"Expected an 'Error' exception, but got {type(err)}."
    else:
        assert False, "Expected an 'Error' exception, but no exception was raised."

def test_context():
    """Test that 'WrapExceptions' class wraps exceptions from context managers."""

    test_obj = _TestClass()
    wrapped_obj = cast(_TestClass, ClassHelpers.WrapExceptions(test_obj))

    try:
        with wrapped_obj:
            pass
    except Error:
        pass
    except Exception as err: # pylint: disable=broad-except
        assert False, f"Expected an 'Error' exception, but got {type(err)}."
    else:
        assert False, "Expected an 'Error' exception, but no exception was raised."
