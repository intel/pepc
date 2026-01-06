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

def _get_project_data_package_name(prjname: str) -> str:
    """
    Return the standard python package name for the data package of the given project.

    Args:
        prjname: Python project name.

    Returns:
        Standard python package name for the project data package.
    """

    return prjname.replace("-", "") + "data"

def _get_python_data_package_path(pkgname: str) -> Path | None:
    """
    Return the full path to a python package. The path is in the standard python "site-packages"
    directory of the running program.

    Args:
        pkgname: Python package name.

    Returns:
        Path to the package directory.
    """

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

def search_project_data(tpath: str | Path,
                        prjname: str = "",
                        pkgname: str = "",
                        pman: ProcessManagerType | None = None,
                        what: str | None = None,
                        envars: Sequence[str] | None = None) -> Generator[Path, None, None]:
    """
    Search for project data in a predefined set of locations and yield found paths. The data to
    search are defined by the 'tpath' argument, which is the sub-path to append to the
    predefined search locations.

    The search order is as follows:
        1. Local host only: the directory of the running program. For example, if the program is
           '/bar/baz/foo':
           - Check '/bar/baz/<tpath>', if it exists, yield the path.
           - Check '/bar/baz/<pkgname>/<tpath>', if it exists, yield the path.
        2. Directories specified by environment variables in 'envars'. For example, if an
           environment variable from 'envars' is set to '/foo/bar/':
           - Check '/foo/bar/<tpath>', if it exists, yield the path.
           - Check '/foo/bar/<pkgname>/<tpath>', if it exists, yield the path.
        3. Local host only: the standard python "site-packages" directory of the running program.
           For example, if the python "site-packages" directory is
           '/base_dir/lib/python3.12/site-packages', and, check
           '/base_dir/lib/python3.12/site-packages/<pkgname>', if it exists, yield the path.
        4. '$VIRTUAL_ENV/share/<prjname>/<tpath>', if 'VIRTUAL_ENV' is set.
        5. '$HOME/.local/share/<prjname>/<tpath>', if 'HOME' is set.
        6. '$HOME/share/<prjname>/<tpath>', if 'HOME' is set.
        7. '/usr/local/share/<prjname>/<tpath>'.
        8. '/usr/share/<prjname>/<tpath>'.
    Args:
        tpath: The sub-path (last part of the full path) to the project data to search for.
        prjname: Name of the project whose data directory is being searched. If not given, paths
                 including "<prjname>" will not be searched.
        pkgname: The python package name for the project data. If not given, generated from
                 'prjname'.
        pman: Process manager object for the host to search on (defaults to local host).
        what: Human-readable description of what is being searched for, used in error messages.
        envars: Collection of environment variable names that may define custom search paths.

    Yields:
        Path objects pointing to found project data paths matching the search criteria.

    Raises:
        ErrorNotFound: If project data cannot be found in any of the searched locations.
    """

    if not prjname and not pkgname:
        raise Error("BUG: Either 'prjname' or 'pkgname' argument must be given")

    if not pkgname:
        pkgname = _get_project_data_package_name(prjname)

    candidates: list[Path] = []
    yield_count = 0

    check_candidates: list[Path]

    with ProcessManager.pman_or_local(pman) as wpman:
        # Check the directory of the running program first.
        if not wpman.is_remote:
            check_candidates = [Path(sys.argv[0]).parent.resolve().absolute() / tpath]
            if pkgname:
                path_with_pkgname = Path(sys.argv[0]).parent.resolve().absolute() / pkgname / tpath
                check_candidates.append(path_with_pkgname)

            for candidate in check_candidates:
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the program directory: {candidate}")
                    yield_count += 1
                    yield candidate

        if envars:
            # Check the directories specified by the environment variables.
            for envar in envars:
                envvar_path = wpman.get_envar(envar)
                if not envvar_path:
                    envvar_path = os.environ.get(envar)
                if not envvar_path:
                    continue

                check_candidates = [Path(envvar_path) / tpath]
                if pkgname:
                    check_candidates.append(Path(envvar_path) / pkgname / tpath)
                for candidate in check_candidates:
                    candidates.append(candidate)
                    if wpman.exists(candidate):
                        _LOG.debug(f"Found '{tpath}' in the '{envar}' environment variable: "
                                   f"{candidate}")
                        yield_count += 1
                        yield candidate

        if pkgname:
            if not wpman.is_remote:
                # Check the standard python "site-packages" directory of the running program.
                pkgpath = _get_python_data_package_path(pkgname)
                if pkgpath:
                    candidate = pkgpath / tpath
                    candidates.append(candidate)
                    if wpman.exists(candidate):
                        _LOG.debug(f"Found '{tpath}' in the python package directory: {candidate}")
                        yield_count += 1
                        yield candidate

        if prjname:
            venvdir = wpman.get_envar("VIRTUAL_ENV")
            if venvdir:
                # Check the virtual environment directory.
                candidate = Path(venvdir) / f"share/{prjname}/{tpath}"
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the virtual environment directory: {candidate}")
                    yield_count += 1
                    yield candidate

            homedir = wpman.get_envar("HOME")
            if homedir:
                # Check the home directory.
                candidate = Path(homedir) / f".local/share/{prjname}/{tpath}"
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the home directory: {candidate}")
                    yield_count += 1
                    yield candidate

                candidate = Path(homedir) / f"share/{prjname}/{tpath}"
                candidates.append(candidate)
                if wpman.exists(candidate):
                    _LOG.debug(f"Found '{tpath}' in the home directory: {candidate}")
                    yield_count += 1
                    yield candidate

            # Check the system directories.
            candidate = Path(f"/usr/local/share/{prjname}/{tpath}")
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the system directory: {candidate}")
                yield_count += 1
                yield candidate

            # Check the system directories.
            candidate = Path(f"/usr/share/{prjname}/{tpath}")
            candidates.append(candidate)
            if wpman.exists(candidate):
                _LOG.debug(f"Found '{tpath}' in the system directory: {candidate}")
                yield_count += 1
                yield candidate

        if yield_count > 0:
            return

        if not what:
            if prjname:
                what = f"'{prjname}' project data '{tpath}'"
            else:
                what = f"'{pkgname}/{tpath}'"

        searched = [str(path) for path in candidates]
        dirs = " * " + "\n * ".join(searched)

        raise ErrorNotFound(f"Cannot find {what}{wpman.hostmsg}, searched in the following "
                            f"locations:\n{dirs}")

def find_project_data(prjname: str,
                      tpath: str | Path,
                      pman: ProcessManagerType | None = None,
                      what: str | None = None) -> Path:
    """
    Similar to 'search_project_data()', but return only the first found path.

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

    envar = get_project_data_envar(prjname)

    try:
        return next(search_project_data(tpath, prjname=prjname, pman=pman, what=what,
                                        envars=(envar,)))
    except ErrorNotFound as err:
        if not what:
            what = f"'{prjname}' project data '{tpath}'"
        envar_msg = f"\nIt is possible to specify a custom location for {what} using the " \
                    f"'{envar}' environment variable"
        raise type(err)(str(err) + envar_msg) from err

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
    pkgname = _get_project_data_package_name(prjname)
    pkgpath = _get_python_data_package_path(pkgname)

    proc_path = Path(sys.argv[0]).parent.resolve().absolute()
    paths = [f"{proc_path}/{tpath} (local host only)",
             f"{proc_path}/{pkgname}/{tpath} (local host only)",
             f"${envar}/{tpath}",
             f"${envar}/{pkgname}/{tpath}"]

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
