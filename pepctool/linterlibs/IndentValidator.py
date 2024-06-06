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

_brackets = {"(": ")", "{": "}", "[": "]"}
_close_brackets = {v: k for k, v in _brackets.items()}

class IndentStack():
    """Helper class for handling indent levels."""

    def add_message(self, *args, **kwargs):
        """Helper for passing a linter message to parent object via 'args' and 'kwargs'."""
        self._parent.add_message(*args, **kwargs)

    def debug(self, *args, **kwargs):
        """Helper for passing debug messages specified via 'args' and 'kwargs' to parent object."""
        self._parent.debug(*args, **kwargs)

    def dump(self, lineno, context=False):
        """
        Debug helper for dumping the contents of the indent stack. Arguments are as follows.
          * lineno - optional line number.
          * context - if True, changes the dump to be printed with 'context' debug tag instead of
                      default 'indent'.
        """

        if context and not self._debug:
            debug_tag = "context"
        else:
            debug_tag = "indent"

        self.debug(debug_tag, "dump: C:{current}, LVLs:{levels}", lineno=lineno,
                   current=self._current, levels=self._levels)

    def _find_elem(self, indent, tag):
        """Helper for finding an indent level 'indent' with 'tag' from the stack."""

        level_nums = self._level_nums

        for idx, _ in enumerate(level_nums):
            elem = self._levels[level_nums[idx]]

            if elem["tag"] != tag:
                continue

            p_indent = 0
            n_indent = None

            if idx > 0:
                p_indent = level_nums[idx - 1]

            if idx + 1 < len(level_nums):
                n_indent = level_nums[idx + 1]

            if p_indent > indent:
                continue

            if n_indent and n_indent < indent:
                continue

            return elem

        return None

    def _push(self, entry):
        """Helper for pushing a new 'entry' to indent stack."""

        self._levels[entry["level"]] = entry
        self._level_nums = sorted(list(self._levels))

    def push(self, level=None, tag=None, offset=None, lineno=None):
        """
        Push a new indent tag and level to the stack. Arguments are as follows.
          * level - indent level to push.
          * tag - tag for the new indent.
          * offset - offset between the tag position and the indented text.
          * lineno - optional line number for logging purposes.
        """

        entry = {"level": level, "tag": tag, "offset": offset, "lineno": lineno}

        if tag in ("*", "-", "o", ":", "num", "str"):
            old = self._find_elem(level, tag)
            if old and old["level"] == level:
                self.pop(elem=old, lineno=lineno)
                self._push(entry)
                return

        if level in self._levels:
            old = self._levels[level]

            if old["level"] != level or old["tag"] != tag or old["offset"] != offset:
                self.add_message("pepc-string-reused-indent-level",
                                 args=(level, tag, old["tag"], old["lineno"]),
                                 line=lineno)
                self.dump(lineno, context=True)
                old["level"] = level
                old["tag"] = tag
                old["offset"] = offset
                old["lineno"] = lineno

            return

        self._push(entry)

        if tag in _brackets:
            self._current += 4

        self.dump(lineno)

    def pop(self, level=None, tag=None, elem=None, lineno=None):
        """
        Pop an indent level from the stack. This removes any indent levels above the specified level
        also. Arguments are as follows.
          * level - target indent level, anything above this are removed.
          * tag - indent tag to match.
          * elem - optional indent stack element.
          * lineno - optional line number for logging purposes.
        """

        if elem:
            level = elem["level"]
            tag = elem["tag"]

        if tag in _close_brackets:
            tag = _close_brackets[tag]
            if self._current > self._base:
                self._current -= 4

        level_nums = self._level_nums

        popped = None

        for lvl_num in reversed(level_nums):
            entry = self._levels[lvl_num]

            if entry["tag"] == tag:
                popped = entry
            elif tag in _brackets and entry["tag"] in _brackets:
                self.add_message("pepc-string-unbalanced-bracket", line=lineno,
                                 args=(_brackets[tag], level, _brackets[entry["tag"]]))
                break

            del self._levels[lvl_num]

            if popped:
                break

        self._level_nums = sorted(list(self._levels))

        self.dump(lineno)

        return popped

    def adjust(self, adjust, lineno=None):
        """
        Adjust base indent level by 'adjust'. Optional line number can be provided via 'lineno'
        for logging purposes.
        """

        self._base += adjust
        self.reset(lineno=lineno)

    def reset(self, lineno=None):
        """
        Reset indent level to base. Optional line number can be provided via 'lineno' for logging
        purposes.
        """

        self._levels = {}
        self._current = self._base

        elem = {"level": self._base, "tag": "base", "lineno": lineno, "offset": 0}
        self._push(elem)

    def current(self):
        """Return current indent level."""
        return self._current

    def find_indent(self, indent, tag=None, elem=None):
        """Find closest indent level to 'indent'. Arguments are as follows.
          * indent - indent level to find.
          * tag - tag type to match for optional 'elem'.
          * elem - optional indent element to match.
        """

        def _try_indent(indent, lvl, elem, tag):
            """Internal helper to match indent 'lvl' to 'tag' type and 'elem'."""
            if tag == elem["tag"]:
                try_indent = lvl - elem["offset"]
            else:
                try_indent = lvl

            return abs(try_indent - indent), try_indent

        min_diff = None
        min_lvl = None

        if elem:
            if indent == elem["level"]:
                return indent

            if tag == elem["tag"] and indent == elem["level"] - elem["offset"]:
                return indent

            min_diff = abs(indent - elem["level"])
            min_lvl = elem["level"]

        if indent == self._current:
            return indent

        if indent in self._levels:
            return indent

        for lvl, iter_elem in self._levels.items():
            diff, try_lvl = _try_indent(indent, lvl, iter_elem, tag)
            if not diff:
                return indent

            if not min_diff or diff < min_diff:
                min_diff = diff
                min_lvl = try_lvl

        if min_lvl:
            return min_lvl

        return self._current

    def __init__(self, parent, base, debug=False):
        """
        Class constructor for 'IndentStack()'. Arguments are as follows.
          * parent - parent object.
          * base - base indent level in characters.
          * debug - True, if debug is enabled.
        """
        self._base = base
        self._parent = parent
        self._debug = debug
        self._level_nums = None
        self.reset()

class StringIndentValidator():
    """Helper class for validating string indentation."""

    def add_message(self, *args, **kwargs):
        """Forward a linter warning to parent object defined by 'args' and 'kwargs'."""
        self._parent.add_message(*args, **kwargs)

    def debug(self, *args, **kwargs):
        """Forward a debug message to parent object defined by 'args' and 'kwargs'."""
        self._parent.debug(*args, **kwargs)

    def match_tag(self, txt):
        """Find the first tag from 'txt'."""
        ch = txt[0]

        if len(txt) > 1:
            nextch = txt[1]
        else:
            nextch = None

        if ch in ("*", "o", "-") and nextch == " ":
            return ch

        if ch in _brackets:
            return ch

        return None

    def validate_line(self, lineno, txt):
        """
        Validate a single line of string content. Arguments are as follows.
          * lineno - line number.
          * txt - line content.
        """

        self._num_lines += 1

        match = re.match(r".*\t", txt)
        if match:
            self.add_message("pepc-string-unexpected-tab", line=lineno)
            txt = txt.expandtabs(4)

        striptxt = txt.lstrip(" ")

        # Check if multiline string starter (""") immediately followed by text.
        if self._num_lines == 1 and txt != "":
            self._stack.adjust(3, lineno=lineno)
            self._base += 3

        # Blank line resets indent levels.
        if striptxt == "":
            self._stack.reset(lineno=lineno)
            return

        txtlen = len(txt)

        indent = txtlen - len(striptxt)

        i = indent

        if self._num_lines == 1:
            indent = indent + self._base

        popped = None

        while i < txtlen:
            ch = txt[i]
            if i > 0:
                prevch = txt[i - 1]
            else:
                prevch = None

            if i < txtlen - 1:
                nextch = txt[i + 1]
            else:
                nextch = None

            i += 1

            if ch == " ":
                continue

            if (ch in ("*", "-", "o") and prevch == " " and nextch == " ") \
               or ch in _brackets or ch == ":":
                offset = 0
                while i + offset < txtlen and txt[i + offset] == " ":
                    offset += 1
                if offset:
                    lvl_offset = i + 1
                else:
                    lvl_offset = i

                if self._num_lines == 1:
                    lvl_offset += indent

                offset += 1
                self._stack.push(level=lvl_offset, offset=offset, tag=ch, lineno=lineno)

            if ch in _close_brackets:
                popped = self._stack.pop(level=i, tag=ch, lineno=lineno)

        tag = None

        # Match any alphanumerical list entries ('1.' or 'A.').
        match = re.match(r"([A-Z]+|[0-9\.]*[0-9]+)\. ", striptxt)
        if match:
            offset = len(match.group(1)) + 2
            match = re.match(r"[A-Z]", striptxt)
            if match:
                tag = "str"
            else:
                tag = "num"

        if tag:
            self._stack.push(level=indent + offset, offset=offset, tag=tag, lineno=lineno)

        # Attempt to match first character if no tag matched yet.
        if not tag:
            tag = self.match_tag(striptxt)

        # Implicitly accept first line content always.
        if self._num_lines == 1:
            return

        closest = self._stack.find_indent(indent, tag=tag, elem=popped)

        if indent != closest:
            self.add_message("pepc-string-bad-indent", line=lineno, args=(closest, indent))
            self._stack.dump(lineno, context=True)

    def __init__(self, parent, base=None, debug=False):
        """
        Constructor for 'StringIndentValidator()' class. Arguments are as follows.
          * parent - parent object.
          * base - base indent level in characters.
          * debug - True, if debugging is enabled.
        """
        self._parent = parent
        self._num_lines = 0
        self._stack = IndentStack(self, base, debug=debug)
        self._base = base
        self._debug = debug

class IndentValidator():
    """Helper class for validating code indentation."""

    def add_message(self, *args, **kwargs):
        """Add a warning message to parent linter based on 'args' and 'kwargs'."""
        self._parent.add_message(*args, **kwargs)

    def debug(self, *args, **kwargs):
        """Print a debug message, based on 'args' and 'kwargs'."""
        self._parent.debug(*args, **kwargs)

    def _validate_string(self, token, lineno, txt):
        """Validate string indentation, if it is a multiline string."""

        if not txt.startswith("\"\"\""):
            return

        base = token.start[1]

        validator = StringIndentValidator(self, base=base, debug=self._debug)

        lineno -= 1

        txt = txt.lstrip("\"\"\"").rstrip("\"\"\"")

        for line in txt.split("\n"):
            lineno += 1

            validator.validate_line(lineno, line)

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

    def __init__(self, parent, debug=False):
        """
        Class constructor for the 'IndentValidator'. Arguments are as follows.
          * parent - parent 'PepcTokenChecker' object.
          * debug - True, if debugging is enabled.
        """

        self._parent = parent
        self._indent = 0
        self._new_indent = None
        self._base_indent = 0
        self._stack = []
        self._pending = []
        self._was_bracket = False
        self._debug = debug
