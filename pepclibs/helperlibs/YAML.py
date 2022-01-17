# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides helpers for dealing with YAML files.
"""

import logging
from pathlib import Path, PosixPath
import yaml
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs import Jinja2

_LOG = logging.getLogger()

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
        return dumper.represent_scalar(u'tag:yaml.org,2002:float', float_format % data)

    def represent_posixpath(dumper, value):
        """Convert 'PosixPath' values to strings."""
        return dumper.represent_scalar(u'tag:yaml.org,2002:str', str(value))

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

    if hasattr(path, "write"):
        yaml.dump(data, path, default_flow_style=False)
        _LOG.debug("wrote YAML file at '%s'", path.name)
    else:
        with open(path, "w") as fobj:
            yaml.dump(data, fobj, default_flow_style=False)
        _LOG.debug("wrote YAML file at '%s'", path)

def _load(path, jenv, included):
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
    if jenv:
        contents = Jinja2.render_template(jenv, path.resolve())
    else:
        try:
            fobj = contents = open(path, "r")
        except OSError as err:
            raise Error(f"failed to open file '{path}':\n{err}") from None

    try:
        loaded = yaml.safe_load(contents)
    except (TypeError, ValueError, yaml.YAMLError) as err:
        raise Error(f"failed to parse YAML file '{path}':\n{err}") from None
    except OSError as err:
        raise Error(f"failed to read YAML file '{path}':\n{err}") from None
    finally:
        if fobj:
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
                raise Error(f"bad include statement in YAML file at '{path}': {err}") from None

            if not value.is_absolute():
                value = path.parent / value

            if value not in included:
                included[value] = path
                result.update(_load(value, jenv, included))
            else:
                raise Error(f"can't include path '{value}' in YAML file '{path}' - it is already "
                            f"included in '{included[value]}'")

    _LOG.debug("loaded YAML file at '%s'", path)
    return result

def load(path, jenv=None):
    """
    Load a YAML file at 'path' while preserving its order. This function also implements including
    other YAML files, which is implemented using the "include" key. The optional 'jenv' argument
    indicates that the YAML file requires a Jinja2 pass.

    Note, the order of Yaml file keys is preserved because in Python 3.6+ dictinaries preserve
    insertion order.
    """

    return _load(path, jenv, False)
