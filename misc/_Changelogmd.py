#!/usr/bin/python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Juha Haapakorpi <juha.haapakorpi@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""Misc. common functions for 'CHANGELOG.md' file processing."""

import re

def get_chmd_entries(path):
    """Reads the 'CHANGELOG.md' file at path 'path' and yields changelog entries."""

    with open(path, "r", encoding="utf-8") as fobj:
        intext = fobj.read()
        # Decoding for regex.
        #
        # The entire regex is structured like this: 'start_line.*?(?=stopline)'
        #
        # Yield 1:
        # ## [1.3.21] - 2022-09-29
		# ## Fixed
		#  - Fix a bug.
		#
		# Yield 2:
        # ## [1.3.20] - 2022-09-21
		# ### Added
		#  - Add a feature
        #
        # So the idea is that we match the 'start_line', which is '## [1.3.21] - 2022-09-29' in this
        # example. We include all lines until we meet 'stopline', which is '## [1.3.20] -
        # 2022-09-21' in this example (or the end of file). We do not include the 'stopline' to the
        # changelog entry, it is actually the beginning of the next changelog entry.
        #
        # The '.*?' part after 'start_line', combined with 're.DOTALL', means "match any character,
        # including a newline, use greedy algorithm". It will try to match as many characters as
        # possible. The '(?stopline)' part basically says - but stop when you meet a line like this.
        #
        # The 'stopline' is structure like this: '(?:(?:startline)|(?:\Z)'.
        #
        # The '(?:)' part is just grouping but without capturing into a group. The '\Z' part is the
        # end of input string. So the entire construct just says that our stopline is either the
        # start of the new changelog entry, or the end of the input (to catch the very last
        # changelog entry too).
        for entry in re.findall(r"##\s+\[.*?(?=(?:(?:\n##\s+\[)|(?:\Z)))", intext, re.DOTALL):
            yield entry

def get_preamble(path):
    """
    Read and return the 'CHANGELOG.md' preamble (everything that goes before the first changelog
    entry.
    """

    with open(path, "r", encoding="utf-8") as fobj:
        intext = fobj.read()

    mobj = re.search(r"^.*?(?=(?:##.*ADD DATE HERE))", intext, re.DOTALL)
    if not mobj:
        return ""
    return mobj.group(0)
