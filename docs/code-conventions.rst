.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

================
Code conventions
================

.. contents::

Class attribute definitions
===========================

Attributes definition
+++++++++++++++++++++

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
         self._do_something_else()

*Don't*:::

 class Blah:
     ....
     def __init__(self, arg1, arg2):
         """Reasonable docstring."""

         self._arg1 = arg1
         self._arg2 = arg2

         self._validate_input_args()
         self._do_something_else()

         self._something = None
         self._foo = None

Storing input arguments
+++++++++++++++++++++++

If you need to store some or all input argument value in attributes, make attribute names to be the
same as the argument names, but prepend them with "_" (unless you want them to be public
attributes).

Try to define the attributes in the order matching the arguments order.

*Do*:::

 class Blah:
     ....
     def __init__(self, unload, pman):
         """Reasonable docstring."""

         self._unload = unload
         self._pman = pman

*Don't*:::

 class Blah:
     ....
     def __init__(self, unload, pman):
         """Reasonable docstring."""

         self._my_pman = pman
         self._my_unload = unload

Class 'close()' method
======================

When 'close()' is needed
++++++++++++++++++++++++

If your class creates objects that have a 'close()' method, the class should implement the 'close()'
method. Example:::

 class Blah:
     ....
     def __init__(self):
         """Reasonable docstring."""
         self._pman = ProcessManager.get_pman()

     def close(self):
         """Uninitialize the object."""
         ClassHelpers.close(self, close_attrs=("_pman", ))

Notice that we use 'ClassHelpers.close()', which takes care of situations when the '_pman' attribute
was not initialized or does not even exist yet.

If your class references an object that has a 'close()' method, your class also needs a 'close()'
method. In practice, this is not necessary in most cases, but this does help in some situations.
Example:::

 class Blah:
     ....
     def __init__(self, pman):
         """Reasonable docstring."""
         self._pman = pman

     def close(self):
         """Uninitialize the object."""
         ClassHelpers.close(self, unref_attrs=("_pman", ))

'close()': base class vs child
++++++++++++++++++++++++++++++

Put the 'close()' method to the same class where the attribute is defined. If the base class defines
the attribute that has to be closed, put 'close()' to the base class. Do this even if the attribute
is actually initialized in the child class. Example:::

 class Base:
     ....
     def __init__(self):
         """Reasonable docstring."""
         self._pman = None

     def close(self):
         """Uninitialize the object."""
         ClassHelpers.close(self, unref_attrs=("_pman", ))

 class Child(Base):
     ....
     def __init__(self):
         """Reasonable docstring."""
         self._something_else = Create()

     def close(self):
         """Uninitialize the object."""

         super().close()
         ClassHelpers.close(self, close_attrs=("_something_else", ))

Functions starting with "validate\_"
====================================

If you have a function or a class method that validates input arguments and raises an exception if
the arguments are incorrect (out of range, bad type, etc), call it ``'validate_something()'``.

Examples:

* ``validate_pname()``
* ``validate_governor_name()``

MSR modules
===========

This section is specific to "pepclibs/msr/" modules.

Methods for single CPU vs multiple CPUs
+++++++++++++++++++++++++++++++++++++++

Some methods accept a single CPU number (argument name s 'cpu'), some methods accept multiple CPU
numbers (argument name is 'cpus'). The convention is to include the "cpu" word in function names
that deal with a single CPU.

Examples:

* ``read_feature(blah, cpus)`` - read a feature for multiple CPUs
* ``read_cpu_feature(blah, cpu)`` - read a feature for a single CPU
