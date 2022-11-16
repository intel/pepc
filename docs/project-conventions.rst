.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

===================
Project conventions
===================


Function starting with "validate\_"
===================================

If you have a function or a class method that validates input arguments and raises an exception if
the arguments are incorrect (out of range, bad type, etc), call it ``'validate_something()'``.

Examples:

* ``validate_pname()``
* ``validate_governor_name()``
