# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""This module is a collection of miscellaneous functions that interact with project paths."""

import os
import sys
from pathlib import Path
from pepclibs.helperlibs import ProcessManager
from pepclibs.helperlibs.Exceptions import ErrorNotFound

def get_project_data_envar(prjname):
    """
    Return the name of the environment variable that points to the data location of project
    'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_DATA_PATH"

def get_project_helpers_envar(prjname):
    """
    Return the name of the environment variable that points to the helper programs location of
    project 'prjname'.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_HELPERSPATH"

def search_project_data(subpath, datadir, pman=None, what=None, envars=None):
    """
    Search for project data directory (or sub-path) 'datadir' and yield the the results. The
    arguments are as follows.
      * subpath - a sub-path which will be appended to the searched paths (not all for them, though,
                  see the search list description).
      * datadir - name of the sub-directory containing the project data. This method basically
                  searches for 'datadir' in a set of pre-defined paths (see below).
      * pman - the process manager object for the host to find the data on (local host by
               default).
      * what - human-readable description of what is searched for, will be used in the error message
               if an error occurs.
      * envars - a collection of environment variable names defining the paths to search the
                  project data in.

    Check for 'datadir' in all of the following paths (and in the following order), and if it
    exists, yield the path to it.
      * in the directory the of the running program.
      * in the directories specified by environment variables in 'envars'.
      * in '$HOME/.local/share/<subpath>/', if it exists.
      * in '$HOME/share/<subpath>/', if it exists.
      * in '$VIRTUAL_ENV/share/<subpath>/', if the environment variable is defined and the directory
            exists.
      * in '/usr/local/share/<subpath>/', if it exists.
      * in '/usr/share/<subpath>/', if it exists.
    """

    searched = []
    paths = []
    num_found = 0

    paths.append(Path(sys.argv[0]).parent.resolve().absolute())

    with ProcessManager.pman_or_local(pman) as wpman:
        if envars:
            for envar in envars:
                path = wpman.get_envar(envar)
                if not path:
                    path = os.environ.get(envar)
                if path:
                    paths.append(Path(path))

        homedir = wpman.get_envar("HOME")
        if homedir:
            paths.append(homedir / Path(f".local/share/{subpath}"))
            paths.append(homedir / Path(f"share/{subpath}"))
        venvdir = wpman.get_envar("VIRTUAL_ENV")
        if venvdir:
            paths.append(Path(venvdir) / Path(f"share/{subpath}"))
        paths.append(Path(f"/usr/local/share/{subpath}"))
        paths.append(Path(f"/usr/share/{subpath}"))

        for path in paths:
            path /= datadir
            if wpman.exists(path):
                num_found += 1
                yield path
            searched.append(path)

        if not what:
            what = f"'{subpath}/{datadir}'"
        searched = [str(s) for s in searched]
        dirs = " * " + "\n * ".join(searched)

        if num_found > 0:
            return

        if envars:
            envar_msg = f"\nYou can specify custom location for {what} using "
            if len(envars) == 1:
                envar_msg += f"the '{envars[0]}' environment variable"
            else:
                envars = ", ".join(envars)
                envar_msg += f"the one of the following environment variables: {envars}"
        else:
            envar_msg = ""

        raise ErrorNotFound(f"cannot find {what}{wpman.hostmsg}, searched in the following "
                            f"locations:\n{dirs}.{envar_msg}")

def find_project_data(prjname, datadir, pman=None, what=None):
    """
    Find and return path to the 'datadir' data directory of project 'prjname'. The arguments are as
    follows.
      * prjname - name of the project the data belongs to.
      * datadir - name of the sub-directory containing the project data. This method basically
                  searches for 'datadir' in a set of pre-defined paths (see below).
      * pman - the process manager object for the host to find the data on (local host by
               default).
      * what - human-readable description of what is searched for, will be used in the error message
               if an error occurs.

    Check for 'datadir' in all of the following paths (and in the following order), and if it
    exists, stop searching and return the path.
      * in the directory the of the running program.
      * in the directory specified by the '<prjname>_DATA_PATH' environment variable.
      * in '$HOME/.local/share/<prjname>/', if it exists.
      * in '$HOME/share/<prjname>/', if it exists.
      * in '/usr/local/share/<prjname>/', if it exists.
      * in '/usr/share/<prjname>/', if it exists.
    """

    return next(search_project_data(prjname, datadir, pman, what,
                                    envars=(get_project_data_envar(prjname),)))

def get_project_data_search_descr(prjname, datadir):
    """
    Return a human-readable string describing the locations the 'find_project_data()' function looks
    for the data at. The arguments are as follows.
      * prjname - name of the project the data belongs to.
      * datadir - name of the sub-directory containing the project data.
    """

    envar = get_project_data_envar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}/{datadir}",
             f"${envar}/{datadir}",
             f"$HOME/.local/share/{prjname}/{datadir}",
             f"/usr/local/share/{prjname}/{datadir}",
             f"/usr/share/{prjname}/{datadir}")

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
      * in the directory of the running program (only when searching on the local host).
      * in the directory specified by the '<prjname>_HELPERSPATH' environment variable.
      * in the paths defined by the 'PATH' environment variable.
      * in '$HOME/.local/bin/', if it exists.
      * in '$HOME/bin/', if it exists.
      * in '$VIRTUAL_ENV/bin/', if the environment variable is defined and the directory exists.
      * in '/usr/local/bin/', if it exists.
      * in '/usr/bin', if it exists.
    """

    paths = []
    with ProcessManager.pman_or_local(pman) as wpman:
        if not wpman.is_remote:
            paths.append(Path(sys.argv[0]).parent)

        path = None
        envar = get_project_helpers_envar(prjname)
        # First check to see if the environment variable is specified on 'wpman' before also
        # checking localhost.
        path = wpman.get_envar(envar)
        if path:
            paths.append(Path(path))
        else:
            path = os.environ.get(envar)

        # Check if the helper is on the PATH.
        path = wpman.which(helper, must_find=False)
        if path:
            paths.append(Path(path))
        searched = ["$PATH"]

        homedir = wpman.get_envar("HOME")
        if homedir:
            paths.append(homedir / Path(".local/bin"))
            paths.append(homedir / Path("bin"))
        venvdir = wpman.get_envar("VIRTUAL_ENV")
        if venvdir:
            paths.append(Path(venvdir) / Path("bin"))
        paths.append(Path("/usr/local/bin"))
        paths.append(Path("/usr/bin"))

        for path in paths:
            if wpman.is_dir(path):
                exe_path = path / helper
            else:
                exe_path = path
            if wpman.is_exe(exe_path):
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

    envar = get_project_helpers_envar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}",
             f"${envar}",
             "All paths in $PATH",
             "$HOME/.local/bin",
             "$HOME/bin",
             "$VIRTUAL_ENV/bin",
             "/usr/local/bin",
             "/usr/bin")

    return ", ".join(paths)
