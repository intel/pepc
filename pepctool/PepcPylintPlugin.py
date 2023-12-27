# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
This module implements pepc coding style checks for pylint as a plugin.
"""

import re
import tokenize
from astroid import nodes
from pylint.checkers import BaseChecker, BaseTokenChecker, BaseRawFileChecker

STATE_COMMENT = 1
STATE_COMMENT_NL = 2
STATE_FUNCTION = 3

def dump_node(node, recursive=False):
    """Dump the contents of the given 'node', and all its children also if 'recursive'."""

    if recursive:
        max_depth = 0
    else:
        max_depth = 1
    print(f"dump_node: node={node.repr_tree(max_depth=max_depth)}")

def _check_generic_string(obj, txt, msg, node=None, lineno=None):
    """Generic checks for strings."""

    match = re.match(r".*[^'](--[a-z0-9_\-]+)(?!')[^']", txt)
    if match:
        obj.add_message(msg, args=match.group(1), node=node, line=lineno)

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
    }
    options = ()

    def _end_comment(self):
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

        if re.match("[a-z]{0,1}'", txt):
            self.add_message("pepc-string-bad-delimiter", line=lineno)

        if token.start[0] != token.end[0]:
            if not re.match("[a-z]{0,1}\"\"\"", txt):
                self.add_message("pepc-bad-multiline-string", line=lineno)

    def _is_reserved(self, tok):
        """
        Check if token matches a reserved name.
        """

        if not tok:
            return False

        if tok.type != tokenize.NAME:
            return False

        if tok.string in ("if", "else", "elif", "and", "or", "not", "in", "yield", "return",
                          "except"):
            return True

        return False

    def _is_function_alike(self):
        """
        Check if the current state classifies as a function/class declaration or function
        call.
        """

        p_tok = self._get_token(2)
        if p_tok and p_tok.type != tokenize.NAME:
            return False

        return not self._is_reserved(p_tok)

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
            prev_reserved = self._is_reserved(prevtok)
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
        if prevprevtok and (self._is_reserved(prevprevtok) or
                            prevprevtok.type in (tokenize.OP, tokenize.NL)):
            prevprevop = self._get_op(prevprevtok, lineno=lineno)
            if prevop in ("-", "*", "**", "@", "~") and not self._is_close_bracket(prevprevop):
                if char == " ":
                    self.add_message("pepc-op-extra-space-after", args=prevop, line=lineno)
                return

        # Everything else should have a space between.
        if curop and char != " ":
            self.add_message("pepc-op-no-space-before", args=curop, line=lineno)

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

    def _get_token(self, index=0):
        """
        Get token from the token history. 'index' is a positive number for how far into the history
        we go. 'index' 0 nominates current token.
        """

        if index >= len(self._tokens):
            return None

        return self._tokens[-index - 1]

    def _check_operand_spacing(self, nexttoken):
        """
        Verify operand spacing between previous, current and 'nexttoken'.
        """

        # We delay processing of operands so that we can see the next token also.
        token = self._get_token(1)

        curop = self._get_op(token)
        if not curop:
            return

        lineno = token.start[0]

        prevtok = self._get_token(2)
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

        p_tok = self._get_token(1)
        if p_tok and p_tok.type != tokenize.NL:
            return False

        p_tok = self._get_token(2)
        if p_tok and p_tok.type != tokenize.COMMENT:
            return False

        return True

    def _check_heading_newline(self, token, lineno):
        """Check for heading newlines."""

        if lineno == 1 and token.type == tokenize.NL:
            p_tok = self._get_token(1)
            if p_tok and p_tok.type == tokenize.ENCODING:
                self.add_message("pepc-heading-newline", line=lineno)

    def _check_double_newline(self, token, lineno):
        """Check for double newline errors."""

        if token.type != tokenize.NL:
            return

        p_tok = self._get_token(1)
        if p_tok and p_tok.type != tokenize.NL:
            return

        pp_tok = self._get_token(2)
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
            p_tok = self._get_token(1)
            if token.string != ":" and p_tok.string != ":":
                self.add_message("pepc-double-space", line=lineno)

    def _check_func_class_defs(self, token, lineno, txt):
        """Check function and class definitions for whitespace errors."""

        if token.type != tokenize.NAME:
            return

        if txt not in ("def", "class"):
            return

        missing_newline = False

        p_tok = self._get_token(1)
        pp_tok = self._get_token(2)

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
        p_tok = self._get_token(1)
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

    def process_tokens(self, tokens):
        """
        Callback for base token checker. Will process all the 'tokens' parsed by parent
        linter.
        """

        for token in tokens:
            # We don't care about these token types.
            if token.type == tokenize.DEDENT:
                continue

            self._tokens.append(token)

            lineno = token.start[0]
            txt = token.string.rstrip()

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

_CLASS_INIT_VALID_TYPES = (nodes.Name, nodes.Assign, nodes.AssignName, nodes.If, nodes.Const)

class ClassInitValidator():
    """Validate the ordering of code in class '__init__()' method."""

    def _validate_node_type(self, node):
        """
        Check that the type of single line of execution is valid for the data initialization
        section.
        """

        valid = isinstance(node, _CLASS_INIT_VALID_TYPES)

        if not valid:
            # Check if we are calling super().__init__().
            if node.as_string().find("super().__init__(") >= 0:
                return True

        if not valid:
            return False

        for child in node.get_children():
            if not self._validate_node_type(child):
                return False

        return True

    def validate(self, node, current_valid=None):
        """
        Validate a single line of code for '__init__()' method. This will check that
        initialization of all the class internal data is done before any complex execution happens.
        Arguments are as follows.
          * node - AST node declaring the code line to be processed.
          * current_valid - True, if the given node is known to be valid.
        """

        if not node:
            return True

        if node == self._prev_node:
            return self._prev_ok

        # Check if previous node is ok.
        prev = node.previous_sibling()
        valid = self.validate(prev)

        # Validate current node.
        if valid and not current_valid:
            valid = self._validate_node_type(node)

        self._prev_node = node
        self._prev_ok = valid

        return valid

    def __init__(self):
        """Constructor for 'ClassInitValidator'."""

        self._prev_node = None
        self._prev_ok = True

class ScopeStack():
    """Provide push/pop functionality for scopes, and variable access data."""

    def _check_variables(self, scope):
        """Verify variables for the given 'scope'."""

        variables = scope["vars"]
        self._parent.debug(f"_check_variables for scope {scope['name']}")

        class_scope = bool(scope["type"] == "class")
        global_scope = bool(scope["type"] == "module")

        for name in variables:
            var = variables[name]
            self._parent.debug(f"   checking {name}: {var}")
            if var["read"]:
                continue
            # Special check for 'self._close_*'.
            match = re.match("self._close_(.*)$", name)
            if match:
                if f"self._{match.group(1)}" in variables:
                    continue

            # Skip checking public and python internal attributes for classes.
            if class_scope and (not name.startswith("self._") or name.startswith("__")):
                continue

            # Skip checking public variables for global scope.
            if global_scope and re.match("^[A-Z][A-Z_0-9]+$", name):
                continue

            self._parent.add_message("pepc-unused-variable", args=name, node=var["node"])

    def pop(self, scope_type):
        """Pop scope of type 'scope_type' from the stack."""

        if scope_type == "func":
            self._check_variables(self._current_scope)
        if scope_type == "module":
            for _, scope in self._classes.items():
                self._check_variables(scope)

        self._stack.pop()
        if self._stack:
            self._current_scope = self._stack[-1]
        else:
            self._current_scope = None

        if scope_type == "class":
            self._class_stack.pop()
            if self._class_stack:
                self._class_scope = self._class_stack[-1]
            else:
                self._class_scope = None

        self._parent.debug(f"popped scope: {self._current_scope}")

    def push(self, node, scope_type):
        """Create new scope for 'node' of given type 'scope_type', and push it to the stack."""

        scope = {"name": node.name, "type": scope_type, "vars": {}}
        self._stack.append(scope)
        self._current_scope = scope

        if scope_type == "class":
            scope["bases"] = [n.as_string() for n in node.bases]
            self._class_stack.append(scope)
            self._class_scope = scope
            self._classes[node.name] = scope
            scope["validator"] = ClassInitValidator()

        if scope_type == "module":
            self._global_scope = scope

        self._parent.debug(f"pushed scope: {scope}")

    def _parse_scope(self, node):
        """Parse scope for an attribute given in 'node'."""

        name = node.as_string()
        if isinstance(node, (nodes.AssignAttr, nodes.Attribute)):
            if not isinstance(node.expr, nodes.Name):
                return None, None
            attr_scope = node.expr.name
            if attr_scope == "self":
                scope_type = "class"
            elif attr_scope == "args":
                scope_type = "global"
            else:
                scope_type = "current"
        elif isinstance(node, (nodes.AssignName, nodes.Name)):
            if name in self._global_scope["vars"]:
                scope_type = "global"
            else:
                scope_type = "current"
        else:
            return None, None

        return name, scope_type

    def _access_variable(self, node, read=False, value=None):
        """
        Access variable in a given scope. Arguments are as follows.
          * node - node reference to the variable.
          * read - True if this is a read access.
          * value - value for the variable, if any.
        """

        name, scope_type = self._parse_scope(node)

        self._parent.debug(f"_access_variable: '{name}' : '{scope_type}' ({node}, read={read}, "
                           f"value={value})")

        if name in ("self", "_", None):
            return None

        if scope_type == "global":
            scope = self._global_scope
        elif scope_type == "class":
            scope = self._class_scope
        else:
            scope = self._current_scope

        if not scope:
            return None

        if name not in scope["vars"]:
            scope["vars"][name] = {"node": node, "read": read}

        if value:
            scope["vars"][name]["value"] = value

        # Check class attribute ordering in constructor.
        if scope_type == "class" and scope["name"] == "__init__":
            if not scope["validator"].validate(node, current_valid=True):
                self._parent.add_message("pepc-bad-constructor-order", args=name, node=node)
            else:
                self._parent.debug("validated init order for {name} as ok.")

        if read:
            scope["vars"][name]["read"] = True

            if "bases" in scope:
                for base_class in scope["bases"]:
                    if base_class in self._classes and name in self._classes[base_class]["vars"]:
                        self._classes[base_class]["vars"][name]["read"] = True

            if "value" in scope["vars"][name]:
                return scope["vars"][name]["value"]

        return None

    def write_variable(self, node, value):
        """Write 'value' to given 'node' variable."""
        self._access_variable(node, value=value)

    def read_variable(self, node):
        """Read value of a given 'node' variable."""

        if isinstance(node, nodes.Const):
            return node.value

        return self._access_variable(node, read=True)

    def get_class_name(self):
        """Get name of current class scope, if any."""

        if self._class_scope:
            return self._class_scope["name"]

        return None

    def __init__(self, parent):
        """
        Class constructor for 'ScopeStack()'. Arguments are as follows.
          * parent - parent linter object.
        """

        self._stack = []
        self._class_stack = []
        self._current_scope = None
        self._class_scope = None
        self._global_scope = None
        self._parent = parent
        self._classes = {}

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
        {"default": False, "type": "yn", "metavar": "<y or n>",
         "help": "Whether to print debugging information or not."
        }),
        (
        "pepc-plugin-strict",
        {"default": False, "type": "yn", "metavar": "<y or n>",
         "help": "Whether to use more stricter checks or not."
        }),
    )

    def debug(self, txt):
        """Print a debug message given in 'txt', if debug is enabled."""

        if self.config.pepc_plugin_debug:
            print(txt)

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

        for line in txt.split("\n", 1):
            match = re.match(r"[^\.]*\.\s*$", line)
            if match and firstline:
                self.add_message(f"pepc-dot-{msgtype}-message", node=node)
            if not match and not firstline:
                self.add_message(f"pepc-no-dot-{msgtype}-message-cont", node=node)

            match = re.match(r"^[A-Z]([a-z]+|\s+)", line)
            if match and firstline:
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

        if isinstance(args[0], nodes.Const):
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

    def visit_assign(self, node):
        """AST callback for assignment. Assignment is declared by 'node'."""

        self.debug(f"visit_assign: {node}")

        value = self._parse_value(node.value)

        for var_node in node.targets:
            self._scope.write_variable(var_node, value)

    def visit_name(self, node):
        """AST callback for a name access to name defined in 'node'."""

        self.debug(f"visit_name: {node}")
        self._scope.read_variable(node)

    def visit_attribute(self, node):
        """AST callback for attribute access to attribute defined in 'node'."""

        self.debug(f"visit_attr: {node}")
        self._scope.read_variable(node)

    def _get_args(self, node):
        """Fetch arguments from a given 'node'."""

        args = []

        for arg in node:
            if arg.name in ("self", "_"):
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
                    if not self.config.pepc_plugin_strict:
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

        if not public and not self.config.pepc_plugin_strict:
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
        self._scope.pop("module")

    def visit_classdef(self, node):
        """AST callback for a class entry to class defined in 'node'."""

        self._scope.push(node, "class")
        self._check_generic_docstring(node)

    def leave_classdef(self, node):
        """AST callback for a class exit from 'node'."""

        # pylint: disable=unused-argument
        self._scope.pop("class")

    def visit_functiondef(self, node):
        """AST callback for a function entry to function defined in 'node'."""

        self._scope.push(node, "func")
        self._check_func_docstring(node)

    def leave_functiondef(self, node):
        """AST callback for a function exit from 'node'."""

        # pylint: disable=unused-argument
        self._scope.pop("func")

    def __init__(self, linter):
        """
        Class constructor for 'PepcASTChecker()'. Arguments are as follows.
          * linter - parent linter object.
        """

        super().__init__(linter=linter)
        self._scope = ScopeStack(self)
        self._documented_args = {}
        self._cross_refer_args = {}

def register(linter):
    """
    Auto register checker during initialization. Arguments are as follows.
      * linter - parent linter object.
    """

    linter.register_checker(PepcTokenChecker(linter))
    linter.register_checker(PepcASTChecker(linter))
