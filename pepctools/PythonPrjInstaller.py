# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Install a Python project on the local or remote host into a Python virtual environment. Supports
creating a standalone zipapp executable that bundles all required packages into a single file.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import stat
import typing
from urllib.parse import urlparse
from pathlib import Path

from pepclibs.helperlibs import LocalProcessManager, LoggerFile, ProcessManager, ToolChecker
from pepclibs.helperlibs import ClassHelpers, Logging
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    import zipfile
    from typing import Final, IO, Literal, Sequence
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    SudoAliasStyle = Literal["refresh", "wrap"]

_LOG = Logging.getLogger(Logging.MAIN_LOGGER_NAME)

# Sentinel value: resolve '$HOME/.pmtools' at runtime on the target host.
DEFAULT_INSTALL_PATH: Final[Path] = Path("$HOME/.pmtools")

# Packages that are typically present in a Python virtual environment, but they are not needed for
# the project at runtime.
_NON_RUNTIME_PYTHON_PACKAGES: Final[frozenset[str]] = frozenset((
    "pip",
    "setuptools",
    "wheel",
    "build",
    "pkg_resources",
    "_distutils_hack"
))

class PythonPrjInstaller(ClassHelpers.SimpleCloseContext):
    """
    Install a Python project on a target host into a Python virtual environment.

    Public methods overview:
        - 'install_dependencies()' - install OS packages required by the project.
        - 'install()' - create the virtual environment and install the project.
        - 'add_sudo_aliases()' - append 'sudo' aliases for the project's tools to the RC file.
        - 'hookup_rc_file()' - source the project RC file from the user's shell RC file.
    """

    def __init__(self,
                 prjname: str,
                 src: str,
                 pman: ProcessManagerType | None = None,
                 install_path: Path = DEFAULT_INSTALL_PATH,
                 logging: bool = False):
        """
        Initialize the installer.

        Args:
            prjname: The name of the Python project to install (e.g. 'pepc').
            src: Installation source: a local directory path or a Git URL.
            pman: The process manager object that defines the target host. Use a local process
                  manager if not provided.
            install_path: Installation directory on the target host. Defaults to
                          'DEFAULT_INSTALL_PATH' ('$HOME/.pmtools' on the target host).
            logging: If 'True', log progress and the output of rsync and pip commands. Set to
                     'False' to suppress all informational output from this class. Defaults to
                     'False'.
        """

        self._prjname = prjname
        self._logging = logging
        self._src_path, self._src_url = self._classify_src(src)
        self._close_pman = pman is None

        self._pman: ProcessManagerType
        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        home_str = self._pman.get_envar("HOME")
        if not home_str:
            raise Error(f"Cannot determine the home directory, the 'HOME' environment variable "
                        f"is not set{self._pman.hostmsg}.\nUse the '--install-path' argument to "
                        f"specify the installation path.")
        self._home = Path(home_str)

        if install_path is DEFAULT_INSTALL_PATH:
            self.install_path = self._home / ".pmtools"
        else:
            self.install_path = install_path
        self.rcfile_path = self.install_path / f".{self._prjname}-rc.sh"

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_pman",)
        ClassHelpers.close(self, close_attrs=close_attrs)

    @staticmethod
    def _classify_src(src: str) -> tuple[Path | None, str]:
        """
        Classify the installation source as a filesystem path or a URL.

        No scheme or 'file://' scheme is treated as a filesystem path on the local host. Any other
        scheme is treated as a URL.

        Args:
            src: The installation source string: a filesystem path or a URL.

        Returns:
            A tuple '(src_path, src_url)'. If the source is a filesystem path, 'src_url' is an
            empty string, otherwise 'src_path' is 'None'.
        """

        try:
            parsed_src = urlparse(src)
        except ValueError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to parse '{src}':\n{errmsg}") from err

        scheme = parsed_src.scheme
        if scheme and scheme != "file":
            return None, src

        # No scheme or 'file://' scheme.
        if scheme == "file":
            src = parsed_src.path

        return Path(src), ""

    def install_dependencies(self, dependencies: Sequence[str]):
        """
        Install OS packages required for the project to be installed and to operate.

        Args:
            dependencies: Names of OS tools required by the project.
        """

        tools: list[str] = list(dependencies)
        if self._src_url:
            # If installing from a Git URL, we also need 'git' to be available.
            tools.append("git")

        if self._src_path:
            # 'rsync' is used to copy the sources to the target host before running pip.
            tools.append("rsync")

            if self._pman.is_remote:
                # For remote installs, 'rsync' is also needed on the local host.
                with LocalProcessManager.LocalProcessManager() as local_pman, \
                     ToolChecker.ToolChecker(local_pman) as local_tchk:
                    try:
                        local_tchk.ensure_tools_available(("rsync",))
                    except Error as err:
                        raise type(err)(f"{err}\nPlease, install 'rsync' on the local host.") \
                              from err

        if self._logging:
            _LOG.info("Checking required OS tools%s: %s", self._pman.hostmsg, ", ".join(tools))

        with ToolChecker.ToolChecker(self._pman) as tchk:
            tchk.ensure_tools_available(tuple(tools))

    def _run_installation(self, src_path: Path | None):
        """
        Run the pip installation step on the target host.

        Args:
            src_path: Path to the installation sources on the target host, or 'None' if installing
                      from a URL.
        """

        if self._logging:
            _LOG.info("Installing Python project '%s' to '%s'%s",
                      self._prjname, self.install_path, self._pman.hostmsg)

        src = self._src_url or src_path
        cmd = f"python3 -m venv '{self.install_path}' && " \
              f"'{self.install_path}/bin/python3' -m pip install --upgrade '{src}'"

        output_fobjs: tuple[IO | None, IO | None]
        if self._logging:
            pfx = "  [pip] "
            output_fobjs = (LoggerFile.LoggerFile(prefix=pfx), LoggerFile.LoggerFile(prefix=pfx))
        else:
            output_fobjs = (None, None)

        self._pman.run_verify(cmd, output_fobjs=output_fobjs)

    def _create_rc_file(self) -> Path:
        """
        Create a shell RC file for the project in the installation directory.

        The file is intended to be sourced from the user's shell RC file (e.g. '.bashrc'). It
        sets up the PATH, tab completions, and man pages.

        Returns:
            The path to the created RC file on the target host.
        """

        rcfile_path = self.rcfile_path

        if self._logging:
            _LOG.info("Creating a configuration file '%s'%s", rcfile_path, self._pman.hostmsg)

        contents = f""" \
# === {self._prjname} settings ===
VENV="{self.install_path}"
VENV_BIN="$VENV/bin"

# Ensure the virtual environment's bin directory is in the PATH.
export PATH="$PATH:$VENV_BIN"

# Enable tab completion for {self._prjname}.
eval "$($VENV_BIN/register-python-argcomplete {self._prjname})"

# Enable man pages.
export MANPATH="$MANPATH:$($VENV_BIN/{self._prjname} --print-man-path)"
# === end of {self._prjname} settings ===
"""

        with self._pman.open(rcfile_path, "w") as fobj:
            fobj.write(contents)

        return rcfile_path

    def add_sudo_aliases(self, toolnames: Sequence[str], style: SudoAliasStyle = "wrap"):
        """
        Append 'sudo' aliases for the project's tools to the RC file.

        The RC file is expected to have been created by 'install()' at
        '<install_path>/.<prjname>-rc.sh'.

        Args:
            toolnames: Names of the tools to create 'sudo' aliases for.
            style: The alias style. Use 'wrap' to run the entire tool process under 'sudo'
                   (e.g. 'alias pepc="sudo ... pepc"'). Use 'refresh' to pre-authorize 'sudo'
                   credentials before each invocation so that 'pepc' can escalate privileges
                   internally as needed (e.g. 'alias pepc="sudo -v && pepc"').
        """

        rcfile_path = self.rcfile_path
        if self._logging:
            _LOG.info("Adding 'sudo' aliases to '%s'%s", rcfile_path, self._pman.hostmsg)

        with self._pman.open(rcfile_path, "a") as fobj:
            fobj.write(f"\n# The '{self._prjname}' tools require superuser privileges.\n")
            for toolname in toolnames:
                if style == "wrap":
                    fobj.write(f'alias {toolname}="sudo PATH=$PATH VIRTUAL_ENV=$VENV '
                               f'$VENV_BIN/{toolname}"\n')
                elif style == "refresh":
                    fobj.write(f'alias {toolname}="sudo -v && {toolname}"\n')
                else:
                    raise Error(f"Unknown sudo alias style '{style}'")

    def hookup_rc_file(self):
        """
        Source the project RC file from the user's shell RC file (e.g. '.bashrc').

        The RC file is expected to have been created by 'install()' at
        '<install_path>/.<prjname>-rc.sh'.
        """

        rcfile_path = self.rcfile_path
        hint = f"Please, add '. {rcfile_path}' to your shell RC file to configure your " \
               f"environment for '{self._prjname}' usage."

        shell_path = self._pman.get_envar("SHELL")
        if not shell_path:
            raise Error(f"Cannot determine shell path, the 'SHELL' environment variable is not "
                        f"set{self._pman.hostmsg}.\n{hint}")

        shell_name = Path(shell_path).name
        if shell_name in ("bash", "zsh"):
            rc_filename = f".{shell_name}rc"
        else:
            _LOG.warning("Unsupported user shell '%s'%s.\n%s",
                         shell_path, self._pman.hostmsg, hint)
            return

        shrc_path = self._home / rc_filename

        if not self._pman.is_file(shrc_path):
            _LOG.warning("Shell RC file '%s' does not exist%s.\n%s",
                         shrc_path, self._pman.hostmsg, hint)
            return

        with self._pman.open(shrc_path, "r") as fobj:
            shrc_contents = fobj.read()

        # Check if the rcfile is already sourced to avoid adding a duplicate entry.
        if str(rcfile_path) in shrc_contents:
            if self._logging:
                _LOG.info("'%s' is already sourced in '%s'%s, skipping.",
                          rcfile_path, shrc_path, self._pman.hostmsg)
            return

        if self._logging:
            _LOG.info("Adding a line to source '%s' to '%s'%s",
                      rcfile_path, shrc_path, self._pman.hostmsg)

        with self._pman.open(shrc_path, "a") as fobj:
            fobj.write(f"\n# The '{self._prjname}' configuration.\n")
            fobj.write(f". {rcfile_path}\n")

    def install(self, exclude: Sequence[str] = ()):
        """Install the Python project on the target host."""

        if self._logging:
            _LOG.info("Installing Python project '%s'%s:\n  Source: %s\n  Target path: %s",
                      self._prjname, self._pman.hostmsg,
                      self._src_url or self._src_path, self.install_path)

        tmpdir: Path | None = None
        target_src_path: Path | None = self._src_path
        try:
            if self._src_path:
                # Always copy the sources to a temporary directory before running pip, even for
                # local installs. For remote installs, the copy transfers the sources to the target
                # host. For local installs, it keeps pip's build artifacts out of the source tree.
                tmpdir = self._pman.mkdtemp(prefix=f"{self._prjname}-installer-")
                target_src_path = tmpdir / "src"

                if self._logging:
                    _LOG.info("Copying installation sources to '%s'%s",
                              target_src_path, self._pman.hostmsg)

                # Exclude unnecessary directories and files.
                all_excludes = ("**/*.pyc", "__pycache__", "build", "*.egg-info") + tuple(exclude)

                output_fobjs: tuple[IO | None, IO | None]
                if self._logging:
                    pfx = "  [rsync] "
                    output_fobjs = (LoggerFile.LoggerFile(prefix=pfx),
                                    LoggerFile.LoggerFile(prefix=pfx))
                    opts = ProcessManager.DEFAULT_RSYNC_OPTS + " -v"
                else:
                    output_fobjs = (None, None)
                    opts = ProcessManager.DEFAULT_RSYNC_OPTS

                # Use trailing slash on 'src' so rsync copies the directory's contents into
                # 'target_src_path', not the directory itself (which would create a subdirectory).
                self._pman.rsync(str(self._src_path) + "/", target_src_path, opts=opts,
                                 remotesrc=False, remotedst=self._pman.is_remote,
                                 exclude=all_excludes, output_fobjs=output_fobjs)

            self._run_installation(target_src_path)
        finally:
            if tmpdir:
                self._pman.rmtree(tmpdir)

        self._create_rc_file()

    def _find_site_packages(self) -> Path:
        """
        Find and return the path to the 'site-packages' directory inside the project's virtual
        environment.

        Returns:
            The path to the 'site-packages' directory.
        """

        lib_dir = self.install_path / "lib"
        found: list[Path] = []
        try:
            with os.scandir(lib_dir) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.startswith("python"):
                        candidate = Path(entry.path) / "site-packages"
                        if candidate.is_dir():
                            found.append(candidate)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to find 'site-packages' under '{lib_dir}':\n{errmsg}") from err

        if not found:
            raise Error(f"Failed to find 'site-packages' under '{lib_dir}'")
        if len(found) > 1:
            _LOG.warning("Found multiple 'site-packages' directories under '%s': %s\n"
                         "Using '%s'.", lib_dir, ", ".join(str(p) for p in found), found[0])

        return found[0]

    def _add_packages_to_zip(self,
                             zipobj: zipfile.ZipFile,
                             site_packages_path: Path,
                             exclude: frozenset[str]):
        """
        Add Python packages from 'site-packages' to an open zip archive.

        Args:
            zipobj: An open zip file object to add packages to.
            site_packages_path: Path to the venv's 'site-packages' directory.
            exclude: Package names to skip.
        """

        # Add all Python packages to the zip archive. Skip '.pyc' bytecode files, '__pycache__'
        # directories, and any packages specified in 'exclude'.
        for item in site_packages_path.iterdir():
            if item.name in exclude:
                continue
            if item.name.endswith((".dist-info", ".egg-info")):
                continue
            if item.name == "__pycache__":
                continue

            if item.is_dir():
                for root, _, files in os.walk(item):
                    root_path = Path(root)
                    if root_path.name == "__pycache__":
                        continue
                    for fname in files:
                        fpath = root_path / fname
                        if fpath.suffix == ".pyc":
                            continue
                        zipobj.write(fpath, arcname=fpath.relative_to(site_packages_path))
            elif item.suffix != ".pyc":
                zipobj.write(item, arcname=item.relative_to(site_packages_path))

    def create_standalone(self,
                          toolname: str,
                          output_path: Path,
                          exclude_pkgs: Sequence[str] = ()):
        """
        Create a standalone zipapp executable of a tool from the Python virtual environment where
        the project is installed. A zipapp is a self-contained executable Python zip archive: a
        single file with a Python shebang followed by a zip containing '__main__.py' and all the
        required Python packages.

        Args:
            toolname: Name of the tool to create the standalone executable for. The tool must be
                      installed in the virtual environment ('self.install_path').
            output_path: Destination path for the standalone executable.
            exclude_pkgs: Package names inside 'site-packages' to exclude.
        """

        if self._pman.is_remote:
            raise Error("Only local host is supported for standalone executable creation")

        tool_path = self.install_path / "bin" / toolname
        try:
            if not tool_path.is_file():
                raise Error(f"Cannot find '{tool_path}'")
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to access '{tool_path}':\n{errmsg}") from err

        site_packages_path = self._find_site_packages()
        exclude_python_packages = _NON_RUNTIME_PYTHON_PACKAGES | set(exclude_pkgs)

        # Read the tool source and strip its shebang if it has one. This step is not strictly
        # necessary, but it makes the resulting standalone file tidier, because the original shebang
        # could be something like '#!/tmp/.../bin/python3'.
        try:
            tool_contents = tool_path.read_text(encoding="utf-8")
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to read '{tool_path}':\n{errmsg}") from err
        if tool_contents.startswith("#!"):
            tool_contents = tool_contents[tool_contents.index("\n") + 1:]

        if self._logging:
            _LOG.info("Creating standalone version of '%s': '%s'", toolname, output_path)

        # pylint: disable-next=import-outside-toplevel
        import zipfile

        # Build the zipapp: a Python shebang line followed by a zip archive containing:
        #   - '__main__.py' at the root - the entry point executed by Python.
        #   - All required Python packages from 'site-packages'.
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as fobj:
                fobj.write(b"#!/usr/bin/python3\n")
                with zipfile.ZipFile(fobj, "w", compression=zipfile.ZIP_DEFLATED) as zipobj:
                    zipobj.writestr("__main__.py", tool_contents)
                    self._add_packages_to_zip(zipobj=zipobj,
                                              site_packages_path=site_packages_path,
                                              exclude=exclude_python_packages)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to create standalone '{output_path}':\n{errmsg}") from err

        try:
            # Set file permissions to u=rwx,g=rx,o=rx.
            mode = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
            output_path.chmod(mode)
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Cannot make '{output_path}' executable:\n{errmsg}") from err
