# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides helpers for loading and saving YAML files.
"""

from pathlib import Path, PosixPath
import yaml
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"pepc.{__name__}")

def dump(data, path, float_format=None, skip_none=False):
    """
    Dump dictionary 'data' to a file. The arguments as follows.
      * path - either the path the to the file to dump to or a file object to dump to.
      * float_format - the floating point output format. For example, if 'float_format' is '%.2f'
                       then only 2 numbers after the decimal points will be used.
      * skip_none: do not dump keys that have 'None' values.
    """

    def represent_none(dumper, _):
        """This representer makes 'yaml.dump()' use empty string for 'None' values."""
        return dumper.represent_scalar("tag:yaml.org,2002:null", "")

    def represent_float(dumper, data):
        """Apply the floating point format."""
        return dumper.represent_scalar("tag:yaml.org,2002:float", float_format % data)

    def represent_posixpath(dumper, value):
        """Convert 'PosixPath' values to strings."""
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(value))

    def copy_skip_none(data):
        """Create a copy of the 'data' dictionary and skip 'None' values."""
        copy = {}
        for key, val in data.items():
            if val is None:
                continue
            if isinstance(val, dict):
                copy[key] = copy_skip_none(val)
            else:
                copy[key] = val
        return copy

    if skip_none:
        data = copy_skip_none(data)

    yaml.add_representer(type(None), represent_none)
    yaml.add_representer(PosixPath, represent_posixpath)

    if float_format:
        yaml.add_representer(float, represent_float)

    try:
        if hasattr(path, "write"):
            yaml.dump(data, path, default_flow_style=False, sort_keys=False)
            _LOG.debug("wrote YAML file at '%s'", path.name)
        else:
            with open(path, "w", encoding="utf-8") as fobj:
                yaml.dump(data, fobj, default_flow_style=False, sort_keys=False)
            _LOG.debug("wrote YAML file at '%s'", path)
    except OSError as err:
        msg = Error(err).indent(2)
        raise Error(f"failed to write YAML file '{path}:{msg}") from err

def _load(path, included, render=None):
    """
    Implements the 'load()' function. The additional 'included' argument is a dictionary containing
    information on what files have already been included before, this is used as a countermeasure
    against circular includes.
    """

    def path_constructor(_, node):
        """Convert strings marked with '!path' tag to pathlib.Path objects."""
        return Path(node.value)

    def dict_constructor(loader, node):
        """
        Rename 'include' keys to be unique so they don't overwrite each other in the dictionary.
        """

        # Rename 'include' keys to be unique so they don't overwrite each other in the dictionary.
        includes = 0
        pairs = loader.construct_pairs(node)
        for idx, pair in enumerate(pairs):
            if pair[0] == "include":
                pairs[idx] = (f"include_{includes}", pair[1])
                includes += 1
            elif str(pair[0]).startswith("include_"):
                raise Error(f"illegal key '{pair[0]}', keys beginning with 'include_' are reserved "
                            f"for internal functions")
        return dict(pairs)

    yaml.SafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                    dict_constructor)
    yaml.SafeLoader.add_constructor("!path", path_constructor)

    fobj = None
    if render:
        func = render["func"]
        args = render["args"]
        contents = func(path.resolve(), *args)
    else:
        # We allow 'path' to be a file-like object.
        if hasattr(path, "read"):
            fobj = path
        else:
            try:
                fobj = open(path, "r", encoding="utf-8") # pylint: disable=consider-using-with
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"failed to open file '{path}':\n{msg}") from None
        contents = fobj

    try:
        loaded = yaml.safe_load(contents)
    except (TypeError, ValueError, yaml.YAMLError) as err:
        msg = Error(err).indent(2)
        raise Error(f"failed to parse YAML file '{path}':\n{msg}") from None
    except OSError as err:
        msg = Error(err).indent(2)
        raise Error(f"failed to read YAML file '{path}':\n{msg}") from None
    finally:
        if fobj and fobj is not path:
            fobj.close()

    if not loaded:
        return {}

    # Handle "include" statements.
    result = {}
    if not included:
        included = {}

    for key, value in loaded.items():
        if not str(key).startswith("include_"):
            result[key] = value
        elif value:
            try:
                value = Path(value)
            except TypeError as err:
                msg = Error(err).indent(2)
                raise Error(f"bad include statement in YAML file at '{path}':\n{msg}") from None

            if not value.is_absolute():
                value = path.parent / value

            if value not in included:
                included[value] = path
                result.update(_load(value, included, render=render))
            else:
                raise Error(f"can't include path '{value}' in YAML file '{path}' - it is already "
                            f"included in '{included[value]}'")

    _LOG.debug("loaded YAML file at '%s'", path)
    return result

def load(path, render=None):
    """
    Load a YAML file at 'path' while preserving its order. This method extends the standard YAML
    loader and adds support for the 'include' statement, which allows for including other YAML
    files. The arguments are as follows.
      * path - path to the YAML file to load or a file-like object to read the YAML contents from.
      * render - and optional argument which can be used for rendering the file at 'path' before
                 loading it. This can be useful if the file at 'path' requires a jinja2 pass before
                 being loaded a YAML file. The 'render' argument should be a dictionary with the
                 following keys:
                   o func - the function to call to render the file at 'path'. This function should
                             return the rendered contents which will then be treated as the YAML
                             file contents and will be passed to the YAML loader.
                   o args - the arguments to pass to the 'func' function. So the function will be
                            called as 'func(path, *args)', where 'path' is path to the file to
                            render.
    """

    if render and hasattr(path, "read"):
        # Can be implemented later if needed.
        raise Error("file-like objects are not supported")

    return _load(path, False, render=render)
