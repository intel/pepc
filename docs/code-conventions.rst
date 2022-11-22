.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

================
Code conventions
================

.. contents::

Function starting with "validate\_"
===================================

If you have a function or a class method that validates input arguments and raises an exception if
the arguments are incorrect (out of range, bad type, etc), call it ``'validate_something()'``.

Examples:

* ``validate_pname()``
* ``validate_governor_name()``

MSR functions with a single CPU argument
===================================

Functions in "pepclibs/msr/" modules that have a single CPU argument, should have "cpu" in the name.
This helps distinguish if the function is a single or multi CPU function.

Examples:

* ``read_feature()`` - many CPUs
* ``read_cpu_feature()`` - one CPU
