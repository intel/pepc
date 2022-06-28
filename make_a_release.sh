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

fatal() {
        printf "Error: %s\n" "$1" >&2
        exit 1
}

usage() {
        cat <<EOF
Usage: ${0##*/} <new_ver> <outdir>

<new_ver>  - new tool version to make in X.Y format
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

[ $# -eq 0 ] && usage
[ $# -eq 1 ] || fatal "insufficient or too many argumetns"

new_ver="$1"; shift

# Validate the new version.
printf "%s" "$new_ver" | egrep -q -x '[[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+' ||
        fatal "please, provide new version in X.Y.Z format"

# Make sure that the current branch is 'master' or 'release'.
current_branch="$(git branch | sed -n -e '/^*/ s/^* //p')"
if [ "$current_branch" != "master" -a "$current_branch" != "release" ]; then
	fatal "current branch is '$current_branch' but must be 'master' or 'release'"
fi

# Remind the maintainer about various important things.
ask_question "Did you run tests"
ask_question "Did you update 'CHANGELOG.md'"

# Change the tool version.
sed -i -e "s/^VERSION = \"[0-9]\+\.[0-9]\+\.[0-9]\+\"$/VERSION = \"$new_ver\"/" pepctool/_Pepc.py
# Change RPM package version.
sed -i -e "s/^Version:\(\s\+\)[0-9]\+\.[0-9]\+\.[0-9]\+$/Version:\1$new_ver/" dist/rpm/pepc.spec

# Update the man page.
argparse-manpage --pyfile pepctool/_Pepc.py --function build_arguments_parser \
                 --project-name 'pepc' --author 'Artem Bityutskiy' \
                 --author-email 'dedekind1@gmail.com' --output docs/man1/pepc.1 \
                 --url 'https://github.com/intel/pepc'
pandoc --toc -t man -s docs/man1/pepc.1 -t rst -o docs/pepc-man.rst

# Commit the changes.
git commit -a -s -m "Release version $new_ver"

outdir="."
tag_name="v$new_ver"
release_name="Version $new_ver"

# Create new signed tag.
printf "%s\n" "Signing tag $tag_name"
git tag -m "$release_name" -s "$tag_name"

if [ "$current_branch" = "master" ]; then
    branchnames="master and release brances"
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
    if [ "$current_branch" = "master" ]; then
        echo "git push $remote master:master"
        echo "git push $remote master:release"
    else
        echo "git push public release:release"
    fi
done

if [ "$current_branch" != "master" ]; then
    echo
    echo "Then merge the release branch back to master, and run the following commands:"

    for remote in "origin" "upstream" "public"; do
        echo "git push $remote master:master"
    done
fi
