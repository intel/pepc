#!/bin/sh -euf
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

PROG="make_a_release.sh"
BASEDIR="$(readlink -ev -- ${0%/*}/..)"

# Regular expression matching pepc version.
VERSION_REGEX='\([0-9]\+\)\.\([0-9]\+\)\.\([0-9]\+\)'
VERSION_VAR_REGEX="^_VERSION\([^=]*\)= \"$VERSION_REGEX\"$"

# File paths containing the version number that we'll have to adjust.
PEPC_FILE="$BASEDIR/pepctools/_Pepc.py"
SPEC_FILE="$BASEDIR/rpm/pepc.spec"

# The python packaging file.
PYPROJECT_TOML="$BASEDIR/pyproject.toml"

# The CHANGELOG.md file path.
CHANGELOG_FILE="$BASEDIR/CHANGELOG.md"

# Documentation directory and files.
MAN_DIR="$BASEDIR/pepcdata/man/man1"
RST_FILES="$BASEDIR/docs/pepc-pstates.rst
           $BASEDIR/docs/pepc-cstates.rst
           $BASEDIR/docs/pepc-uncore.rst
           $BASEDIR/docs/pepc-cpu-hotplug.rst
           $BASEDIR/docs/pepc-topology.rst
           $BASEDIR/docs/pepc-pmqos.rst
           $BASEDIR/docs/pepc-tpmi.rst
           $BASEDIR/docs/pepc-aspm.rst"

# Path to the script that prepares CHANGELOG.md for the release.
PREPARE_CHENGELOG_MD="$BASEDIR/misc/prepare_changelog_md"

fatal() {
        printf "$PROG: error: %s\n" "$1" >&2
        exit 1
}

usage() {
        cat <<EOF
Usage: ${0##*/} <new_ver>

<new_ver> - new tool version to make in X.Y.Z format. The X.Y.(Z+1) version
            will be used by default.
EOF
        exit 0
}

ask_question() {
	local question=$1

	while true; do
		printf "%s\n" "$question (yes/no)?"
		IFS= read answer
		if [ "$answer" == "yes" ]; then
			printf "%s\n" "Very good!"
			return
		elif [ "$answer" == "no" ]; then
			printf "%s\n" "Please, do that!"
			exit 1
		else
			printf "%s\n" "Please, answer \"yes\" or \"no\""
		fi
	done
}

if [ $# -eq 1 ]; then
    new_ver="$1"; shift
    # Validate the new version.
    printf "%s" "$new_ver" | grep -q -x "$VERSION_REGEX" ||
           fatal "Provide new version in X.Y.Z format"
elif [ $# -eq 0 ]; then
    # The new version was not provided, increment the current version umber.
    ver_start="$(sed -n -e "s/$VERSION_VAR_REGEX/\2.\3./p" "$PEPC_FILE")"
    ver_end="$(sed -n -e "s/$VERSION_VAR_REGEX/\4/p" "$PEPC_FILE")"
    ver_end="$(($ver_end+1))"
    new_ver="$ver_start$ver_end"
else
    usage
fi

echo "New pepc version: $new_ver"

# Validate the new version.
printf "%s" "$new_ver" | grep -q -x "$VERSION_REGEX" ||
         fatal "Provide new version in X.Y.Z format"

# Make sure that the current branch is 'main' or 'release'.
current_branch="$(git -C "$BASEDIR" branch | sed -n -e '/^*/ s/^* //p')"
if [ "$current_branch" != "main" -a "$current_branch" != "release" ]; then
	fatal "Current branch is '$current_branch' but must be 'main' or 'release'"
fi

# Remind the maintainer about various important things.
ask_question "Did you run tests"
ask_question "Did you update 'CHANGELOG.md'"

# Update CHANGELOG.md.
"$PREPARE_CHENGELOG_MD" "$new_ver" "$CHANGELOG_FILE"

# Update the tool version.
sed -i -e "s/$VERSION_VAR_REGEX/_VERSION\1= \"$new_ver\"/" "$PEPC_FILE"
sed -i -e "s/^version = \"$VERSION_REGEX\"$/version = \"$new_ver\"/" "$PYPROJECT_TOML"
# Update RPM package version.
sed -i -e "s/^Version:\(\s\+\)$VERSION_REGEX$/Version:\1$new_ver/" "$SPEC_FILE"

# Update the man pages.
for file in $RST_FILES; do
    manfile="${MAN_DIR}/$(basename "$file" ".rst").1"
    pandoc -f rst -s "$file" -t man -o "$manfile"
    git add "$manfile"
done

# Commit the changes.
git -C "$BASEDIR" commit -a -s -m "Release version $new_ver"

outdir="."
tag_name="v$new_ver"
release_name="Version $new_ver"

# Create new signed tag.
printf "%s\n" "Signing tag $tag_name"
git -C "$BASEDIR" tag -m "$release_name" -s "$tag_name"

if [ "$current_branch" = "main" ]; then
    branchnames="main and release brances"
else
    branchnames="release branch"
fi

cat <<EOF
To finish the release:
  1. push the $tag_name tag out
  2. push $branchnames branches out

The commands would be:
EOF

for remote in "origin" "upstream" "public"; do
    echo "git push $remote $tag_name"
    if [ "$current_branch" = "main" ]; then
        echo "git push $remote main:main"
        echo "git push $remote main:release"
    else
        echo "git push $remote release:release"
    fi
done

if [ "$current_branch" != "main" ]; then
    echo
    echo "Then merge the release branch back to main, and run the following commands:"

    for remote in "origin" "upstream" "public"; do
        echo "git push $remote main:main"
    done
fi
