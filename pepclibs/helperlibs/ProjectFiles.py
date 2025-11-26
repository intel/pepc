# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Provide API for fining project files."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import sys
import typing
import contextlib
from pathlib import Path
from pepclibs.helperlibs import ProcessManager, Logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

if typing.TYPE_CHECKING:
    from typing import Generator, Sequence
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# TODO: remove the 'importlib_resources' import and use 'importlib.resources' instead when
#       switching to Python 3.10+. This hack is needed only to support Python 3.9.
if sys.version_info < (3, 10):
    import importlib_resources
    _importlib_resources_files = importlib_resources.files
else:
    import importlib.resources
    _importlib_resources_files = importlib.resources.files

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def get_project_data_envar(prjname: str) -> str:
    """
    Return the default environment variable name for the data directory of the given project.

    Args:
        prjname: Project name.

    Returns:
        Environment variable name for the project data directory.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_DATA_PATH"

def get_project_helpers_envar(prjname: str) -> str:
    """
    Return the default environment variable name for the helper programs directory of the given
    project.

    Args:
        prjname: Project name.

    Returns:
        Environment variable name for the project helper programs directory.
    """

    name = prjname.replace("-", "_").upper()
    return f"{name}_HELPERSPATH"

def get_python_data_package_path(prjname: str) -> Path | None:
    """
    Return the path to the package directory of the given project. The path is in the standard
    python "site-packages" directory of the running program.

    Args:
        prjname: Project name.

    Returns:
        Path to the package directory.
    """

    pkgname = prjname.replace("-", "") + "data"
    pkgpath: Path | None = None
    try:
        with contextlib.suppress(ModuleNotFoundError):
            # I could not find a simpler way of turning the 'MultiplexedPath' object returned by
            # 'improtlib.resources.files()' into a 'Path' object. Just using 'str()' does not work.
            # However, with 'joinpath()' it is possible to get a string, and then we can convert it
            # to a 'Path' object.
            multiplexed_path = _importlib_resources_files(pkgname)
            pkgpath = Path(str(multiplexed_path.joinpath(f"../{pkgname}")))
        if pkgpath:
            return pkgpath.resolve()
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"Failed to find the python package directory for '{pkgname}':{msg}") from err

    return None

def search_project_data(subpath: str,
                        tpath: str | Path,
                        pman: ProcessManagerType | None = None,
                        what: str | None = None,
                        envars: Sequence[str] | None = None) -> Generator[Path, None, None]:
    """
    Search for project data in a predefined set of locations and yield found paths. The data to
    search are defined by the 'tpath' argument, which is the sub-path to append to the
    predefined search locations.

    The search order is as follows:
        1. Local host only: the directory of the running program (e.g., if the program is
           '/bar/baz/foo', check '/bar/baz/<tpath>', if it exists, yield the path).
        2. Directories specified by environment variables in 'envars' (e.g., if an environment
           variable from 'envars' is set to '/foo/bar/', check '/foo/bar/<tpath>', and if it
           exists, yield the path).
        3. Local host only: the standard python "site-packages" directory of the running program.
           Search for python package '<subpath>data'. For example, if the program site-packages
           directory is '/base_dir/lib/python3.12/site-packages', and 'subpath' is 'xyz', check
           '/base_dir/lib/python3.12/<subpath>xyz', and if it exists, yield the path.
        4. '$VIRTUAL_ENV/share/<subpath>/<tpath>', if 'VIRTUAL_ENV' is set.
        5. '$HOME/.local/share/<subpath>/<tpath>', if 'HOME' is set.
        6. '$HOME/share/<subpath>/<tpath>', if 'HOME' is set.
        7. '/usr/local/share/<subpath>/<tpath>'.
        8. '/usr/share/<subpath>/<tpath>'.

    Args:
        subpath: Sub-path to append to the searched paths (used only for some of the predefined
                 locations).
        tpath: The sub-path (last part of the full path) to the project data to search for.
        pman: Process manager object for the host to search on (defaults to local host).
        what: Human-readable description of what is being searched for, used in error messages.
        envars: Collection of environment variable names that may define custom search paths.

    Yields:
        Path objects pointing to found project data paths matching the search criteria.

    Raises:
        ErrorNotFound: If project data cannot be found in any of the searched locations.
    """

    searched = []
    yield_count = 0
    candidates = []

    with ProcessManager.pman_or_local(pman) as wpman:
        # Check the directory of the running program first.
        if not wpman.is_remote:
            candidate = Path(sys.argv[0]).parent.resolve().absolute() / tpath
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the program directory: {candidate}")
                yield_count += 1
                yield candidate

        if envars:
            # Check the directories specified by the environment variables.
            for envar in envars:
                path = wpman.get_envar(envar)
                if not path:
                    path = os.environ.get(envar)
                if not path:
                    continue

                candidate = Path(path) / tpath
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the '{envar}' environment variable: "
                               f"{candidate}")
                    yield_count += 1
                    yield candidate

        if not wpman.is_remote:
            # Check the standard python "site-packages" directory of the running program.
            pkgpath = get_python_data_package_path(subpath)
            if pkgpath:
                candidate = pkgpath / tpath
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the python package directory: {candidate}")
                    yield_count += 1
                    yield candidate

        venvdir = wpman.get_envar("VIRTUAL_ENV")
        if venvdir:
            # Check the virtual environment directory.
            candidate = Path(venvdir) / f"share/{subpath}/{tpath}"
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the virtual environment directory: {candidate}")
                yield_count += 1
                yield candidate

        homedir = wpman.get_envar("HOME")
        if homedir:
            # Check the home directory.
            candidate = Path(homedir) / f".local/share/{subpath}/{tpath}"
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the home directory: {candidate}")
                yield_count += 1
                yield candidate

            candidate = Path(homedir) / f"share/{subpath}/{tpath}"
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the home directory: {candidate}")
                yield_count += 1
                yield candidate

        # Check the system directories.
        candidate = Path(f"/usr/local/share/{subpath}/{tpath}")
        candidates.append(candidate)
        if wpman.exists(candidate):
            _LOG.debug(f"Found '{tpath}' in the system directory: {candidate}")
            yield_count += 1
            yield candidate

        # Check the system directories.
        candidate = Path(f"/usr/share/{subpath}/{tpath}")
        candidates.append(candidate)
        if wpman.exists(candidate):
            _LOG.debug(f"Found '{tpath}' in the system directory: {candidate}")
            yield_count += 1
            yield candidate

        if yield_count > 0:
            return

        if not what:
            what = f"'{subpath}/{tpath}'"
        searched = [str(path) for path in candidates]
        dirs = " * " + "\n * ".join(searched)

        if envars:
            envar_msg = f"\nIt is possible to specify a custom location for {what} using "
            if len(envars) == 1:
                envar_msg += f"the '{envars[0]}' environment variable"
            else:
                envars = ", ".join(envars)
                envar_msg += f"the one of the following environment variables: {envars}"
        else:
            envar_msg = ""

        raise ErrorNotFound(f"Cannot find {what}{wpman.hostmsg}, searched in the following "
                            f"locations:\n{dirs}.{envar_msg}")

def find_project_data(prjname: str,
                      tpath: str | Path,
                      pman: ProcessManagerType | None = None,
                      what: str | None = None) -> Path:
    """
    Search for project data in a predefined set of locations and return the first found path. The
    data to search are defined by the 'tpath' argument, which is the sub-path to append to the
    predefined search locations.

    The search order is as follows:
        1. Local host only: the directory of the running program (e.g., if the program is
           '/bar/baz/foo', check '/bar/baz/<tpath>', if it exists, return the path).
        2. The directory specified by the '<prjname>_DATA_PATH' environment variable. (e.g., if the
           environment variable from is set to '/foo/bar/', check '/foo/bar/<tpath>', and if it
           exists, return the path).
        3. Local host only: the standard python "site-packages" directory of the running program,
           search for python package '<prjname>data'. For example, if the program site-packages
           directory is '/base_dir/lib/python3.12/site-packages', and project name is 'foo', check
           '/base_dir/lib/python3.12/foodata', and if it exists, yield the path.
        3. '$VIRTUAL_ENV/share/<subpath>/<tpath>', if 'VIRTUAL_ENV' is set.
        4. '$HOME/.local/share/<prjname>/'.
        5. '$HOME/share/<prjname>/'.
        6. '/usr/local/share/<prjname>/'.
        7. '/usr/share/<prjname>/'.

    Args:
        prjname: Name of the project whose data directory is being searched.
        tpath: The sub-path (last part of the full path) to the project data to search for.
        pman: Process manager object for the host to search on (defaults to local host).
        what: Human-readable description of what is being searched for, used in error messages.

    Returns:
        The found project data path.

    Raises:
        ErrorNotFound: If project data cannot be found in any of the searched locations.
    """

    return next(search_project_data(prjname, tpath, pman=pman, what=what,
                                    envars=(get_project_data_envar(prjname),)))

def get_project_data_search_descr(prjname: str, tpath: str | Path) -> str:
    """
    Generate a human-readable description of the search locations for project data.

    Args:
        prjname: The name of the project whose data is being searched for.
        tpath: The sub-path (last part of the full path) to the project data that is being searched
               for.

    Returns:
        A string describing all possible data search locations (a comma-separated list of paths).
    """

    envar = get_project_data_envar(prjname)

    paths = [f"{Path(sys.argv[0]).parent}/{tpath} (local host only)",
             f"${envar}/{tpath}"]

    pkgpath = get_python_data_package_path(prjname)
    if pkgpath:
        paths.append(f"{pkgpath}/{tpath} (local host only)")

    paths += [f"$VIRTUAL_ENV/share/{prjname}/{tpath}",
              f"$HOME/.local/share/{prjname}/{tpath}",
              f"/usr/local/share/{prjname}/{tpath}",
              f"/usr/share/{prjname}/{tpath}"]

    return ", ".join(paths)

def find_project_helper(prjname: str, helper: str, pman: ProcessManagerType | None = None) -> Path:
    """
    Search for a helper program 'helper' belonging to a specified project in a predefined set of
    locations and return the first found path.

    The search order is as follows:
        1. Local host only: the directory of the running program (e.g., if the program is
           '/bar/baz/foo', check '/bar/baz/<helper>', if it exists and executable, return the path).
        2. The directory specified by the '<prjname>_DATA_PATH' environment variable. (e.g., if the
           environment variable from is set to '/foo/bar/', check '/foo/bar/<helper>', and if it
           exists and is executable, return the path).
        3. '$VIRTUAL_ENV/bin/', if the environment variable is set.
        4. Directories listed in the 'PATH' environment variable.
        4. '$HOME/.local/bin/'.
        5. '$HOME/bin/'.
        7. '/usr/local/bin/'.
        8. '/usr/bin'.

    Args:
        prjname: Name of the project the helper program belongs to.
        helper: Name of the helper program to find.
        pman: Process manager object for the host to search on (defaults to local host).

    Returns:
        Path to the found helper program executable.

    Raises:
        ErrorNotFound: If the helper program cannot be found in any of the searched locations.
    """

    candidates = []
    with ProcessManager.pman_or_local(pman) as wpman:
        if not wpman.is_remote:
            candidate = Path(sys.argv[0]).parent / helper
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

        # Check the directory specified by the environment variable.
        envar = get_project_helpers_envar(prjname)
        path = wpman.get_envar(envar)
        if not path:
            path = os.environ.get(envar)
        if path:
            candidate = Path(path) / helper
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

        venvdir = wpman.get_envar("VIRTUAL_ENV")
        if venvdir:
            # Check the virtual environment directory.
            candidate = Path(venvdir) / f"bin/{helper}"
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

        path = wpman.which(helper, must_find=False)
        if path:
            # Check the directories listed in the 'PATH' environment variable.
            candidate = Path(path)
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

        homedir = wpman.get_envar("HOME")
        if homedir:
            # Check the home directory.
            candidate = Path(homedir) / f".local/bin/{helper}"
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

            candidate = Path(homedir) / f"bin/{helper}"
            candidates.append(candidate)
            if wpman.is_exe(candidate):
                return candidate

        # Check the system directories.
        candidate = Path(f"/usr/local/bin/{helper}")
        candidates.append(candidate)
        if wpman.is_exe(candidate):
            return candidate

        candidate = Path(f"/usr/bin/{helper}")
        candidates.append(candidate)
        if wpman.is_exe(candidate):
            return candidate

        searched = " * " + "\n * ".join([str(path) for path in candidates])
        raise ErrorNotFound(f"Cannot find the '{helper}' program{wpman.hostmsg}, searched in the "
                            f"following locations:\n{searched}")

def get_project_helpers_search_descr(prjname: str) -> str:
    """
    Return a human-readable description of the search locations for project helpers.

    Args:
        prjname: The project name, whose helper is being searched for.

    Returns:
        A comma-separated string describing the search locations for project helpers.
    """

    envar = get_project_helpers_envar(prjname)
    paths = (f"{Path(sys.argv[0]).parent}",
             f"${envar}",
             "$VIRTUAL_ENV/bin",
             "All paths in $PATH",
             "$HOME/.local/bin",
             "$HOME/bin",
             "/usr/local/bin",
             "/usr/bin")

    return ", ".join(paths)
