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

def search_project_data(subpath, datadir, pman=None, what=None, envvars=None):
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
      * envvars - a collection of environment variable names defining the paths to search the
                  project data in.

    Check for 'datadir' in all of the following paths (and in the following order), and if it
    exists, yield the path to it.
      * in the directory the of the running program.
      * in the directories specified by environment variables in 'envvars'.
      * in '$HOME/.local/share/<subpath>/', if it exists.
      * in '$HOME/share/<subpath>/', if it exists.
      * in '/usr/local/share/<subpath>/', if it exists.
      * in '/usr/share/<subpath>/', if it exists.
    """

    searched = []
    paths = []
    num_found = 0

    paths.append(Path(sys.argv[0]).parent.resolve().absolute())

    if envvars:
        for envvar in envvars:
            path = os.environ.get(envvar)
            if path:
                paths.append(Path(path))

    with ProcessManager.pman_or_local(pman) as wpman:
        homedir = wpman.get_homedir()
        paths.append(homedir / Path(f".local/share/{subpath}"))
        paths.append(homedir / Path(f"share/{subpath}"))
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

        if envvars:
            envvar_msg = f"\nYou can specify custom location for {what} using "
            if len(envvars) == 1:
                envvar_msg += f"the '{envvars[0]}' environment variable"
            else:
                envvars = ", ".join(envvars)
                envvar_msg += f"the one of the following environment variables: {envvars}"
        else:
            envvar_msg = ""

        raise ErrorNotFound(f"cannot find {what}{wpman.hostmsg}, searched in the following "
                            f"locations:\n{dirs}.{envvar_msg}")

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
                                    envvars=(get_project_data_envvar(prjname),)))

def get_project_data_search_descr(prjname, datadir):
    """
    Return a human-readable string describing the locations the 'find_project_data()' function looks
    for the data at. The arguments are as follows.
      * prjname - name of the project the data belongs to.
      * datadir - name of the sub-directory containing the project data.
    """

    envvar = get_project_data_envvar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}/{datadir}",
             f"${envvar}/{datadir}",
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
      * in '/usr/local/bin/', if it exists.
      * in '/usr/bin', if it exists.
    """

    paths = []
    with ProcessManager.pman_or_local(pman) as wpman:
        if not wpman.is_remote:
            paths.append(Path(sys.argv[0]).parent)

        path = None
        envvar = get_project_helpers_envvar(prjname)
        # First check to see if the environment variable is specified on 'wpman' before also
        # checking localhost.
        if wpman.is_remote:
            stdout, _ = wpman.run_verify(f"echo ${envvar}")
            path = stdout.strip()
        if not path:
            path = os.environ.get(envvar)

        if path:
            paths.append(Path(path))

        # Check if the helper is on the PATH.
        path = wpman.which(helper, must_find=False)
        if path:
            paths.append(Path(path))
        searched = ["$PATH"]

        homedir = wpman.get_homedir()
        paths.append(homedir / Path(".local/bin"))
        paths.append(homedir / Path("bin"))
        paths.append(Path("/usr/local/bin"))
        paths.append(Path("/usr/bin"))

        for path in paths:
            if path.is_dir():
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

    envvar = get_project_helpers_envvar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}",
             f"${envvar}",
             "All paths in $PATH",
             "$HOME/.local/bin",
             "$HOME/bin",
             "/usr/local/bin",
             "/usr/bin")

    return ", ".join(paths)
