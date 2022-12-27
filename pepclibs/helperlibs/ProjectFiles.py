# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This module is a collection of miscellaneous functions that interact with project paths."""

import os
import sys
from pathlib import Path
from pepclibs.helperlibs.Exceptions import ErrorNotFound

def find_project_data(prjname, subpath, descr=None):
    """
    Search for project 'prjname' data. The data are searched for in the 'subpath' sub-path of
    the following directories (and in the following order).
      * in the directory the of the running process.
      * in the directory specified by the '<prjname>_DATA_PATH' environment variable.
      * in '$HOME/.local/share/<prjname>/', if it exists.
      * in '/usr/local/share/<prjname>/', if it exists.
      * in '/usr/share/<prjname>/', if it exists.

    The 'descr' argument is a human-readable description of 'subpath', which will be used in the
    error message if error is raised.
    """

    searched = []
    paths = []

    paths.append(Path(sys.argv[0]).parent)

    name = prjname.replace("-", "_").upper()
    path = os.environ.get(f"{name}_DATA_PATH")
    if path:
        paths.append(Path(path))

    for path in paths:
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    path = Path.home() / Path(f".local/share/{prjname}/{subpath}")
    if path.exists():
        return path

    searched.append(path)

    for path in (Path(f"/usr/local/share/{prjname}"), Path(f"/usr/share/{prjname}")):
        path /= subpath
        if path.exists():
            return path
        searched.append(path)

    if not descr:
        descr = f"'{subpath}'"
    searched = [str(s) for s in searched]
    dirs = " * " + "\n * ".join(searched)

    raise ErrorNotFound(f"cannot find {descr}, searched in the following locations:\n{dirs}")

def find_project_executable(prjname, executable):
    """
    Search for an executable file 'executable' belonging to the 'prjname' project. The executable is
    searched for in the following locations (and in the following order).
      * in the paths defined by the 'PATH' environment variable.
      * in the directory the of the running process.
      * in the directory specified by the '<prjname>_HELPERSPATH' environment variable.
      * in '$HOME/.local/bin/', if it exists.
      * in '/usr/local/bin/', if it exists.
      * in '/usr/bin', if it exists.
    """

    from pepclibs.helperlibs import LocalProcessManager # pylint: disable=import-outside-toplevel

    with LocalProcessManager.LocalProcessManager() as lpman:
        exe_path = lpman.which(executable, must_find=False)
        if exe_path:
            return exe_path

    searched = ["$PATH"]
    paths = [Path(sys.argv[0]).parent]

    name = prjname.replace("-", "_").upper()
    path = os.environ.get(f"{name}_HELPERSPATH")
    if path:
        paths.append(Path(path))

    paths.append(Path.home() / Path(".local/bin"))
    paths.append(Path("/usr/local/bin"))
    paths.append(Path("/usr/bin"))

    for path in paths:
        exe_path = path / executable
        if exe_path.exists():
            return exe_path
        searched.append(str(path))

    dirs = " * " + "\n * ".join(searched)
    raise ErrorNotFound(f"cannot find the '{executable}' program, searched in the "
                        f"following locations:\n{dirs}")
