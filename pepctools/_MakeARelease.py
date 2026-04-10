# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""make-a-release - make a new 'pepc' project release."""

from __future__ import annotations # Remove when switching to Python 3.10+.

import types
import typing
import subprocess
from pathlib import Path

try:
    argcomplete: types.ModuleType | None
    import argcomplete
except ImportError:
    # We can live without argcomplete, we only lose tab completions.
    argcomplete = None

from pepclibs.helperlibs import ArgParse, Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error
from pepctools import ReleaseHelpers

if typing.TYPE_CHECKING:
    import argparse
    from typing import Final, Literal, cast
    from pepclibs.helperlibs.ArgParse import SSHArgsTypedDict

    _SkippableStepsType = Literal["branch-check", "remotes-check", "uncommitted-check"]

    class _CmdlineArgsTypedDict(SSHArgsTypedDict, total=False):
        """
        A typed dictionary for command-line arguments of this tool. Includes all attributes from
        'SSHArgsTypedDict', plus the following:

        Attributes:
            src_path: Path to 'pepc' project git repository to make a release from (default is the
                      current directory).
            patch: Whether to increment the patch version component (x.y.z -> x.y.(z+1)).
            minor: Whether to increment the minor version component (x.y.z -> x.(y+1).0).
            major: Whether to increment the major version component (x.y.z -> (x+1).0.0).
            skip: A set of steps to skip.
            restore: Restore all modified files upon exit.
        """

        src_path: Path
        patch: bool
        minor: bool
        major: bool
        skip: set[_SkippableStepsType]
        restore: bool

_VERSION: Final[str] = "0.1"
_TOOLNAME: Final[str] = "make-a-release"

# Note, logger name is the project name, not the tool name.
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc").configure(prefix=_TOOLNAME)

def _build_arguments_parser() -> ArgParse.ArgsParser:
    """
    Build and return the command-line arguments parser.

    Returns:
        An initialized command-line arguments parser object.
    """

    text = f"""{_TOOLNAME} - make a new 'pepc' project release."""
    parser = ArgParse.ArgsParser(description=text, prog=_TOOLNAME, ver=_VERSION)
    ArgParse.add_ssh_options(parser)

    text = """Path to the 'pepc' project git repository to make a release from (default is the
              current directory)."""
    parser.add_argument("-s", "--src-path", help=text, type=Path, default=Path.cwd())

    text = """Increment the patch version component: x.y.z -> x.y.(z+1). This is the default
              if no version component increment options are specified."""
    parser.add_argument("-p", "--patch", help=text, action="store_true")

    text = """Increment the minor version component: x.y.z -> x.(y+1).0."""
    parser.add_argument("-m", "--minor", help=text, action="store_true")

    text = """Increment the major version component: x.y.z -> (x+1).0.0."""
    parser.add_argument("-M", "--major", help=text, action="store_true")

    text = """Skip one or more steps. Accepts a comma-separated list of step names. Valid step
              names are: 'branch-check', 'remotes-check', 'uncommitted-check'. For development \
              and debugging only."""
    parser.add_argument("--skip", help=text, default="")

    text = """Restore all files modified by this tool upon exit. For development and debugging
              only."""
    parser.add_argument("--restore", help=text, action="store_true")

    if argcomplete is not None:
        getattr(argcomplete, "autocomplete")(parser)

    return parser

def _parse_arguments() -> argparse.Namespace:
    """
    Parse the command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """

    parser = _build_arguments_parser()
    args = parser.parse_args()

    return args

def _get_cmdline_args(args: argparse.Namespace) -> _CmdlineArgsTypedDict:
    """
    Format command-line arguments into a typed dictionary.

    Args:
        args: Command-line arguments namespace.

    Returns:
        A dictionary containing the parsed command-line arguments.
    """

    cmdl: _CmdlineArgsTypedDict = {**ArgParse.format_ssh_args(args)}

    src_path: Path = args.src_path
    cmdl["src_path"] = src_path.resolve()

    cmdl["patch"] = args.patch
    cmdl["minor"] = args.minor
    cmdl["major"] = args.major

    if not (cmdl["patch"] or cmdl["minor"] or cmdl["major"]):
        # Default to patch increment if no version component increment options are specified.
        cmdl["patch"] = True

    if sum((cmdl["patch"], cmdl["minor"], cmdl["major"])) > 1:
        raise Error("Only one of the '--patch', '--minor', or '--major' options can be specified")

    cmdl["skip"] = set()
    if args.skip:
        skip = set(Trivial.split_csv_line(args.skip))
        if typing.TYPE_CHECKING:
            cmdl["skip"] = cast(set[_SkippableStepsType], skip)
        else:
            cmdl["skip"] = skip

        valid_skip: set[_SkippableStepsType] = {"branch-check", "remotes-check",
                                                "uncommitted-check"}

        unknown = cmdl["skip"] - valid_skip
        if unknown:
            raise Error(f"Unknown '--skip' value(s): {', '.join(sorted(unknown))}\n"
                        f"Valid values are: {', '.join(sorted(valid_skip))}")

    cmdl["restore"] = args.restore
    return cmdl

def _regenerate_man_pages(src_path: Path) -> list[Path]:
    """
    Regenerate pepc man pages from the markdown source files in 'docs/man/'.

    Args:
        src_path: Path to the 'pepc' project git repository.

    Returns:
        A list of paths to the regenerated man page files.
    """

    md_dir = src_path / "docs" / "man"
    man_dir = src_path / "pepcdata" / "man" / "man1"

    man_paths: list[Path] = []
    for md_path in sorted(md_dir.glob("*.md")):
        stem = md_path.stem
        man_path = man_dir / f"{stem}.1"
        cmd = ["pandoc", "-f", "markdown_strict+definition_lists", "-s",
               "-M", f"title={stem.upper()}", "-M", "section=1",
               str(md_path), "-t", "man", "-o", str(man_path)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.SubprocessError as err:
            raise Error(f"Failed to regenerate man page '{man_path}': {err}") from err
        _LOG.info("Regenerated man page '%s'", man_path)
        man_paths.append(man_path)

    return man_paths

def _main(cmdl: _CmdlineArgsTypedDict):
    """
    The main body of the tool.

    Args:
        cmdl: The command-line arguments description dictionary.
    """

    src_path = cmdl["src_path"]
    cur_version = ReleaseHelpers.get_current_version(src_path)
    upcoming_version = ReleaseHelpers.get_upcoming_version(cur_version, cmdl["patch"],
                                                           cmdl["minor"], cmdl["major"])
    branch = ReleaseHelpers.get_current_branch(src_path)
    if "branch-check" not in cmdl["skip"] and branch != "main":
        raise Error(f"Current branch is '{branch}', but must be 'main'")
    if "remotes-check" not in cmdl["skip"]:
        ReleaseHelpers.check_remote_branches(src_path)

    _LOG.info("Project version: %d.%d.%d -> %d.%d.%d", *cur_version, *upcoming_version)

    if "uncommitted-check" not in cmdl["skip"]:
        ReleaseHelpers.check_everything_committed(src_path)

    modified: list[Path] = []
    committed = False
    tagged = False

    try:
        ReleaseHelpers.prepare_changelog(src_path, cur_version, upcoming_version)
        modified.append(src_path / "CHANGELOG.md")
        ReleaseHelpers.prepare_pyproject_toml(src_path, upcoming_version)
        modified.append(src_path / "pyproject.toml")
        ReleaseHelpers.update_tool_version(src_path / "pepctools" / "_Pepc.py", upcoming_version)
        modified.append(src_path / "pepctools" / "_Pepc.py")
        modified.extend(_regenerate_man_pages(src_path))
        ReleaseHelpers.commit_release(src_path, upcoming_version, modified)
        committed = True
        ReleaseHelpers.tag_release(src_path, upcoming_version)
        tagged = True
    finally:
        if cmdl["restore"]:
            if tagged:
                ReleaseHelpers.untag_release(src_path, upcoming_version)
            if committed:
                ReleaseHelpers.uncommit_release(src_path)
            ReleaseHelpers.restore_files(modified)

    if not cmdl["restore"]:
        ReleaseHelpers.print_push_instructions(upcoming_version)

def main():
    """
    The entry point of the tool.

    Returns:
        The program exit code.
    """

    try:
        args = _parse_arguments()
        cmdl = _get_cmdline_args(args)
        _main(cmdl)
    except KeyboardInterrupt:
        _LOG.info("\nInterrupted, exiting")
    except Error as err:
        _LOG.error_out(str(err))

    return 0
