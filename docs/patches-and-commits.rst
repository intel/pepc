.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

===================
Patches and commits
===================

.. contents::

Commit subject prefix
=====================

Overall, the goal of the subject is to give a good idea about the patch:

 * What area does it touch?
 * Is it a cosmetic change, bug fix, an improvement?

Please, prefix the commit subjects with something gives an idea about what area the commit changes.
In many cases, specifying module name is sufficient. Examples:

 * ``YAML: support specifying files with a file object``
 * ``CStates: return 'None' when property not supported``

If the patch is just a cleanup, or a cosmetic change, you may specify it with a prefix too. But you
can also just say this in the subject. Examples:

 * ``CStates: cosmetic: improve docstrting``
 * ``tests: cleanup and extend readme.txt``
