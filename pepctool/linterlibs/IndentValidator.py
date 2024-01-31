# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""Indent validator module for the PepcPylintPlugin."""

import re
import tokenize

class IndentValidator():
    """Helper class for validating code indentation."""

    def _validate_string(self, token, lineno, txt):
        """Validate string indentation, if it is a multiline string."""

        if not txt.startswith("\"\"\""):
            return

        base = token.start[1]
        current = base
        tag = None
        levels = {}

        prevline = None
        linecache = None
        lineno -= 1

        txt = txt.lstrip("\"\"\"").rstrip("\"\"\"")

        for line in txt.split("\n"):
            lineno += 1

            prevline = linecache
            linecache = line

            match = re.match(r".*\t", line)
            if match:
                self._parent.add_message("pepc-string-unexpected-tab", line=lineno)
                line = line.expandtabs(4)

            stripline = line.lstrip(" ")
            if prevline is None and line != "":
                base += 3
                linecache = stripline
                current = base
                continue

            if stripline == "":
                # Blank line resets indent levels.
                levels = {}
                linecache = ""
                current = base
                continue

            indent = len(line) - len(stripline)

            bracket_map = {"(": ")", "{": "}", "[": "]"}

            i = base

            while i < len(line):
                ch = line[i]
                if i > 0:
                    prevch = line[i - 1]
                else:
                    prevch = None

                if i < len(line) - 1:
                    nextch = line[i + 1]
                else:
                    nextch = None

                i += 1

                if ch == " ":
                    continue
                if (ch in ("*", "-", "o") and prevch == " " and nextch == " ") \
                   or ch in ("(", "{", "[", ":"):
                    offset = 0
                    while i + offset < len(line) and line[i + offset] == " ":
                        offset += 1
                    if offset:
                        lvl_offset = i + 1
                    else:
                        lvl_offset = i
                    offset += 1
                    levels[lvl_offset] = {"offset": offset, "tag": ch}
                    continue
                if ch in (")", "}", "]") and levels:
                    prev = levels[list(levels)[-1]]
                    if prev["tag"] in bracket_map and bracket_map[prev["tag"]] == ch:
                        levels.popitem()
                        if not levels:
                            current = base

            tag = None

            match = re.match(r"([A-Z]+|[0-9\.]*[0-9]+)\. ", stripline)
            if match:
                offset = len(match.group(1)) + 2
                match = re.match(r"[A-Z]", stripline)
                if match:
                    tag = "str"
                else:
                    tag = "num"

            if tag:
                if indent + offset not in levels:
                    levels[indent + offset] = {"offset": offset, "tag": tag}
                    current = indent + offset
                else:
                    if levels[indent + offset]["tag"] != tag:
                        self._parent.add_message("pepc-string-reused-indent-level",
                                                 args=(tag, levels[indent + offset]["tag"]),
                                                 line=lineno)
                continue

            if indent != current:
                if indent == base:
                    current = indent
                else:
                    for lvl_indent, lvl in levels.items():
                        if indent == lvl_indent:
                            current = lvl_indent
                            break
                        if indent == lvl_indent - lvl["offset"]:
                            indent = lvl_indent
                            current = lvl_indent

            if current != indent:
                closest = current
                min_diff = abs(current - indent)

                for lvl in levels:
                    diff = abs(lvl - indent)
                    if not closest or diff < min_diff:
                        closest = lvl
                        min_diff = diff

                self._parent.add_message("pepc-string-bad-indent", line=lineno,
                                         args=(closest, indent))

    def validate(self, token, lineno, txt):
        """
        Verify the alignment of a token, if it is the first token on a line. The arguments are as
        follows.
          * token - token to check.
          * lineno - current line number.
          * txt - text content of current token.
        """

        # Previous token updated a new indent level for us.
        if self._new_indent:
            self._indent = self._new_indent
            self._new_indent = None

        if token.type == tokenize.STRING:
            self._validate_string(token, lineno, txt)

        # Bracket immediately followed by a newline marks the start of a data struct level. In this
        # case, force the indent level to base + 4, and update the saved indent level in the stack
        # also.
        if self._was_bracket and token.type == tokenize.NL:
            self._indent = self._base_indent + len(self._stack) * 4
            self._stack[-1] = self._indent - 4

        self._was_bracket = False

        # Reset indent tracking at newline.
        if token.type == tokenize.NEWLINE:
            self._indent = self._base_indent
            self._stack = []
            return

        # Update expected indent level at brackets.
        if txt in ("(", "{", "["):
            self._stack.append(self._indent)
            self._new_indent = token.end[1]
            self._was_bracket = True
        elif txt in (")", "}", "]"):
            self._indent = self._stack.pop()
            return

        if token.type == tokenize.INDENT:
            self._indent += 4
            self._base_indent += 4
            return

        if token.type == tokenize.DEDENT:
            self._indent -= 4
            self._base_indent -= 4
            return

        if token.type == tokenize.NL:
            return

        if self._indent == self._base_indent and self._new_indent is None and \
           (self._parent.is_reserved(token) or (token.type == tokenize.OP and txt != ".")):
            self._new_indent = token.end[1] + 1

        prevtok = self._parent.get_token(0, skip=(tokenize.NL,))
        if not prevtok:
            return

        prevline = prevtok.end[0]
        if prevline == lineno:
            return

        if token.type == tokenize.COMMENT:
            self._pending.append(token)
            return

        if prevtok.type == tokenize.STRING and token.type == tokenize.STRING:
            self._indent = prevtok.start[1]

        tokens = [token]
        tokens += self._pending

        for tok in tokens:
            indent = tok.start[1]

            if indent != self._indent:
                self._parent.add_message("pepc-bad-indent", line=tok.start[0],
                                         args=(self._indent, indent))

        self._pending = []

    def __init__(self, parent):
        """
        Class constructor for the 'IndentValidator'. Arguments are as follows.
          * parent - parent 'PepcTokenChecker' object.
        """

        self._parent = parent
        self._indent = 0
        self._new_indent = None
        self._base_indent = 0
        self._stack = []
        self._pending = []
        self._was_bracket = False
