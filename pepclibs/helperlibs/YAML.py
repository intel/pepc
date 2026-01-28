# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide YAML file reading and writing capabilities with extended functionality. For the loading,
support "include" statements and pre-rendering.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pathlib import Path, PosixPath
from collections.abc import Callable
import yaml
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Any, IO, cast, TypedDict, Mapping


    class RenderTypedDict(TypedDict):
        """
        A dictionary type for the 'render' argument in the 'load()' function.

        Attributes:
            func: The function to call for rendering the file. It accepts the following arguments.
                    - 'path': The path to the file to render, used for logging, messages, may be
                              resolving some relative paths, but not for reading the contents.
                    - 'fobj': A file-like object for the file to render, will be used for reading
                              the contents of the file.
                  The function returns a tuple containing the following:
                    - 'path': The path to the rendered file.
                    - 'fobj': An optional file-like object for the rendered file. If provided, it
                              will be used for reading the contents of the rendered file, and 'path'
                              will not be used for reading the contents (will only be used for
                              logging and resolving relative 'include' paths) If not provided (None
                              value), 'path' will be used for reading the contents of the rendered
                              file.
            args: The arguments to pass to the 'func' function.
        """

        func: Callable[[Path, IO[str], Any], tuple[Path, IO[str] | None]]
        args: tuple[Any, ...] | list[Any]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _drop_none(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Create a copy of the input dictionary, excluding keys with 'None' values.

    Args:
        data: The input dictionary to process.

    Returns:
        A new dictionary without keys that had 'None' values.
    """

    copy = {}
    for key, val in data.items():
        if val is None:
            continue
        if isinstance(val, dict):
            copy[key] = _drop_none(val)
        else:
            copy[key] = val

    return copy

def _represent_none(dumper: yaml.Dumper, _) -> yaml.ScalarNode:
    """
    Represent 'None' values as empty strings in YAML output.

    Args:
        dumper: The YAML dumper instance used for serialization.
        _: The value to be represented (ignored in this case).

    Returns:
        A YAML scalar node representing an empty string.
    """

    return dumper.represent_scalar("tag:yaml.org,2002:null", "")

def _represent_posixpath(dumper: yaml.Dumper, value: PosixPath) -> yaml.ScalarNode:
    """
    Represent a 'PosixPath' object as a YAML scalar node.

    Args:
        dumper: The YAML dumper instance used to serialize the object.
        value: The 'PosixPath' object to be converted and represented.

    Returns:
        A YAML scalar node representing the 'PosixPath' object as a string.
    """

    return dumper.represent_scalar("tag:yaml.org,2002:str", str(value))

def dump(data: Mapping[str, Any],
         path: Path | IO[str],
         float_format: str = "",
         int_format: str = "",
         skip_none: bool = False):
    """
    Dump a dictionary to a YAML file.

    Args:
        data: The dictionary to dump.
        path: The file path or file object to write the YAML data to.
        float_format: The floating-point output format. For example, if set to '%.2f', only two
                      decimal places will be used for floating-point numbers. Use python 'yaml'
                      module default format if an empty string.
        skip_none: If True, exclude keys with 'None' values from the output.
    """

    def _represent_float(dumper: yaml.Dumper, data: float) -> yaml.ScalarNode:
        """
        Represent a floating-point number in YAML format using format in 'float_format'.

        Args:
            dumper: The YAML dumper instance used to serialize the data.
            data: The floating-point number to be formatted and represented.

        Returns:
            A YAML scalar node representing the formatted floating-point number.
        """

        _data = float_format % data
        return dumper.represent_scalar("tag:yaml.org,2002:float", _data)

    def _represent_int(dumper: yaml.Dumper, data: int) -> yaml.ScalarNode:
        """
        Represent an integer in YAML format using format in 'int_format'.

        Args:
            dumper: The YAML dumper instance used to serialize the data.
            data: The integer to be formatted and represented.

        Returns:
            A YAML scalar node representing the formatted integer.
        """

        _data = int_format % data
        return dumper.represent_scalar("tag:yaml.org,2002:int", _data)

    if skip_none:
        data = _drop_none(data)

    yaml.add_representer(type(None), _represent_none)
    yaml.add_representer(PosixPath, _represent_posixpath)

    if float_format:
        yaml.add_representer(float, _represent_float)

    if int_format:
        yaml.add_representer(int, _represent_int)

    try:
        if hasattr(path, "write"):
            yaml.dump(data, path, default_flow_style=False, sort_keys=False)
            if hasattr(path, "name"):
                _LOG.debug("wrote YAML file at '%s'", path.name)
        else:
            with open(path, "w", encoding="utf-8") as fobj:
                yaml.dump(data, fobj, default_flow_style=False, sort_keys=False)
            _LOG.debug("wrote YAML file at '%s'", path)
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"failed to write YAML file '{path}':\n{msg}") from err

def _dict_constructor(loader: yaml.Loader, node: yaml.Node) -> dict[str, Any]:
    """
    Process a YAML mapping node and rename 'include' keys to ensure uniqueness.

    Args:
        loader: The YAML loader instance.
        node: The YAML node representing the mapping.

    Returns:
        A dictionary with modified "include" keys.
    """

    # Rename 'include' keys to be unique so they don't overwrite each other in the dictionary.
    includes = 0
    pairs = loader.construct_pairs(node)
    for idx, pair in enumerate(pairs):
        if pair[0] == "include":
            pairs[idx] = (f"__include_{includes}", pair[1])
            includes += 1
        elif str(pair[0]).startswith("include_"):
            raise Error(f"illegal key '{pair[0]}', keys beginning with '__include_' are reserved "
                        f"for internal functions")
    return dict(pairs)

def _path_constructor(_, node: yaml.ScalarNode) -> Path:
    """
    Convert a YAML scalar node with the '!path' tag to a pathlib.Path object.

    Args:
        _: The YAML loader or dumper instance (unused).
        node: The YAML scalar node containing the string to convert.

    Returns:
        A pathlib.Path object representing the path from the node's value.
    """

    return Path(node.value)

def _merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]):
    """
    Merge two dictionaries recursively.

    Args:
        dict1: The dictionary to merge into.
        dict2: The dictionary to merge from.
    """

    for key2, val2 in dict2.items():
        if isinstance(val2, dict) and key2 in dict1 and isinstance(dict1[key2], dict):
            _merge_dicts(dict1[key2], val2)
        else:
            dict1[key2] = val2

def _load(fobj: IO[str],
          path: Path,
          included: dict[Path, Path | str],
          render: RenderTypedDict | None = None) -> dict[str, Any]:
    """
    Load and parse a YAML file.

    Args:
        fobj: The file-like object to read the YAML content from.
        path: The path to the YAML file, used for error messages and resolving relative "include"
              paths. Not used for reading the contents.
        included: A dictionary with keys being file paths that have already been included, and
                  values being the paths to the YAML files that included them. This dictionary is
                  used to track included files and prevent circular dependencies.
        render: Optional dictionary containing a rendering function and its arguments. If provided,
                the rendering function is used to preprocess the file contents before parsing.

    Returns:
        A dictionary representing the loaded YAML content.
    """

    _LOG.debug("Loading YAML file at '%s'", path)

    yaml.SafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                    _dict_constructor)
    yaml.SafeLoader.add_constructor("!path", _path_constructor)

    close_fobj = False

    if render:
        func = render["func"]
        args = render["args"]
        path, rendered_fobj = func(path, fobj, *args)
        if rendered_fobj is None:
            try:
                # pylint: disable=consider-using-with
                fobj = open(path, "r", encoding="utf-8")
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to open rendered YAML file '{path}':\n{errmsg}") from None
            close_fobj = True
        else:
            fobj = rendered_fobj

    try:
        loaded: dict[str, Any] = yaml.safe_load(fobj)
    except (TypeError, ValueError, yaml.YAMLError) as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to parse YAML file {path}:\n{errmsg}") from None
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to read YAML file {path}:\n{errmsg}") from None
    finally:
        if close_fobj:
            fobj.close()

    if not loaded:
        return {}

    result = {}

    for key, value in loaded.items():
        # Keep in mind that "include" keys are renamed to "__include_0", "__include_1", etc, because
        # there may be multiple of them in the same file.
        if not str(key).startswith("__include_"):
            result[key] = value
            continue

        try:
            incl_path = Path(value)
        except TypeError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Bad 'include' statement in YAML file '{path}':\n{errmsg}") from None

        try:
            if not incl_path.is_absolute():
                incl_path = path.parent / incl_path
                incl_path = incl_path.resolve().absolute()
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to resolve 'include' path '{incl_path}' in YAML file '{path}':\n"
                        f"{errmsg}") from None

        if incl_path in included:
            raise Error(f"Circular dependency found:\n"
                        f"  * {path} includes {incl_path}\n"
                        f"  * {included[incl_path]} includes {incl_path}")

        included[incl_path] = path
        try:
            with open(incl_path, "r", encoding="utf-8") as incl_fobj:
                contents = _load(incl_fobj, path, included, render=render)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to open included YAML file '{incl_path}':\n"
                        f"{errmsg}") from None
        _merge_dicts(result, contents)

    return result

def load(path: str | Path, fobj: IO[str] | None = None,
         render: RenderTypedDict | None = None) -> dict[str, Any]:
    """
    Load a YAML file. Extend the standard YAML loader by adding support for the 'include'
    statements, which allows YAML files including other YAML files. Optionally, render the file
    using a custom function before loading it as YAML (e.g., the YAML file can be a Jinja2 template,
    which will be pre-rendered before YAML parser reads it).

    If file YAML file A includes file B, the contents of file B will be merged into file A. For
    example, if file A has a key "key1" and file B has a key "key2", the resulting dictionary will
    contain both keys. If file A has a key "key1" and file B has a sub-dictionary with the same key,
    the sub-dictionary will be merged into the "key1" dictionary in file A. If file A has a key
    "key1" and file B has a key "key1", and they are leaf nodes (not dictionaries), then the value
    from file B will override the value in file A.

    Args:
        path: The path to the YAML file to load.
        fobj: Optional file-like object to read the YAML contents from. If provided, the data
               will be read from this object instead of the file at 'path', and 'path' will be used
               for resolving relative "include" paths.
        render: Optional argument for rendering the file before loading it.

    Returns:
        A dictionary representing the contents of the loaded YAML file.
    """

    path = Path(path)

    try:
        path = path.resolve().absolute()
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        raise Error(f"Failed to resolve path '{path}':\n{errmsg}") from None

    included: dict[Path, str | Path] = {path: "the original (top level) YAML file"}
    if not fobj:
        try:
            with open(path, "r", encoding="utf-8") as load_fobj:
                return _load(load_fobj, path, included, render=render)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to open YAML file '{path}':\n{errmsg}") from None

    return _load(fobj, path, included, render=render)
