# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides capabilities of redefining exceptions in existing classes.
"""

import types
import logging
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

class WrapExceptions:
    """This class allows for wrapping objects in order to intercept their exceptions."""

    def _get_exception(self, name, err):
        """
        Format and return an 'Error' exception object for exception 'err' happened in method
        'name'.
        """

        # pylint: disable=protected-access
        errno = getattr(err, "errno", None)
        if self._we_get_err_prefix:
            return Error("%s: %s" % (self._we_get_err_prefix(self._obj, name), err),
                         errno=errno)
        return Error("method '%s()' failed: %s" % (name, err), errno=errno)
        # pylint: enable=protected-access

    def __init__(self, obj, methods=None, exceptions=None, get_err_prefix=None):
        """
        Wrap 'obj' and intercept exceptions in the 'exceptions' collection from every method in
        'methods' (default all non-private) and raise an 'Error' type exception instead. If
        'get_err_prefix' argument is provided, it should be a function which must return a string
        that will be used as the error message prefix. The function signature is
        'get_err_prefix(obj, methodname)'. The wrapped version of 'obj' is returned.
        """

        def wrap(name):
            """Create and return the wrapper for the 'name' method of the wrapped class."""

            def wrapper(self, *args, **kwargs):
                """The actual wrapper."""
                try:
                    return getattr(self._obj, name)(*args, **kwargs)
                except self._we_exceptions as err:
                    raise self._get_exception(name, err) from err

            return types.MethodType(wrapper, self)

        if not exceptions:
            exceptions = (Exception, )

        self._obj = obj
        self._we_exceptions = exceptions
        self._we_get_err_prefix = get_err_prefix

        if not methods:
            methods = dir(obj)

        for name in methods:
            if not hasattr(obj, name):
                continue

            value = getattr(obj, name)
            # If the attribute is not a private attribute and it is a function, then wrap it.
            if (name[0] != "_" and hasattr(value, "__call__")) or name == "__next__":
                setattr(self, name, wrap(name))

    def __enter__(self):
        """The context enter method."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """The context exit method."""
        self.close()

    def __getattr__(self, name):
        """Fall-back to the wrapped object attributes."""
        return getattr(self._obj, name)

    def __iter__(self):
        """Return iterator."""

        if hasattr(self._obj, "__iter__"):
            return self
        raise Error("object of type '%s' is not iterable" % type(self._obj))

    def __next__(self):
        """Next iteration."""
        return self._obj.__next__()
