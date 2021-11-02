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

format_changelog() {
	local logfile="$1"; shift
	local pfx1="$1"; shift
	local pfx2="$1"; shift
	local pfx_len="$(printf "%s" "$pfx1" | wc -c)"
	local width="$((80-$pfx_len))"

	while IFS= read -r line; do
		printf "%s\n" "$line" | fold -c -s -w "$width" | \
			sed -e "1 s/^/$pfx1/" | sed -e "1! s/^/$pfx2/" | \
			sed -e "s/[\t ]\+$//"
	done < "$logfile"
}

[ $# -eq 0 ] && usage
[ $# -eq 1 ] || fatal "insufficient or too many argumetns"

new_ver="$1"; shift

# Validate the new version
printf "%s" "$new_ver" | egrep -q -x '[[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+' ||
        fatal "please, provide new version in X.Y.Z format"

# Make sure that the current branch is 'master'
current_branch="$(git branch | sed -n -e '/^*/ s/^* //p')"
if [ "$current_branch" != "master" ]; then
	fatal "current branch is '$current_branch' but must be 'master'"
fi

# Remind the maintainer about various important things
ask_question "Did you run tests"
ask_question "Did you update man pages"
ask_question "Did you update 'debian/changelog'"

# Make sure the git index is up-to-date
[ -z "$(git status --porcelain)" ] || fatal "git index is not up-to-date"

outdir="."
tag_name="v$new_ver"
release_name="Version $new_ver"

# Create new signed tag
printf "%s\n" "Signing tag $tag_name"
git tag -m "$release_name" -s "$tag_name"

cat <<EOF
To finish the release:
  1. push the $tag_name tag out
  2. push the master and release branches out

The commands would be:

git push public $tag_name
git push public master:master
git push public master:release
EOF
