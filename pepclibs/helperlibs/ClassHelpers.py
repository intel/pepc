# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Miscellaneous common helpers for class objects.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

from typing import Any, Callable
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorNotFound

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class SimpleCloseContext:
    """
    Provide a simple context manager implementation for classes.

    This class can be subclassed to avoid duplicating the implementation of the
    '__enter__()' and '__exit__()' methods. It ensures that the 'close()' method
    is called automatically when exiting the runtime context.
    """

    def close(self):
        """Uninitialize the class object. Supposed to be implemented by the subclass."""

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, *_: Any):
        """Exit from the runtime context."""

        self.close()

class WrapExceptions:
    """
    A class to wrap objects, intercept their exceptions and translate them into custom exceptions.

    Exception Translation:
        - PermissionError -> ErrorPermissionDenied
        - FileNotFoundError -> ErrorNotFound
        - Other exceptions derived from 'Exception' -> Error
        - Exceptions not derived from 'Exception' are not translated.
    """

    def __init__(self, obj: Any, get_err_prefix: Callable[[Any, str], str] | None = None):
        """
        Initialize the instance and set up exception interception and translation.

        Args:
            obj: The object to intercept and translate exceptions for.
            get_err_prefix: A callable that generates a prefix for exception messages. Called when
                            forming the exception message. The callable should return a string to be
                            used as the exception message prefix. The arguments are the object and
                            the object method name where the exception occurred.
        """

        self._obj = obj
        self._get_err_prefix = get_err_prefix
        self._iterable: Any = None

    def _format_exception(self, name: str, err: Exception, exc_type: type[Error]) -> Error:
        """
        Format and return a custom exception object for an exception raised by a method of the
        wrapped object.

        Args:
            name: Name of the wrapped object method where the exception occurred.
            err: The original exception that was raised by the method.
            exc_type: The type of the custom exception to format and return.

        Returns:
            A formatted exception object of the specified type.
        """

        errmsg = Error(str(err)).indent(2)
        if self._get_err_prefix:
            msg = f"{self._get_err_prefix(self._obj, name)}:\n{errmsg}"
        else:
            msg = f"method '{name}()' failed:\n{errmsg}"

        kwargs: dict[str, Any] = {}
        if hasattr(err, "errno"):
            kwargs["errno"] = getattr(err, "args", None)

        return exc_type(msg, **kwargs)

    def _handle_exception(self, name: str, err: Exception):
        """
        Handle an exception from a method of the wrapped object.

        Args:
            name: The name of the method that raised the exception.
            err: The exception object raised by the method.

        Raises:
            # noqa: DAR401
            # noqa: DAR402
            ErrorPermissionDenied: If the exception is a PermissionError.
            ErrorNotFound: If the exception is a FileNotFoundError.
            Error: For all other types of exceptions.
        """

        exc_type: type[Error]
        if isinstance(err, PermissionError):
            exc_type = ErrorPermissionDenied
        elif isinstance(err, FileNotFoundError):
            exc_type = ErrorNotFound
        else:
            exc_type = Error

        raise self._format_exception(name, err, exc_type)

    def _get_wapper(self, name: str, method: Callable) -> Callable:
        """
        Wrap exceptions for a method.

        Args:
            name: The name of the method to wrap exceptions for.
            method: The method to wrap exceptions for.

        Returns:
            The wrapped version of the method.
        """

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrap the exceptions."""

            try:
                return method(*args, **kwargs)
            except Error:
                # Do not translate exceptions that are already based on 'Error'.
                raise
            except StopIteration:
                # Do not translate 'StopIteration' exceptions, they belong to the iteration
                # protocol.
                raise
            except Exception as err: # pylint: disable=broad-except
                # Translate the exception into a custom exception.
                self._handle_exception(name, err)

            return None

        return wrapper

    def __getattr__(self, name: str) -> Callable:
        """
        Override attribute access to wrap method calls with exception handling.

        Args:
            name: The name of the attribute to access.

        Returns:
            The attribute value or a wrapped callable method.
        """

        attr = getattr(self._obj, name)

        if name.startswith("_") or not hasattr(attr, "__call__"):
            # A private method or not a method, do not wrap exceptions.
            return attr

        return self._get_wapper(name, attr)

    def __enter__(self):
        """Enter the run-time context."""

        name = "__enter__"
        method = getattr(self._obj, name)
        return self._get_wapper(name, method)()

    def __exit__(self, *args: Any):
        """Exit from the runtime context."""

        name = "__exit__"
        method = getattr(self._obj, name)
        return self._get_wapper(name, method)(*args)

    def __iter__(self):
        """Return an iterator for the wrapped object."""

        name = "__iter__"
        method = getattr(self._obj, name)
        self._iterable = self._get_wapper(name, method)()
        return self

    def __next__(self):
        """Return the next iteration item."""

        if self._iterable is None:
            raise Error("No iterable object found.")

        name = "__next__"
        method = getattr(self._iterable, name)
        return self._get_wapper(name, method)()

def close(cls_obj: Any,
          close_attrs: list[str] | tuple[str, ...] = tuple(),
          unref_attrs: list[str] | tuple[str, ...] = tuple()):
    """
    Uninitialize a class object by freeing objects referred to by its attributes.

    Args:
        cls_obj: The class object to uninitialize.
        close_attrs: Attribute names referring to objects created by the class object. These objects
                     will be closed by calling their 'close()' method, and then set to 'None' to
                     remove references. Note, calling the 'close()' can be influenced by an
                     additional attribute named '_close_{attr}' in the class object.
        unref_attrs: Attribute names referring to objects created outside the class object. These
                     attributes will be set to 'None' to remove references.

    Behavior:
        1. For attributes in 'close_attrs', check if the attribute exists in the class object. If it
           exists and is not 'None', determine whether to close the object by checking for an
           additional attribute named '_close_{attr}'. If '_close_{attr}' exists and is 'True', call
           the 'close()' method of the object (if available) and set the attribute to 'None'. If
           '_close_{attr}' does not exist, assume the object should be closed.
        2. For attributes in 'unref_attrs', check if the attribute exists in the class object. If it
           exists and is not 'None', set the attribute to 'None' to remove the reference.
    """

    for attr in close_attrs:
        if not hasattr(cls_obj, attr):
            _LOG.warning("close(close_attrs=<attrs>): non-existing attribute '%s' in '%s'",
                         attr, cls_obj)

        obj = getattr(cls_obj, attr, None)
        if not obj:
            continue

        if attr.startswith("_"):
            name = f"_close{attr}"
        else:
            name = f"_close_{attr}"

        run_close = True
        if hasattr(cls_obj, name):
            run_close = getattr(cls_obj, name)
            if run_close not in (True, False):
                _LOG.warning("Bad value of attribute '%s' in '%s'", attr, cls_obj)
                _LOG.debug_print_stacktrace()
                setattr(cls_obj, attr, None)
                continue

        if run_close:
            if hasattr(obj, "close"):
                getattr(obj, "close")()
            else:
                _LOG.debug("No 'close()' method in '%s'", obj)
                _LOG.debug_print_stacktrace()

        setattr(cls_obj, attr, None)

    for attr in unref_attrs:
        if not hasattr(cls_obj, attr):
            _LOG.warning("close(unref_attrs=<list>): non-existing attribute '%s' in '%s'",
                         name, cls_obj)

        obj = getattr(cls_obj, attr, None)
        if obj:
            setattr(cls_obj, attr, None)
