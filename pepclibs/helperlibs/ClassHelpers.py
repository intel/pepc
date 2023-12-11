# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Miscellaneous common helpers for class objects.
"""

import types
import logging
from pepclibs.helperlibs.Exceptions import Error, ErrorPermissionDenied, ErrorNotFound

_LOG = logging.getLogger()

class SimpleCloseContext():
    """
    Many classes we that we have use the same context manager '__enter__()' and '__exit__()' methods
    implementation. This class helps avoid code duplication and can be sub-classed to get the
    default implementation of the context manager that just calls 'close()' on exit.
    """

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close() # pylint: disable=no-member

class WrapExceptions:
    """This class allows for wrapping objects in order to intercept their exceptions."""

    def _get_exception(self, name, err, target_exception):
        """
        Format and return a 'target_exception' exception object for exception 'err' happened in
        method 'name'.
        """

        errmsg = Error(err).indent(2)
        if self._get_err_prefix:
            msg = f"{self._get_err_prefix(self._obj, name)}:\n{errmsg}"
        else:
            msg = f"method '{name}()' failed:\n{errmsg}"

        errno = getattr(err, "errno", None)
        return target_exception(msg, errno=errno)

    def _wrap(self, name):
        """Wrap the 'name' method."""

        def wrapper(self, *args, **kwargs):
            """The actual wrapper."""

            try:
                return getattr(self._obj, name)(*args, **kwargs)
            except Error:
                # Do not translate exceptions that are already based on 'Error'.
                raise
            except PermissionError as err:
                raise self._get_exception(name, err, ErrorPermissionDenied) from err
            except FileNotFoundError as err:
                raise self._get_exception(name, err, ErrorNotFound) from err
            except Exception as err:
                raise self._get_exception(name, err, Error) from err

        setattr(self, name, types.MethodType(wrapper, self))

    def __init__(self, obj, get_err_prefix=None):
        """
        Intercept and translate exceptions of object 'obj' to exceptions defined in 'Exceptions.py'.
        The arguments are as follows.
          * obj - the object to intercept and translate exceptions for.
          * get_err_prefix - a method which will be called when forming the exception message.
                             Should return a string, which will be used as the exception message
                             prefix.

        The translation is as follows.
           * PermissionError -> ErrorPermissionDenied
           * FileNotFoundError -> ErrorNotFound
           * If source exception is based on 'Exception', translate to 'Error', otherwise do not
             translate.
        """

        self._obj = obj
        self._get_err_prefix = get_err_prefix

        for name in dir(obj):
            attr = getattr(obj, name, None)
            if not attr:
                continue

            # If the attribute is not a private attribute and it is a function, then wrap it.
            if not name.startswith("_") and hasattr(attr, "__call__"):
                self._wrap(name)
            # But we want to wrap iteration methods.
            elif name in {"__next__", "__iter__"}:
                self._wrap(name)

    def __enter__(self):
        """The context enter method."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """The context exit method."""
        try:
            self.close()
        except Exception as err: # pylint: disable=broad-exception-caught
            _LOG.warning(err)

    def __getattr__(self, name):
        """Fall-back to the wrapped object attributes."""
        return getattr(self._obj, name)

    def __iter__(self):
        """Return iterator."""

        if hasattr(self._obj, "__iter__"):
            return self
        raise self._target_exception(f"object of type '{type(self._obj)}' is not iterable")

    def __next__(self):
        """Next iteration."""
        return self._obj.__next__()

def close(cls_obj, close_attrs=None, unref_attrs=None):
    """
    Uninitialize a class object 'cls_obj' by freeing objects referred to by attributes in 'attrs'.

    1. The 'cls_obj' class object may store references to other objects, which were created outside
       of 'cls_obj' (for example, were provided to 'cls_obj.__init__()'). A typical example:
       'self._pman'. The list of 'cls_obj' attribute names of this sort should be provided via
       'unref_attrs'. In this case, this method will set the attributes to 'None', thus removing a
       reference to the object.

    2. The 'cls_obj' class object may store references to other objects, which were created by
       'cls_obj'. The list of 'cls_obj' attribute names of this sort should be provided via
       'close_attrs'. In this case, this method will first close the object by calling its 'close()'
       method, then set the attribute to 'None' to remove a reference.

    3. Some attributes of the 'cls_obj' class may store references to other objects which are of
       type #1 or #2, depending on various factors. For example, 'self._pman' may be provided by the
       user, or may be created by 'cls_obj'. In this situation, this method expects the 'cls_obj' to
       have an extra attribute named as '_close_{attr}', containing a boolean which tells whether
       the object in '{attr}' have to be closed. For example, if 'self._close_pman' attribute exists
       and it is 'True', then the 'self._pman' object should be closed. Otherwise it won't be
       closed.

    Note, the implementation uses a lot of 'getattr()' and 'hasattr()' because the assumption is
    that this function can be called from the destructor, which may happen even before the
    '__init__()' has finished (consider a crash in the middle of '__init__()'), so the attributes
    may not even exists.
    """

    if unref_attrs is None:
        unref_attrs = []
    if close_attrs is None:
        close_attrs = []

    for attr in close_attrs:
        if not hasattr(cls_obj, attr):
            _LOG.warning("close(close_attrs=<list>): non-existing attribute '%s' in '%s'",
                         name, cls_obj)

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
                _LOG.warning("BUG: bad value of attribute '%s' in '%s'", name, cls_obj)
                _LOG.debug_print_stack()
                setattr(cls_obj, attr, None)
                continue

        if run_close:
            if hasattr(obj, "close"):
                getattr(obj, "close")()
            else:
                _LOG.debug("BUG: no 'close()' method in '%s'", obj)
                _LOG.debug_print_stack()

        setattr(cls_obj, attr, None)

    for attr in unref_attrs:
        if not hasattr(cls_obj, attr):
            _LOG.warning("close(unref_attrs=<list>): non-existing attribute '%s' in '%s'",
                         name, cls_obj)

        obj = getattr(cls_obj, attr, None)
        if obj:
            setattr(cls_obj, attr, None)
