# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Helper functions for making a project release.

Terminology used throughout this module:
  - current release: the latest already-released version.
  - upcoming release: the new version being released now.
  - future release: the version that will follow the upcoming release.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import typing
import shutil
import tomllib
import subprocess
from datetime import date
from pathlib import Path

from pepclibs.helperlibs import Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Iterable

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc")

# Future release section template to prepend to 'CHANGELOG.md' after each release.
_FUTURE_RELEASE_SECTION = """\
## [ADD NEW VERSION HERE] - ADD DATE HERE
### Fixed
### Added
### Removed
### Changed
"""

# Standard branches used for publishing a release.
_BRANCHES = ("main", "release")

# Standard remotes used for publishing a release.
_REMOTES = ("public", "upstream", "origin")

def get_current_version(src_path: Path) -> tuple[int, int, int]:
    """
    Get the current release version of the project from the git repository at 'src_path'.

    Args:
        src_path: Path to the project git repository.

    Returns:
        The current release version as a (major, minor, patch) tuple of integers.

    Notes:
        - The version is read from 'pyproject.toml' in the repository.
    """

    pyproject_path = src_path / "pyproject.toml"

    try:
        with pyproject_path.open("rb") as fobj:
            data = tomllib.load(fobj)
    except OSError as err:
        raise Error(f"Failed to read '{pyproject_path}': {err}") from err

    version_str = data.get("project", {}).get("version", "")
    if not version_str:
        raise Error(f"No version found in '{pyproject_path}'")

    parts = Trivial.split_csv_line_int(version_str, sep=".",
                                       what=f"version in '{pyproject_path}'")
    if len(parts) != 3:
        raise Error(f"Unexpected version format '{version_str}' in '{pyproject_path}', "
                    f"expected 'major.minor.patch'")

    return parts[0], parts[1], parts[2]

def get_upcoming_version(cur_version: tuple[int, int, int],
                         patch: bool,
                         minor: bool,
                         major: bool) -> tuple[int, int, int]:
    """
    Compute the upcoming release version by incrementing the appropriate component of
    'cur_version'.

    Args:
        cur_version: The current release version as a (major, minor, patch) tuple.
        patch: Whether to increment the patch version component.
        minor: Whether to increment the minor version component.
        major: Whether to increment the major version component.

    Returns:
        The upcoming release version as a (major, minor, patch) tuple.
    """

    vmajor, vminor, vpatch = cur_version

    if major:
        return vmajor + 1, 0, 0
    if minor:
        return vmajor, vminor + 1, 0
    if patch:
        return vmajor, vminor, vpatch + 1
    raise Error("At least one of 'patch', 'minor', or 'major' must be True")

def prepare_changelog(src_path: Path,
                      cur_version: tuple[int, int, int],
                      upcoming_version: tuple[int, int, int]):
    """
    Validate the upcoming release section in 'CHANGELOG.md', print it, and update the file for
    the upcoming release.

    Args:
        src_path: Path to the project git repository.
        cur_version: The current release version as a (major, minor, patch) tuple.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.

    Notes:
        - The first current release header must match 'cur_version'.
        - The upcoming release entry starts with '## [ADD NEW VERSION HERE] - ADD DATE HERE'.
        - Valid sections are '### Fixed', '### Added', '### Removed', '### Changed'.
        - At least one bullet item must be present across any of the four sections.
        - Each bullet item must start with ' - '.
        - No line in the upcoming release section may exceed 80 characters.
    """

    changelog_path = src_path / "CHANGELOG.md"

    # Read the entire file in one pass, splitting into three parts.
    #   1. preamble: text before the upcoming release header.
    #   2. upcoming: from the upcoming header up to (not including) the first current release
    #                header.
    #   3. released: the current release header and all text after it.
    preamble_lines: list[str] = []
    upcoming_lines: list[str] = []
    released_lines: list[str] = []
    state = "preamble"

    try:
        with changelog_path.open(encoding="utf-8") as fobj:
            for line in fobj:
                line = line.rstrip("\n")
                if state == "preamble":
                    if line == "## [ADD NEW VERSION HERE] - ADD DATE HERE":
                        state = "upcoming"
                        upcoming_lines = [line]
                    else:
                        preamble_lines.append(line)
                elif state == "upcoming":
                    if not line:
                        continue
                    if re.match(r"^## \[\d", line):
                        state = "released"
                        released_lines.append(line)
                    else:
                        upcoming_lines.append(line)
                else:
                    released_lines.append(line)
    except OSError as err:
        raise Error(f"Failed to read '{changelog_path}': {err}") from err

    if state == "preamble":
        raise Error(f"No upcoming release entry found in '{changelog_path}'.\n"
                    f"Expected a line '## [ADD NEW VERSION HERE] - ADD DATE HERE'")

    if not released_lines:
        raise Error(f"No current release entry found in '{changelog_path}'.\n"
                    f"Expected a line like "
                    f"'## [{cur_version[0]}.{cur_version[1]}.{cur_version[2]}] - <date>'")

    expected_header = f"## [{cur_version[0]}.{cur_version[1]}.{cur_version[2]}]"
    cur_release_line = released_lines[0]
    if not cur_release_line.startswith(expected_header):
        raise Error(f"Unexpected current release header in '{changelog_path}':\n"
                    f"  Found:    {cur_release_line}\n"
                    f"  Expected: {expected_header} - <date>")

    # Validate bullet items from the upcoming release section. At least one is required.
    for line in upcoming_lines[1:]:
        if line.startswith(" - "):
            break
    else:
        raise Error(f"No changelog entries found in the upcoming release section of "
                    f"'{changelog_path}'.\nAdd at least one bullet item under a section header "
                    f"(e.g., '### Added').'")

    for line in upcoming_lines:
        if len(line) > 80:
            raise Error(f"Line exceeds 80 characters in '{changelog_path}':\n  {line}")

    # Build the updated CHANGELOG.md content.
    #   1. Preamble (everything before the upcoming release header).
    #   2. Future release section.
    #   3. The upcoming release section with version and date filled in.
    #   4. Current and previous releases.
    upcoming_ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"
    today = date.today().strftime("%Y-%m-%d")
    upcoming_lines[0] = f"## [{upcoming_ver_str}] - {today}"

    _LOG.info("Upcoming release changelog:\n%s", "\n".join(upcoming_lines))

    new_content = ("\n".join(preamble_lines) + "\n"
                   + _FUTURE_RELEASE_SECTION
                   + "\n"
                   + "\n".join(upcoming_lines) + "\n\n"
                   + "\n".join(released_lines) + "\n")

    tmp_path = changelog_path.with_suffix(".md.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fobj:
            fobj.write(new_content)
            fobj.flush()
            os.fsync(fobj.fileno())
        shutil.move(str(tmp_path), changelog_path)
    except OSError as err:
        raise Error(f"Failed to write '{changelog_path}': {err}") from err
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def restore_files(paths: Iterable[Path]):
    """
    Restore files to their last committed state using a single 'git checkout' call.

    Args:
        paths: Paths to the files to restore.
    """

    paths = list(paths)
    if not paths:
        return

    _LOG.info("Restoring:\n%s", "\n".join(f"  {p}" for p in paths))

    try:
        subprocess.run(["git", "checkout", "HEAD", "--"] + [str(p) for p in paths],
                       cwd=paths[0].parent, capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to restore files: {err}") from err

def check_everything_committed(src_path: Path):
    """
    Check that there are no uncommitted changes in the git repository at 'src_path'.

    Args:
        src_path: Path to the project git repository.
    """

    try:
        result = subprocess.run(["git", "status", "--porcelain"], cwd=src_path,
                                capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to check git status in '{src_path}': {err}") from err

    if result.stdout:
        raise Error(f"Uncommitted changes found in '{src_path}'. Please commit them.")

def get_current_branch(src_path: Path) -> str:
    """
    Return the current git branch name in the repository at 'src_path'.

    Args:
        src_path: Path to the project git repository.

    Returns:
        The current branch name as a string.
    """

    try:
        result = subprocess.run(["git", "branch", "--show-current"], cwd=src_path,
                                capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to get current branch in '{src_path}': {err}") from err

    return result.stdout.strip()

def check_remote_branches(src_path: Path):
    """
    Verify that pushes to all standard remotes will be fast-forwards.

    Args:
        src_path: Path to the project git repository.
    """

    for remote in _REMOTES:
        _LOG.info("Fetching '%s'", remote)
        try:
            subprocess.run(["git", "fetch", remote], cwd=src_path,
                           capture_output=True, text=True, check=True)
        except subprocess.SubprocessError as err:
            raise Error(f"Failed to fetch remote '{remote}' in '{src_path}': {err}") from err

    refs = [f"{remote}/{branch}" for remote in _REMOTES for branch in _BRANCHES]

    for ref in refs:
        try:
            result = subprocess.run(["git", "merge-base", "--is-ancestor", ref, "HEAD"],
                                    cwd=src_path, capture_output=True, text=True, check=False)
        except subprocess.SubprocessError as err:
            raise Error(f"Failed to run 'git merge-base' in '{src_path}': {err}") from err

        if result.returncode == 1:
            raise Error(f"Local 'main' is not based on '{ref}'. Please rebase the local 'main' "
                        f"branch against '{ref}' before releasing.")
        if result.returncode != 0:
            raise Error(f"Failed to check if '{ref}' is an ancestor of 'HEAD' in "
                        f"'{src_path}':\n{result.stderr.strip()}")

def prepare_pyproject_toml(src_path: Path, upcoming_version: tuple[int, int, int]):
    """
    Update the project version in 'pyproject.toml' to 'upcoming_version'.

    Args:
        src_path: Path to the project git repository.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
    """

    pyproject_path = src_path / "pyproject.toml"
    upcoming_ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"

    try:
        lines = pyproject_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as err:
        raise Error(f"Failed to read '{pyproject_path}': {err}") from err

    # Scan line by line, substituting 'version = "..."' only within the '[project]' section.
    in_project = False
    version_count = 0
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_project = False

        if in_project and re.match(r'^version\s*=\s*"[^"]*"', line):
            version_count += 1
            line = re.sub(r'^(version\s*=\s*")[^"]*(")', rf"\g<1>{upcoming_ver_str}\g<2>", line)

        new_lines.append(line)

    if version_count == 0:
        raise Error(f"No 'version = \"...\"' line found in '[project]' section of "
                    f"'{pyproject_path}'")
    if version_count > 1:
        raise Error(f"Multiple 'version = \"...\"' lines found in '[project]' section of "
                    f"'{pyproject_path}'")

    tmp_path = pyproject_path.with_suffix(".toml.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fobj:
            fobj.writelines(new_lines)
            fobj.flush()
            os.fsync(fobj.fileno())
        shutil.move(str(tmp_path), pyproject_path)
    except OSError as err:
        raise Error(f"Failed to write '{pyproject_path}': {err}") from err
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def update_tool_version(tool_path: Path, upcoming_version: tuple[int, int, int]):
    """
    Update the '_VERSION: Final[str] = "..."' line in a tool's Python source file to
    'upcoming_version'.

    Args:
        tool_path: Path to the tool's Python source file.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
    """

    upcoming_ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"

    try:
        content = tool_path.read_text(encoding="utf-8")
    except OSError as err:
        raise Error(f"Failed to read '{tool_path}': {err}") from err

    pattern = r'(_VERSION\s*:\s*Final\[str\]\s*=\s*")[^"]*(")'
    new_content, count = re.subn(pattern, rf"\g<1>{upcoming_ver_str}\g<2>", content, count=2)
    if count == 0:
        raise Error(f"No '_VERSION: Final[str] = ...' line found in '{tool_path}'")
    if count > 1:
        raise Error(f"Multiple '_VERSION: Final[str] = ...' lines found in '{tool_path}'")

    tmp_path = tool_path.with_suffix(".py.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fobj:
            fobj.write(new_content)
            fobj.flush()
            os.fsync(fobj.fileno())
        shutil.move(str(tmp_path), tool_path)
    except OSError as err:
        raise Error(f"Failed to write '{tool_path}': {err}") from err
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def commit_release(src_path: Path,
                   upcoming_version: tuple[int, int, int],
                   paths: Iterable[Path]):
    """
    Stage and commit all release files with a signed-off release commit message.

    Args:
        src_path: Path to the project git repository.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
        paths: Paths to the files to stage and commit.
    """

    paths = list(paths)
    ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"
    msg = f"Release version {ver_str}"

    try:
        subprocess.run(["git", "add", "--"] + [str(p) for p in paths],
                       cwd=src_path, capture_output=True, text=True, check=True)
        subprocess.run(["git", "commit", "-s", "-m", msg],
                       cwd=src_path, capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to commit release '{msg}': {err}") from err

    _LOG.info("Committed: %s", msg)

def uncommit_release(src_path: Path):
    """
    Undo the last git commit, keeping the changes in the working tree.

    Args:
        src_path: Path to the project git repository.
    """

    try:
        subprocess.run(["git", "reset", "--soft", "HEAD^"],
                       cwd=src_path, capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to uncommit in '{src_path}': {err}") from err

    _LOG.info("Uncommitted the release commit")

def tag_release(src_path: Path, upcoming_version: tuple[int, int, int]):
    """
    Create a signed git tag for the upcoming release.

    Args:
        src_path: Path to the project git repository.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
    """

    ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"
    tag_name = f"v{ver_str}"
    tag_msg = f"Version {ver_str}"

    _LOG.info("Signing tag '%s'", tag_name)
    try:
        subprocess.run(["git", "tag", "-s", "-m", tag_msg, tag_name],
                       cwd=src_path, capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to create tag '{tag_name}': {err}") from err

def untag_release(src_path: Path, upcoming_version: tuple[int, int, int]):
    """
    Delete the signed git tag for the upcoming release.

    Args:
        src_path: Path to the project git repository.
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
    """

    ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"
    tag_name = f"v{ver_str}"

    try:
        subprocess.run(["git", "tag", "-d", tag_name],
                       cwd=src_path, capture_output=True, text=True, check=True)
    except subprocess.SubprocessError as err:
        raise Error(f"Failed to delete tag '{tag_name}': {err}") from err

    _LOG.info("Deleted tag '%s'", tag_name)

def print_push_instructions(upcoming_version: tuple[int, int, int]):
    """
    Print the git push commands needed to publish the release.

    Args:
        upcoming_version: The upcoming release version as a (major, minor, patch) tuple.
    """

    ver_str = f"{upcoming_version[0]}.{upcoming_version[1]}.{upcoming_version[2]}"
    tag_name = f"v{ver_str}"

    lines = ["To finish the release:",
             f"  1. Push the '{tag_name}' tag.",
             "  2. Push the 'main' and 'release' branches.",
             "",
             "The commands are:"]

    for remote in _REMOTES:
        lines.append(f"  git push {remote} {tag_name}")
        for branch in _BRANCHES:
            lines.append(f"  git push {remote} main:{branch}")

    _LOG.info("%s", "\n".join(lines))
