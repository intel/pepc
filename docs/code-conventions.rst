.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

================
Code conventions
================

.. contents::

Class attribute definitions
===========================

All class attributes must be defined at the top of the constructor.

*Do*:::

 class Blah:
     ....
     def __init__(self, arg1, arg2):
         """Reasonable docstring."""

         self._arg1 = arg1
         self._arg2 = arg2

         self._something = None
         self._foo = None

         self._validate_input_args()
         self._do_somthing_else()

*Don't*:::

 class Blah:
     ....
     def __init__(self, arg1, arg2):
         """Reasonable docstring."""

         self._arg1 = arg1
         self._arg2 = arg2

         self._validate_input_args()
         self._do_somthing_else()

         self._something = None
         self._foo = None

Functions starting with "validate\_"
====================================

If you have a function or a class method that validates input arguments and raises an exception if
the arguments are incorrect (out of range, bad type, etc), call it ``'validate_something()'``.

Examples:

* ``validate_pname()``
* ``validate_governor_name()``

MSR modules
============

This section is specific to "pepclibs/msr/" modules.

Methods for single CPU vs multiple CPUs
+++++++++++++++++++++++++++++++++++++++

Some methods accept a single CPU number (argument name s 'cpu'), some methods accept multiple CPU
numbers (argument name is 'cpus'). The convention is to include the "cpu" word in function names
that deal with a single CPU.

Examples:

* ``read_feature(blah, cpus)`` - read a feature for multiple CPUs
* ``read_cpu_feature(blah, cpu)`` - read a feature for a single CPU