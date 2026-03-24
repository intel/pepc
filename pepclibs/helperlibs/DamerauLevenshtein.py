# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Jan-Kristian Herring

"""Provide Damerau-Levenshtein distance calculation helpers."""

from __future__ import annotations # Remove when switching to Python 3.10+.

def closest_match(string: str,
                   strings: list[str],
                   max_distance: int = 2,
                   case_sensitive: bool = False) -> str:
    """
    Return the closest match to 'string' in 'strings' using optimal string alignment.

    Args:
        string: The string to find a match for.
        strings: List of strings to search for matches.
        max_distance: Maximum allowed distance for a match. Defaults to 2.
        case_sensitive: If 'False', case will be ignored. Defaults to 'False'.

    Returns:
        The closest matching string, or an empty string if no strings are close enough.
    """

    def osa_distance(first: str, second: str) -> int:
        """Calculate the optimal string alignment distance."""

        matrix = [[idx] for idx in range(len(first) + 1)]
        matrix[0] = list(range(len(second) + 1))

        # Calculate the distance with the matrix.
        for fdx in range(1, len(first) + 1):
            for sdx in range(1, len(second) + 1):
                # Cost 1 if we need an action to correct this part of the string.
                cost = 0 if first[fdx - 1] == second[sdx - 1] else 1

                matrix[fdx].append(min(matrix[fdx - 1][sdx] + 1, # Deletion.
                                       matrix[fdx][sdx - 1] + 1, # Insertion.
                                       matrix[fdx - 1][sdx - 1] + cost)) # Substitution.

                if fdx > 1 and sdx > 1 and first[fdx - 1] == second[sdx - 2] and \
                   first[fdx - 2] == second[sdx - 1]: # Transposition.
                    matrix[fdx][sdx] = min(matrix[fdx][sdx], matrix[fdx - 2][sdx - 2] + cost)

        return matrix[len(first)][len(second)]

    options = {option if case_sensitive else option.lower() : option for option in strings}
    if not case_sensitive:
        string = string.lower()

    best: tuple[int, str] = (max_distance + 1, "")
    for option in options:
        score = osa_distance(string, option)
        if score < best[0]:
            best = (score, option)

    if best[1]:
        return options[best[1]]
    return ""
