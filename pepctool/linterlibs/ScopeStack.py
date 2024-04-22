# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""Scope stack helper module for the PepcPylintPlugin."""

import re
from astroid import nodes
from pepctool.linterlibs import ClassInitValidator

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

            # Skip checks for public attributes.
            name_split = name.rsplit(".", 1)

            if len(name_split) == 2 and not name_split[1].startswith("_"):
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
            scope["validator"] = ClassInitValidator.ClassInitValidator()

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
