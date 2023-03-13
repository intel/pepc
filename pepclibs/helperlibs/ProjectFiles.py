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
from pepclibs.helperlibs import ProcessManager
from pepclibs.helperlibs.Exceptions import ErrorNotFound

def get_project_data_envvar(prjname):
    """
    Return the name of the environment variable that points to the data location of project
    'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_DATA_PATH"

def get_project_helpers_envvar(prjname):
    """
    Return the name of the environment variable that points to the helper programs location of
    project 'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_HELPERSPATH"

def find_project_data(prjname, subpath, pman=None, what=None):
    """
    Search for project 'prjname' data. The arguments are as follows.
      * prjname - name of the project the data belongs to.
      * subpath - the sub-path of the data in the data project installation base directory.
      * pman - the process manager object for the host to find the data on (local host by
               default).
      * what - human-readable description of 'subpath' (or what is searched for), which will be used
               in the error message if an error occurs.

    The data are searched for in the 'subpath' sub-path of the following directories (and in the
    following order).
      * in the directory the of the running program.
      * in the directory specified by the '<prjname>_DATA_PATH' environment variable.
      * in '$HOME/.local/share/<prjname>/', if it exists.
      * in '$HOME/share/<prjname>/', if it exists.
      * in '/usr/local/share/<prjname>/', if it exists.
      * in '/usr/share/<prjname>/', if it exists.
    """

    searched = []
    paths = []

    paths.append(Path(sys.argv[0]).parent)

    path = os.environ.get(get_project_data_envvar(prjname))
    if path:
        paths.append(Path(path))

    with ProcessManager.pman_or_local(pman) as wpman:
        homedir = wpman.get_homedir()
        paths.append(homedir / Path(f".local/share/{prjname}"))
        paths.append(Path(f"/usr/local/share/{prjname}"))
        paths.append(Path(f"/usr/share/{prjname}"))

        for path in paths:
            path /= subpath
            if wpman.exists(path):
                return path
            searched.append(path)

        if not what:
            what = f"'{subpath}'"
        searched = [str(s) for s in searched]
        dirs = " * " + "\n * ".join(searched)

        raise ErrorNotFound(f"cannot find {what}{wpman.hostmsg}, searched in the following "
                            f"locations:\n{dirs}")

def get_project_data_search_descr(prjname, subpath):
    """
    This method returns a human-readable string describing the locations the 'find_project_data()'
    function looks for the data at. The arguments are the same as in 'find_project_data()'.
    """

    envvar = get_project_data_envvar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}/{subpath}",
             f"${envvar}/{subpath}",
             f"$HOME/.local/share/{prjname}/{subpath}",
             f"/usr/local/share/{prjname}/{subpath}",
             f"/usr/share/{prjname}/{subpath}")

    return ", ".join(paths)

def find_project_helper(prjname, helper, pman=None):
    """
    Search for a helper program 'helper' belonging to the 'prjname' project. The arguments are as
    follows:
      * prjname - name of the project the helper program belongs to.
      * helper - the helper program to find.
      * pman - the process manager object for the host to find the helper on (local host by
               default).

    The helper program is searched for in the following locations (and in the following order).
    The data are searched for in the 'subpath' sub-path of the following directories (and in the
    following order).
      * in the paths defined by the 'PATH' environment variable.
      * in the directory of the running program.
      * in the directory specified by the '<prjname>_HELPERSPATH' environment variable.
      * in '$HOME/.local/bin/', if it exists.
      * in '$HOME/bin/', if it exists.
      * in '/usr/local/bin/', if it exists.
      * in '/usr/bin', if it exists.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        exe_path = wpman.which(helper, must_find=False)
        if exe_path:
            return exe_path

        searched = ["$PATH"]
        paths = [Path(sys.argv[0]).parent]

        path = os.environ.get(get_project_helpers_envvar(prjname))
        if path:
            paths.append(Path(path))

        homedir = wpman.get_homedir()
        paths.append(homedir / Path(".local/bin"))
        paths.append(homedir / Path("bin"))
        paths.append(Path("/usr/local/bin"))
        paths.append(Path("/usr/bin"))

        for path in paths:
            exe_path = path / helper
            if pman.is_exe(exe_path):
                return exe_path
            searched.append(str(path))

        dirs = " * " + "\n * ".join(searched)
        raise ErrorNotFound(f"cannot find the '{helper}' program{wpman.hostmsg}, searched in the "
                            f"following locations:\n{dirs}")

def get_project_helpers_search_descr(prjname):
    """
    This method returns a human-readable string describing the locations the 'find_project_helper()'
    function looks for the helper at. The argument is the same as in 'find_project_helper()'.
    """

    envvar = get_project_helpers_envvar(prjname)
    paths = ("All paths in $PATH"
             f"{Path(sys.argv[0]).parent}",
             f"${envvar}",
             "$HOME/.local/bin",
             "$HOME/bin",
             "/usr/local/bin",
             "/usr/bin")

    return ", ".join(paths)
