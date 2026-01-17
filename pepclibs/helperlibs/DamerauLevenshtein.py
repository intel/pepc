# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Jan-Kristian Herring

"""
This module provides the Damerau-Levenshtein distance calculation helpers.
"""

def closest_match(string, strings, max_distance=2, case_sensitive=False):
    """
    Return the closest match to 'string' in 'strings' using optimal string alignment. 'max_distance'
    can be used to toggle how far the returned string is allowed to be, if no strings close enough
    are found, 'None' is returned. If 'case_sensitive' is 'False', case will be ignored.
    """

    def osa_distance(first, second):
        """Helper to calculate the 'optimal string alignment distance'."""

        matrix = [[idx] for idx in range(len(first) + 1)]
        matrix[0] = list(range(len(second) + 1))

        # Calculate the distance with the matrix.
        for fdx in range(1, len(first) + 1):
            for sdx in range(1, len(second) + 1):
                # Cost 1 if we need an action to correct this part of the string.
                cost = 0 if first[fdx-1] == second[sdx-1] else 1

                matrix[fdx].append(min(matrix[fdx-1][sdx] + 1, # Deletion.
                                       matrix[fdx][sdx-1] + 1, # Insertion.
                                       matrix[fdx-1][sdx-1] + cost)) # Substitution.

                if fdx > 1 and sdx > 1 and first[fdx-1] == second[sdx-2] and \
                   first[fdx-2] == second[sdx-1]: # Transposition.
                    matrix[fdx][sdx] = min(matrix[fdx][sdx], matrix[fdx-2][sdx-2] + cost)

        return matrix[len(first)][len(second)]

    options = {option if case_sensitive else option.lower() : option for option in strings}
    if not case_sensitive:
        string = string.lower()

    best = (max_distance + 1, None)
    for option in options:
        score = osa_distance(string, option)
        if score < best[0]:
            best = (score, option)

    if best[1]:
        return options[best[1]]
