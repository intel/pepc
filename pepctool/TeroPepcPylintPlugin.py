# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>
#
# TODO: This is the pepc pylint plugin originally written by Tero. Saved for reference. May be
# removed somewhere in 2026.

"""
This module implements pepc coding style checks for pylint as a plugin.
"""

import re
import tokenize
from astroid import nodes
from pylint.checkers import BaseChecker, BaseTokenChecker, BaseRawFileChecker
from pepctool.linterlibs import IndentValidator, ScopeStack

STATE_COMMENT = 1
STATE_COMMENT_NL = 2
STATE_FUNCTION = 3

HAS_FSTRING_TOKENS = hasattr(tokenize, "FSTRING_START")

DEBUG_OPTS = ["all", "strings", "indent", "visit", "scope", "context"]

def _debug(opt, fmt, debug=None, lineno=None, **kwargs):
    if debug and (opt in debug or "all" in debug):
        lineno = kwargs.get("lineno", lineno)

        if "node" in kwargs:
            lineno = kwargs["node"].lineno

        print(f"L{lineno}: {opt}: ", fmt.format(**kwargs))

def dump_node(node, recursive=False):
    """Dump the contents of the given 'node', and all its children also if 'recursive'."""

    if recursive:
        max_depth = 0
    else:
        max_depth = 1
    print(f"dump_node: node={node.repr_tree(max_depth=max_depth)}")

def _check_generic_string(obj, txt, msg, node=None, lineno=None):
    """Generic checks for strings."""

    match = re.match(r"[^']*('{0,1})[^']*(--[a-z][a-z0-9_\-]+)[^']*('{0,1})[^']*$", txt)
    if match and (match.group(1) != "'" or match.group(3) != "'"):
        obj.add_message(msg, args=match.group(2), node=node, line=lineno)

class PepcTokenChecker(BaseTokenChecker, BaseRawFileChecker):
    """Pepc linter class using tokens."""

    priority = -1
    name = "pepc-token"
    msgs = {
        "W9901": (
            "No dot at end of comment",
            "pepc-comment-no-dot",
            (
                "Used when there is no dot at the end of a comment."
            ),
        ),
        "W9902": (
            "No space at beginning of comment",
            "pepc-comment-no-space",
            (
                "Used when there is no space at the beginning of comment."
            ),
        ),
        "W9903": (
            "Bad string delimiter",
            "pepc-string-bad-delimiter",
            (
                "Used when a single hyphen is used to delimit string instead of double quote."
            ),
        ),
        "W9904": (
            "Missing space before operand '%s'",
            "pepc-op-no-space-before",
            (
                "Used when there is no space before an operand."
            ),
        ),
        "W9905": (
            "Missing space after operand '%s'",
            "pepc-op-no-space-after",
            (
                "Used when there is no space after an operand."
            ),
        ),
        "W9906": (
            "Extra space before operand '%s'",
            "pepc-op-extra-space-before",
            (
                "Used when there is a space before an operand where there should be none."
            ),
        ),
        "W9907": (
            "Extra space after operand '%s'",
            "pepc-op-extra-space-after",
            (
                "Used when there is a space after an operand where there should be none."
            ),
        ),
        "W9908": (
            "Double newline",
            "pepc-double-newline",
            (
                "Used when an double newline is detected."
            ),
        ),
        "W9909": (
            "Double space character",
            "pepc-double-space",
            (
                "Used when double space character is detected."
            ),
        ),
        "W9910": (
            "Missing newline before class definition",
            "pepc-missing-newline-before-class",
            (
                "Used when class definition does not have blank line before it."
            ),
        ),
        "W9911": (
            "Missing newline before function definition",
            "pepc-missing-newline-before-def",
            (
                "Used when function definition does not have blank line before it."
            ),
        ),
        "W9912": (
            "Code can fit a single line",
            "pepc-can-fit-single-line",
            (
                "Used when code is spread over multiple lines, but can fit a single line."
            ),
        ),
        "W9913": (
            "Command line option '%s' is documented without hyphens",
            "pepc-comment-option-without-hyphens",
            (
                "Comment refers to an option, but it doesn't have hyphens around it."
            ),
        ),
        "W9914": (
            "Heading newline",
            "pepc-heading-newline",
            (
                "File begins with newline characters."
            ),
        ),
        "W9915": (
            "Unnecessary trailing backslash",
            "pepc-unnecessary-backslash",
            (
                "Unnecessary backslash used to continue line."
            ),
        ),
        "W9916": (
            "Bad multiline string format",
            "pepc-bad-multiline-string",
            (
                """
                Bad multiline string format, should either use triple quotes or split to separate
                strings.
                """
            ),
        ),
        "W9917": (
            "Bad indentation, expected %s, got %s spaces",
            "pepc-bad-indent",
            (
                "Used when code is badly indented."
            ),
        ),
        "W9918": (
            "Unexpected tab",
            "pepc-string-unexpected-tab",
            (
                "Unexpected tab character in multiline string."
            ),
        ),
        "W9919": (
            "Reused indent level at offset %d in string by '%s', already used by '%s' from line "
            "%d",
            "pepc-string-reused-indent-level",
            (
                "Used when multiple bullets / lists use the same indent level."
            ),
        ),
        "W9920": (
            "Bad indentation, expected %s, got %s spaces",
            "pepc-string-bad-indent",
            (
                "Used when bad indent level is used in a multiline string."
            ),
        ),
        "W9921": (
            "Newline should be at the end of string on previous line",
            "pepc-string-bad-nl-split",
            (
                """
                Used when a string starts with a newline when it should be part of the string on
                previous line.
                """
            ),
        ),
        "W9922": (
            # pylint: disable=pepc-string-bad-integer-formatter
            "Should use '%d' instead of '%i'",
            "pepc-string-bad-integer-formatter",
            (
                "Used when %d should be used instead of %i for string format"
            ),
        ),
        "W9923": (
            "Unbalanced bracket '%s' at offset %d, expected '%s'",
            "pepc-string-unbalanced-bracket",
            (
                "Used when unbalanced brackets are used within string"
            ),
        ),
    }
    options = ()

    def debug(self, opt, *args, **kwargs):
        """Print a debug message given in 'args' and 'kwargs', if debug is enabled for 'opt'."""
        if "lineno" not in kwargs:
            kwargs["lineno"] = self._lineno

        _debug(opt, *args, debug=self._debug, **kwargs)

    def _end_comment(self):
        # pylint: disable=pepc-string-bad-indent
        """
        Tag the end of the current comment and verify that it ends with either '}', ']', ')' or '.'.
        If the comment contains some data structure snippet, it can end with closing parenthesis,
        e.g.
           # This is some data struct:
           # { "intval": 7, "txt": "test" }
        """

        if self._comment and self._commentline != 1:
            # Below regex matches any line that ends with '}', ']', ')' or '.'.
            match = re.match(r".*[}\]\)\.]\s*$", self._comment)
            if not match:
                self.add_message("pepc-comment-no-dot", line=self._commentline)

        self._comment = None
        self._commentline = None
        self._commentstate = None

    def _process_comment(self, token, lineno, txt):
        """
        Verify format of inline comments. Arguments are as follows.
          * token - current token being processed.
          * lineno - current line number for code.
          * txt - string representation of the current token.
        """

        if token.type == tokenize.COMMENT:
            self._commentstate = STATE_COMMENT
            _check_generic_string(self, txt, "pepc-comment-option-without-hyphens", lineno=lineno)

        if self._commentstate not in (STATE_COMMENT, STATE_COMMENT_NL):
            return

        if token.type == tokenize.NL and self._commentstate != STATE_COMMENT_NL:
            # Ignore newlines within the initial block of file.
            if not self._commentline or self._commentline == 1:
                return

            # Newline within comment, double newline will end current comment.
            self._commentstate = STATE_COMMENT_NL
            return

        if token.type != tokenize.COMMENT:
            # End of comment.
            self._end_comment()
            return

        if self._commentline != 1 and len(txt) >= 9 and txt[0:9] == "# pylint:":
            self._end_comment()
            return

        if lineno == 1 and len(txt) >= 3 and txt[0:3] == "#!/":
            txt = ""

        if len(txt) >= 2 and txt[1] != " ":
            self.add_message("pepc-comment-no-space", line=lineno)

        if self._comment is None:
            self._commentline = lineno
            self._comment = ""

        self._comment += txt.replace("#", "")

    def _check_string_format(self, token, lineno, txt):
        """
        Verify string format for a code token. The arguments are the same as in 
        '_process_comment()'.
        """

        if token.type != tokenize.STRING:
            return

        ptok = self.get_token(1)
        if ptok.type == tokenize.NL:
            pptok = self.get_token(2)
            if pptok.type == tokenize.STRING:
                if re.match(r"[a-z]{0,1}\"\\n", txt):
                    self.add_message("pepc-string-bad-nl-split", line=lineno)

        if re.match("[a-z]{0,1}'", txt):
            self.add_message("pepc-string-bad-delimiter", line=lineno)

        if token.start[0] != token.end[0]:
            if not re.match("[a-z]{0,1}\"\"\"", txt):
                self.add_message("pepc-bad-multiline-string", line=lineno)

        if re.match(r".*[^%]%i", txt): # pylint: disable=pepc-string-bad-integer-formatter
            self.add_message("pepc-string-bad-integer-formatter", line=lineno)

    def is_reserved(self, token):
        """
        Check if 'token' matches a reserved name.
        """

        if not token:
            return False

        if token.type != tokenize.NAME:
            return False

        if token.string in ("if", "else", "elif", "and", "or", "not", "in", "yield", "return",
                            "except", "for", "with", "raise", "assert", "import"):
            return True

        return False

    def _is_function_alike(self):
        """
        Check if the current state classifies as a function/class declaration or function
        call.
        """

        p_tok = self.get_token(2)
        if p_tok and p_tok.type == tokenize.OP and p_tok.string == ")":
            return True
        if p_tok and p_tok.type != tokenize.NAME:
            return False

        return not self.is_reserved(p_tok)

    def _is_bracket(self, char):
        """Returns True if 'char' is of any type of bracket."""

        if char in ("(", ")", "{", "}", "[", "]"):
            return True

        return False

    def _is_open_bracket(self, char):
        """Returns True if 'char' is any of the opening bracket types."""

        if char in ("(", "[", "{"):
            return True

        return False

    def _is_close_bracket(self, char):
        """Returns True if 'char' is any of the closing bracket types."""

        if char in (")", "]", "}"):
            return True

        return False

    def __check_operand_spacing(self, prevtok, prevop, tok, curop, lineno, char, prevprevtok=None):
        """Verify spacing between two operands."""

        # Newline between is always accepted.
        if char == "\n" or (prevtok and (prevtok.type == tokenize.NL or tok.start[0] !=
                                         prevtok.start[0])):
            return

        # Brackets must be grouped together.
        if self._is_bracket(prevop) and self._is_bracket(curop):
            if char == " ":
                self.add_message("pepc-op-extra-space-after", args=prevop, line=lineno)
            return

        # Handle assignments.
        if curop == "=" or prevop == "=":
            if prevop == "=":
                msg = "after"
            else:
                msg = "before"

            if self._context == STATE_FUNCTION:
                if char == " ":
                    self.add_message(f"pepc-op-extra-space-{msg}", args="=", line=lineno)
            else:
                if char not in (" ", "\n"):
                    self.add_message(f"pepc-op-no-space-{msg}", args="=", line=lineno)
            return

        # Handle 'dot'. It must have no spaces around it.
        if curop == "." or prevop == ".":
            if char == " ":
                self.add_message("pepc-op-extra-space-after", args=".", line=lineno)
            return

        # Any number of spaces is allowed after 'colon'.
        if prevop == ":":
            return

        if prevop == ",":
            if self._is_singlet_tuple(1) and char == " ":
                self.add_message("pepc-op-extra-space-after", args=prevop, line=lineno)
                return

            if self._is_close_bracket(curop):
                # Accept any number of spaces between ',' and ')' or '}'.
                return
            if char != " ":
                self.add_message("pepc-op-no-space-after", args=prevop, line=lineno)
            return

        # Special check for dict keys, allow spaces before ':'.
        if curop == ":" and prevtok and prevtok.type == tokenize.STRING:
            return

        if curop in (":", ","):
            if char == " ":
                self.add_message("pepc-op-extra-space-before", args=curop, line=lineno)
            return

        # Opening braces must have no space before them, unless preceded by an operand.
        if curop in ("(", "["):
            prev_reserved = self.is_reserved(prevtok)
            if (prevop or prev_reserved) and char != " ":
                self.add_message("pepc-op-no-space-before", args=curop, line=lineno)
            if not (prevop or prev_reserved) and char == " ":
                self.add_message("pepc-op-extra-space-before", args=curop, line=lineno)
            return

        # Remaining opening brackets must have no space after.
        if self._is_open_bracket(prevop):
            if char == " ":
                self.add_message("pepc-op-extra-space-after", args=prevop, line=lineno)
            return

        # Remaining closing brackets must have no space before.
        if self._is_close_bracket(curop):
            if char == " ":
                self.add_message("pepc-op-extra-space-before", args=curop, line=lineno)
            return

        # Check unary operators, they must have no space after.
        if prevprevtok and (self.is_reserved(prevprevtok) or
                            prevprevtok.type in (tokenize.OP, tokenize.NL)):
            prevprevop = self._get_op(prevprevtok, lineno=lineno)
            if prevop in ("-", "*", "**", "@", "~") and not self._is_close_bracket(prevprevop):
                if char == " ":
                    self.add_message("pepc-op-extra-space-after", args=prevop, line=lineno)
                return

        # Everything else should have a space between.
        if curop and char != " ":
            self.add_message("pepc-op-no-space-before", args=curop, line=lineno)
            return

        if prevop and char != " ":
            self.add_message("pepc-op-no-space-after", args=prevop, line=lineno)

    def _get_op(self, token, lineno=None):
        """Get operand from a token."""

        if not token:
            return None

        if lineno and token.start[0] != lineno:
            return None

        operand = token.string.rstrip()

        if token.type == tokenize.OP:
            return operand

        if token.type == tokenize.NAME and operand in ("not", "in", "and", "or"):
            return operand

        return None

    def get_token(self, index=0, skip=None):
        """
        Get token from the token history. 'index' is a positive number for how far into the history
        we go. 'index' 0 nominates current token. 'skip' can be used to indicate token types we want
        to skip.
        """

        while True:
            if index >= len(self._tokens):
                return None

            token = self._tokens[-index - 1]
            if skip and token.type in skip:
                index += 1
                continue

            return token

    def _check_operand_spacing(self, nexttoken):
        """
        Verify operand spacing between previous, current and 'nexttoken'.
        """

        # We delay processing of operands so that we can see the next token also.
        token = self.get_token(1)

        curop = self._get_op(token)
        if not curop:
            return

        lineno = token.start[0]

        prevtok = self.get_token(2)
        prevop = None
        nextop = None

        # Strip any comment potentially following the line.
        line = re.sub(" *#[^#\"]+$", "\n", token.line)

        before = line[token.start[1] - 1]
        after = line[token.end[1]]

        prevop = self._get_op(prevtok, lineno=lineno)
        if prevop and prevtok.end[1] == token.start[1]:
            before = ""

        nextop = self._get_op(nexttoken, lineno=lineno)

        # Detect function/class definitions and function calls, as the assignments within their
        # parameters is handled differently.
        if curop == "(":
            if self._is_function_alike():
                self._context = STATE_FUNCTION
            self._context_stack.append(self._context)
        elif curop == ")":
            self._context_stack.pop()
            if self._context_stack:
                self._context = self._context_stack[-1]
            else:
                self._context = None

        self.__check_operand_spacing(prevtok, prevop, token, curop, lineno, before)
        if not nextop:
            self.__check_operand_spacing(token, curop, nexttoken, nextop, lineno, after,
                                         prevprevtok=prevtok)

    def _prev_is_line_comment(self):
        """Returns true if the previous tokens consist of a line comment."""

        p_tok = self.get_token(1)
        if p_tok and p_tok.type != tokenize.NL:
            return False

        p_tok = self.get_token(2)
        if p_tok and p_tok.type != tokenize.COMMENT:
            return False

        return True

    def _check_heading_newline(self, token, lineno):
        """Check for heading newlines."""

        if lineno == 1 and token.type == tokenize.NL:
            p_tok = self.get_token(1)
            if p_tok and p_tok.type == tokenize.ENCODING:
                self.add_message("pepc-heading-newline", line=lineno)

    def _check_double_newline(self, token, lineno):
        """Check for double newline errors."""

        if token.type != tokenize.NL:
            return

        p_tok = self.get_token(1)
        if p_tok and p_tok.type != tokenize.NL:
            return

        pp_tok = self.get_token(2)
        if pp_tok and pp_tok.type != tokenize.COMMENT:
            self.add_message("pepc-double-newline", line=lineno)

    def _is_indented(self, token):
        """Check if the line is indented before the token."""

        begin = token.line[0:token.start[1]]

        if begin == " " * len(begin):
            return True

        return False

    def _check_double_space(self, token, lineno):
        """Check for double space errors."""

        if self._is_indented(token):
            return

        chars = token.line[token.start[1] - 2:token.start[1]]

        if chars == "  ":
            p_tok = self.get_token(1)
            if token.string != ":" and p_tok.string != ":" and token.type != tokenize.COMMENT:
                self.add_message("pepc-double-space", line=lineno)
                self.debug("context", "token:{token}, prev_token:{p_tok}", token=token, p_tok=p_tok)

    def _check_func_class_defs(self, token, lineno, txt):
        """Check function and class definitions for whitespace errors."""

        if token.type != tokenize.NAME:
            return

        if txt not in ("def", "class"):
            return

        missing_newline = False

        p_tok = self.get_token(1)
        pp_tok = self.get_token(2)

        if p_tok and p_tok.type not in (tokenize.NL, tokenize.NEWLINE):
            missing_newline = True

        if pp_tok and pp_tok.type not in (tokenize.NL, tokenize.NEWLINE):
            if pp_tok.type == tokenize.NAME:
                match = re.match(" *@staticmethod", pp_tok.line)
                if not match:
                    missing_newline = True

        if missing_newline:
            self.add_message(f"pepc-missing-newline-before-{txt}", line=lineno)

    def _check_whitespaces(self, token, lineno, txt):
        """Check for whitespacing errors."""

        self._check_heading_newline(token, lineno)
        self._check_double_newline(token, lineno)
        self._check_double_space(token, lineno)
        self._check_func_class_defs(token, lineno, txt)

    def _check_multiline(self, token, lineno):
        """Check if linefeed is unnecessary."""

        # Grab previous token, if it is NEWLINE, ignore, as we have just started a fresh.
        p_tok = self.get_token(1)
        if p_tok and p_tok.type == tokenize.NEWLINE:
            p_tok = None

        if self._prev_is_line_comment():
            p_tok = None

        # Store current line at newlines.
        if token.type == tokenize.NEWLINE or (p_tok and p_tok.start[0] != token.start[0]):
            txt = p_tok.line

            # Remove leading newline.
            txt = re.sub(r"^\n", "", txt)

            # Remove trailing newline or backslash.
            txt = re.sub(r"[\\\n]$", "", txt)

            # If this is not first line, remove leading tabulation.
            if self._multiline_txt != "":
                txt = re.sub("^ *", "", txt)

            self._multiline_txt += txt
            self._multiline_lines += 1

        if self._multiline_txt == "":
            self._multiline_lineno = lineno
            self._multiline_lines = 0

        if token.type == tokenize.NEWLINE:
            if len(self._multiline_txt) < 100 and self._multiline_lines > 1:
                self.add_message("pepc-can-fit-single-line", line=self._multiline_lineno)
            self._multiline_txt = ""
            self._multiline_lineno = None

    def _check_backslashes(self, start, end):
        """Check for unnecessary backslashes."""

        while True:
            if not self._backslash_lines:
                return
            lineno = self._backslash_lines[0]
            if lineno >= end:
                return
            if lineno < end:
                self._backslash_lines.pop(0)
                if lineno >= start:
                    self.add_message("pepc-unnecessary-backslash", line=lineno)

    def _process_parenthesis(self, token, lineno, txt):
        """Store the parenthesis depth."""

        if token.type != tokenize.OP:
            return

        if txt in ("(", "[", "{"):
            self._parenthesis_depth += 1
            if self._parenthesis_depth == 1:
                self._parenthesis_line = lineno
        elif txt in (")", "]", "}"):
            self._parenthesis_depth -= 1
            if not self._parenthesis_depth:
                self._check_backslashes(self._parenthesis_line, lineno)

    def _match_token_sequence(self, sequence, index=0):
        """Check that the current token sequence matches the given pattern."""

        for match in reversed(sequence):
            token = self.get_token(index)
            if not token:
                return False

            index += 1

            if match["type"] == "any":
                continue

            if token.type != match["type"] or token.string.rstrip() != match["txt"]:
                return False

        return True

    def _is_singlet_tuple(self, index=0):
        """Check if the preceding code is a singlet tuple, i.e. tuple with only single element."""

        sequence = [{"type": tokenize.OP, "txt": "("},
                    {"type": "any"},
                    {"type": tokenize.OP, "txt": ","},
                    {"type": tokenize.OP, "txt": ")"}]

        return self._match_token_sequence(sequence, index=index)

    def process_tokens(self, tokens):
        """
        Callback for base token checker. Will process all the 'tokens' parsed by parent
        linter.
        """

        fstring_token = None
        fstring_txt = None

        for token in tokens:
            lineno = token.start[0]
            txt = token.string.rstrip()

            self._lineno = lineno

            # Stitch possible fstring tokens into a single string token.
            if HAS_FSTRING_TOKENS:
                if token.type == tokenize.FSTRING_START:
                    fstring_token = token
                    fstring_txt = txt
                    continue

                if fstring_txt:
                    fstring_txt += txt

                    if token.type == tokenize.FSTRING_END:
                        txt = fstring_txt
                        token = tokenize.TokenInfo(tokenize.STRING, txt, fstring_token.start,
                                                   token.end, fstring_token.line)
                        lineno = token.start[0]
                        fstring_token = None
                        fstring_txt = None
                    else:
                        continue

            # First, verify alignment.
            self._alignment.validate(token, lineno, txt)

            # Ignore DEDENT / INDENT tokens for rest of the checks.
            if token.type in (tokenize.INDENT, tokenize.DEDENT):
                continue

            self._tokens.append(token)

            # Global checks here.
            self._check_string_format(token, lineno, txt)
            self._check_operand_spacing(token)
            self._check_whitespaces(token, lineno, txt)

            self._check_multiline(token, lineno)

            # Processing based on current state.
            self._process_comment(token, lineno, txt)

            # Store parenthesis depth.
            self._process_parenthesis(token, lineno, txt)

    def process_module(self, node):
        """Process the raw text for 'node'."""

        with node.stream() as stream:
            for lineno, line in enumerate(stream):
                line = line.rstrip().decode("utf-8")

                if line.endswith("\\"):
                    self._backslash_lines += [lineno + 1]

    def open(self):
        """Initialize internal variables for 'PepcTokenChecker()'."""

        self._debug = self.linter.config.pepc_plugin_debug
        self._alignment = IndentValidator.IndentValidator(self, debug="indent" in self._debug)

    def __init__(self, linter):
        """
        Class constructor for the 'PepcTokenChecker'. Arguments are as follows.
          * linter - parent linter object.
        """

        super().__init__(linter=linter)
        self._comment = None
        self._commentline = None
        self._commentstate = None
        self._context = None
        self._context_stack = []
        self._tokens = []
        self._multiline_lineno = None
        self._multiline_txt = ""
        self._multiline_lines = 0
        self._backslash_lines = []
        self._parenthesis_depth = 0
        self._parenthesis_line = None
        self._debug = False
        self._lineno = None
        self._alignment = None

class PepcASTChecker(BaseChecker):
    """Pepc linter class using AST nodes."""

    priority = -1
    name = "pepc-ast"
    msgs = {
        "W9954": (
            "Capitalized non-info log message",
            "pepc-cap-log-message",
            (
                "Used when a non-info log message starts with capitalized word."
            ),
        ),
        "W9955": (
            "Non-info log message ending at dot",
            "pepc-dot-log-message",
            (
                "Used when a non-info, single sentence log message ends in dot."
            ),
        ),
        "W9956": (
            "Unused variable '%s'",
            "pepc-unused-variable",
            (
                "Used when a variable is only written to, never read."
            ),
        ),
        "W9957": (
            "Capitalized exception message",
            "pepc-cap-error-message",
            (
                "Used when an exception message is capitalized."
            ),
        ),
        "W9958": (
            "Exception message ending at dot",
            "pepc-dot-error-message",
            (
                "Used when an exception message ends at a dot."
            ),
        ),
        "W9959": (
            "Class attribute '%s' must be defined at the top of the constructor",
            "pepc-bad-constructor-order",
            (
                "Used when class attributes are defined in mixed order."
            ),
        ),
        "W9960": (
            "Function argument '%s' not documented",
            "pepc-arg-not-documented",
            (
                "Used when a function argument is not documented."
            ),
        ),
        "W9961": (
            "Function argument document reference '%s' not found",
            "pepc-arg-doc-ref-not-found",
            (
                """
                Docstring refers to another function for argument reference, but argument not
                found.
                """),
        ),
        "W9962": (
            "Function argument document for '%s' is external",
            "pepc-arg-doc-ref-not-local",
            (
                "Docstring refers to another function that is not local to this file."
            ),
        ),
        "W9963": (
            "Command line option '%s' is documented without hyphens",
            "pepc-option-without-hyphens",
            (
                "Docstring refers to an option, but it doesn't have hyphens around it."
            ),
        ),
        "W9964": (
            "New line of log message starting in lower case",
            "pepc-lower-case-log-message-cont",
            (
                "Used when the next line of a non-info log message starts with lower case letter."
            ),
        ),
        "W9965": (
            "New line of log message not ending in dot",
            "pepc-no-dot-log-message-cont",
            (
                "Used when the next line of a non-info log message does not end in dot."
            ),
        ),
        "W9966": (
            "New line of error message starting in lower case",
            "pepc-lower-case-error-message-cont",
            (
                "Used when the next line of an error message starts with lower case letter."
            ),
        ),
        "W9967": (
            "New line of error message not ending in dot",
            "pepc-no-dot-error-message-cont",
            (
                "Used when the next line of an error message does not end in dot."
            ),
        ),
    }

    options = (
        (
            "pepc-plugin-debug",
            {"default": [], "type": "csv", "metavar": "<comma separated list>",
             "help": "Whether to print debugging information for a sub-feature or not. Available "
                     f"features: {', '.join(DEBUG_OPTS)}"
            }),
        (
            "pepc-plugin-strict",
            {"default": False, "type": "yn", "metavar": "<y or n>",
             "help": "Whether to use more stricter checks or not."
            }),
    )

    def debug(self, opt, *args, **kwargs):
        """Print a debug message given in 'args' and 'kwargs' if debug is enabled for 'opt'."""
        _debug(opt, *args, lineno=self._lineno, debug=self._debug, **kwargs)

    def _check_string(self, node, args, islog=False):
        """
        Verify string passed to either exception or _LOG print. Arguments are as follows.
          * node - AST node for the initial operation.
          * args - arguments passed to the operation.
          * islog - True, if this is a logging operation, False, if it is exception.
        """

        txt = self._scope.read_variable(args[0])

        if not txt or not isinstance(txt, str):
            return

        if islog:
            msgtype = "log"
        else:
            msgtype = "error"

        firstline = True
        multidot = txt.count(".") > 1

        for line in txt.split("\n", 1):
            line = line.replace("\n", " ")
            match = re.match(r".*(%[^a-z]*[a-z]|{.+})$", line)
            if not match:
                if firstline:
                    # If this is the first line of a multiline string, attempt to match a single dot
                    # at the end of the line for an error condition.
                    match = re.match(r"[^.]*\.\s*$", line)
                    if match and not multidot:
                        self.add_message(f"pepc-dot-{msgtype}-message", node=node)
                else:
                    # For rest of the string (can be multiple lines), there should be at least one
                    # dot found.
                    match = re.match(r".*\.\s*$", line)
                    if not match:
                        self.add_message(f"pepc-no-dot-{msgtype}-message-cont", node=node)

            match = re.match(r"^[%{]", line)
            if not match:
                match = re.match(r"^[A-Z]([a-z]+|\s+)", line)
                if match and firstline and not multidot:
                    self.add_message(f"pepc-cap-{msgtype}-message", node=node)
                if not match and not firstline:
                    self.add_message(f"pepc-lower-case-{msgtype}-message-cont", node=node)
            firstline = False

    def _check_log(self, node):
        """Verify '_LOG.' call for a given 'node'."""

        if node.args and node.func.attrname != "info":
            self._check_string(node, node.args, islog=True)

    def visit_call(self, node):
        """AST callback for a function call. The function call is declared in 'node'."""

        if (isinstance(node.func, nodes.Attribute)
            and isinstance(node.func.expr, nodes.Name)
            and node.func.expr.name == "_LOG"):
            self._check_log(node)

    def visit_raise(self, node):
        """AST callback for raising an exception. The raise operation is declared in 'node'."""

        if not node.exc or isinstance(node.exc, nodes.Name):
            return
        args = node.exc.args

        if args and isinstance(args[0], nodes.Const):
            self._check_string(node, args, islog=False)

    def _parse_value(self, node):
        """Parse value given by 'node'."""

        value = "(UNKNOWN)"

        if isinstance(node, nodes.JoinedStr):
            value = ""
            for val in node.values:
                value += self._parse_value(val)
        elif isinstance(node, nodes.Const):
            value = node.value

        return value

    def visit_augassign(self, node):
        """AST callback for binop assignment. Assignment is declared by 'node'."""

        self.debug("visit", "visit_augassign: {node}", node=node)

        if node.op == "+=":
            add = self._parse_value(node.value)

            val = self._scope.read_variable(node.target)
            if val is None:
                val = add
            else:
                if type(val) != type(add): # pylint: disable=unidiomatic-typecheck
                    val = "(UNKNOWN)"
                else:
                    val = val + add
            self._scope.write_variable(node.target, val)

    def visit_assign(self, node):
        """AST callback for assignment. Assignment is declared by 'node'."""

        self.debug("visit", "visit_assign: {node}", node=node)

        value = self._parse_value(node.value)

        for var_node in node.targets:
            self._scope.write_variable(var_node, value)

    def visit_name(self, node):
        """AST callback for a name access to name defined in 'node'."""

        self.debug("visit", "visit_name: {node}", node=node)
        self._scope.read_variable(node)

    def visit_attribute(self, node):
        """AST callback for attribute access to attribute defined in 'node'."""

        self.debug("visit", "visit_attr: {node}", node=node)
        self._scope.read_variable(node)

    def _get_args(self, node):
        """Fetch arguments from a given 'node'."""

        args = []

        for arg in node:
            if arg.name in ("self", "cls", "_"):
                continue
            args.append(arg.name)

        return args

    def _document_arg(self, func, arg):
        """Tag a single 'arg' as documented for function 'func'."""

        if func not in self._documented_args:
            self._documented_args[func] = set()

        self._documented_args[func].add(arg)

        if func in self._cross_refer_args:
            for arg_ref in self._cross_refer_args[func]:
                if arg_ref["name"] == arg:
                    self._document_arg(arg_ref["func"], arg)
                    arg_ref["found"] = True

    def _document_args(self, func, args):
        """Tag 'args' as documented for function 'func'."""

        for arg in args:
            self._document_arg(func, arg)

    def _is_local_class(self, class_name):
        """Check if the class is local to this file or not."""

        for func in self._documented_args:
            match = re.match(fr"^{class_name}.", func)
            if match:
                return True

        return False

    def _is_local_ref(self, func):
        """Check if the function is local to this file or not."""

        func_name = func.split(".")

        if len(func_name) >= 2:
            return self._is_local_class(func_name[0])

        return True

    def _verify_cross_ref_args(self):
        """Verify that all cross referenced function arguments have been documented."""

        for func, func_args in self._cross_refer_args.items():
            local = self._is_local_ref(func)
            for arg in func_args:
                if "found" in arg:
                    continue
                if not local:
                    if not self.linter.config.pepc_plugin_strict:
                        continue

                    self.add_message("pepc-arg-doc-ref-not-local", args=arg["name"],
                                     node=arg["node"])
                else:
                    self.add_message("pepc-arg-doc-ref-not-found", args=arg["name"],
                                     node=arg["node"])

    def _cross_refer_arg(self, node, func, arg, func_ref):
        """Cross refer documentation for function argument."""

        if func_ref in self._documented_args and arg in self._documented_args[func_ref]:
            return

        if func_ref not in self._cross_refer_args:
            self._cross_refer_args[func_ref] = []

        self._cross_refer_args[func_ref] += [{"name": arg, "func": func, "node": node}]

    def _check_generic_docstring(self, node, docstring=None):
        """Generic checks for all docstrings."""

        if not node.doc_node:
            return

        if not docstring:
            docstring = node.doc_node.value.replace("\n", " ")

        _check_generic_string(self, docstring, "pepc-option-without-hyphens", node=node)

    def _check_func_docstring(self, node):
        """
        Verify function docstring for 'node'. Checks that either all the function arguments are
        specified in the docstring, or none of them are.
        """

        if not node.doc_node:
            return

        docstring = node.doc_node.value.replace("\n", " ")

        self._check_generic_docstring(node, docstring=docstring)

        name = node.name
        public = not name.startswith("_")
        if not public and name == "__init__":
            public = True

        if not public and not self.linter.config.pepc_plugin_strict:
            return

        # Generate name for current function.
        name = node.name
        class_name = self._scope.get_class_name()
        if class_name:
            name = class_name + "." + name

        args = set(self._get_args(node.args.args))

        doc_long = set()
        doc_short = set()

        for arg in args:
            match = re.search(fr" *\* {arg} - ", docstring, re.MULTILINE)
            if match:
                doc_long.add(arg)

            match = re.search(fr"'{arg}'", docstring, re.MULTILINE)
            if match:
                doc_short.add(arg)

        # Use long format if it is available.
        if doc_long:
            documented_args = doc_long
        else:
            documented_args = doc_short

        self._document_args(name, documented_args)

        missing_args = args.difference(documented_args)

        # Check for argument documentation cross references.
        match = re.search(r"^[^\*]*[Ss]ame as \S* *'([^']+)\(\)'", docstring, re.MULTILINE)
        if match:
            for arg in missing_args:
                self._cross_refer_arg(node, name, arg, match.group(1))
        else:
            if args != documented_args and (public or missing_args != args):
                for arg in missing_args:
                    self.add_message("pepc-arg-not-documented", args=arg, node=node.doc_node)

    def visit_module(self, node):
        """AST callback for a module entry to module defined in 'node'."""
        self._scope.push(node, "module")
        self._check_generic_docstring(node)

    def leave_module(self, node):
        """AST callback for a module exit from 'node'."""

        # pylint: disable=unused-argument
        self._verify_cross_ref_args()
        self._scope.pop("module", node)

    def visit_classdef(self, node):
        """AST callback for a class entry to class defined in 'node'."""

        self._scope.push(node, "class")
        self._check_generic_docstring(node)

    def leave_classdef(self, node):
        """AST callback for a class exit from 'node'."""

        # pylint: disable=unused-argument
        self._scope.pop("class", node)

    def visit_functiondef(self, node):
        """AST callback for a function entry to function defined in 'node'."""

        self._scope.push(node, "func")
        self._check_func_docstring(node)

    def leave_functiondef(self, node):
        """AST callback for a function exit from 'node'."""

        # pylint: disable=unused-argument
        self._scope.pop("func", node)

    def open(self):
        """Initialize variables for 'PepcASTChecker()'."""
        self._debug = self.linter.config.pepc_plugin_debug

    def __init__(self, linter):
        """
        Class constructor for 'PepcASTChecker()'. Arguments are as follows.
          * linter - parent linter object.
        """

        super().__init__(linter=linter)
        self._scope = ScopeStack.ScopeStack(self)
        self._documented_args = {}
        self._cross_refer_args = {}
        self._lineno = None
        self._debug = False

def load_configuration(linter):
    """Verify debug options for 'linter'."""

    for cfg in linter.config.pepc_plugin_debug:
        if cfg not in DEBUG_OPTS:
            supported = ", ".join(DEBUG_OPTS)
            raise ValueError(f"Bad value for --pepc-plugin-debug: '{cfg}', supported values are:\n"
                             f"  {supported}")

def register(linter):
    """
    Auto register checker during initialization. Arguments are as follows.
      * linter - parent linter object.
    """

    linter.register_checker(PepcTokenChecker(linter))
    linter.register_checker(PepcASTChecker(linter))
