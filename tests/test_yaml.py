# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Test the YAML module.
"""

from  __future__ import annotations # Remove when switching to Python 3.10+.

import io
from typing import Any, IO
from pathlib import Path
from pepclibs.helperlibs import YAML

def _assert(fobj: IO[str], expected: str):
    """
    Verify that the contents of the given file object match the expected string.

    Args:
        fobj: A file-like object to be checked.
        expected: The expected string content to compare against.

    Raises:
        AssertionError: If the contents of the file object do not match the expected string.
    """

    fobj.seek(0)
    assert fobj.read().strip() == expected.strip()

def test_yaml_dump(tmp_path: Path):
    """
    Test the YAML dump function.

    Args:
        tmp_path: A temporary directory path for testing (provided by the pytest framework).
    """

    yaml_dict: dict[str, Any] = {"key": "value"}
    fobj = io.StringIO()
    YAML.dump(yaml_dict, fobj)
    _assert(fobj, "key: value")

    # Test dumping to a file defined by a path.
    with open(tmp_path / "test.yaml", "w+", encoding="utf-8") as file_obj:
        YAML.dump(yaml_dict, file_obj)
        _assert(file_obj, "key: value")

    # Test additional options for dumping.
    yaml_dict = {"key": 1.238, "key2": None}

    fobj = io.StringIO()
    YAML.dump(yaml_dict, fobj)
    _assert(fobj, "key: 1.238\nkey2:")

    fobj = io.StringIO()
    YAML.dump(yaml_dict, fobj, skip_none=True)
    _assert(fobj, "key: 1.238")

    fobj = io.StringIO()
    YAML.dump(yaml_dict, fobj, float_format="%2.2f", skip_none=True)
    _assert(fobj, "key: 1.24")

def test_yaml_load(tmp_path: Path):
    """
    Test the YAML load function with and without a custom render function.

    Args:
        tmp_path: A temporary directory path for testing (provided by the pytest framework).
    """

    yaml_str = """cm:
    sut1:
        type: qemu
        cpus: 5
        image: !path "/tmp/image"
"""

    fobj = io.StringIO(yaml_str)
    yaml_dict = YAML.load(Path("/tmp/fake/path"), fobj=fobj)
    assert yaml_dict == {
        "cm": {
            "sut1": {
                "type": "qemu",
                "cpus": 5,
                "image": Path("/tmp/image"),
            }
        }
    }

    def _render_func(path: Path, fobj: IO[str], *_: Any) -> tuple[Path, IO[str]]:
        """
        A dummy YAML file render function. Just add a marker to the contents.

        Args:
            path: The path to the YAML file to render.
            fobj: The file object to read the contents from.
            *_: Additional arguments (unused).

        Returns:
            A tuple containing the path to the rendered version of the YAML file and a file-like
            object that can be used for reading the rendered contents.
        """

        contents: str = fobj.read()
        contents += "rendered: true"
        return path, io.StringIO(contents)

    path = tmp_path / "test.yaml"
    with open(path, "w+", encoding="utf-8") as file_obj:
        file_obj.write(yaml_str)

    render: YAML.RenderTypedDict = {
        "func": _render_func,
        "args": []
    }

    yaml_dict = YAML.load(path, render=render)
    assert yaml_dict == {
        "cm": {
            "sut1": {
                "type": "qemu",
                "cpus": 5,
                "image": Path("/tmp/image"),
            }
        },
        "rendered": True
    }

def test_yaml_load_include(tmp_path: Path):
    """
    Test the YAML load function for YAML files that contain 'include' directives.

    Args:
        tmp_path: A temporary directory path for testing (provided by the pytest framework).
    """

    yaml_str1 = f"""cm:
    sut1:
        type: qemu
        misc: "descr"
        cpus: 2
include: "file2.yaml"
include: "{tmp_path}/file3.yaml"
"""
    yaml_str2 = """cm:
    sut1:
        type: container
        misc: ["descr1", "descr2"]
    sut2:
        type: qemu"""

    yaml_str3 = """cm:
    sut1:
        type: "baremetal"
        misc: false
    sut2:
        cpus: 4"""

    with open(tmp_path / "file1.yaml", "w+", encoding="utf-8") as file_obj1, \
         open(tmp_path / "file2.yaml", "w+", encoding="utf-8") as file_obj2, \
         open(tmp_path / "file3.yaml", "w+", encoding="utf-8") as file_obj3:
        file_obj1.write(yaml_str1)
        file_obj2.write(yaml_str2)
        file_obj3.write(yaml_str3)

    yaml_dict = YAML.load(tmp_path / "file1.yaml")
    assert yaml_dict == {
        "cm": {
            "sut1": {
                "type": "baremetal",
                "misc": False,
                "cpus": 2,
            },
            "sut2": {
                "type": "qemu",
                "cpus": 4,
            }
        },
    }
