# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module is a collection of miscellaneous high level functions that are helpful for tools that
use 'statscollectlib' modules.
"""

import os
import sys
from pathlib import Path
from pepclibs.helperlibs.Exceptions import ErrorNotFound

def find_project_data(prjname, subpath, descr=None):
    """
    Search for project 'prgname' data. The data are searched for in the 'subpath' sub-path of
    the following directories (and in the following order).
      * in the directory the of the running process (sys.argv[0]/<subpath>).
      * in the directory specified by the '<prjname>_DATA_PATH' environment variable.
      * $HOME/.local/share/<prjname>/, if it exists.
      * /usr/local/share/<prjname>/, if it exists.
      * /usr/share/<prjname>/, if it exists.

    The 'descr' argument is a human-readable description of 'subpath', which will be used in the
    error message if error is raised.
    """

    searched = []
    paths = []

    paths.append(Path(sys.argv[0]).parent)

    path = os.environ.get("WULT_DATA_PATH".upper())
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

    raise ErrorNotFound(f"cannot find {descr}, searched in the following directories on local "
                        f"host:\n{dirs}")
