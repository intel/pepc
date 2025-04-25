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

from  __future__ import annotations # Remove when switching to Python 3.10+.

from pathlib import Path, PosixPath
from typing import Any, IO, cast, TypedDict
from collections.abc import Callable
import yaml
from pepclibs.helperlibs import Logging
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class RenderTypedDict(TypedDict):
    """
    A dictionary type for the 'render' argument in the 'load()' function.

    Attributes:
        func: The function to call for rendering the file. It should accept a file-like object for
              the file to render, and any additional arguments. The function should return a
              file-like object with the rendered contents.
        args: The arguments to pass to the 'func' function.
    """

    func: Callable[[IO[str], Any], IO[str]]
    args: tuple[Any, ...] | list[Any]

def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
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

def dump(data: dict[str, Any],
         path: Path | IO[str],
         float_format: str | None = None,
         skip_none: bool = False):
    """
    Dump a dictionary to a YAML file.

    Args:
        data: The dictionary to dump.
        path: The file path or file object to write the YAML data to.
        float_format: The floating-point output format. For example, if set to '%.2f', only two
                      decimal places will be used for floating-point numbers. Use python 'yaml'
                      module default format if None.
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

        return dumper.represent_scalar("tag:yaml.org,2002:float", cast(str, float_format) % data)

    if skip_none:
        data = _drop_none(data)

    yaml.add_representer(type(None), _represent_none)
    yaml.add_representer(PosixPath, _represent_posixpath)

    if float_format:
        yaml.add_representer(float, _represent_float)

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

def _get_yaml_file_info_msg(fobj, basepath: str | Path | None) -> str:
    """
    Generate a descriptive message for a YAML file.

    Args:
        fobj: File object representing the YAML file.
        basepath: Optional YAML file base path to include in the message.

    Returns:
        A string containing the descriptive message for the YAML file.
    """

    msg = "YAML file"
    if hasattr(fobj, "name"):
        msg += f" '{fobj.name}'"
    if basepath:
        msg += f" (basepath '{basepath}')"

    return msg

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
          included: set[Path],
          basepath: str | Path | None,
          render: RenderTypedDict | None = None) -> dict[str, Any]:
    """
    Load and parse a YAML file.

    Args:
        fobj: The file-like object to read the YAML content from.
        included: A set with file paths that have already been included to prevent circular
                  includes.
        basepath: The base path for resolving relative "include" paths in the YAML file.
        render: Optional dictionary containing a rendering function and its arguments. If provided,
                the rendering function is used to preprocess the file contents before parsing.

    Returns:
        A dictionary representing the loaded YAML content.
    """

    yaml.SafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                    _dict_constructor)
    yaml.SafeLoader.add_constructor("!path", _path_constructor)

    close_fobj = False

    if render:
        func = render["func"]
        args = render["args"]
        fobj = func(fobj, *args)
        close_fobj = True

    try:
        loaded: dict[str, Any] = yaml.safe_load(fobj)
    except (TypeError, ValueError, yaml.YAMLError) as err:
        errmsg = Error(str(err)).indent(2)
        file_msg = _get_yaml_file_info_msg(fobj, basepath=basepath)
        raise Error(f"Failed to parse {file_msg}:\n{errmsg}") from None
    except OSError as err:
        errmsg = Error(str(err)).indent(2)
        file_msg = _get_yaml_file_info_msg(fobj, basepath=basepath)
        raise Error(f"Failed to read {file_msg}:\n{errmsg}") from None
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
            path = Path(value)
        except TypeError as err:
            errmsg = Error(str(err)).indent(2)
            file_msg = _get_yaml_file_info_msg(fobj, basepath=basepath)
            raise Error(f"Bad 'include' statement in {file_msg}':\n{errmsg}") from None

        if not path.is_absolute():
            if basepath is None:
                file_msg = _get_yaml_file_info_msg(fobj, basepath=basepath)
                raise Error(f"Relative 'include' path '{path}' in {file_msg} but no base path "
                            "was provided")
            path = basepath / path

        if path not in included:
            included.add(path)
            with open(path, "r", encoding="utf-8") as fobj:
                contents = _load(fobj, included, basepath=path.parent, render=render)
            _merge_dicts(result, contents)
        else:
            file_msg = _get_yaml_file_info_msg(fobj, basepath=basepath)
            raise Error(f"Circular dependency found: Include path '{path}' in '{file_msg}' "
                        f"was already included")

    if not hasattr(fobj, "read"):
        _LOG.debug("Loaded YAML file at '%s'", fobj)

    return result

def load(fobj: IO[str],
         basepath: str | Path | None = None,
         render: RenderTypedDict | None = None) -> dict[str, Any]:
    """
    Load a YAML file. Extend the standard YAML loader by adding support for the 'include' statement,
    which allows including other YAML files. Optionally, it can render the file using a custom
    function before loading it as YAML (e.g., for Jinja2 rendering).
 
    If the the included file overrides a key in the main file, the value from the the
    sub-dictionaries will be merged.

    Args:
        fobj: The file-like object to read the YAML contents from.
        path: The base path for resolving relative "include" paths in the YAML file.
        render: Optional argument for rendering the file before loading it.

    Returns:
        A dictionary representing the contents of the loaded YAML file.
    """

    return _load(fobj, set(), basepath=basepath, render=render)
