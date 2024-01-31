# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""Class initialization order validator for PepcPylintPlugin."""

from astroid import nodes

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
